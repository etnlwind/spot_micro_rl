import argparse
import collections
import os
import subprocess
import sys
import time
import uuid


SCRIPT_PATH = os.path.abspath(__file__)
SCRIPT_DIR = os.path.dirname(SCRIPT_PATH)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
_BOOTSTRAP_ENV_VAR = "SPOT_MICRO_SUPERVISOR_BOOTSTRAPPED"
_BACKGROUND_LAUNCH_ENV_VAR = "SPOT_MICRO_SUPERVISOR_BACKGROUND"


def _load_bootstrap_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip().lstrip("\ufeff")] = value.strip()
    return env


def _normalize_bootstrap_path(raw_path: str | None) -> str | None:
    if raw_path is None:
        return None
    candidate = str(raw_path).strip()
    if not candidate:
        return None
    if (candidate.startswith('"') and candidate.endswith('"')) or (candidate.startswith("'") and candidate.endswith("'")):
        candidate = candidate[1:-1].strip()
    return os.path.abspath(candidate) if candidate else None


def _resolve_bootstrap_activate_bat(env_values: dict[str, str]) -> str | None:
    conda_exe = os.environ.get("CONDA_EXE", "")
    conda_dir = os.path.dirname(conda_exe) if conda_exe else ""
    conda_root = os.path.dirname(conda_dir) if conda_dir else ""
    candidates = [
        env_values.get("CONDA_ACTIVATE_BAT"),
        os.path.join(conda_dir, "activate.bat") if conda_dir else None,
        os.path.join(conda_root, "condabin", "activate.bat") if conda_root else None,
        os.path.join(conda_root, "condabin", "conda.bat") if conda_root else None,
    ]
    for raw_candidate in candidates:
        candidate = _normalize_bootstrap_path(raw_candidate)
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _target_conda_env(env_values: dict[str, str]) -> str:
    return env_values.get("CONDA_ENV_NAME") or os.environ.get("CONDA_DEFAULT_ENV", "env_isaaclab") or "env_isaaclab"


def _running_in_target_env(target_env: str) -> bool:
    active_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    if active_env.lower() == target_env.lower():
        return True
    prefix_name = os.path.basename(sys.prefix.rstrip("\\/")) if sys.prefix else ""
    if prefix_name.lower() == target_env.lower():
        return True
    executable_dir = os.path.basename(os.path.dirname(sys.executable).rstrip("\\/")) if sys.executable else ""
    return executable_dir.lower() == target_env.lower()


def _should_bootstrap(argv: list[str]) -> bool:
    if len(argv) <= 1:
        return False
    help_flags = {"-h", "--help"}
    return any(arg not in help_flags for arg in argv[1:])


def _bootstrap_into_conda_if_needed() -> None:
    if sys.platform != "win32":
        return
    if os.environ.get(_BOOTSTRAP_ENV_VAR) == "1":
        return
    if not _should_bootstrap(sys.argv):
        return
    env_values = _load_bootstrap_env(ENV_FILE)
    target_env = _target_conda_env(env_values)
    if _running_in_target_env(target_env):
        return
    activate_bat = _resolve_bootstrap_activate_bat(env_values)
    if not activate_bat:
        return
    forwarded_args = subprocess.list2cmdline(sys.argv[1:])
    command = (
        (
            f'call "{activate_bat}" activate {target_env} && '
            if os.path.basename(activate_bat).lower() == "conda.bat"
            else f'call "{activate_bat}" && conda activate {target_env} && '
        )
        + f'cd /d "{PROJECT_ROOT}" && '
        + f'set {_BOOTSTRAP_ENV_VAR}=1 && '
        + 'set PYTHONIOENCODING=utf-8 && '
        + f'python "{SCRIPT_PATH}" {forwarded_args}'
    )
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        shell=True,
        env={**os.environ, _BOOTSTRAP_ENV_VAR: "1", "PYTHONIOENCODING": "utf-8"},
    )
    raise SystemExit(result.returncode)


_bootstrap_into_conda_if_needed()

if __package__:
    from . import common
else:
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import common


_RECENT_UPDATE_IDS = collections.deque(maxlen=128)
_RECENT_UPDATE_ID_SET: set[int] = set()
_RECENT_COMMAND_WINDOW_SEC = 15.0
_RECENT_COMMAND_TIMES: dict[tuple[str | None, str | None, str], float] = {}


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


def _is_duplicate_command(chat_id: str | None, user_id: str | None, command_key: str) -> bool:
    now = time.monotonic()
    expired = [key for key, timestamp in _RECENT_COMMAND_TIMES.items() if now - timestamp > _RECENT_COMMAND_WINDOW_SEC]
    for key in expired:
        _RECENT_COMMAND_TIMES.pop(key, None)
    dedupe_key = (chat_id, user_id, command_key)
    previous = _RECENT_COMMAND_TIMES.get(dedupe_key)
    _RECENT_COMMAND_TIMES[dedupe_key] = now
    return previous is not None and now - previous <= _RECENT_COMMAND_WINDOW_SEC


def _send_notice(title: str, body: str, icon: str = "👮") -> None:
    common.send_text(
        f"{icon} <b>SUPERVISOR — {title}</b>\n<i>{body}</i>",
        common.SUPERVISOR_LOG,
        parse_mode="HTML",
    )


def _parse_command_request(text: str) -> tuple[str, str]:
    stripped = (text or "").strip()
    if not stripped:
        return "", ""
    parts = stripped.split(maxsplit=1)
    command = common.normalize_command(parts[0])
    arg_text = parts[1].strip() if len(parts) > 1 else ""
    return command, arg_text


