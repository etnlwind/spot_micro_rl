import argparse
import os
import sys
import time

if __package__:
    from . import common
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import common


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
        report_data = common.stop_and_report(run_dir, checkpoint, common.SUPERVISOR_LOG)
        common.send_text(
            common.format_report_summary(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"]),
            common.SUPERVISOR_LOG,
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
            f"📹 latest {view_key} | {os.path.basename(run_dir)} | iter {common.legacy_supervisor.get_checkpoint_iter(checkpoint) if checkpoint else 0:,}",
            common.SUPERVISOR_LOG,
        )
        return

    with common.busy_lock(view_key):
        common.update_state(mode="rendering", last_command=view_key, last_error="")
        videos = common.ensure_current_videos(run_dir, checkpoint, common.SUPERVISOR_LOG)
        video_path = videos.get(view_key)
        if not video_path:
            raise RuntimeError(f"{view_key} view was not generated.")
        common.send_video(
            video_path,
            f"📹 current {view_key} | {os.path.basename(run_dir)} | iter {common.legacy_supervisor.get_checkpoint_iter(checkpoint):,}",
            common.SUPERVISOR_LOG,
        )
        common.update_state(mode="stopped", last_command=view_key, last_error="")


def handle_command(command: str) -> None:
    run_dir, checkpoint = common.resolve_context()

    if command == "help":
        common.send_text(common.help_text(), common.SUPERVISOR_LOG)
        return

    if command == "status":
        common.send_text(common.build_status_text(), common.SUPERVISOR_LOG)
        return

    if command == "start":
        result = common.launch_training(common.SUPERVISOR_LOG)
        run_name = os.path.basename(result["run_dir"]) if result["run_dir"] else "N/A"
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "fresh"
        if result["mode"] == "already-running":
            common.send_text(
                f"▶️ 이미 훈련 중입니다.\n- run: {run_name}\n- checkpoint: {checkpoint_name}",
                common.SUPERVISOR_LOG,
            )
        else:
            common.send_text(
                f"▶️ 훈련 시작 요청 완료\n- run: {run_name}\n- checkpoint: {checkpoint_name}",
                common.SUPERVISOR_LOG,
            )
        return

    if command == "stop":
        result = common.stop_training(common.SUPERVISOR_LOG)
        checkpoint_name = os.path.basename(result["checkpoint"]) if result["checkpoint"] else "N/A"
        common.send_text(
            f"⏹️ 훈련 중단 완료\n- killed: {len(result['killed'])}\n- checkpoint: {checkpoint_name}",
            common.SUPERVISOR_LOG,
        )
        return

    if not run_dir or not checkpoint:
        common.send_text("⚠️ active run/checkpoint를 찾지 못했습니다.", common.SUPERVISOR_LOG)
        return

    if command == "report":
        _handle_report_command(run_dir, checkpoint)
        return

    if command in {"front", "rear", "top", "side"}:
        _handle_view_command(command, run_dir, checkpoint)
        return

    common.send_text(f"⚠️ 알 수 없는 명령: {command}\n\n{common.help_text()}", common.SUPERVISOR_LOG)


def main() -> None:
    parser = argparse.ArgumentParser(description="V2 training supervisor")
    parser.add_argument("--poll", type=int, default=common.SUPERVISOR_POLL_SECONDS, help="Telegram polling interval seconds")
    args = parser.parse_args()

    common.acquire_pid_lock(common.SUPERVISOR_PID_FILE, "v2 supervisor", common.SUPERVISOR_LOG)
    common.update_state(last_command="startup", last_error="")
    common.send_text("🤖 V2 supervisor 시작\n" + common.help_text(), common.SUPERVISOR_LOG)

    try:
        while True:
            try:
                for update in common.fetch_updates(timeout_sec=0):
                    text, chat_id = common.extract_message(update)
                    if not text or chat_id != str(common.TELEGRAM_CHAT_ID):
                        continue
                    command = common.normalize_command(text)
                    if command not in common.command_variants():
                        continue
                    handle_command(command)
            except Exception as err:
                common.update_state(last_error=str(err))
                common.write_log("Command loop error:\n" + common.capture_exception(), common.SUPERVISOR_LOG)
                common.send_text(f"⚠️ V2 supervisor error: {err}", common.SUPERVISOR_LOG)
            time.sleep(max(1, args.poll))
    finally:
        common.release_pid_lock(common.SUPERVISOR_PID_FILE)


if __name__ == "__main__":
    main()
