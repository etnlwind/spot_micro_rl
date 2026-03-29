"""isaac_ops/listener.py — IsaacOps: unified training listener with threaded Telegram receiver.

Architecture:
  Thread 1 (receiver): getUpdates → queue (dedicated, always polling)
  Main loop: queue.get(0.5s) for commands + periodic monitoring
"""

import argparse
import collections
import contextlib
import html
import os
import queue
import re
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import common  # noqa: E402

# ── Constants ──
_OPS_LOG_DIR = os.path.join(SCRIPT_DIR, "log")
LOG = os.path.join(_OPS_LOG_DIR, "listener.log")
PID_FILE = os.path.join(_OPS_LOG_DIR, "listener.pid")
_CONFIRM_TIMEOUT_SEC = 15.0

# Collapse detection config (from TRAINING_CONFIG)
_collapse_cfg = common.TRAINING_CONFIG.get("collapse_restart", {})
_COLLAPSE_CHECK_ITER_MIN = _collapse_cfg.get("check_iter_min", 200)
_COLLAPSE_CHECK_ITER_MIN_WARN = _collapse_cfg.get("check_iter_warn_min", 100)
_COLLAPSE_CHECK_ITER_MAX = _collapse_cfg.get("check_iter_max", 300)
_COLLAPSE_CONTACT_THRESHOLD = _collapse_cfg.get("contact_threshold", 0.05)
_COLLAPSE_PROPULSION_THRESHOLD = _collapse_cfg.get("propulsion_threshold", 0.05)
_COLLAPSE_SWING_THRESHOLD = _collapse_cfg.get("swing_threshold", 0.95)
_COLLAPSE_CONSECUTIVE_REQUIRED = _collapse_cfg.get("consecutive_required", 3)
_COLLAPSE_LEGS = ("fl", "fr", "rl", "rr")

# Deduplication
_RECENT_UPDATE_IDS: collections.deque = collections.deque(maxlen=128)
_RECENT_UPDATE_ID_SET: set[int] = set()
_RECENT_COMMAND_WINDOW_SEC = 15.0
_RECENT_COMMAND_TIMES: dict[tuple, float] = {}

# Thread-safe lock for shared state (pending_confirm, state.json)
_confirm_lock = threading.Lock()


# ═══════════════════════════════════════════
# Telegram Receiver Thread
# ═══════════════════════════════════════════

_msg_queue: queue.Queue = queue.Queue()
_receiver_stop = threading.Event()


def _telegram_receiver():
    """Dedicated thread: polls getUpdates with long polling."""
    while not _receiver_stop.is_set():
        try:
            # Long polling: Telegram holds connection up to 30s, returns immediately on new message
            updates = common.fetch_updates(timeout_sec=30, log_path=LOG)
            for update in updates:
                _msg_queue.put(update)
        except Exception:
            # Network error — brief pause before retry
            _receiver_stop.wait(3.0)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════

def _safe_basename(path: str | None) -> str:
    return os.path.basename(path) if path else "N/A"


def _send_notice(title: str, body: str, icon: str = "👮", version: str | None = None) -> None:
    ver = version or common.TRAIN_VERSION or "?"
    common.send_text(
        f"{icon} <b>IsaacOps — {title}</b>  <code>[{ver}]</code>\n<i>{body}</i>",
        LOG, parse_mode="HTML",
    )


def _remember_update_id(update_id: int) -> bool:
    if update_id <= 0:
        return True
    if update_id in _RECENT_UPDATE_ID_SET:
        return False
    if len(_RECENT_UPDATE_IDS) == _RECENT_UPDATE_IDS.maxlen:
        evicted = _RECENT_UPDATE_IDS.popleft()
        _RECENT_UPDATE_ID_SET.discard(evicted)
    _RECENT_UPDATE_IDS.append(update_id)
    _RECENT_UPDATE_ID_SET.add(update_id)
    return True


def _is_duplicate_command(chat_id, user_id, command_key: str) -> bool:
    now = time.monotonic()
    expired = [k for k, t in _RECENT_COMMAND_TIMES.items() if now - t > _RECENT_COMMAND_WINDOW_SEC]
    for k in expired:
        _RECENT_COMMAND_TIMES.pop(k, None)
    key = (chat_id, user_id, command_key)
    prev = _RECENT_COMMAND_TIMES.get(key)
    _RECENT_COMMAND_TIMES[key] = now
    return prev is not None and now - prev <= _RECENT_COMMAND_WINDOW_SEC


def _parse_command(text: str) -> tuple[str, str]:
    stripped = (text or "").strip()
    if not stripped:
        return "", ""
    parts = stripped.split(maxsplit=1)
    command = common.normalize_command(parts[0])
    arg_text = parts[1].strip() if len(parts) > 1 else ""
    return command, arg_text


def _parse_command_args(arg_text: str) -> tuple[str | None, list[int]]:
    arg_text = (arg_text or "").strip()
    if not arg_text:
        return None, []
    version_pattern = re.compile(r"^[Vv]\d+", re.IGNORECASE)
    parts = arg_text.split()
    version = None
    iter_tokens = parts
    if version_pattern.match(parts[0]):
        version = parts[0].upper()
        iter_tokens = parts[1:]
    if not iter_tokens:
        return version, []
    iters = []
    for token in iter_tokens:
        if not token.isdigit():
            return version, []
        n = int(token)
        if n > 0:
            iters.append(n)
    return version, iters


def _resolve_requested_checkpoint(run_dir, checkpoint_iter):
    if checkpoint_iter is None:
        return common.resolve_active_checkpoint(run_dir)
    checkpoint = common.get_checkpoint_by_iter(run_dir, checkpoint_iter)
    if checkpoint:
        return checkpoint
    raise RuntimeError(f"checkpoint model_{checkpoint_iter}.pt not found")


