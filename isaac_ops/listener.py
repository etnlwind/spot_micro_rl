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
_CONFIRM_TIMEOUT_SEC = 60.0

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


# ═══════════════════════════════════════════
# Telegram Receiver Thread
# ═══════════════════════════════════════════

_msg_queue: queue.Queue = queue.Queue()
_receiver_stop = threading.Event()


def _telegram_receiver():
    """Dedicated thread: polls getUpdates and puts messages in queue."""
    while not _receiver_stop.is_set():
        try:
            updates = common.fetch_updates(timeout_sec=0, log_path=LOG)
            for update in updates:
                _msg_queue.put(update)
        except Exception:
            pass
        _receiver_stop.wait(1.0)  # sleep 1s, but interruptible


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


def _handle_start(pending_confirm_ref: list) -> None:
    """Start command — may set pending_confirm for user confirmation."""
    common.reload_train_version()
    active_run_dir = common.resolve_active_run_dir()
    existing_checkpoint = common.resolve_active_checkpoint(active_run_dir) if active_run_dir else None
    run_version = (common._read_run_train_version(active_run_dir) if active_run_dir else "") or ""
    version_changed = run_version and run_version != common.TRAIN_VERSION

    if existing_checkpoint and not version_changed:
        pending_confirm_ref.clear()
        pending_confirm_ref.append({
            "action": "fresh_start",
            "expires_at": time.time() + _CONFIRM_TIMEOUT_SEC,
        })
        common.send_text(
            f"⚠️ <b>확인 필요 — {common.TRAIN_VERSION} 새 훈련</b>\n"
            f"새로 구성된 reward/env 설정으로 <b>iter 0부터 새 훈련을 시작</b>합니다.\n"
            f"<i>계속하려면 Y를 입력하세요. (60초 내, 다른 입력은 취소)</i>",
            LOG, parse_mode="HTML",
        )
    else:
        if version_changed:
            common.send_text(
                f"🆕 <b>VERSION UPGRADE — {run_version} → {common.TRAIN_VERSION}</b>\n"
                f"<i>새 버전이므로 확인 없이 iter 0부터 시작합니다.</i>",
                LOG, parse_mode="HTML",
            )
        result = common.launch_training(LOG, fresh=True)
        run_name = _safe_basename(result["run_dir"])
        common.send_text(
            f"🚀 <b>TRAINING START</b>\n<i>run: {run_name}</i>\n<i>version: {common.TRAIN_VERSION}</i>",
            LOG, parse_mode="HTML",
        )


def _handle_stop() -> None:
    result = common.stop_training(LOG)
    checkpoint_name = _safe_basename(result["checkpoint"])
    run_version = common.get_run_version(result.get("run_dir", ""))
    _send_notice("TRAINING STOPPED", f"killed: {len(result['killed'])}\ncheckpoint: {checkpoint_name}", icon="⏹️", version=run_version)


def _handle_resume() -> None:
    common.reload_train_version()
    result = common.launch_training(LOG, fresh=False)
    run_name = _safe_basename(result["run_dir"])
    checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A (fresh)"
    run_version = common.get_run_version(result.get("run_dir", ""))
    icon = "▶️"
    if result["mode"] == "already-running":
        _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon=icon, version=run_version)
    else:
        _send_notice("TRAINING RESUME", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon=icon, version=run_version)