def _parse_command_args(arg_text: str) -> tuple[str | None, list[int]]:
    """인자 문자열을 (version, iters) 로 파싱.

    형식:
      ""                → (None, [])              현재 버전 최신
      "1000"            → (None, [1000])           현재 버전 iter 1000
      "800 600 400"     → (None, [800, 600, 400])  다중 iter 순차 처리
      "V26.1"           → ("V26.1", [])            V26.1 최신
      "V26.1 1000"      → ("V26.1", [1000])        V26.1 iter 1000
      "V26.1 800 600"   → ("V26.1", [800, 600])    V26.1 다중 iter
      "v26.1 1000"      → ("V26.1", [1000])        대소문자 무관
    """
    import re
    arg_text = (arg_text or "").strip()
    if not arg_text:
        return None, []
    version_pattern = re.compile(r'^[Vv]\d+', re.IGNORECASE)
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
            raise ValueError(f"iter는 양의 정수여야 합니다: '{token}'")
        n = int(token)
        if n <= 0:
            raise ValueError(f"iter는 0보다 커야 합니다: {n}")
        iters.append(n)
    return version, iters


def _resolve_requested_checkpoint(run_dir: str | None, checkpoint_iter: int | None) -> str | None:
    if checkpoint_iter is None:
        return common.resolve_active_checkpoint(run_dir)
    checkpoint = common.get_checkpoint_by_iter(run_dir, checkpoint_iter)
    if checkpoint:
        return checkpoint
    raise RuntimeError(f"checkpoint model_{checkpoint_iter}.pt not found in any {common._read_run_train_version(run_dir) or 'V?'} run")


def _build_command_ack(command: str, checkpoint_iters: list[int] | None = None, target_version: str | None = None) -> str:
    checkpoint_iters = checkpoint_iters or []
    first_iter = checkpoint_iters[0] if checkpoint_iters else None
    run_dir = common.resolve_run_dir_for_version(target_version) if target_version else common.resolve_active_run_dir()
    try:
        checkpoint = _resolve_requested_checkpoint(run_dir, first_iter)
    except RuntimeError:
        checkpoint = None
    if checkpoint and run_dir:
        checkpoint_run = os.path.dirname(os.path.abspath(checkpoint))
        if os.path.abspath(run_dir) != checkpoint_run:
            run_dir = checkpoint_run
    run_name = os.path.basename(run_dir) if run_dir else "N/A"
    checkpoint_name = os.path.basename(checkpoint) if checkpoint else "N/A"
    training_running = common.is_training_running()
    if len(checkpoint_iters) > 1:
        iter_seq = " → ".join(str(i) for i in checkpoint_iters)
        checkpoint_hint = f"\n<i>{len(checkpoint_iters)}건 순차 처리: {iter_seq}</i>"
    elif first_iter is not None:
        checkpoint_hint = f"\n<i>requested checkpoint: model_{first_iter}.pt</i>"
    else:
        checkpoint_hint = ""
    if command == "start":
        return (
            f"🚀 <b>TRAINING START (FRESH) — {run_name}</b>\n"
            "<i>iter 0부터 새로 시작합니다. checkpoint가 있으면 확인을 요청합니다.</i>"
        )
    if command == "resume":
        return (
            f"▶️ <b>TRAINING RESUME — {run_name}</b>\n"
            f"<i>checkpoint: {checkpoint_name}</i>\n"
            "<i>마지막 checkpoint에서 재개합니다.</i>"
        )
    if command == "stop":
        return "⏹️ <b>TRAINING STOP — 진행 중인 훈련을 중단합니다</b>"
    if command == "status":
        return "👮 <b>SUPERVISOR STATUS — 현재 상태를 조회합니다</b>"
    if command == "help":
        return "❔ <b>HELP — 명령 목록을 전송합니다</b>"
    if command == "shutdown":
        return "🛑 <b>SUPERVISOR SHUTDOWN — 종료를 준비합니다</b>"
    if command == "report":
        if training_running:
            return (
                f"📦 <b>REPORT REQUEST — {run_name} (훈련 중)</b>\n"
                "<i>최신 ZIP 리포트를 찾아 전송합니다.</i>"
                f"{checkpoint_hint}"
            )
        return (
            f"📦 <b>REPORT REQUEST — {run_name} | {checkpoint_name}</b>\n"
            "<i>영상, 분석, ZIP 리포트를 생성합니다.</i>"
            f"{checkpoint_hint}"
        )
    if command in {"front", "rear", "top", "side"}:
        if training_running:
            return (
                f"🎥 <b>VIDEO REQUEST — {command} | {run_name} (훈련 중)</b>\n"
                f"<i>최신 {command} 영상을 찾아 전송합니다.</i>"
                f"{checkpoint_hint}"
            )
        return (
            f"🎥 <b>VIDEO REQUEST — {command} | {checkpoint_name}</b>\n"
            f"<i>{command} 영상을 생성합니다.</i>"
            f"{checkpoint_hint}"
        )
    return f"🎛️ <b>{command.upper()} — 요청 수신</b>"