# ═══════════════════════════════════════════
# Command Handlers
# ═══════════════════════════════════════════

def _handle_hb(run_dir: str, iteration: int | None = None) -> None:
    data = common.read_tfevents(run_dir)
    if not data or not data.get("Train/mean_reward"):
        common.send_text(
            "⚠️ <b>IsaacOps — HB</b>\n<i>tfevents 데이터를 읽지 못했습니다.</i>",
            LOG, parse_mode="HTML",
        )
        return
    run_name = os.path.basename(run_dir)
    cycle_num = (iteration // common.HEARTBEAT_ITER_STEP) if iteration else 0
    report_text = common.format_report(data, run_name, cycle_num, iteration=iteration)
    common.send_text(report_text, LOG, parse_mode="HTML")


def _handle_status() -> None:
    common.send_text(common.format_status_html(), LOG, parse_mode="HTML")


def _handle_start(pending_confirm_ref: list, headless: bool = True) -> None:
    """Start command — may set pending_confirm for user confirmation."""
    common.reload_train_version()
    active_run_dir = common.resolve_active_run_dir()
    existing_checkpoint = common.resolve_active_checkpoint(active_run_dir) if active_run_dir else None
    run_version = (common._read_run_train_version(active_run_dir) if active_run_dir else "") or ""
    version_changed = run_version and run_version != common.TRAIN_VERSION
    mode_str = "headless" if headless else "GUI"

    if existing_checkpoint and not version_changed:
        with _confirm_lock:
            pending_confirm_ref.clear()
            pending_confirm_ref.append({
                "action": "fresh_start",
                "headless": headless,
                "expires_at": time.time() + _CONFIRM_TIMEOUT_SEC,
            })
        common.send_text(
            f"<b>{common.TRAIN_VERSION} [{mode_str}]</b>\n"
            f"iter 0 from-scratch.\n"
            f"<i>Y to confirm (60s)</i>",
            LOG, parse_mode="HTML",
        )
    else:
        if version_changed:
            common.send_text(
                f"<b>VERSION {run_version} -> {common.TRAIN_VERSION} [{mode_str}]</b>\n"
                f"<i>New version, starting iter 0.</i>",
                LOG, parse_mode="HTML",
            )
        result = common.launch_training(LOG, fresh=True, headless=headless)
        run_name = _safe_basename(result["run_dir"])
        common.send_text(
            f"<b>TRAINING START [{mode_str}]</b>\n<i>run: {run_name}</i>\n<i>version: {common.TRAIN_VERSION}</i>",
            LOG, parse_mode="HTML",
        )


def _handle_stop(monitor=None) -> None:
    result = common.stop_training(LOG)
    if monitor is not None:
        monitor.disable_stall_detection()
    checkpoint_name = _safe_basename(result["checkpoint"])
    run_version = common.get_run_version(result.get("run_dir", ""))
    _send_notice("TRAINING STOPPED", f"killed: {len(result['killed'])}\ncheckpoint: {checkpoint_name}", icon="⏹️", version=run_version)


def _handle_resume(headless: bool = True, target_iter: int | None = None) -> None:
    common.reload_train_version()
    mode_str = "headless" if headless else "GUI"
    iter_str = f" iter={target_iter}" if target_iter is not None else ""
    result = common.launch_training(LOG, fresh=False, headless=headless, target_iter=target_iter)
    run_name = _safe_basename(result["run_dir"])
    checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A (fresh)"
    run_version = common.get_run_version(result.get("run_dir", ""))
    if result["mode"] == "already-running":
        _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon=">>", version=run_version)
    else:
        _send_notice(f"TRAINING RESUME [{mode_str}]{iter_str}", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon=">>", version=run_version)