def _handle_report(run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    if common.is_training_running():
        if checkpoint_iter is not None:
            common.send_text(
                "⚠️ <b>IsaacOps — REPORT</b>\n<i>특정 iteration 리포트는 훈련이 정지된 상태에서만 생성할 수 있습니다.</i>",
                LOG, parse_mode="HTML",
            )
            return
        zip_path = common.find_latest_report_zip(run_dir)
        if not zip_path:
            common.send_text(
                "⚠️ <b>IsaacOps — REPORT</b>\n<i>현재 훈련 중이며 전송할 최신 ZIP 리포트가 없습니다.</i>",
                LOG, parse_mode="HTML",
            )
            return
        common.send_document(zip_path, f"📦 latest report | {os.path.basename(run_dir)}", LOG)
        return

    with common.busy_lock("report"):
        common.update_state(mode="reporting", last_command="report", last_error="")
        report_data = common.stop_and_report(run_dir, checkpoint, LOG, force=True)
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
        common.update_state(mode="stopped", last_command="report", last_error="")


def _handle_view(view_key: str, run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    if common.is_training_running():
        if checkpoint_iter is not None:
            common.send_text(
                f"⚠️ <b>IsaacOps — {view_key.upper()}</b>\n<i>특정 iteration 영상은 훈련이 정지된 상태에서만 생성할 수 있습니다.</i>",
                LOG, parse_mode="HTML",
            )
            return
        video_path = common.find_latest_video(view_key, run_dir)
        if not video_path:
            common.send_text(
                f"⚠️ <b>IsaacOps — {view_key.upper()}</b>\n<i>최근 {view_key} 영상을 찾지 못했습니다.</i>",
                LOG, parse_mode="HTML",
            )
            return
        common.send_video(video_path, f"📹 latest {view_key} | {os.path.basename(run_dir)}", LOG)
        return

    with common.busy_lock(view_key):
        common.update_state(mode="rendering", last_command=view_key, last_error="")
        videos = common.ensure_current_videos(run_dir, checkpoint, LOG, force=True)
        video_path = videos.get(view_key)
        if not video_path:
            raise RuntimeError(f"{view_key} view was not generated.")
        common.send_video(
            video_path,
            f"📹 {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
            LOG,
        )
        common.update_state(mode="stopped", last_command=view_key, last_error="")


def _dispatch_command(command: str, arg_text: str, pending_confirm: list) -> None:
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
        _handle_start(pending_confirm)
        return
    if command == "stop":
        _handle_stop()
        return
    if command == "resume":
        _handle_resume()
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

    common.write_log(f"[VideoReport] iter {milestone} (current={current_iter})", LOG)
    common.log_event("HB", "VIDEO_REPORT", f"iter={milestone} current={current_iter} catchup={is_catchup}")
    notice_lines = [f"🎬 <b>AUTO VIDEO REPORT — iter {milestone:,}{catchup_label}</b>"]
    if is_catchup:
        notice_lines.append(f"<i>현재 iter {current_iter:,}, iter {milestone:,} 소급 생성</i>")
    else:
        notice_lines.append("<i>훈련 일시 정지 후 영상 녹화</i>")
    notice_lines.append(f"<i>checkpoint: model_{milestone}.pt</i>")
    common.send_text("\n".join(notice_lines), LOG, parse_mode="HTML")

    try:
        report_data = common.stop_and_report(run_dir, checkpoint, LOG, force=True)
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

    def __init__(self, iter_step: int, video_iter_step: int):
        self.iter_step = iter_step
        self.video_iter_step = video_iter_step
        self.last_sent_milestone = 0
        self.last_video_milestone = 0
        self.last_run_name = ""
        self.collapse_consecutive = 0
        self.collapse_restart_done = False
        self.perf_checked = False
        self.training_stopped = False
        self._last_tick = 0.0
        self._tick_interval = 10.0  # check every 10 seconds

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

            # New run detection
            if run_name != self.last_run_name:
                self.last_run_name = run_name
                self.last_sent_milestone = _restore_last_milestone(run_dir, self.iter_step)
                self.last_video_milestone = _restore_last_milestone(run_dir, self.video_iter_step, report_kind="video_report")
                resume_iter = _get_resume_checkpoint_iter()
                if resume_iter > 0:
                    skip_up_to = (resume_iter // self.video_iter_step) * self.video_iter_step
                    self.last_video_milestone = max(self.last_video_milestone, skip_up_to)
                elif self.last_video_milestone == 0:
                    skip_up_to = (current_iter // self.video_iter_step) * self.video_iter_step
                    self.last_video_milestone = skip_up_to
                self.collapse_consecutive = 0
                self.collapse_restart_done = False
                self.perf_checked = False

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

            # ── Video report milestones ──
            missed = _collect_missed_milestones(self.last_video_milestone, current_iter, self.video_iter_step)
            if missed:
                common.stop_training(LOG)
                self.training_stopped = True
                total_missed = len(missed)
                for idx, milestone in enumerate(missed, start=1):
                    _run_video_report(run_dir, milestone, current_iter, total_missed, idx, self.video_iter_step)
                    self.last_video_milestone = milestone
                next_milestone = self.last_video_milestone + self.video_iter_step
                common.launch_training(LOG)
                self.training_stopped = False
                common.write_log(f"[VideoReport] all done, training restarted", LOG)
                catchup_summary = f"iter {', '.join(f'{m:,}' for m in missed)}"
                common.send_text(
                    f"🚀 <b>TRAINING RESUME — {catchup_summary}</b>\n"
                    f"<i>다음 리포트: iter {next_milestone:,}</i>",
                    LOG, parse_mode="HTML",
                )
                text_milestone = (current_iter // self.iter_step) * self.iter_step
                self.last_sent_milestone = max(self.last_sent_milestone, text_milestone)
                return

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

    monitor = Monitor(args.iter_step, args.video_iter_step)
    pending_confirm: list = []  # mutable container for confirmation state
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
                        # Pending confirmation handling
                        if pending_confirm:
                            if time.time() > pending_confirm[0].get("expires_at", 0):
                                pending_confirm.clear()
                                _send_notice("START CANCELLED", "확인 시간 초과 (60초).", icon="⛔")
                            elif text.strip().lower().startswith("y"):
                                pending_confirm.clear()
                                _send_notice(f"{common.TRAIN_VERSION} 새 훈련 확인", "iter 0부터 시작합니다.", icon="✅")
                                result = common.launch_training(LOG, fresh=True)
                                run_name = _safe_basename(result["run_dir"])
                                common.send_text(
                                    f"🚀 <b>TRAINING START</b>\n<i>run: {run_name}</i>",
                                    LOG, parse_mode="HTML",
                                )
                                continue
                            else:
                                pending_confirm.clear()
                                _send_notice("START CANCELLED", "취소되었습니다.", icon="⛔")
                                continue

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
                                    _dispatch_command(command, arg_text, pending_confirm)
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
        if monitor.training_stopped:
            try:
                common.write_log("IsaacOps exiting while training stopped — attempting recovery", LOG)
                common.launch_training(LOG)
            except Exception:
                pass
        common.write_log(f"IsaacOps exiting: reason={exit_reason}", LOG)
        common.release_pid_lock(PID_FILE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
