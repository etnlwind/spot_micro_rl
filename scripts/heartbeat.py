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


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only heartbeat")
    parser.add_argument("--iter_step", type=int, default=common.HEARTBEAT_ITER_STEP, help="send report every N iterations")
    parser.add_argument("--poll", type=int, default=common.HEARTBEAT_POLL_SECONDS, help="poll interval seconds")
    args = parser.parse_args()
    common.acquire_pid_lock(common.HEARTBEAT_PID_FILE, "heartbeat", common.HEARTBEAT_LOG)
    common.write_log(f"Heartbeat started | iter_step={args.iter_step} | poll={args.poll}s", common.HEARTBEAT_LOG)
    last_sent_milestone = 0
    last_run_name = ""
    try:
        while True:
            try:
                run_dir = common.resolve_active_run_dir()
                if not run_dir or not os.path.isdir(run_dir):
                    time.sleep(args.poll)
                    continue
                data = common.read_tfevents(run_dir)
                if not data:
                    time.sleep(args.poll)
                    continue
                reward_vals = data.get("Train/mean_reward", [])
                if not reward_vals:
                    time.sleep(args.poll)
                    continue
                current_iter = int(reward_vals[-1][0])
                milestone = (current_iter // args.iter_step) * args.iter_step
                run_name = os.path.basename(run_dir)
                if run_name != last_run_name:
                    last_run_name = run_name
                    last_sent_milestone = 0
                if milestone <= 0 or milestone <= last_sent_milestone:
                    time.sleep(args.poll)
                    continue
                report_text = common.format_report(data, run_name, cycle_num=(milestone // args.iter_step))
                record = common.build_report_record(data, run_name, cycle_num=(milestone // args.iter_step), report_kind="heartbeat")
                common.append_report_record(run_dir, record)
                common.send_text(report_text, common.HEARTBEAT_LOG)
                last_sent_milestone = milestone
            except Exception as err:
                common.write_log(f"Heartbeat loop error: {err}\n{common.capture_exception()}", common.HEARTBEAT_LOG)
            time.sleep(args.poll)
    finally:
        common.release_pid_lock(common.HEARTBEAT_PID_FILE)


if __name__ == "__main__":
    main()
