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


# V25: restart-on-collapse 설정
_COLLAPSE_CHECK_ITER_MIN = 100   # iter 100 이전은 warming-up — 감지 안 함
_COLLAPSE_CHECK_ITER_MAX = 300   # iter 300 이후는 이미 늦음 — 재시작 대신 알림만
_COLLAPSE_CONTACT_THRESHOLD = 0.05
_COLLAPSE_SWING_THRESHOLD = 0.95
_COLLAPSE_CONSECUTIVE_REQUIRED = 3  # 연속 N회 감지 시 실제 collapse로 판정


def _get_collapse_metrics(data: dict) -> tuple[float | None, float | None]:
    """tfevents data에서 최신 contact_ratio_rl, swing_time_rl 반환."""
    def _latest(tag):
        vals = data.get(f"Episode_Reward/{tag}", [])
        return float(vals[-1][1]) if vals else None
    return _latest("contact_ratio_rl"), _latest("swing_time_rl")


def _restore_last_milestone(run_dir: str, iter_step: int) -> int:
    records = common.load_report_history(run_dir)
    last_milestone = 0
    for record in records:
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


def _restore_last_video_milestone(run_dir: str, video_iter_step: int) -> int:
    records = common.load_report_history(run_dir)
    last_milestone = 0
    for record in records:
        if record.get("report_kind") != "video_report":
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
            milestone = cycle_num * int(video_iter_step)
        last_milestone = max(last_milestone, milestone)
    return last_milestone


def _get_resume_checkpoint_iter() -> int:
    """state.json의 active_checkpoint에서 iter 번호를 추출. 예: model_1800.pt → 1800."""
    import re
    state = common.load_state()
    checkpoint = state.get("active_checkpoint") or ""
    m = re.search(r"model_(\d+)\.pt", os.path.basename(checkpoint))
    return int(m.group(1)) if m else 0


def _collect_missed_milestones(last_video_milestone: int, current_iter: int, video_iter_step: int) -> list[int]:
    """last_video_milestone 이후 current_iter 이하의 누락된 milestone 목록을 순서대로 반환."""
    milestones = []
    candidate = last_video_milestone + video_iter_step
    while candidate <= current_iter:
        milestones.append(candidate)
        candidate += video_iter_step
    return milestones


