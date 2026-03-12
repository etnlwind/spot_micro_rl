import argparse
import collections
import os
import subprocess
import sys
import time


SCRIPT_PATH = os.path.abspath(__file__)
SCRIPT_DIR = os.path.dirname(SCRIPT_PATH)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
_BOOTSTRAP_ENV_VAR = "SPOT_MICRO_SUPERVISOR_BOOTSTRAPPED"


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


def _is_duplicate_command(chat_id: str | None, user_id: str | None, command: str) -> bool:
    now = time.monotonic()
    expired = [key for key, timestamp in _RECENT_COMMAND_TIMES.items() if now - timestamp > _RECENT_COMMAND_WINDOW_SEC]
    for key in expired:
        _RECENT_COMMAND_TIMES.pop(key, None)
    dedupe_key = (chat_id, user_id, command)
    previous = _RECENT_COMMAND_TIMES.get(dedupe_key)
    _RECENT_COMMAND_TIMES[dedupe_key] = now
    return previous is not None and now - previous <= _RECENT_COMMAND_WINDOW_SEC


def _send_notice(title: str, body: str, icon: str = "👮") -> None:
    common.send_text(
        f"{icon} <b>{title}</b>\n<i>{body}</i>",
        common.SUPERVISOR_LOG,
        parse_mode="HTML",
    )


def _build_command_ack(command: str) -> str:
    run_dir, checkpoint = common.resolve_context()
    run_name = os.path.basename(run_dir) if run_dir else "N/A"
    checkpoint_name = os.path.basename(checkpoint) if checkpoint else "N/A"
    training_running = common.is_training_running()
    if command == "start":
        return (
            "🚀 <b>START 요청 수신</b>\n"
            f"<i>run: {run_name}</i>\n"
            f"<i>checkpoint: {checkpoint_name}</i>\n"
            "<i>현재 supervisor context 기준으로 훈련 시작 또는 재개를 준비합니다.</i>"
        )
    if command == "stop":
        return "⏹️ <b>STOP 요청 수신</b>\n<i>현재 훈련 프로세스를 중단합니다.</i>"
    if command == "status":
        return "👮 <b>SUPERVISOR STATUS 요청 수신</b>\n<i>현재 상태를 조회합니다.</i>"
    if command == "help":
        return "❔ <b>HELP 요청 수신</b>\n<i>명령 목록을 전송합니다.</i>"
    if command == "shutdown":
        return "🛑 <b>SHUTDOWN 요청 수신</b>\n<i>supervisor 종료를 준비합니다.</i>"
    if command == "report":
        if training_running:
            return (
                "📦 <b>REPORT 요청 수신</b>\n"
                f"<i>run: {run_name}</i>\n"
                "<i>훈련 중이므로 최신 ZIP 리포트를 찾아 전송합니다.</i>"
            )
        return (
            "📦 <b>REPORT 요청 수신</b>\n"
            f"<i>run: {run_name}</i>\n"
            f"<i>checkpoint: {checkpoint_name}</i>\n"
            "<i>현재 checkpoint 기준으로 영상, 분석, ZIP 리포트를 생성합니다.</i>"
        )
    if command in {"front", "rear", "top", "side"}:
        if training_running:
            return (
                f"🎥 <b>{command.upper()} 요청 수신</b>\n"
                f"<i>run: {run_name}</i>\n"
                f"<i>훈련 중이므로 최신 {command} 영상을 찾아 전송합니다.</i>"
            )
        return (
            f"🎥 <b>{command.upper()} 요청 수신</b>\n"
            f"<i>run: {run_name}</i>\n"
            f"<i>checkpoint: {checkpoint_name}</i>\n"
            f"<i>현재 checkpoint 기준으로 {command} 영상을 생성합니다.</i>"
        )
    return f"🎛️ <b>{command.upper()} 요청 수신</b>"


def _handle_report_command(run_dir: str, checkpoint: str) -> None:
    if common.is_training_running():
        zip_path = common.find_latest_report_zip(run_dir)
        if not zip_path:
            common.send_text("⚠️ 현재 훈련 중이며 전송할 최신 ZIP 리포트가 없습니다.", common.SUPERVISOR_LOG)
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
            common.format_report_summary_html(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"]),
            common.SUPERVISOR_LOG,
            parse_mode="HTML",
        )
        common.send_document(
            report_data["zip_path"],
            f"📦 current report | {os.path.basename(run_dir)} | {os.path.basename(report_data['zip_path'])}",
            common.SUPERVISOR_LOG,
        )
        common.update_state(mode="stopped", last_command="report", last_error="")


def _handle_view_command(view_key: str, run_dir: str, checkpoint: str) -> None:
    if common.is_training_running():
        video_path = common.find_latest_video(view_key, run_dir)
        if not video_path:
            common.send_text(f"⚠️ 현재 훈련 중이며 최근 {view_key} 영상을 찾지 못했습니다.", common.SUPERVISOR_LOG)
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


