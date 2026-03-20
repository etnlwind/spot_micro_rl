import argparse
import os
import re
import sys
import time

if __package__:
    from . import common
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import common


_collapse_cfg = common.TRAINING_CONFIG.get("collapse_restart", {})
_COLLAPSE_CHECK_ITER_MIN = _collapse_cfg.get("check_iter_min", 200)
_COLLAPSE_CHECK_ITER_MIN_WARN = _collapse_cfg.get("check_iter_warn_min", 100)
_COLLAPSE_CHECK_ITER_MAX = _collapse_cfg.get("check_iter_max", 300)
_COLLAPSE_CONTACT_THRESHOLD = _collapse_cfg.get("contact_threshold", 0.05)
_COLLAPSE_PROPULSION_THRESHOLD = _collapse_cfg.get("propulsion_threshold", 0.05)
_COLLAPSE_SWING_THRESHOLD = _collapse_cfg.get("swing_threshold", 0.95)
_COLLAPSE_CONSECUTIVE_REQUIRED = _collapse_cfg.get("consecutive_required", 3)
_COLLAPSE_LEGS = ("fl", "fr", "rl", "rr")


def _get_collapse_metrics(data: dict) -> tuple[str | None, float | None, float | None, float | None]:
    """tfevents data에서 4발 중 가장 collapse에 가까운 다리와 수치 반환.

    V27.1a: RL 하나만 보던 V25 방식에서 FL/FR/RL/RR 전체로 확장.
    contact < threshold AND propulsion < threshold AND swing > threshold 를
    모두 만족하는 다리가 있으면 해당 다리명과 수치를 반환한다.
    복수 다리가 해당하는 경우 contact가 가장 낮은 다리를 반환.
    """
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
    # contact가 가장 낮은 다리를 대표로 반환
    worst = min(collapsed_legs, key=lambda x: x[1])
    return worst[0], worst[1], worst[2], worst[3]


