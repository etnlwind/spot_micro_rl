"""isaac_ops/cli_send.py — CLI for IsaacOps: execute commands or send messages."""

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import common  # noqa: E402

LOG = os.path.join(common._OPS_LOG_DIR, "listener.log")

# Known commands that should be executed directly (not just sent as text)
_COMMANDS = common.command_variants()


def _normalize(text: str) -> str:
    return common.normalize_command(text.split()[0]) if text.strip() else ""


def _exec_hb(arg_text: str) -> None:
    run_dir = common.resolve_active_run_dir()
    if not run_dir:
        print("[WARN] active run not found")
        return
    data = common.read_tfevents(run_dir)
    if not data or not data.get("Train/mean_reward"):
        print("[WARN] no tfevents data")
        return
    run_name = os.path.basename(run_dir)
    report = common.format_report(data, run_name, cycle_num=0)
    common.send_text(report, LOG, parse_mode="HTML")
    print("[OK] hb report sent")


def _exec_status() -> None:
    common.send_text(common.format_status_html(), LOG, parse_mode="HTML")
    print("[OK] status sent")


def _exec_selfcheck() -> None:
    common.send_text(f"<pre>{common.build_context_resolution_text()}</pre>", LOG, parse_mode="HTML")
    print("[OK] selfcheck sent")


def _exec_help() -> None:
    common.send_text(
        f"❔ <b>IsaacOps — COMMAND MENU</b>  <code>[{common.TRAIN_VERSION}]</code>\n<i>{common.help_text()}</i>",
        LOG, parse_mode="HTML",
    )
    print("[OK] help sent")


def _exec_stop() -> None:
    result = common.stop_training(LOG)
    checkpoint_name = os.path.basename(result["checkpoint"]) if result.get("checkpoint") else "N/A"
    run_version = common.get_run_version(result.get("run_dir", ""))
    common.send_text(
        f"⏹️ <b>IsaacOps — TRAINING STOPPED</b>  <code>[{run_version}]</code>\n"
        f"<i>killed: {len(result['killed'])}\ncheckpoint: {checkpoint_name}</i>",
        LOG, parse_mode="HTML",
    )
    print(f"[OK] stopped, killed {len(result['killed'])} procs, checkpoint: {checkpoint_name}")


def _exec_resume() -> None:
    common.reload_train_version()
    result = common.launch_training(LOG, fresh=False)
    run_name = os.path.basename(result["run_dir"]) if result.get("run_dir") else "N/A"
    checkpoint_name = os.path.basename(result["checkpoint"]) if result.get("checkpoint") else "N/A (fresh)"
    run_version = common.get_run_version(result.get("run_dir", ""))
    common.send_text(
        f"▶️ <b>IsaacOps — TRAINING RESUME</b>  <code>[{run_version}]</code>\n"
        f"<i>run: {run_name}\ncheckpoint: {checkpoint_name}</i>",
        LOG, parse_mode="HTML",
    )
    print(f"[OK] resume: {run_name} / {checkpoint_name}")


def _exec_start(headless: bool = True) -> None:
    common.reload_train_version()
    mode_str = "headless" if headless else "GUI"
    result = common.launch_training(LOG, fresh=True, headless=headless)
    run_name = os.path.basename(result["run_dir"]) if result.get("run_dir") else "N/A"
    common.send_text(
        f"<b>TRAINING START [{mode_str}]</b>  <code>[{common.TRAIN_VERSION}]</code>\n"
        f"<i>run: {run_name}</i>",
        LOG, parse_mode="HTML",
    )
    print(f"[OK] started: {run_name} [{mode_str}]")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: cli.cmd <command|message>")
        print()
        print("Commands (executed directly):")
        print("  cli status    — training status")
        print("  cli hb        — heartbeat report")
        print("  cli stop      — stop training")
        print("  cli resume    — resume training")
        print("  cli start     — fresh start (headless)")
        print("  cli start gui — fresh start (GUI mode)")
        print("  cli selfcheck — context resolution")
        print("  cli help      — command menu")
        print()
        print("Message (sent to Telegram):")
        print("  cli 훈련 500 iter 도달")
        return 1

    text = " ".join(sys.argv[1:])
    cmd = _normalize(text)

    # CLI-only commands (no Telegram equivalent)
    _CLI_ONLY = {"selfcheck", "hb"}

    try:
        if cmd in _CLI_ONLY:
            common.log_event("CMD", "CLI_EXEC", cmd)
            if cmd == "selfcheck":
                _exec_selfcheck()
            elif cmd == "hb":
                _exec_hb(text)
        elif cmd in _COMMANDS:
            # Telegram 명령어는 전부 리스너가 처리 (단일 실행 루트)
            common.log_event("CMD", "CLI_SEND", text[:50])
            common.send_text(text, LOG, parse_mode=None)
            print(f"[OK] sent to listener: {text}")
        else:
            # Plain message
            common.log_event("CMD", "CLI_SEND", text[:50])
            common.send_text(text, LOG, parse_mode=None)
            print(f"[OK] sent: {text}")
    except Exception as e:
        print(f"[ERR] {e}")
        common.log_event("ERROR", "CLI_FAILED", f"{cmd}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