def _handle_hb_command(run_dir: str, iteration: int | None = None) -> None:
    data = common.read_tfevents(run_dir)
    if not data or not data.get("Train/mean_reward"):
        common.send_text("⚠️ <b>SUPERVISOR — HB</b>\n<i>tfevents 데이터를 읽지 못했습니다.</i>", common.SUPERVISOR_LOG, parse_mode="HTML")
        return
    run_name = os.path.basename(run_dir)
    # iteration 미지정 시 최신 iter 사용
    if iteration is None:
        cycle_num = 0  # 조회용이므로 cycle 기록 불필요
    else:
        cycle_num = iteration // common.HEARTBEAT_ITER_STEP
    report_text = common.format_report(data, run_name, cycle_num, iteration=iteration)
    common.send_text(report_text, common.SUPERVISOR_LOG, parse_mode="HTML")


def _handle_report_command(run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    if common.is_training_running():
        if checkpoint_iter is not None:
            common.send_text("⚠️ <b>SUPERVISOR — REPORT</b>\n<i>특정 iteration 리포트는 훈련이 정지된 상태에서만 생성할 수 있습니다.</i>", common.SUPERVISOR_LOG, parse_mode="HTML")
            return
        zip_path = common.find_latest_report_zip(run_dir)
        if not zip_path:
            common.send_text("⚠️ <b>SUPERVISOR — REPORT</b>\n<i>현재 훈련 중이며 전송할 최신 ZIP 리포트가 없습니다.</i>", common.SUPERVISOR_LOG, parse_mode="HTML")
            return
        common.send_document(
            zip_path,
            f"📦 latest report | {os.path.basename(run_dir)} | {os.path.basename(zip_path)}",
            common.SUPERVISOR_LOG,
        )
        return
    with common.busy_lock("report"):
        common.update_state(mode="reporting", last_command="report", last_error="")
        report_data = common.stop_and_report(run_dir, checkpoint, common.SUPERVISOR_LOG, force=True)
        common.send_text(
            common.format_report_summary_html(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"], metrics_run_dir=report_data.get("metrics_run_dir")),
            common.SUPERVISOR_LOG,
            parse_mode="HTML",
        )
        common.send_document(
            report_data["zip_path"],
            f"📦 current report | {os.path.basename(run_dir)} | {os.path.basename(report_data['zip_path'])}",
            common.SUPERVISOR_LOG,
        )
        common.update_state(mode="stopped", last_command="report", last_error="")


def _handle_view_command(view_key: str, run_dir: str, checkpoint: str, checkpoint_iter: int | None = None) -> None:
    if common.is_training_running():
        if checkpoint_iter is not None:
            common.send_text(f"⚠️ <b>SUPERVISOR — {view_key.upper()}</b>\n<i>특정 iteration 영상은 훈련이 정지된 상태에서만 생성할 수 있습니다.</i>", common.SUPERVISOR_LOG, parse_mode="HTML")
            return
        video_path = common.find_latest_video(view_key, run_dir)
        if not video_path:
            common.send_text(f"⚠️ <b>SUPERVISOR — {view_key.upper()}</b>\n<i>현재 훈련 중이며 최근 {view_key} 영상을 찾지 못했습니다.</i>", common.SUPERVISOR_LOG, parse_mode="HTML")
            return
        common.send_video(
            video_path,
            f"📹 latest {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
            common.SUPERVISOR_LOG,
        )
        return
    with common.busy_lock(view_key):
        common.update_state(mode="rendering", last_command=view_key, last_error="")
        videos = common.ensure_current_videos(run_dir, checkpoint, common.SUPERVISOR_LOG, force=True)
        video_path = videos.get(view_key)
        if not video_path:
            raise RuntimeError(f"{view_key} view was not generated.")
        common.send_video(
            video_path,
            f"📹 current {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
            common.SUPERVISOR_LOG,
        )
        common.update_state(mode="stopped", last_command=view_key, last_error="")


def handle_command(command: str, checkpoint_iters: list[int] | None = None, target_version: str | None = None) -> None:
    checkpoint_iters = checkpoint_iters or []
    base_run_dir = None
    if target_version:
        base_run_dir = common.resolve_run_dir_for_version(target_version)
        if not base_run_dir:
            _send_notice("VERSION NOT FOUND", f"'{target_version}' 버전의 훈련 데이터를 찾지 못했습니다.", icon="⚠️")
            return
    else:
        base_run_dir = common.resolve_active_run_dir()

    # single-iter 명령(hb 등)을 위해 첫 번째 iter 또는 None
    first_iter = checkpoint_iters[0] if checkpoint_iters else None

    if command == "help":
        _send_notice("COMMAND MENU", common.help_text().replace("\n", "\n"), icon="❔")
        return
    if command == "status":
        common.send_text(common.format_status_html(), common.SUPERVISOR_LOG, parse_mode="HTML")
        return
    if command == "selfcheck":
        common.send_text(f"<pre>{common.build_context_resolution_text()}</pre>", common.SUPERVISOR_LOG, parse_mode="HTML")
        return
    if command == "resume":
        common.reload_train_version()  # .env에서 최신 TRAIN_VERSION 재로드
        result = common.launch_training(common.SUPERVISOR_LOG, fresh=False)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A (fresh)"
        if result["mode"] == "already-running":
            _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nversion: {common.TRAIN_VERSION}", icon="▶️")
        else:
            _send_notice("TRAINING RESUME", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nversion: {common.TRAIN_VERSION}", icon="▶️")
        return
    if command == "stop":
        result = common.stop_training(common.SUPERVISOR_LOG)
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A"
        _send_notice("TRAINING STOPPED", f"killed: {len(result['killed'])}\ncheckpoint: {checkpoint_name}", icon="⏹️")
        return
    if command == "shutdown":
        common.request_supervisor_shutdown("telegram-command")
        _send_notice("SUPERVISOR SHUTDOWN QUEUED", "Supervisor 종료 요청을 기록했습니다.", icon="👮")
        return
    if command == "hb":
        if not base_run_dir:
            _send_notice("CONTEXT NOT FOUND", "active run을 찾지 못했습니다.", icon="⚠️")
            return
        _handle_hb_command(base_run_dir, iteration=first_iter)
        return

    # report / view: iter 리스트 순차 처리
    if command in {"report", "front", "rear", "top", "side"}:
        iter_list = checkpoint_iters if checkpoint_iters else [None]
        for iter_num in iter_list:
            run_dir = base_run_dir
            try:
                checkpoint = _resolve_requested_checkpoint(run_dir, iter_num)
            except RuntimeError as e:
                _send_notice("NOT FOUND", str(e), icon="⚠️")
                continue
            if checkpoint and run_dir:
                checkpoint_run = os.path.dirname(os.path.abspath(checkpoint))
                if os.path.abspath(run_dir) != checkpoint_run:
                    run_dir = checkpoint_run
            if not run_dir or not checkpoint:
                label = f"model_{iter_num}.pt" if iter_num else "latest checkpoint"
                _send_notice("NOT FOUND", f"{label}를 찾지 못했습니다.", icon="⚠️")
                continue
            if command == "report":
                _handle_report_command(run_dir, checkpoint, checkpoint_iter=iter_num)
            else:
                _handle_view_command(command, run_dir, checkpoint, checkpoint_iter=iter_num)
        return

    _send_notice("UNKNOWN COMMAND", f"{command}\n\n{common.help_text()}", icon="⚠️")


def _print_local(message: str) -> None:
    try:
        print(message, flush=True)
    except OSError:
        common.write_log(f"Local console output suppressed: {message}", common.SUPERVISOR_LOG)


def _build_listen_command(args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        SCRIPT_PATH,
        "--listen",
        "--poll",
        str(args.poll),
        "--iter-step",
        str(args.iter_step),
        "--heartbeat-poll",
        str(args.heartbeat_poll),
    ]


def _run_supervisor_background(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        raise RuntimeError("background supervisor launch is only supported on Windows")
    live_pid = common._read_live_pid_lock(common.SUPERVISOR_PID_FILE)
    if live_pid:
        _print_local(f"supervisor already running (pid {live_pid})")
        return 0
    child_env = dict(os.environ)
    child_env.pop(_BACKGROUND_LAUNCH_ENV_VAR, None)
    creationflags = 0
    for flag_name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        creationflags |= int(getattr(subprocess, flag_name, 0) or 0)
    command = _build_listen_command(args)
    common.write_log(f"Launching supervisor background process: {' '.join(command)}", common.SUPERVISOR_LOG)
    with open(common.SUPERVISOR_STDOUT_LOG, "ab") as stdout_file, open(common.SUPERVISOR_STDERR_LOG, "ab") as stderr_file:
        proc = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            close_fds=True,
            creationflags=creationflags,
        )
    common.write_log(f"Supervisor background launcher PID: {proc.pid}", common.SUPERVISOR_LOG)
    time.sleep(3)
    live_pid = common._read_live_pid_lock(common.SUPERVISOR_PID_FILE)
    if live_pid:
        common.write_log(f"Supervisor background active PID: {live_pid}", common.SUPERVISOR_LOG)
        _print_local(f"supervisor launched in background (pid {live_pid})")
        _print_local("use supervisor.cmd --status to inspect or supervisor.cmd --shutdown to stop")
        return 0
    stdout_tail = common._read_text_tail(common.SUPERVISOR_STDOUT_LOG)
    stderr_tail = common._read_text_tail(common.SUPERVISOR_STDERR_LOG)
    if proc.poll() is not None:
        common.write_log(f"Supervisor background process exited before lock acquisition (rc={proc.returncode})", common.SUPERVISOR_LOG)
    if stdout_tail:
        common.write_log(f"Supervisor stdout tail before startup failure:\n{stdout_tail}", common.SUPERVISOR_LOG)
    if stderr_tail:
        common.write_log(f"Supervisor stderr tail before startup failure:\n{stderr_tail}", common.SUPERVISOR_LOG)
    raise RuntimeError("supervisor background launch did not acquire the supervisor lock")


def _require_context() -> tuple[str, str]:
    run_dir, checkpoint = common.resolve_context()
    if not run_dir or not checkpoint:
        raise RuntimeError("active run/checkpoint를 찾지 못했습니다.")
    return run_dir, checkpoint


def _handle_report_local(run_dir: str, checkpoint: str) -> None:
    if common.is_training_running():
        zip_path = common.find_latest_report_zip(run_dir)
        if not zip_path:
            raise RuntimeError("현재 훈련 중이며 전송할 최신 ZIP 리포트가 없습니다.")
        common.send_document(
            zip_path,
            f"📦 latest report | {os.path.basename(run_dir)} | {os.path.basename(zip_path)}",
            common.SUPERVISOR_LOG,
        )
        _print_local(f"latest report: {zip_path}")
        return
    with common.busy_lock("report"):
        common.update_state(mode="reporting", last_command="report", last_error="")
        report_data = common.stop_and_report(run_dir, checkpoint, common.SUPERVISOR_LOG, force=True)
        common.update_state(mode="stopped", last_command="report", last_error="")
    common.send_text(
        common.format_report_summary_html(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"]),
        common.SUPERVISOR_LOG,
        parse_mode="HTML",
    )
    common.send_document(
        report_data["zip_path"],
        f"📦 current report | {os.path.basename(run_dir)} | {os.path.basename(report_data['zip_path'])}",
        common.SUPERVISOR_LOG,
    )
    _print_local(common.format_report_summary(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"]))
    _print_local(f"zip: {report_data['zip_path']}")


def _handle_view_local(view_key: str, run_dir: str, checkpoint: str) -> None:
    if common.is_training_running():
        video_path = common.find_latest_video(view_key, run_dir)
        if not video_path:
            raise RuntimeError(f"현재 훈련 중이며 최근 {view_key} 영상을 찾지 못했습니다.")
        common.send_video(
            video_path,
            f"📹 latest {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
            common.SUPERVISOR_LOG,
        )
        _print_local(f"latest {view_key}: {video_path}")
        return
    with common.busy_lock(view_key):
        common.update_state(mode="rendering", last_command=view_key, last_error="")
        videos = common.ensure_current_videos(run_dir, checkpoint, common.SUPERVISOR_LOG, force=True)
        common.update_state(mode="stopped", last_command=view_key, last_error="")
    video_path = videos.get(view_key)
    if not video_path:
        raise RuntimeError(f"{view_key} view was not generated.")
    common.send_video(
        video_path,
        f"📹 current {view_key} | {os.path.basename(run_dir)} | iter {common.get_display_iteration(run_dir, checkpoint):,}",
        common.SUPERVISOR_LOG,
    )
    _print_local(f"{view_key}: {video_path}")


def _resolve_v23_refresh_run_dir() -> str | None:
    active_run_dir = common.resolve_active_run_dir()
    if active_run_dir and os.path.isdir(active_run_dir):
        return active_run_dir
    if not os.path.isdir(common.LOG_BASE):
        return None
    candidates: list[str] = []
    for run_name in os.listdir(common.LOG_BASE):
        candidate_run_dir = os.path.join(common.LOG_BASE, run_name)
        if not os.path.isdir(candidate_run_dir):
            continue
        if not os.path.isfile(common.get_heartbeat_history_path(candidate_run_dir)):
            continue
        candidates.append(candidate_run_dir)
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _run_local_action(action: str, args: argparse.Namespace) -> int:
    if action == "status":
        common.send_text(common.format_status_html(), common.SUPERVISOR_LOG, parse_mode="HTML")
        _print_local(common.build_status_text())
        return 0
    if action == "selfcheck":
        text = common.build_context_resolution_text()
        common.send_text(f"<pre>{text}</pre>", common.SUPERVISOR_LOG, parse_mode="HTML")
        _print_local(text)
        return 0
    if action == "start":
        common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
        result = common.launch_training(common.SUPERVISOR_LOG, fresh=True)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        if result["mode"] == "already-running":
            existing_ckpt = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A"
            _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {existing_ckpt}\nversion: {common.TRAIN_VERSION}\nsource: cli", icon="🚀")
            _print_local(f"training already running\nrun: {run_name}\ncheckpoint: {existing_ckpt}")
        else:
            _send_notice("TRAINING START (FRESH)", f"run: {run_name}\ncheckpoint: iter 0 (fresh)\nversion: {common.TRAIN_VERSION}\nsource: cli", icon="🚀")
            _print_local(f"training started fresh\nrun: {run_name}")
        return 0
    if action == "resume":
        common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
        result = common.launch_training(common.SUPERVISOR_LOG, fresh=False)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A"
        if result["mode"] == "already-running":
            _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nversion: {common.TRAIN_VERSION}\nsource: cli", icon="▶️")
            _print_local(f"training already running\nrun: {run_name}\ncheckpoint: {checkpoint_name}")
        else:
            _send_notice("TRAINING RESUME", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nversion: {common.TRAIN_VERSION}\nsource: cli", icon="▶️")
            _print_local(f"training resumed\nrun: {run_name}\ncheckpoint: {checkpoint_name}")
        return 0
    if action == "stop":
        result = common.stop_training(common.SUPERVISOR_LOG)
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A"
        _send_notice("TRAINING STOPPED", f"killed: {len(result['killed'])}\ncheckpoint: {checkpoint_name}\nsource: cli", icon="⏹️")
        _print_local(f"training stopped\nkilled: {len(result['killed'])}\ncheckpoint: {checkpoint_name}")
        return 0
    if action == "heartbeat-start":
        result = common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
        _send_notice("HEARTBEAT ACTIVE", f"mode: {result['mode']}\nsource: cli", icon="💓")
        _print_local(f"heartbeat: {result['mode']}")
        return 0
    if action == "heartbeat-stop":
        killed = common.stop_heartbeat(common.SUPERVISOR_LOG)
        _send_notice("HEARTBEAT STOPPED", f"killed: {len(killed)}\nsource: cli", icon="💓")
        _print_local(f"heartbeat stopped\nkilled: {len(killed)}")
        return 0
    if action == "heartbeat-status":
        processes = common.list_heartbeat_processes()
        if not processes:
            _send_notice("HEARTBEAT STATUS", "stopped\nsource: cli", icon="💓")
            _print_local("heartbeat: stopped")
            return 0
        lines = [f"heartbeat: alive ({len(processes)})"]
        lines.extend(f"- pid {entry['pid']}: {entry['name']}" for entry in processes)
        _send_notice("HEARTBEAT STATUS", f"alive: {len(processes)}\nsource: cli", icon="💓")
        _print_local("\n".join(lines))
        return 0
    if action == "shutdown":
        common.request_supervisor_shutdown("cli-command")
        _send_notice("SUPERVISOR SHUTDOWN QUEUED", "Supervisor 종료 요청을 기록했습니다.\nsource: cli", icon="👮")
        _print_local("supervisor shutdown requested")
        return 0
    if action == "v23-backfill":
        max_runs = args.v23_max_runs if args.v23_max_runs and args.v23_max_runs > 0 else None
        result = common.backfill_v23_run_workbooks(
            common.SUPERVISOR_LOG,
            max_runs=max_runs,
            overwrite=args.v23_overwrite,
        )
        refresh_run_dir = _resolve_v23_refresh_run_dir()
        refresh_summary = "master refresh skipped"
        if refresh_run_dir:
            refresh_result = common.refresh_v23_training_logs(refresh_run_dir, common.SUPERVISOR_LOG)
            refresh_summary = (
                f"master refreshed\n"
                f"run: {os.path.basename(refresh_run_dir)}\n"
                f"skipped: {len(refresh_result.get('skipped_runs') or [])}"
            )
        _print_local(
            "v23 backfill complete\n"
            f"processed: {result.get('processed_runs', 0)}\n"
            f"created: {len(result.get('created_runs') or [])}\n"
            f"skipped: {len(result.get('skipped_runs') or [])}\n"
            f"failed: {len(result.get('failed_runs') or [])}\n"
            f"{refresh_summary}"
        )
        _send_notice(
            "V23 BACKFILL COMPLETE",
            (
                f"processed: {result.get('processed_runs', 0)}\n"
                f"created: {len(result.get('created_runs') or [])}\n"
                f"skipped: {len(result.get('skipped_runs') or [])}\n"
                f"failed: {len(result.get('failed_runs') or [])}\n"
                f"{refresh_summary}\n"
                "source: cli"
            ),
            icon="📚",
        )
        return 0
    run_dir, checkpoint = _require_context()
    if action == "report":
        _handle_report_local(run_dir, checkpoint)
        return 0
    if action in {"front", "rear", "top", "side"}:
        _handle_view_local(action, run_dir, checkpoint)
        return 0
    raise RuntimeError(f"Unsupported action: {action}")


def _run_supervisor_loop(args: argparse.Namespace) -> int:
    session_id = uuid.uuid4().hex[:12]
    exit_reason = "loop-returned"
    exit_detail = ""
    common.clear_supervisor_shutdown_request()
    common.acquire_pid_lock(common.SUPERVISOR_PID_FILE, "supervisor", common.SUPERVISOR_LOG)
    common.mark_supervisor_started(session_id, os.getpid(), common.SUPERVISOR_LOG)
    common.write_log(f"Supervisor session started: session={session_id} pid={os.getpid()}", common.SUPERVISOR_LOG)
    common.prime_update_offset(common.SUPERVISOR_LOG)
    common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
    common.update_state(mode="training" if common.is_training_running() else "idle", last_command="startup", last_error="")
    import datetime as _dt
    _sv_ver = _dt.datetime.fromtimestamp(os.path.getmtime(__file__)).strftime("%Y-%m-%d %H:%M")
    common.send_text(
        f"👮 <b>SUPERVISOR ACTIVE</b>  version: <code>{_sv_ver}</code>\n\n"
        + common.help_text(),
        common.SUPERVISOR_LOG,
        parse_mode="HTML",
    )
    pending_confirm: dict | None = None  # {"action": "fresh_start", "ckpt_iter": int, "ckpt_name": str, "expires_at": float}
    _CONFIRM_TIMEOUT_SEC = 60.0
    try:
        while True:
            try:
                common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
                for update in common.fetch_updates(timeout_sec=0, log_path=common.SUPERVISOR_LOG):
                    update_id = int(update.get("update_id", 0) or 0)
                    if not _remember_update_id(update_id):
                        common.write_log(f"Skipped duplicate Telegram update_id={update_id}", common.SUPERVISOR_LOG)
                        continue
                    text, chat_id, user_id = common.extract_message(update)
                    if not text:
                        continue
                    if not common.is_authorized_message(chat_id, user_id):
                        common.write_log(
                            f"Ignored unauthorized Telegram message chat_id={chat_id} user_id={user_id}",
                            common.SUPERVISOR_LOG,
                        )
                        continue

                    # pending confirmation 처리 — y/Y 로 시작하면 확인, 나머지는 모두 취소
                    if pending_confirm:
                        if time.time() > pending_confirm.get("expires_at", 0):
                            pending_confirm = None
                            _send_notice("START CANCELLED", "확인 시간이 초과되었습니다 (60초).", icon="⛔")
                            # fall through to normal command processing
                        elif text.strip().lower().startswith("y"):
                            action = pending_confirm["action"]
                            pending_confirm = None
                            common.write_log(f"[Confirm] action={action} confirmed by user", common.SUPERVISOR_LOG)
                            if action == "fresh_start":
                                result = common.launch_training(common.SUPERVISOR_LOG, fresh=True)
                                run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
                                if result["mode"] == "already-running":
                                    _send_notice("TRAINING ACTIVE", f"run: {run_name}", icon="🚀")
                                else:
                                    common.send_text(
                                        f"🚀 <b>TRAINING START (FRESH)</b>\n"
                                        f"<i>run: {run_name}</i>\n"
                                        f"<i>version: {common.TRAIN_VERSION}</i>\n"
                                        f"<i>iter 0부터 시작합니다.</i>",
                                        common.SUPERVISOR_LOG,
                                        parse_mode="HTML",
                                    )
                            continue
                        else:
                            # y/Y로 시작하지 않는 모든 입력 → 취소
                            pending_confirm = None
                            _send_notice("START CANCELLED", "취소되었습니다.", icon="⛔")
                            continue

                    command, arg_text = _parse_command_request(text)
                    if command not in common.command_variants():
                        continue
                    command_key = f"{command} {arg_text}".strip()
                    if _is_duplicate_command(chat_id, user_id, command_key):
                        common.write_log(
                            f"Skipped duplicate Telegram command chat_id={chat_id} user_id={user_id} command={command_key}",
                            common.SUPERVISOR_LOG,
                        )
                        continue
                    target_version, checkpoint_iters = _parse_command_args(arg_text)

                    # /start: 버전이 동일한 경우에만 checkpoint 덮어쓰기 확인 요청.
                    # 버전이 다르면 (예: V27.1b → V28) 확인 없이 바로 fresh start.
                    if command == "start":
                        # ── 버전 검증: env_cfg.py(권위) vs .env 불일치 체크 ──
                        # reload_train_version()은 env_cfg.py를 우선 읽고 .env와 불일치 시 WARNING 출력
                        cfg_ver_before = common._read_env_cfg_train_version()
                        env_ver_before = common._load_env(common.ENV_FILE).get("TRAIN_VERSION", "")
                        if cfg_ver_before and env_ver_before and cfg_ver_before != env_ver_before:
                            common.send_text(
                                f"⚠️ <b>버전 불일치 감지 — 훈련을 중단합니다</b>\n"
                                f"<code>env_cfg.py: {cfg_ver_before}</code>\n"
                                f"<code>.env:       {env_ver_before}</code>\n\n"
                                f".env의 TRAIN_VERSION을 <b>{cfg_ver_before}</b>로 수정한 뒤 다시 /start 하세요.\n"
                                f"<i>(자동 수정하려면 /fix_version 명령)</i>",
                                common.SUPERVISOR_LOG,
                                parse_mode="HTML",
                            )
                            continue
                        common.reload_train_version()  # env_cfg.py 기준으로 TRAIN_VERSION 갱신
                        _state = common.load_state()
                        state_ckpt = _state.get("active_checkpoint") or ""
                        _active_run_dir = common.resolve_active_run_dir()
                        existing_checkpoint = common.resolve_active_checkpoint(_active_run_dir) or state_ckpt
                        # 실제 run 디렉토리의 버전과 비교 (state.json train_version은 /start 시도 시
                        # 미리 업데이트될 수 있어 신뢰 불가)
                        run_version = (common._read_run_train_version(_active_run_dir) if _active_run_dir else "") or ""
                        version_changed = run_version and run_version != common.TRAIN_VERSION
                        if existing_checkpoint and not version_changed:
                            # 동일 버전에서 기존 진행상황 있음 → 덮어쓰기 확인 필요
                            ckpt_name = os.path.basename(existing_checkpoint)
                            ckpt_iter = common.get_checkpoint_iter(existing_checkpoint)
                            pending_confirm = {"action": "fresh_start", "ckpt_iter": ckpt_iter, "ckpt_name": ckpt_name, "expires_at": time.time() + _CONFIRM_TIMEOUT_SEC}
                            common.send_text(
                                f"⚠️ <b>확인 필요 — FRESH START ({common.TRAIN_VERSION})</b>\n"
                                f"<i>현재 진행: iter {ckpt_iter:,} ({ckpt_name})</i>\n\n"
                                f"이 진행상황을 초기화하고 <b>iter 0부터 새로 시작</b>합니다.\n"
                                f"<i>계속하려면 Y를 입력하세요. (60초 내, 다른 입력은 취소)</i>",
                                common.SUPERVISOR_LOG,
                                parse_mode="HTML",
                            )
                        else:
                            # 버전 업그레이드이거나 checkpoint 없음 → 확인 없이 바로 시작
                            if version_changed:
                                common.send_text(
                                    f"🆕 <b>VERSION UPGRADE — {run_version} → {common.TRAIN_VERSION}</b>\n"
                                    f"<i>새 버전이므로 확인 없이 iter 0부터 시작합니다.</i>",
                                    common.SUPERVISOR_LOG,
                                    parse_mode="HTML",
                                )
                            result = common.launch_training(common.SUPERVISOR_LOG, fresh=True)
                            run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
                            common.send_text(
                                f"🚀 <b>TRAINING START (FRESH)</b>\n"
                                f"<i>run: {run_name}</i>\n"
                                f"<i>version: {common.TRAIN_VERSION}</i>\n"
                                f"<i>iter 0부터 시작합니다.</i>",
                                common.SUPERVISOR_LOG,
                                parse_mode="HTML",
                            )
                        continue

                    common.send_text(_build_command_ack(command, checkpoint_iters=checkpoint_iters, target_version=target_version), common.SUPERVISOR_LOG, parse_mode="HTML")
                    handle_command(command, checkpoint_iters=checkpoint_iters, target_version=target_version)
                shutdown_source = common.consume_supervisor_shutdown_request()
                if shutdown_source:
                    exit_reason = f"shutdown-request:{shutdown_source}"
                    common.write_log(f"Supervisor shutdown requested by {shutdown_source}", common.SUPERVISOR_LOG)
                    common.send_text(
                        f"👮 <b>SUPERVISOR STOPPED — {shutdown_source}</b>",
                        common.SUPERVISOR_LOG,
                        parse_mode="HTML",
                    )
                    break
            except Exception as err:
                common.update_state(last_error=str(err))
                common.write_log("Command loop error:\n" + common.capture_exception(), common.SUPERVISOR_LOG)
                common.send_text(common.format_supervisor_error_text(err), common.SUPERVISOR_LOG)
            time.sleep(max(1, args.poll))
    except KeyboardInterrupt as err:
        exit_reason = "keyboard-interrupt"
        exit_detail = str(err)
        common.write_log("Supervisor interrupted by keyboard signal.", common.SUPERVISOR_LOG)
        raise
    except BaseException as err:
        exit_reason = f"fatal:{type(err).__name__}"
        exit_detail = str(err)
        common.update_state(last_error=str(err))
        common.write_log("Supervisor fatal error:\n" + common.capture_exception(), common.SUPERVISOR_LOG)
        raise
    finally:
        common.write_log(
            f"Supervisor session exiting: session={session_id} reason={exit_reason}" + (f" detail={exit_detail}" if exit_detail else ""),
            common.SUPERVISOR_LOG,
        )
        common.mark_supervisor_exited(session_id, exit_reason, exit_detail)
        common.stop_heartbeat(common.SUPERVISOR_LOG)
        common.release_pid_lock(common.SUPERVISOR_PID_FILE)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SpotMicro training supervisor",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "examples:\n"
            "  .\\supervisor.cmd --listen\n"
            "  .\\supervisor.cmd --listen --foreground\n"
            "  .\\supervisor.cmd --status\n"
            "  .\\supervisor.cmd --start\n"
            "  .\\supervisor.cmd --report\n"
            "  .\\supervisor.cmd --v23-backfill --v23-max-runs 20\n"
            "  .\\supervisor.ps1 --status"
        ),
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--listen", dest="action", action="store_const", const="listen", help="Telegram supervisor loop 실행 (supervisor.cmd에서는 기본 background 상주 실행)")
    action_group.add_argument("--start", dest="action", action="store_const", const="start", help="iter 0부터 새로 훈련 시작 (checkpoint 무시)")
    action_group.add_argument("--resume", dest="action", action="store_const", const="resume", help="마지막 checkpoint에서 재개")
    action_group.add_argument("--stop", dest="action", action="store_const", const="stop", help="현재 훈련 중단")
    action_group.add_argument("--status", dest="action", action="store_const", const="status", help="현재 상태 출력")
    action_group.add_argument("--selfcheck", dest="action", action="store_const", const="selfcheck", help="run/checkpoint/context 해석 우선순위 점검")
    action_group.add_argument("--report", dest="action", action="store_const", const="report", help="리포트 ZIP 생성 또는 최신 ZIP 경로 출력")
    action_group.add_argument("--front", dest="action", action="store_const", const="front", help="front 영상 생성 또는 최신 경로 출력")
    action_group.add_argument("--rear", dest="action", action="store_const", const="rear", help="rear 영상 생성 또는 최신 경로 출력")
    action_group.add_argument("--top", dest="action", action="store_const", const="top", help="top 영상 생성 또는 최신 경로 출력")
    action_group.add_argument("--side", dest="action", action="store_const", const="side", help="side 영상 생성 또는 최신 경로 출력")
    action_group.add_argument("--shutdown", dest="action", action="store_const", const="shutdown", help="실행 중인 supervisor 종료 요청")
    action_group.add_argument("--heartbeat-start", dest="action", action="store_const", const="heartbeat-start", help="heartbeat 시작")
    action_group.add_argument("--heartbeat-stop", dest="action", action="store_const", const="heartbeat-stop", help="heartbeat 중단")
    action_group.add_argument("--heartbeat-status", dest="action", action="store_const", const="heartbeat-status", help="heartbeat 상태 출력")
    action_group.add_argument("--v23-backfill", dest="action", action="store_const", const="v23-backfill", help="V23 per-run workbook cache backfill 후 master/review refresh")
    parser.add_argument("--poll", type=int, default=common.SUPERVISOR_POLL_SECONDS, help="Telegram polling interval seconds")
    parser.add_argument("--iter-step", type=int, default=common.HEARTBEAT_ITER_STEP, help="heartbeat report iteration step")
    parser.add_argument("--heartbeat-poll", type=int, default=common.HEARTBEAT_POLL_SECONDS, help="heartbeat polling interval seconds")
    parser.add_argument("--v23-max-runs", type=int, default=20, help="--v23-backfill 시 최근 처리할 최대 run 수 (0 이하이면 전체)")
    parser.add_argument("--v23-overwrite", action="store_true", help="--v23-backfill 시 기존 per-run workbook도 다시 생성")
    return parser


def main() -> None:
    parser = _build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return
    args = parser.parse_args()
    if not args.action:
        parser.print_help()
        return
    if args.action == "listen":
        if os.environ.get(_BACKGROUND_LAUNCH_ENV_VAR) == "1":
            raise SystemExit(_run_supervisor_background(args))
        raise SystemExit(_run_supervisor_loop(args))
    try:
        raise SystemExit(_run_local_action(args.action, args))
    except SystemExit:
        raise
    except Exception as err:
        common.update_state(last_error=str(err))
        common.write_log("Local command error:\n" + common.capture_exception(), common.SUPERVISOR_LOG)
        _send_notice("LOCAL COMMAND FAILED", f"action: {args.action}\ndetail: {err}", icon="⚠️")
        raise


if __name__ == "__main__":
    main()