def handle_command(command: str) -> None:
    run_dir, checkpoint = common.resolve_context()
    if command == "help":
        _send_notice("COMMAND MENU", common.help_text().replace("\n", "\n"), icon="❔")
        return
    if command == "status":
        common.send_text(common.format_status_html(), common.SUPERVISOR_LOG, parse_mode="HTML")
        return
    if command == "start":
        result = common.launch_training(common.SUPERVISOR_LOG)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "fresh"
        if result["mode"] == "already-running":
            _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon="🚀")
        else:
            _send_notice("TRAINING LAUNCH REQUESTED", f"run: {run_name}\ncheckpoint: {checkpoint_name}", icon="🚀")
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
    if not run_dir or not checkpoint:
        _send_notice("CONTEXT NOT FOUND", "active run/checkpoint를 찾지 못했습니다.", icon="⚠️")
        return
    if command == "report":
        _handle_report_command(run_dir, checkpoint)
        return
    if command in {"front", "rear", "top", "side"}:
        _handle_view_command(command, run_dir, checkpoint)
        return
    _send_notice("UNKNOWN COMMAND", f"{command}\n\n{common.help_text()}", icon="⚠️")


def _print_local(message: str) -> None:
    print(message, flush=True)


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
    if action == "start":
        common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
        result = common.launch_training(common.SUPERVISOR_LOG)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "fresh"
        if result["mode"] == "already-running":
            _send_notice("TRAINING ACTIVE", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nsource: cli", icon="🚀")
            _print_local(f"training already running\nrun: {run_name}\ncheckpoint: {checkpoint_name}")
        else:
            _send_notice("TRAINING LAUNCH REQUESTED", f"run: {run_name}\ncheckpoint: {checkpoint_name}\nsource: cli", icon="🚀")
            _print_local(f"training launch requested\nrun: {run_name}\ncheckpoint: {checkpoint_name}")
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
    common.clear_supervisor_shutdown_request()
    common.acquire_pid_lock(common.SUPERVISOR_PID_FILE, "supervisor", common.SUPERVISOR_LOG)
    common.prime_update_offset(common.SUPERVISOR_LOG)
    common.ensure_heartbeat_running(common.SUPERVISOR_LOG, iter_step=args.iter_step, poll=args.heartbeat_poll)
    common.update_state(last_command="startup", last_error="")
    common.send_text(
        "👮 <b>SUPERVISOR ACTIVE</b>\n"
        "<i>Supervisor is ready for commands.</i>\n\n"
        + common.help_text(),
        common.SUPERVISOR_LOG,
        parse_mode="HTML",
    )
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
                    command = common.normalize_command(text)
                    if command not in common.command_variants():
                        continue
                    if _is_duplicate_command(chat_id, user_id, command):
                        common.write_log(
                            f"Skipped duplicate Telegram command chat_id={chat_id} user_id={user_id} command={command}",
                            common.SUPERVISOR_LOG,
                        )
                        continue
                    common.send_text(_build_command_ack(command), common.SUPERVISOR_LOG, parse_mode="HTML")
                    handle_command(command)
                shutdown_source = common.consume_supervisor_shutdown_request()
                if shutdown_source:
                    common.write_log(f"Supervisor shutdown requested by {shutdown_source}", common.SUPERVISOR_LOG)
                    common.send_text(
                        "👮 <b>SUPERVISOR STOPPED</b>\n"
                        f"<i>Supervisor is going offline.</i>\n"
                        f"source: {shutdown_source}",
                        common.SUPERVISOR_LOG,
                        parse_mode="HTML",
                    )
                    break
            except Exception as err:
                common.update_state(last_error=str(err))
                common.write_log("Command loop error:\n" + common.capture_exception(), common.SUPERVISOR_LOG)
                common.send_text(common.format_supervisor_error_text(err), common.SUPERVISOR_LOG)
            time.sleep(max(1, args.poll))
    finally:
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
            "  .\\supervisor.cmd --status\n"
            "  .\\supervisor.cmd --start\n"
            "  .\\supervisor.cmd --report\n"
            "  .\\supervisor.cmd --v23-backfill --v23-max-runs 20\n"
            "  .\\supervisor.ps1 --status"
        ),
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--listen", dest="action", action="store_const", const="listen", help="Telegram supervisor loop 실행")
    action_group.add_argument("--start", dest="action", action="store_const", const="start", help="훈련 시작 또는 latest checkpoint 재개")
    action_group.add_argument("--stop", dest="action", action="store_const", const="stop", help="현재 훈련 중단")
    action_group.add_argument("--status", dest="action", action="store_const", const="status", help="현재 상태 출력")
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