def _handle_report(run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    training_running = common.is_training_running()
    device = "cpu" if training_running else "cuda:0"

    def _do_report():
        try:
            with common.busy_lock("report"):
                common.update_state(mode="reporting", last_command="report", last_error="")
                report_data = common.stop_and_report(run_dir, checkpoint, LOG, force=True, device=device)
                common.send_text(
                    common.format_report_summary_html(
                        run_dir, checkpoint, report_data["analysis_text"],
                        report_data["kpi_snapshot"],
                        metrics_run_dir=report_data.get("metrics_run_dir"),
                    ),
                    LOG, parse_mode="HTML",
                )
                common.send_document(
                    report_data["zip_path"],
                    f"📦 report | {os.path.basename(run_dir)} | {os.path.basename(report_data['zip_path'])}",
                    LOG,
                )
                restore_mode = "training" if training_running else "stopped"
                common.update_state(mode=restore_mode, last_command="report", last_error="")
        except Exception as err:
            common.write_log(f"[Report] background thread error: {err}\n{common.capture_exception()}", LOG)
            _send_notice("REPORT FAILED", str(err), icon="⚠️")

    common.send_text(
        f"📦 <b>REPORT — {'CPU 백그라운드' if training_running else '생성'} 시작</b>\n<i>완료 시 전송합니다.</i>",
        LOG, parse_mode="HTML",
    )
    t = threading.Thread(target=_do_report, daemon=True, name="cmd-report")
    t.start()


def _handle_view(view_key: str, run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    training_running = common.is_training_running()
    device = "cpu" if training_running else "cuda:0"

    def _do_view():
        try:
            with common.busy_lock(view_key):
                common.update_state(mode="rendering", last_command=view_key, last_error="")
                videos = common.ensure_current_videos(run_dir, checkpoint, LOG, force=True, device=device)
                video_path = videos.get(view_key)
                if not video_path:
                    raise RuntimeError(f"{view_key} view was not generated.")
                common.send_video(
                    video_path,
                    f"📹 {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
                    LOG,
                )
                restore_mode = "training" if training_running else "stopped"
                common.update_state(mode=restore_mode, last_command=view_key, last_error="")
        except Exception as err:
            common.write_log(f"[View] background thread error: {err}\n{common.capture_exception()}", LOG)
            _send_notice(f"{view_key.upper()} FAILED", str(err), icon="⚠️")

    common.send_text(
        f"📹 <b>{view_key.upper()} — {'CPU 백그라운드' if training_running else ''} 녹화 시작</b>\n<i>완료 시 전송합니다.</i>",
        LOG, parse_mode="HTML",
    )
    t = threading.Thread(target=_do_view, daemon=True, name=f"cmd-{view_key}")
    t.start()


def _dispatch_command(command: str, arg_text: str, pending_confirm: list, monitor=None) -> None:
    """Dispatch parsed command to handler."""
    target_version, checkpoint_iters = _parse_command_args(arg_text)
    first_iter = checkpoint_iters[0] if checkpoint_iters else None

    if command == "help":
        _send_notice("COMMAND MENU", common.help_text(), icon="❔")
        return
    if command == "status":
        _handle_status()
        return
    if command == "selfcheck":
        common.send_text(f"<pre>{common.build_context_resolution_text()}</pre>", LOG, parse_mode="HTML")
        return
    if command == "start":
        gui_mode = "gui" in arg_text.lower()
        _handle_start(pending_confirm, headless=not gui_mode)
        return
    if command == "stop":
        _handle_stop(monitor=monitor)
        return
    if command == "resume":
        gui_mode = "gui" in arg_text.lower()
        # Parse iter number from args (e.g., "/resume gui 200" or "/resume 200")
        resume_iter = None
        for token in arg_text.split():
            if token.isdigit():
                resume_iter = int(token)
                break
        _handle_resume(headless=not gui_mode, target_iter=resume_iter)
        return
    if command == "shutdown":
        common.request_supervisor_shutdown("telegram-command")
        _send_notice("SHUTDOWN QUEUED", "IsaacOps 종료 요청을 기록했습니다.", icon="🛑")
        return

    # Commands that need run context
    base_run_dir = None
    if target_version:
        base_run_dir = common.resolve_run_dir_for_version(target_version)
        if not base_run_dir:
            _send_notice("VERSION NOT FOUND", f"'{target_version}' 버전을 찾지 못했습니다.", icon="⚠️")
            return
    else:
        base_run_dir = common.resolve_active_run_dir()

    if command == "hb":
        if not base_run_dir:
            _send_notice("CONTEXT NOT FOUND", "active run을 찾지 못했습니다.", icon="⚠️")
            return
        _handle_hb(base_run_dir, iteration=first_iter)
        return

    if command in {"report", "front", "rear", "top", "side"}:
        iter_list = checkpoint_iters if checkpoint_iters else [None]
        for iter_num in iter_list:
            try:
                checkpoint = _resolve_requested_checkpoint(base_run_dir, iter_num)
            except RuntimeError as e:
                _send_notice("NOT FOUND", str(e), icon="⚠️")
                continue
            run_dir = base_run_dir
            if checkpoint and run_dir:
                checkpoint_run = os.path.dirname(os.path.abspath(checkpoint))
                if os.path.abspath(run_dir) != checkpoint_run:
                    run_dir = checkpoint_run
            if not run_dir or not checkpoint:
                _send_notice("NOT FOUND", f"checkpoint를 찾지 못했습니다.", icon="⚠️")
                continue
            if command == "report":
                _handle_report(run_dir, checkpoint, checkpoint_iter=iter_num)
            else:
                _handle_view(command, run_dir, checkpoint, checkpoint_iter=iter_num)
        return


# ═══════════════════════════════════════════
# Monitoring (heartbeat logic)
# ═══════════════════════════════════════════

def _get_collapse_metrics(data: dict):
    def _latest(tag):
        vals = data.get(f"Episode_Reward/{tag}", [])
        return float(vals[-1][1]) if vals else None

    collapsed_legs = []
    for leg in _COLLAPSE_LEGS:
        contact = _latest(f"contact_ratio_{leg}")
        prop = _latest(f"propulsion_{leg}")
        swing = _latest(f"swing_time_{leg}")
        if contact is None or prop is None or swing is None:
            continue
        if (contact < _COLLAPSE_CONTACT_THRESHOLD
                and prop < _COLLAPSE_PROPULSION_THRESHOLD
                and swing > _COLLAPSE_SWING_THRESHOLD):
            collapsed_legs.append((leg, contact, prop, swing))
    if not collapsed_legs:
        return None, None, None, None
    worst = min(collapsed_legs, key=lambda x: x[1])
    return worst


def _restore_last_milestone(run_dir: str, iter_step: int, report_kind: str | None = None) -> int:
    records = common.load_report_history(run_dir)
    last_milestone = 0
    for record in records:
        if report_kind and record.get("report_kind") != report_kind:
            continue
        try:
            milestone = int(record.get("milestone") or 0)
        except (TypeError, ValueError):
            milestone = 0
        if milestone <= 0:
            try:
                cycle_num = int(record.get("cycle_num") or 0)
            except (TypeError, ValueError):
                cycle_num = 0
            milestone = cycle_num * int(iter_step)
        last_milestone = max(last_milestone, milestone)
    return last_milestone


def _get_resume_checkpoint_iter() -> int:
    state = common.load_state()
    checkpoint = state.get("active_checkpoint") or ""
    m = re.search(r"model_(\d+)\.pt", os.path.basename(checkpoint))
    return int(m.group(1)) if m else 0


def _collect_missed_milestones(last_video_milestone: int, current_iter: int, video_iter_step: int) -> list[int]:
    milestones = []
    candidate = last_video_milestone + video_iter_step
    while candidate <= current_iter:
        milestones.append(candidate)
        candidate += video_iter_step
    return milestones


def _run_video_report(run_dir: str, milestone: int, current_iter: int, total_missed: int, missed_index: int, video_iter_step: int) -> None:
    is_catchup = current_iter > milestone
    catchup_label = ""
    if is_catchup and total_missed == 1:
        catchup_label = " (누락 보완)"
    elif is_catchup and total_missed > 1:
        catchup_label = f" (누락 보완 {missed_index}/{total_missed})"

    checkpoint = common.get_checkpoint_by_iter(run_dir, milestone)
    if not checkpoint:
        common.write_log(f"[VideoReport] model_{milestone}.pt not found, skipping", LOG)
        common.send_text(
            f"⚠️ <b>VIDEO REPORT — iter {milestone:,}{catchup_label} (파일 없음)</b>\n"
            f"<i>model_{milestone}.pt 파일이 없어 건너뜁니다.</i>",
            LOG, parse_mode="HTML",
        )
        return

    common.write_log(f"[VideoReport] iter {milestone} (current={current_iter}) — background CPU recording", LOG)
    common.log_event("HB", "VIDEO_REPORT", f"iter={milestone} current={current_iter} catchup={is_catchup}")
    notice_lines = [f"🎬 <b>AUTO VIDEO REPORT — iter {milestone:,}{catchup_label}</b>"]
    if is_catchup:
        notice_lines.append(f"<i>현재 iter {current_iter:,}, iter {milestone:,} 소급 생성</i>")
    else:
        notice_lines.append("<i>훈련 계속 진행 중 (CPU 백그라운드 녹화)</i>")
    notice_lines.append(f"<i>checkpoint: model_{milestone}.pt</i>")
    common.send_text("\n".join(notice_lines), LOG, parse_mode="HTML")

    try:
        report_data = common.stop_and_report(run_dir, checkpoint, LOG, force=True, device="cpu")
        common.send_text(
            common.format_report_summary_html(
                run_dir, checkpoint, report_data["analysis_text"],
                report_data["kpi_snapshot"],
                metrics_run_dir=report_data.get("metrics_run_dir"),
            ),
            LOG, parse_mode="HTML",
        )
        common.send_document(
            report_data["zip_path"],
            f"📦 auto report | {os.path.basename(run_dir)} | iter {milestone:,}{catchup_label}",
            LOG,
        )
        data = common.read_tfevents(run_dir)
        run_name = os.path.basename(run_dir)
        record = common.build_report_record(data, run_name, cycle_num=(milestone // video_iter_step), report_kind="video_report")
        if record:
            record["milestone"] = milestone
            record["current_iter"] = current_iter
            common.append_report_record(run_dir, record)
        common.write_log(f"[VideoReport] iter {milestone}: complete", LOG)
    except Exception as err:
        common.write_log(f"[VideoReport] iter {milestone}: failed: {err}\n{common.capture_exception()}", LOG)
        common.send_text(
            f"⚠️ <b>VIDEO REPORT — iter {milestone:,} (실패)</b>\n<i>{err}</i>",
            LOG, parse_mode="HTML",
        )


class Monitor:
    """Periodic training monitor — replaces heartbeat.py."""

    def __init__(self, iter_step: int, video_iter_step: int, pending_confirm: list | None = None):
        self.iter_step = iter_step
        self.video_iter_step = video_iter_step
        self.last_sent_milestone = 0
        self.last_video_milestone = 0
        self.last_run_name = ""
        self.collapse_consecutive = 0
        self.collapse_restart_done = False
        self.perf_checked = False
        self._last_tick = 0.0
        self._tick_interval = 10.0  # check every 10 seconds
        self._pending_confirm = pending_confirm  # shared with main loop
        self._pending_video_milestones: list[int] = []  # milestones awaiting user approval
        self._pending_video_run_dir = ""
        self._pending_video_current_iter = 0
        # Pre-confirmation: predict milestone arrival, ask 5 min early
        self._iter_samples: list[tuple[float, int]] = []  # (time, iter) for speed estimation
        self._pre_confirm_milestone = 0  # milestone for which pre-confirm was sent
        self._pre_confirm_declined = False  # user said N
        # Stall detection: auto-resume if training dies
        self._stall_disabled = False  # /stop 시 True, /start·/resume 시 False
        self._last_iter_seen = 0
        self._last_iter_change_time = time.time()
        self._stall_notified = False
        self._STALL_TIMEOUT_SEC = 600.0  # 10 min no progress = dead
        self._video_disabled = False  # True after report-caused crash
        self._auto_resume_count = 0  # consecutive auto-resumes without progress
        self._AUTO_RESUME_MAX = 3  # max consecutive attempts before giving up
        self._video_thread: threading.Thread | None = None  # background video generation

    def _do_video_check(self, run_dir: str, current_iter: int) -> None:
        """Video report: predict milestone, pre-confirm, generate on arrival."""
        next_video_milestone = ((self.last_video_milestone // self.video_iter_step) + 1) * self.video_iter_step
        if next_video_milestone <= self.last_video_milestone:
            next_video_milestone = self.last_video_milestone + self.video_iter_step

        # Estimate seconds until next milestone
        eta_sec = None
        if len(self._iter_samples) >= 2 and current_iter < next_video_milestone:
            t0, i0 = self._iter_samples[0]
            t1, i1 = self._iter_samples[-1]
            dt = t1 - t0
            di = i1 - i0
            if dt > 0 and di > 0:
                iter_per_sec = di / dt
                remaining = next_video_milestone - current_iter
                eta_sec = remaining / iter_per_sec

        # Pre-confirm: ask 5 min before predicted arrival
        _PRE_CONFIRM_LEAD_SEC = 300.0
        with _confirm_lock:
            if (eta_sec is not None
                    and eta_sec > 0
                    and eta_sec <= _PRE_CONFIRM_LEAD_SEC
                    and self._pre_confirm_milestone != next_video_milestone
                    and not self._pre_confirm_declined
                    and self._pending_confirm is not None
                    and not self._pending_confirm):
                self._pre_confirm_milestone = next_video_milestone
                self._pending_confirm.clear()
                self._pending_confirm.append({
                    "action": "video_pre_confirm",
                    "milestone": next_video_milestone,
                })
                eta_min = int(eta_sec / 60)
                common.send_text(
                    f"<b>iter {next_video_milestone:,} 도달 예정 (~{eta_min}분 후)</b>\n"
                    f"도달 시 자동으로 영상 리포트를 생성합니다.\n"
                    f"<i>건너뛰려면 N을 입력하세요.</i>",
                    LOG, parse_mode="HTML",
                )
                common.write_log(
                    f"[VideoReport] pre-confirm sent for iter {next_video_milestone} (ETA ~{eta_min}min)", LOG,
                )

        # Milestone reached — generate immediately (no waiting)
        missed = _collect_missed_milestones(self.last_video_milestone, current_iter, self.video_iter_step)
        if missed:
            with _confirm_lock:
                if self._pending_confirm is not None and self._pending_confirm:
                    action = self._pending_confirm[0].get("action", "")
                    if action == "video_pre_confirm":
                        self._pending_confirm.clear()

            if self._pre_confirm_declined:
                common.write_log(f"[VideoReport] skipping milestones {missed} (user declined)", LOG)
                for m in missed:
                    self.last_video_milestone = m
                self._pre_confirm_declined = False
                self._pre_confirm_milestone = 0
            elif self._video_thread is not None and self._video_thread.is_alive():
                # Previous video report still running — skip this milestone set
                common.write_log(f"[VideoReport] skipping milestones {missed} (previous report still running)", LOG)
            else:
                # Launch video report in background thread (non-blocking)
                for m in missed:
                    self.last_video_milestone = m
                self._pre_confirm_milestone = 0
                milestones_copy = list(missed)
                run_dir_copy = run_dir
                cur_iter_copy = current_iter
                video_step_copy = self.video_iter_step

                def _bg_video():
                    total = len(milestones_copy)
                    for idx, m in enumerate(milestones_copy, start=1):
                        _run_video_report(run_dir_copy, m, cur_iter_copy, total, idx, video_step_copy)
                    common.write_log(f"[VideoReport] background thread done for milestones: {milestones_copy}", LOG)

                self._video_thread = threading.Thread(target=_bg_video, daemon=True, name="video-report")
                self._video_thread.start()
                common.write_log(f"[VideoReport] background thread started for milestones: {missed}", LOG)

    def reset_safety_flags(self) -> None:
        """Reset video_disabled and auto_resume_count — call on explicit /start."""
        self._video_disabled = False
        self._auto_resume_count = 0
        self._stall_disabled = False

    def disable_stall_detection(self) -> None:
        """Disable stall detection — call on explicit /stop."""
        self._stall_disabled = True

    def tick(self) -> None:
        """Called frequently from main loop. Rate-limits actual work."""
        now = time.time()
        if now - self._last_tick < self._tick_interval:
            return
        self._last_tick = now
        self._do_monitor()

    def _do_monitor(self) -> None:
        try:
            run_dir = common.resolve_active_run_dir()
            if not run_dir or not os.path.isdir(run_dir):
                return
            data = common.read_tfevents(run_dir)
            if not data:
                return
            reward_vals = data.get("Train/mean_reward", [])
            if not reward_vals:
                return
            current_iter = int(reward_vals[-1][0])
            run_name = os.path.basename(run_dir)

            # ── Stall detection: training died? ──
            if self._stall_disabled:
                return
            if current_iter != self._last_iter_seen:
                self._last_iter_seen = current_iter
                self._last_iter_change_time = time.time()
                self._stall_notified = False
                self._auto_resume_count = 0  # progress made, reset counter
            elif time.time() - self._last_iter_change_time > self._STALL_TIMEOUT_SEC:
                if not self._stall_notified:
                    self._stall_notified = True
                    alive = common.is_training_running()
                    if not alive:
                        # Determine if crash was likely caused by video report
                        crash_during_report = (
                            self.last_video_milestone > 0
                            and current_iter <= self.last_video_milestone + 100
                        )
                        common.write_log(
                            f"[Stall] Training dead — iter stuck at {current_iter} for "
                            f"{int(time.time() - self._last_iter_change_time)}s, process not found. Auto-resuming."
                            f" (report_suspected={crash_during_report})",
                            LOG,
                        )
                        if crash_during_report and not self._video_disabled:
                            self._video_disabled = True
                            common.send_text(
                                f"<b>TRAINING DEAD — report crash suspected</b>\n"
                                f"iter {current_iter:,}에서 프로세스 사망\n"
                                f"<i>CPU 백그라운드 녹화로 인한 crash 의심.</i>\n"
                                f"<i>자동 resume + 이후 video report 비활성화.</i>",
                                LOG, parse_mode="HTML",
                            )
                        else:
                            common.send_text(
                                f"<b>TRAINING DEAD — auto-resume</b>\n"
                                f"iter {current_iter:,}에서 {int(self._STALL_TIMEOUT_SEC/60)}분간 진행 없음\n"
                                f"<i>프로세스 사망 확인. 자동 resume 시도.</i>",
                                LOG, parse_mode="HTML",
                            )
                        self._auto_resume_count += 1
                        common.log_event("TRAIN", "STALL_RESUME", f"iter={current_iter} report_crash={crash_during_report} attempt={self._auto_resume_count}")
                        if self._auto_resume_count > self._AUTO_RESUME_MAX:
                            common.write_log(f"[Stall] Max auto-resume attempts ({self._AUTO_RESUME_MAX}) reached. Giving up.", LOG)
                            common.send_text(
                                f"<b>AUTO-RESUME GAVE UP</b>\n"
                                f"iter {current_iter:,}에서 {self._AUTO_RESUME_MAX}회 재시작 실패\n"
                                f"<i>수동 개입 필요.</i>",
                                LOG, parse_mode="HTML",
                            )
                        else:
                            try:
                                common.launch_training(LOG, fresh=False)
                            except Exception as err:
                                common.write_log(f"[Stall] Auto-resume failed: {err}", LOG)
                                common.send_text(
                                    f"<b>AUTO-RESUME FAILED</b>\n<i>{err}</i>",
                                    LOG, parse_mode="HTML",
                                )
                    else:
                        common.write_log(
                            f"[Stall] iter stuck at {current_iter} for "
                            f"{int(time.time() - self._last_iter_change_time)}s, but process alive. Waiting.",
                            LOG,
                        )

            # New run detection
            if run_name != self.last_run_name:
                self.last_run_name = run_name
                self._version_mismatch_notified = False
                self.last_sent_milestone = _restore_last_milestone(run_dir, self.iter_step)
                self.last_video_milestone = _restore_last_milestone(run_dir, self.video_iter_step, report_kind="video_report")
                resume_iter = _get_resume_checkpoint_iter()
                if resume_iter > 0:
                    skip_up_to = (resume_iter // self.video_iter_step) * self.video_iter_step
                    self.last_video_milestone = max(self.last_video_milestone, skip_up_to)
                elif self.last_video_milestone == 0:
                    # Skip past milestones but keep the most recent one pending
                    # so at least one report is generated when listener joins mid-run
                    skip_up_to = (current_iter // self.video_iter_step) * self.video_iter_step
                    self.last_video_milestone = max(0, skip_up_to - self.video_iter_step)
                self.collapse_consecutive = 0
                self.collapse_restart_done = False
                self.perf_checked = False
                # Clear stale pending_confirm from previous run
                with _confirm_lock:
                    if self._pending_confirm is not None and self._pending_confirm:
                        common.write_log(f"[VideoReport] clearing stale pending_confirm from previous run", LOG)
                        self._pending_confirm.clear()
                        self._pending_video_milestones.clear()
                self._iter_samples.clear()
                self._pre_confirm_milestone = 0
                self._pre_confirm_declined = False
                # Reset stall detection for new run
                self._last_iter_seen = current_iter
                self._last_iter_change_time = time.time()
                self._stall_notified = False
                # Reset safety flags only on fresh start (iter near 0), not on resume
                if current_iter < 50:
                    self._video_disabled = False
                    self._auto_resume_count = 0
                # Auto-detect train version and update state
                run_version = common._read_run_train_version(run_dir) or ""
                if run_version:
                    common.reload_train_version()
                    common.update_state(
                        mode="training",
                        active_run=run_name,
                        train_version=run_version,
                    )
                    common.write_log(f"[Monitor] New run detected: {run_name} (version={run_version})", LOG)
                # Immediate status heartbeat on new run detection
                try:
                    report_text = common.format_report(data, run_name, cycle_num=(current_iter // self.iter_step))
                    common.send_text(report_text, LOG, parse_mode="HTML")
                    self.last_sent_milestone = (current_iter // self.iter_step) * self.iter_step
                    common.write_log(f"[Monitor] Immediate heartbeat sent: iter={current_iter}", LOG)
                except Exception:
                    pass

            # Version mismatch detection (code vs running training)
            if not getattr(self, '_version_mismatch_notified', False):
                common.reload_train_version()
                run_version = common._read_run_train_version(run_dir) or ""
                if run_version and run_version != common.TRAIN_VERSION:
                    self._version_mismatch_notified = True
                    common.send_text(
                        f"⚠️ <b>VERSION MISMATCH</b>\n"
                        f"실행 중인 훈련: <code>{run_version}</code>\n"
                        f"현재 코드: <code>{common.TRAIN_VERSION}</code>\n"
                        f"<i>/start 명령으로 새 버전 훈련을 시작하세요.</i>",
                        LOG, parse_mode="HTML",
                    )

            # ── Perf check (once per run at iter 20+) ──
            if not self.perf_checked and current_iter >= 20:
                self.perf_checked = True
                perf_ct = data.get("Perf/collection time", [])
                perf_fps = data.get("Perf/total_fps", [])
                if perf_ct and len(perf_ct) >= 3:
                    avg_ct = sum(v for _, v in perf_ct[-5:]) / min(len(perf_ct), 5)
                    avg_fps = sum(v for _, v in perf_fps[-5:]) / min(len(perf_fps), 5) if perf_fps else 0
                    common.write_log(f"[Perf] iter={current_iter} ct={avg_ct:.1f}s fps={avg_fps:.0f}", LOG)
                    if avg_ct > 30.0:
                        common.write_log(f"[Perf] WARNING: ct {avg_ct:.1f}s >> normal", LOG)
                        common.send_text(
                            f"🐢 <b>PERF WARNING</b> — run {run_name}\n"
                            f"<code>collection_time={avg_ct:.1f}s (normal ~15s)</code>\n"
                            f"<code>fps={avg_fps:.0f} (normal ~80k)</code>\n"
                            f"<i>iter {current_iter}: 훈련 속도 비정상</i>",
                            LOG, parse_mode="HTML",
                        )

            # ── Collapse detection ──
            if (not self.collapse_restart_done
                    and _COLLAPSE_CHECK_ITER_MIN_WARN <= current_iter < _COLLAPSE_CHECK_ITER_MIN):
                leg, contact, prop, swing = _get_collapse_metrics(data)
                if leg is not None:
                    common.write_log(
                        f"[Collapse-WARN] iter={current_iter} leg={leg} c={contact:.4f} p={prop:.4f} s={swing:.4f}",
                        LOG,
                    )

            if (not self.collapse_restart_done
                    and _COLLAPSE_CHECK_ITER_MIN <= current_iter <= _COLLAPSE_CHECK_ITER_MAX):
                leg, contact, prop, swing = _get_collapse_metrics(data)
                if leg is not None:
                    self.collapse_consecutive += 1
                    common.write_log(
                        f"[Collapse] iter={current_iter} leg={leg} c={contact:.4f} p={prop:.4f} s={swing:.4f}"
                        f" ({self.collapse_consecutive}/{_COLLAPSE_CONSECUTIVE_REQUIRED})",
                        LOG,
                    )
                    if self.collapse_consecutive >= _COLLAPSE_CONSECUTIVE_REQUIRED:
                        self.collapse_restart_done = True
                        common.write_log(f"[Collapse] RESTART triggered @ iter {current_iter}", LOG)
                        common.log_event("TRAIN", "COLLAPSE_RESTART", f"iter={current_iter} leg={leg}")
                        common.stop_training(LOG)
                        common.send_text(
                            f"🚨 <b>COLLAPSE RESTART — iter {current_iter:,}</b>\n"
                            f"<i>leg={leg}: c={contact:.4f}, p={prop:.4f}, s={swing:.4f}</i>\n"
                            f"<i>collapse 확정 — 훈련 재시작</i>",
                            LOG, parse_mode="HTML",
                        )
                        common.launch_training(LOG, fresh=True)
                        return
                else:
                    self.collapse_consecutive = 0

            # ── Video report milestones (prediction-based pre-confirm) ──
            # Track iteration speed for arrival prediction
            now = time.time()
            self._iter_samples.append((now, current_iter))
            # Keep last 10 samples for smoothing
            if len(self._iter_samples) > 10:
                self._iter_samples = self._iter_samples[-10:]

            # Skip video report if disabled (after report-caused crash)
            if self._video_disabled:
                missed = _collect_missed_milestones(self.last_video_milestone, current_iter, self.video_iter_step)
                for m in missed:
                    self.last_video_milestone = m
                # Jump to text heartbeat (skip all video logic below)
            else:
                self._do_video_check(run_dir, current_iter)

            # ── Text heartbeat ──
            milestone = (current_iter // self.iter_step) * self.iter_step
            if milestone <= 0 or milestone <= self.last_sent_milestone:
                return
            report_text = common.format_report(data, run_name, cycle_num=(milestone // self.iter_step))
            record = common.build_report_record(data, run_name, cycle_num=(milestone // self.iter_step), report_kind="heartbeat")
            common.append_report_record(run_dir, record)
            common.send_text(report_text, LOG, parse_mode="HTML")
            self.last_sent_milestone = milestone
            rw = float(record.get("mean_reward", 0)) if record else 0
            el = float(record.get("mean_episode_length", 0)) if record else 0
            common.log_event("HB", "MILESTONE", f"iter={milestone}", version=common.get_run_version(run_dir), reward=f"{rw:.1f}", ep_len=f"{el:.1f}")

        except Exception as err:
            try:
                common.write_log(f"Monitor error: {err}\n{common.capture_exception()}", LOG)
            except Exception:
                pass


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="IsaacOps — unified training listener")
    parser.add_argument("--iter-step", type=int, default=common.HEARTBEAT_ITER_STEP, help="text heartbeat interval")
    parser.add_argument("--video-iter-step", type=int, default=common.VIDEO_REPORT_ITER_STEP, help="video report interval")
    parser.add_argument("--resume", action="store_true", default=False, help="process queued messages from before restart")
    args = parser.parse_args()

    # PID lock — 기존 listener가 있으면 graceful shutdown 요청 → 대기 → 타임아웃 시 kill
    old_pid = 0
    try:
        if os.path.isfile(PID_FILE):
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
    except Exception:
        old_pid = 0
    if old_pid and old_pid != os.getpid():
        import psutil
        if psutil.pid_exists(old_pid):
            print(f"[listener] Previous listener found (PID {old_pid}), requesting graceful shutdown...")
            common.request_supervisor_shutdown("listener-restart")
            common.log_event("LISTEN", "GRACEFUL_REQ", f"pid={old_pid}")
            deadline = time.time() + 3
            while time.time() < deadline and psutil.pid_exists(old_pid):
                time.sleep(0.5)
            if psutil.pid_exists(old_pid):
                print(f"[listener] PID {old_pid} did not exit in 3s, force killing...")
                try:
                    psutil.Process(old_pid).kill()
                    common.log_event("LISTEN", "FORCE_KILLED", f"pid={old_pid} (graceful timeout)")
                    time.sleep(1)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            else:
                print(f"[listener] Previous listener (PID {old_pid}) exited cleanly")
                common.log_event("LISTEN", "GRACEFUL_OK", f"pid={old_pid} exited cleanly")
            common.clear_supervisor_shutdown_request()
        else:
            print(f"[listener] Stale PID file (PID {old_pid} not running), cleaning up")
    else:
        print("[listener] No previous listener found")
    common.release_pid_lock(PID_FILE)
    common.acquire_pid_lock(PID_FILE, "isaac_ops", LOG)
    print(f"[listener] PID lock acquired (PID {os.getpid()})")
    common.write_log(
        f"IsaacOps started | iter_step={args.iter_step} | video_iter_step={args.video_iter_step} | pid={os.getpid()}",
        LOG,
    )
    common.log_event("LISTEN", "STARTED", f"pid={os.getpid()} iter_step={args.iter_step} video_step={args.video_iter_step}")

    # Flush stale messages unless --resume
    if not args.resume:
        flushed = common.fetch_updates(timeout_sec=0, log_path=LOG)
        if flushed:
            common.write_log(f"Flushed {len(flushed)} stale message(s) from before restart", LOG)
            print(f"[listener] Flushed {len(flushed)} stale message(s)")
        else:
            print("[listener] No stale messages to flush")

    # Start receiver thread
    receiver = threading.Thread(target=_telegram_receiver, daemon=True, name="tg-receiver")
    receiver.start()
    print("[listener] Telegram receiver thread started")
    common.write_log("Telegram receiver thread started", LOG)

    # Startup notification
    common.send_text(
        f"👮 <b>IsaacOps ACTIVE</b>  <code>[{common.TRAIN_VERSION}]</code>\n"
        f"<i>pid={os.getpid()} | iter_step={args.iter_step} | video={args.video_iter_step}</i>",
        LOG, parse_mode="HTML",
    )
    print(f"[listener] IsaacOps ACTIVE [{common.TRAIN_VERSION}] — monitoring started")

    pending_confirm: list = []  # mutable container for confirmation state
    monitor = Monitor(args.iter_step, args.video_iter_step, pending_confirm=pending_confirm)
    exit_reason = "normal"

    try:
        while True:
            # ── 1. Process Telegram commands from queue ──
            try:
                update = _msg_queue.get(timeout=0.5)
            except queue.Empty:
                update = None

            if update is not None:
                update_id = int(update.get("update_id", 0) or 0)
                if not _remember_update_id(update_id):
                    pass  # duplicate
                else:
                    text, chat_id, user_id = common.extract_message(update)
                    if text and common.is_authorized_message(chat_id, user_id):
                        # Pending confirmation handling (thread-safe)
                        with _confirm_lock:
                            if pending_confirm:
                                action = pending_confirm[0].get("action", "")
                                if action == "video_pre_confirm":
                                    milestone = pending_confirm[0].get("milestone", 0)
                                    if text.strip().lower().startswith("n"):
                                        pending_confirm.clear()
                                        monitor._pre_confirm_declined = True
                                        _send_notice("REPORT SKIP", f"iter {milestone:,} 리포트를 건너뜁니다.", icon="⛔")
                                        common.write_log(f"[VideoReport] user declined pre-confirm for iter {milestone}", LOG)
                                    else:
                                        pending_confirm.clear()
                                        _send_notice("REPORT OK", f"iter {milestone:,} 도달 시 자동 생성합니다.", icon="✅")
                                        common.write_log(f"[VideoReport] user confirmed pre-confirm for iter {milestone}", LOG)
                                    continue
                                elif time.time() >= pending_confirm[0].get("expires_at", 0):
                                    pending_confirm.clear()
                                    _send_notice("START CANCELLED", "확인 시간 초과 (60초).", icon="⛔")
                                elif text.strip().lower().startswith("y"):
                                    confirmed_headless = pending_confirm[0].get("headless", True)
                                    pending_confirm.clear()
                                    if action == "fresh_start":
                                        mode_label = "headless" if confirmed_headless else "GUI"
                                        _send_notice(f"{common.TRAIN_VERSION} [{mode_label}]", "iter 0 confirmed.", icon="OK")
                                        monitor.reset_safety_flags()
                                        result = common.launch_training(LOG, fresh=True, headless=confirmed_headless)
                                        run_name = _safe_basename(result["run_dir"])
                                        common.send_text(
                                            f"<b>TRAINING START [{mode_label}]</b>\n<i>run: {run_name}</i>",
                                            LOG, parse_mode="HTML",
                                        )
                                    continue
                                else:
                                    pending_confirm.clear()
                                    _send_notice("CANCELLED", "취소되었습니다.", icon="⛔")

                        command, arg_text = _parse_command(text)
                        if command in common.command_variants():
                            command_key = f"{command} {arg_text}".strip()
                            if not _is_duplicate_command(chat_id, user_id, command_key):
                                common.log_event("CMD", "RECEIVED", f"{command} {arg_text}".strip())
                                # Immediate ACK
                                common.send_text(
                                    f"🎛️ <b>{command.upper()} — 요청 수신</b>",
                                    LOG, parse_mode="HTML",
                                )
                                try:
                                    _dispatch_command(command, arg_text, pending_confirm, monitor=monitor)
                                    common.log_event("CMD", "COMPLETED", command)
                                except Exception as err:
                                    common.write_log(f"Command error: {err}\n{common.capture_exception()}", LOG)
                                    common.log_event("ERROR", "CMD_FAILED", f"{command}: {err}")
                                    _send_notice("ERROR", str(err), icon="⚠️")

            # ── 2. Check shutdown ──
            shutdown_source = common.consume_supervisor_shutdown_request()
            if shutdown_source:
                exit_reason = f"shutdown:{shutdown_source}"
                common.write_log(f"Shutdown requested by {shutdown_source}", LOG)
                common.log_event("LISTEN", "SHUTDOWN", shutdown_source)
                common.send_text(
                    f"👮 <b>IsaacOps STOPPED — {shutdown_source}</b>",
                    LOG, parse_mode="HTML",
                )
                break

            # ── 3. Periodic monitoring ──
            monitor.tick()

    except KeyboardInterrupt:
        exit_reason = "keyboard-interrupt"
    except BaseException as err:
        exit_reason = f"fatal:{type(err).__name__}"
        try:
            common.write_log(f"IsaacOps fatal: {err}\n{common.capture_exception()}", LOG)
        except Exception:
            pass
        raise
    finally:
        _receiver_stop.set()
        common.write_log(f"IsaacOps exiting: reason={exit_reason}", LOG)
        common.release_pid_lock(PID_FILE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