def _restore_last_milestone(run_dir: str, iter_step: int, report_kind: str | None = None) -> int:
    """report_kind 지정 시 해당 종류의 record만 포함."""
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
    """state.json의 active_checkpoint에서 iter 번호를 추출. 예: model_1800.pt → 1800."""
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
    common.release_pid_lock(common.HEARTBEAT_PID_FILE)  # stale lock 방어
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
    _training_stopped_by_heartbeat = False  # heartbeat가 stop_training 호출했는지 추적
    _perf_checked = False  # 현재 run에서 perf 체크 완료 여부
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
                    last_video_milestone = _restore_last_milestone(run_dir, args.video_iter_step, report_kind="video_report")
                    # 재개 시작 iter 이전 milestone은 이미 완료된 것으로 간주
                    resume_iter = _get_resume_checkpoint_iter()
                    if resume_iter > 0:
                        skip_up_to = (resume_iter // args.video_iter_step) * args.video_iter_step
                        last_video_milestone = max(last_video_milestone, skip_up_to)
                    elif last_video_milestone == 0:
                        # fresh start(resume_iter=0)에서 heartbeat가 뒤늦게 시작된 경우:
                        # 마지막 1개 milestone은 남겨서 리포트 생성 기회 제공
                        skip_up_to = (current_iter // args.video_iter_step) * args.video_iter_step
                        last_video_milestone = max(0, skip_up_to - args.video_iter_step)
                    collapse_consecutive_count = 0
                    collapse_restart_done = False
                    _perf_checked = False  # 새 run → perf 체크 리셋

                # ── Perf check: 새 run iter 20+ 시점에서 1회 속도 점검 ──
                if not _perf_checked and current_iter >= 20:
                    _perf_checked = True
                    perf_ct = data.get("Perf/collection time", [])
                    perf_fps = data.get("Perf/total_fps", [])
                    if perf_ct and len(perf_ct) >= 3:
                        avg_ct = sum(v for _, v in perf_ct[-5:]) / min(len(perf_ct), 5)
                        avg_fps = sum(v for _, v in perf_fps[-5:]) / min(len(perf_fps), 5) if perf_fps else 0
                        common.write_log(
                            f"[Perf] iter={current_iter} avg_collection_time={avg_ct:.1f}s avg_fps={avg_fps:.0f}",
                            common.HEARTBEAT_LOG,
                        )
                        if avg_ct > 30.0:
                            common.write_log(
                                f"[Perf] WARNING: collection_time {avg_ct:.1f}s >> 15s normal — abnormally slow!",
                                common.HEARTBEAT_LOG,
                            )
                            common.send_text(
                                f"🐢 <b>PERF WARNING</b> — run {run_name}\n"
                                f"<code>collection_time={avg_ct:.1f}s (normal ~15s)</code>\n"
                                f"<code>fps={avg_fps:.0f} (normal ~80k)</code>\n"
                                f"<i>iter {current_iter}: 훈련 속도 비정상 — 코드 또는 환경 점검 필요</i>",
                                common.HEARTBEAT_LOG,
                                parse_mode="HTML",
                            )

                # restart-on-collapse: iter 범위/임계값은 TRAINING_CONFIG["collapse_restart"] 기준
                if (not collapse_restart_done
                        and _COLLAPSE_CHECK_ITER_MIN_WARN <= current_iter < _COLLAPSE_CHECK_ITER_MIN):
                    collapsed_leg, leg_contact, leg_prop, leg_swing = _get_collapse_metrics(data)
                    if collapsed_leg is not None:
                        common.write_log(
                            f"[Collapse-WARN] iter={current_iter} leg={collapsed_leg}"
                            f" contact={leg_contact:.4f} prop={leg_prop:.4f} swing={leg_swing:.4f}"
                            f" (warning only — restart disabled until iter {_COLLAPSE_CHECK_ITER_MIN})",
                            common.HEARTBEAT_LOG,
                        )
                if (not collapse_restart_done
                        and _COLLAPSE_CHECK_ITER_MIN <= current_iter <= _COLLAPSE_CHECK_ITER_MAX):
                    collapsed_leg, leg_contact, leg_prop, leg_swing = _get_collapse_metrics(data)
                    if collapsed_leg is not None:
                        collapse_consecutive_count += 1
                        common.write_log(
                            f"[Collapse] iter={current_iter} leg={collapsed_leg}"
                            f" contact={leg_contact:.4f} prop={leg_prop:.4f} swing={leg_swing:.4f}"
                            f" consecutive={collapse_consecutive_count}/{_COLLAPSE_CONSECUTIVE_REQUIRED}",
                            common.HEARTBEAT_LOG,
                        )
                        if collapse_consecutive_count >= _COLLAPSE_CONSECUTIVE_REQUIRED:
                            collapse_restart_done = True
                            common.write_log(
                                f"[Collapse] RESTART triggered @ iter {current_iter} — {collapsed_leg} collapse confirmed",
                                common.HEARTBEAT_LOG,
                            )
                            common.stop_training(common.HEARTBEAT_LOG)
                            common.send_text(
                                f"🚨 <b>COLLAPSE RESTART — iter {current_iter:,}</b>\n"
                                f"<i>leg={collapsed_leg}: contact={leg_contact:.4f}, prop={leg_prop:.4f}, swing={leg_swing:.4f}</i>\n"
                                f"<i>single-limb collapse 확정 ({_COLLAPSE_CONSECUTIVE_REQUIRED}회 연속, iter {_COLLAPSE_CHECK_ITER_MIN}+) — 훈련 재시작</i>",
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
                    # 사용자에게 확인 요청 (훈련 중지 전)
                    milestone_str = ", ".join(f"{m:,}" for m in missed)
                    common.send_text(
                        f"📹 <b>리포트 생성 확인 — iter {milestone_str}</b>\n"
                        f"훈련을 일시 중지하고 영상 리포트를 생성합니다.\n"
                        f"<i>계속하려면 Y, 건너뛰려면 N을 입력하세요. (60초 내)</i>",
                        common.HEARTBEAT_LOG,
                        parse_mode="HTML",
                    )
                    common.write_log(f"[VideoReport] awaiting user confirmation for milestones: {missed}", common.HEARTBEAT_LOG)

                    # Telegram 응답 대기 (60초)
                    approved = False
                    deadline = time.time() + 60.0
                    while time.time() < deadline:
                        time.sleep(3)
                        try:
                            for upd in common.fetch_updates(timeout_sec=0, log_path=common.HEARTBEAT_LOG):
                                txt, cid, uid = common.extract_message(upd)
                                if not txt or not common.is_authorized_message(cid, uid):
                                    continue
                                reply = txt.strip().lower()
                                if reply.startswith("y"):
                                    approved = True
                                    break
                                elif reply.startswith("n"):
                                    break
                            if approved or (txt and txt.strip().lower().startswith("n")):
                                break
                        except Exception:
                            pass

                    if not approved:
                        # 거절 또는 타임아웃 — 마일스톤 건너뛰기
                        for m in missed:
                            last_video_milestone = m
                        common.send_text(
                            f"⛔ <b>REPORT SKIPPED</b> — iter {milestone_str}\n"
                            f"<i>리포트를 건너뜁니다. 다음: iter {last_video_milestone + args.video_iter_step:,}</i>",
                            common.HEARTBEAT_LOG,
                            parse_mode="HTML",
                        )
                        common.write_log(f"[VideoReport] user declined or timeout, skipping {missed}", common.HEARTBEAT_LOG)
                        time.sleep(args.poll)
                        continue

                    # 사용자 승인 — 리포트 생성
                    common.send_text(
                        f"✅ <b>REPORT CONFIRMED</b> — 영상 리포트를 생성합니다.",
                        common.HEARTBEAT_LOG,
                        parse_mode="HTML",
                    )
                    common.stop_training(common.HEARTBEAT_LOG)
                    _training_stopped_by_heartbeat = True
                    total_missed = len(missed)
                    for idx, milestone in enumerate(missed, start=1):
                        _run_video_report(run_dir, milestone, current_iter, total_missed, idx, args.video_iter_step)
                        last_video_milestone = milestone  # 각 milestone 완료 후 즉시 업데이트
                    # 다음 예정 milestone 안내
                    next_milestone = last_video_milestone + args.video_iter_step
                    catchup_summary = f"iter {', '.join(f'{m:,}' for m in missed)}" if total_missed > 1 else f"iter {missed[0]:,}"
                    common.launch_training(common.HEARTBEAT_LOG)
                    _training_stopped_by_heartbeat = False
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
                try:
                    common.write_log(f"Heartbeat loop error: {err}\n{common.capture_exception()}", common.HEARTBEAT_LOG)
                except Exception:
                    pass  # write_log 실패로 프로세스 죽이지 않음
            time.sleep(args.poll)
    finally:
        # heartbeat가 stop_training 호출 후 죽었으면 training 복구
        if _training_stopped_by_heartbeat:
            try:
                common.write_log("Heartbeat exiting while training stopped — attempting training recovery", common.HEARTBEAT_LOG)
                common.launch_training(common.HEARTBEAT_LOG)
            except Exception:
                pass  # 복구 실패해도 PID lock은 반드시 해제
        common.release_pid_lock(common.HEARTBEAT_PID_FILE)


if __name__ == "__main__":
    main()