def _run_video_report(run_dir: str, milestone: int, current_iter: int, total_missed: int, missed_index: int, video_iter_step: int) -> None:
    """milestone 기준 checkpoint로 영상+리포트 생성 후 전송. 훈련은 호출 전 이미 정지된 상태."""
    is_catchup = current_iter > milestone
    catchup_label = ""
    if is_catchup and total_missed == 1:
        catchup_label = " (누락 보완)"
    elif is_catchup and total_missed > 1:
        catchup_label = f" (누락 보완 {missed_index}/{total_missed})"

    checkpoint = common.get_checkpoint_by_iter(run_dir, milestone)
    if not checkpoint:
        common.write_log(f"[VideoReport] model_{milestone}.pt not found, skipping iter {milestone}", common.HEARTBEAT_LOG)
        common.send_text(
            f"⚠️ <b>VIDEO REPORT — iter {milestone:,}{catchup_label} (파일 없음)</b>\n"
            f"<i>model_{milestone}.pt 파일이 없어 건너뜁니다.</i>",
            common.HEARTBEAT_LOG,
            parse_mode="HTML",
        )
        return

    common.write_log(f"[VideoReport] iter {milestone} (current={current_iter}): recording with model_{milestone}.pt", common.HEARTBEAT_LOG)

    notice_lines = [f"🎬 <b>AUTO VIDEO REPORT — iter {milestone:,}{catchup_label}</b>"]
    if is_catchup:
        notice_lines.append(f"<i>현재 훈련은 iter {current_iter:,} 진행 중이나 iter {milestone:,} 리포트가 누락되어 소급 생성합니다.</i>")
    else:
        notice_lines.append("<i>훈련을 일시 정지하고 영상 녹화를 시작합니다.</i>")
    notice_lines.append(f"<i>checkpoint: model_{milestone}.pt</i>")
    common.send_text("\n".join(notice_lines), common.HEARTBEAT_LOG, parse_mode="HTML")

    try:
        report_data = common.stop_and_report(run_dir, checkpoint, common.HEARTBEAT_LOG, force=True)
        common.send_text(
            common.format_report_summary_html(run_dir, checkpoint, report_data["analysis_text"], report_data["kpi_snapshot"], metrics_run_dir=report_data.get("metrics_run_dir")),
            common.HEARTBEAT_LOG,
            parse_mode="HTML",
        )
        common.send_document(
            report_data["zip_path"],
            f"📦 auto report | {os.path.basename(run_dir)} | iter {milestone:,}{catchup_label}",
            common.HEARTBEAT_LOG,
        )
        data = common.read_tfevents(run_dir)
        run_name = os.path.basename(run_dir)
        record = common.build_report_record(data, run_name, cycle_num=(milestone // video_iter_step), report_kind="video_report")
        if record:
            record["milestone"] = milestone
            record["current_iter"] = current_iter
            common.append_report_record(run_dir, record)
        common.write_log(f"[VideoReport] iter {milestone}: report complete", common.HEARTBEAT_LOG)
    except Exception as err:
        common.write_log(f"[VideoReport] iter {milestone}: report failed: {err}\n{common.capture_exception()}", common.HEARTBEAT_LOG)
        common.send_text(
            f"⚠️ <b>VIDEO REPORT — iter {milestone:,} (실패)</b>\n<i>{err}</i>",
            common.HEARTBEAT_LOG,
            parse_mode="HTML",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Heartbeat with periodic video report")
    parser.add_argument("--iter_step", type=int, default=common.HEARTBEAT_ITER_STEP, help="send text report every N iterations")
    parser.add_argument("--video_iter_step", type=int, default=common.VIDEO_REPORT_ITER_STEP, help="stop training and send video report every N iterations")
    parser.add_argument("--poll", type=int, default=common.HEARTBEAT_POLL_SECONDS, help="poll interval seconds")
    args = parser.parse_args()
    common.acquire_pid_lock(common.HEARTBEAT_PID_FILE, "heartbeat", common.HEARTBEAT_LOG)
    common.write_log(
        f"Heartbeat started | iter_step={args.iter_step} | video_iter_step={args.video_iter_step} | poll={args.poll}s",
        common.HEARTBEAT_LOG,
    )
    last_sent_milestone = 0
    last_video_milestone = 0
    last_run_name = ""
    collapse_consecutive_count = 0
    collapse_restart_done = False  # 현재 run에서 이미 restart했으면 중복 방지
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
                run_name = os.path.basename(run_dir)
                if run_name != last_run_name:
                    last_run_name = run_name
                    last_sent_milestone = _restore_last_milestone(run_dir, args.iter_step)
                    last_video_milestone = _restore_last_video_milestone(run_dir, args.video_iter_step)
                    # 재개 시작 iter 이전 milestone은 이미 완료된 것으로 간주
                    resume_iter = _get_resume_checkpoint_iter()
                    if resume_iter > 0:
                        skip_up_to = (resume_iter // args.video_iter_step) * args.video_iter_step
                        last_video_milestone = max(last_video_milestone, skip_up_to)
                    collapse_consecutive_count = 0
                    collapse_restart_done = False

                # V25: restart-on-collapse (iter 100~300 구간)
                if (not collapse_restart_done
                        and _COLLAPSE_CHECK_ITER_MIN <= current_iter <= _COLLAPSE_CHECK_ITER_MAX):
                    rl_contact, rl_swing = _get_collapse_metrics(data)
                    if (rl_contact is not None and rl_swing is not None
                            and rl_contact < _COLLAPSE_CONTACT_THRESHOLD
                            and rl_swing > _COLLAPSE_SWING_THRESHOLD):
                        collapse_consecutive_count += 1
                        common.write_log(
                            f"[Collapse] iter={current_iter} contact_rl={rl_contact:.4f} swing_rl={rl_swing:.4f}"
                            f" consecutive={collapse_consecutive_count}/{_COLLAPSE_CONSECUTIVE_REQUIRED}",
                            common.HEARTBEAT_LOG,
                        )
                        if collapse_consecutive_count >= _COLLAPSE_CONSECUTIVE_REQUIRED:
                            collapse_restart_done = True
                            common.write_log(
                                f"[Collapse] RESTART triggered @ iter {current_iter} — rear-left collapse confirmed",
                                common.HEARTBEAT_LOG,
                            )
                            common.stop_training(common.HEARTBEAT_LOG)
                            common.send_text(
                                f"🚨 <b>COLLAPSE RESTART — iter {current_iter:,}</b>\n"
                                f"<i>contact_ratio_rl={rl_contact:.4f}, swing_time_rl={rl_swing:.4f}</i>\n"
                                f"<i>rear-left collapse 확정 ({_COLLAPSE_CONSECUTIVE_REQUIRED}회 연속) — 훈련 재시작</i>",
                                common.HEARTBEAT_LOG,
                                parse_mode="HTML",
                            )
                            common.launch_training(common.HEARTBEAT_LOG, fresh=True)
                            time.sleep(args.poll)
                            continue
                    else:
                        collapse_consecutive_count = 0

                # 누락된 video milestone 목록 수집 (복수 대응)
                missed = _collect_missed_milestones(last_video_milestone, current_iter, args.video_iter_step)
                if missed:
                    # 훈련 정지는 한 번만
                    common.stop_training(common.HEARTBEAT_LOG)
                    total_missed = len(missed)
                    for idx, milestone in enumerate(missed, start=1):
                        _run_video_report(run_dir, milestone, current_iter, total_missed, idx, args.video_iter_step)
                    last_video_milestone = missed[-1]
                    # 다음 예정 milestone 안내
                    next_milestone = last_video_milestone + args.video_iter_step
                    catchup_summary = f"iter {', '.join(f'{m:,}' for m in missed)}" if total_missed > 1 else f"iter {missed[0]:,}"
                    common.launch_training(common.HEARTBEAT_LOG)
                    common.write_log(f"[VideoReport] all done ({catchup_summary}), training restarted", common.HEARTBEAT_LOG)
                    common.send_text(
                        f"🚀 <b>TRAINING RESUME — {'누락 보완 완료' if current_iter > missed[0] else '영상 리포트 완료'}: {catchup_summary}</b>\n"
                        f"<i>다음 리포트: iter {next_milestone:,}</i>",
                        common.HEARTBEAT_LOG,
                        parse_mode="HTML",
                    )
                    # text milestone도 현재 기준으로 앞당김 (중복 전송 방지)
                    text_milestone = (current_iter // args.iter_step) * args.iter_step
                    last_sent_milestone = max(last_sent_milestone, text_milestone)
                    time.sleep(args.poll)
                    continue

                # 텍스트 heartbeat (video milestone이 없을 때)
                milestone = (current_iter // args.iter_step) * args.iter_step
                if milestone <= 0 or milestone <= last_sent_milestone:
                    time.sleep(args.poll)
                    continue
                report_text = common.format_report(data, run_name, cycle_num=(milestone // args.iter_step))
                record = common.build_report_record(data, run_name, cycle_num=(milestone // args.iter_step), report_kind="heartbeat")
                common.append_report_record(run_dir, record)
                common.send_text(report_text, common.HEARTBEAT_LOG, parse_mode="HTML")
                last_sent_milestone = milestone
            except Exception as err:
                common.write_log(f"Heartbeat loop error: {err}\n{common.capture_exception()}", common.HEARTBEAT_LOG)
            time.sleep(args.poll)
    finally:
        common.release_pid_lock(common.HEARTBEAT_PID_FILE)


if __name__ == "__main__":
    main()
