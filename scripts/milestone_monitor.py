"""Milestone Checkpoint Monitor — V20 Ramp1 전후 관측 포인트 자동 점검

특정 iteration에서 상세 스냅샷을 캡처하고 텔레그램으로 전송합니다.
기존 heartbeat (100iter 주기)와 독립적으로 동작.

Milestones: 500, 1000, 1400 (pre-ramp1), 1550 (ramp1 진입 직후), 1700 (ramp1 중반)
핵심: ramp1(iter 1500) 전후 비교

Usage:
    conda activate env_isaaclab
    python scripts/milestone_monitor.py [--poll 30] [--run_dir <path>]
"""

import argparse
import datetime
import io
import json
import os
import sys
import time
import traceback
import urllib.parse
import urllib.request

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def _load_env(path):
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_env = _load_env(ENV_FILE)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or _env.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _env.get("TELEGRAM_CHAT_ID", "")
_log_subdir = _env.get("LOG_SUBDIR", "spot_micro_flat")
LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", _log_subdir)
SNAPSHOT_DIR = os.path.join(PROJECT_ROOT, "logs", "milestone_snapshots")

# V20 커리큘럼 경계
RAMP1_START = 1500
RAMP1_END = 3000
RAMP2_START = 5500
RAMP2_END = 8000

# 관측 마일스톤 정의
MILESTONES = {
    500:  {"label": "Phase1 Mid-Check", "desc": "STAND 중간 점검 — baseline 안정도 확인"},
    1000: {"label": "Phase1 Late-Check", "desc": "STAND 후반 점검 — ramp1 진입 준비도 확인"},
    1400: {"label": "Pre-Ramp1 Snapshot", "desc": "🔴 Ramp1 직전 (100 iter 남음) — Phase1 baseline 최종 캡처"},
    1550: {"label": "Ramp1 Entry Check", "desc": "🟡 Ramp1 진입 직후 (50 iter 경과) — critic shock 여부 확인"},
    1700: {"label": "Ramp1 Mid-Check", "desc": "🟢 Ramp1 중반 (200 iter 경과) — 보간 안정성 확인"},
}

# 핵심 메트릭 태그
CORE_TAGS = [
    "Train/mean_reward",
    "Train/mean_episode_length",
    "Loss/value_loss",
    "Loss/surrogate",
    "Policy/mean_noise_std",
]

REWARD_TAGS = [
    "Episode_Reward/standing_height",
    "Episode_Reward/flat_orientation_l2",
    "Episode_Reward/forward_velocity",
    "Episode_Reward/trot_gait",
    "Episode_Reward/diagonal_coupling",
    "Episode_Reward/foot_clearance",
    "Episode_Reward/leg_lift",
    "Episode_Reward/rear_joint_velocity",
    "Episode_Reward/rear_swing",
    "Episode_Reward/rear_forward_stride",
    "Episode_Reward/stride_length",
    "Episode_Reward/gait_cycle_period",
    "Episode_Reward/shoulder_neutral",
    "Episode_Reward/shoulder_symmetry",
    "Episode_Reward/joint_vel_l2",
    "Episode_Reward/action_rate_l2",
    "Episode_Reward/dof_acc_l2",
    "Episode_Reward/ang_vel_xy_l2",
    "Episode_Reward/lin_vel_z_l2",
    "Episode_Reward/same_side_penalty",
]

TERMINATION_TAGS = [
    "Episode_Termination/time_out",
    "Episode_Termination/bad_orientation",
]


def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] No credentials — skip")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = []
    while len(text) > 4000:
        split_at = text[:4000].rfind("\n")
        if split_at < 100:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)
    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"[TG ERROR] {e}")
        time.sleep(0.3)


def find_latest_run():
    if not os.path.isdir(LOG_BASE):
        return None
    runs = sorted([d for d in os.listdir(LOG_BASE)
                   if os.path.isdir(os.path.join(LOG_BASE, d)) and not d.endswith("_current")])
    return os.path.join(LOG_BASE, runs[-1]) if runs else None


def read_tfevents(run_dir):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    event_files = [f for f in os.listdir(run_dir) if f.startswith("events.out.tfevents")]
    if not event_files:
        return None
    ea = EventAccumulator(run_dir)
    ea.Reload()
    data = {}
    for tag in ea.Tags().get("scalars", []):
        events = ea.Scalars(tag)
        data[tag] = [(e.step, e.value) for e in events]
    return data


def get_value_at_iter(data, tag, target_iter):
    """특정 iter에 가장 가까운 값을 반환."""
    if tag not in data or not data[tag]:
        return None
    vals = data[tag]
    best = min(vals, key=lambda x: abs(x[0] - target_iter))
    return best[1]


def get_latest_value(data, tag):
    if tag not in data or not data[tag]:
        return None
    return data[tag][-1][1]


def get_recent_trend(data, tag, window=50):
    """최근 window의 평균 vs 그 이전 window의 평균 변화율."""
    if tag not in data or len(data[tag]) < 20:
        return 0.0, "➡️"
    vals = data[tag]
    if len(vals) < window * 2:
        mid = len(vals) // 2
        first = [v for _, v in vals[:mid]]
        second = [v for _, v in vals[mid:]]
    else:
        first = [v for _, v in vals[-(window*2):-window]]
        second = [v for _, v in vals[-window:]]
    avg1 = sum(first) / len(first) if first else 0
    avg2 = sum(second) / len(second) if second else 0
    pct = ((avg2 - avg1) / abs(avg1) * 100) if avg1 != 0 else 0
    if pct > 10:
        icon = "🔺"
    elif pct > 3:
        icon = "📈"
    elif pct < -10:
        icon = "🔻"
    elif pct < -3:
        icon = "📉"
    else:
        icon = "➡️"
    return pct, icon


def capture_snapshot(data, current_iter):
    """현재 상태의 전체 스냅샷을 dict로 캡처."""
    snap = {"iter": current_iter, "timestamp": datetime.datetime.now().isoformat()}
    for tag in CORE_TAGS + REWARD_TAGS + TERMINATION_TAGS:
        val = get_latest_value(data, tag)
        if val is not None:
            snap[tag] = val
    return snap


def save_snapshot(snap, milestone_iter, run_name):
    """스냅샷을 JSON으로 저장."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    fname = f"milestone_{milestone_iter}_{run_name}.json"
    fpath = os.path.join(SNAPSHOT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, ensure_ascii=False)
    return fpath


def load_snapshot(milestone_iter, run_name):
    """이전에 저장한 스냅샷을 로드."""
    fname = f"milestone_{milestone_iter}_{run_name}.json"
    fpath = os.path.join(SNAPSHOT_DIR, fname)
    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def format_milestone_report(data, milestone_iter, run_name):
    """마일스톤 리포트 포맷."""
    ms = MILESTONES[milestone_iter]
    now = datetime.datetime.now().strftime("%H:%M:%S")
    current_iter = int(data.get("Train/mean_reward", [(0, 0)])[-1][0])

    # 현재 값
    reward = get_latest_value(data, "Train/mean_reward") or 0
    ep_len = get_latest_value(data, "Train/mean_episode_length") or 0
    vf_loss = get_latest_value(data, "Loss/value_loss") or 0
    surr_loss = get_latest_value(data, "Loss/surrogate") or 0
    noise = get_latest_value(data, "Policy/mean_noise_std") or 0
    timeout = get_latest_value(data, "Episode_Termination/time_out") or 0
    bad_orient = get_latest_value(data, "Episode_Termination/bad_orientation") or 0
    total_term = timeout + bad_orient
    timeout_pct = (timeout / total_term * 100) if total_term > 0 else 0
    survival_pct = (ep_len / 500) * 100  # 10s × 50Hz

    # 커리큘럼 위치
    if current_iter < RAMP1_START:
        phase_str = f"Phase 1 STAND (ramp1까지 {RAMP1_START - current_iter} iter)"
    elif current_iter < RAMP1_END:
        progress = (current_iter - RAMP1_START) / (RAMP1_END - RAMP1_START) * 100
        phase_str = f"Ramp 1 STAND→WALK ({progress:.0f}%)"
    elif current_iter < RAMP2_START:
        phase_str = f"Phase 2 WALK (ramp2까지 {RAMP2_START - current_iter} iter)"
    elif current_iter < RAMP2_END:
        progress = (current_iter - RAMP2_START) / (RAMP2_END - RAMP2_START) * 100
        phase_str = f"Ramp 2 WALK→TROT ({progress:.0f}%)"
    else:
        phase_str = "Phase 3 TROT"

    lines = []
    lines.append(f"📍 <b>Milestone: {ms['label']}</b>")
    lines.append(f"⏰ {now} | iter {current_iter:,} | {phase_str}")
    lines.append(f"📋 {ms['desc']}")
    lines.append("")

    # 핵심 메트릭
    reward_pct, reward_icon = get_recent_trend(data, "Train/mean_reward")
    lines.append(f"<b>📊 핵심 메트릭</b>")
    lines.append(f"  {reward_icon} Reward: {reward:.1f} (trend {reward_pct:+.1f}%)")
    lines.append(f"  📏 Ep Length: {ep_len:.1f} (생존 {survival_pct:.1f}%)")
    lines.append(f"  🧠 VF Loss: {vf_loss:.2f}")
    lines.append(f"  📐 Surrogate: {surr_loss:.5f}")
    lines.append(f"  🔊 Noise: {noise:.4f}")
    lines.append(f"  💀 종료: timeout {timeout_pct:.0f}% / fall {100-timeout_pct:.0f}%")
    lines.append("")

    # 보행 관련 보상
    lines.append(f"<b>🦿 보행 보상</b>")
    gait_metrics = [
        ("standing_height", "기립높이"),
        ("forward_velocity", "전진속도"),
        ("trot_gait", "트로트"),
        ("diagonal_coupling", "관절커플링"),
        ("foot_clearance", "발높이"),
        ("leg_lift", "다리들기"),
        ("rear_joint_velocity", "뒷다리속도"),
        ("rear_swing", "뒷다리스윙"),
    ]
    for metric, label in gait_metrics:
        tag = f"Episode_Reward/{metric}"
        val = get_latest_value(data, tag)
        if val is not None:
            pct, icon = get_recent_trend(data, tag)
            lines.append(f"  {icon} {label}: {val:+.4f} ({pct:+.1f}%)")
    lines.append("")

    # 페널티
    lines.append(f"<b>⛔ 페널티</b>")
    penalty_metrics = [
        ("shoulder_neutral", "어깨중립"),
        ("joint_vel_l2", "관절속도"),
        ("action_rate_l2", "행동변화"),
        ("flat_orientation_l2", "자세수평"),
        ("ang_vel_xy_l2", "각속도"),
        ("same_side_penalty", "동측보행"),
    ]
    for metric, label in penalty_metrics:
        tag = f"Episode_Reward/{metric}"
        val = get_latest_value(data, tag)
        if val is not None:
            pct, icon = get_recent_trend(data, tag)
            lines.append(f"  {icon} {label}: {val:+.4f} ({pct:+.1f}%)")
    lines.append("")

    return "\n".join(lines)


def format_ramp_comparison(data, pre_snap, current_iter, run_name):
    """Ramp1 전후 비교 리포트 (1400 vs 현재)."""
    lines = []
    lines.append(f"<b>🔬 Ramp1 전후 비교</b>")
    lines.append(f"  기준: iter {pre_snap['iter']} (pre-ramp) → iter {current_iter} (현재)")
    lines.append("")

    # critic shock 핵심 지표
    pre_vf = pre_snap.get("Loss/value_loss", 0)
    cur_vf = get_latest_value(data, "Loss/value_loss") or 0
    vf_ratio = cur_vf / pre_vf if pre_vf > 0 else 0
    if vf_ratio > 5:
        shock_icon = "🚨"
        shock_msg = f"CRITIC SHOCK 가능! ({vf_ratio:.1f}x 증가)"
    elif vf_ratio > 2:
        shock_icon = "⚠️"
        shock_msg = f"VF loss 경고 수준 ({vf_ratio:.1f}x 증가)"
    elif vf_ratio > 1.3:
        shock_icon = "🟡"
        shock_msg = f"소폭 증가 ({vf_ratio:.1f}x) — 정상 범위"
    else:
        shock_icon = "✅"
        shock_msg = f"안정 ({vf_ratio:.1f}x) — critic shock 없음"
    lines.append(f"  {shock_icon} <b>VF Loss: {pre_vf:.2f} → {cur_vf:.2f} ({shock_msg})</b>")
    lines.append("")

    # 주요 메트릭 변화
    compare_tags = [
        ("Train/mean_reward", "Reward"),
        ("Train/mean_episode_length", "Ep Length"),
        ("Loss/surrogate", "Surrogate"),
        ("Policy/mean_noise_std", "Noise Std"),
        ("Episode_Reward/standing_height", "기립높이"),
        ("Episode_Reward/forward_velocity", "전진속도"),
        ("Episode_Reward/trot_gait", "트로트"),
        ("Episode_Reward/diagonal_coupling", "관절커플링"),
        ("Episode_Reward/foot_clearance", "발높이"),
        ("Episode_Reward/shoulder_neutral", "어깨중립"),
        ("Episode_Reward/action_rate_l2", "행동변화"),
    ]
    lines.append(f"  <code>{'Metric':<14} {'Pre':>8} {'Now':>8} {'Δ':>8} {'%':>7}</code>")
    lines.append(f"  <code>{'─'*14} {'─'*8} {'─'*8} {'─'*8} {'─'*7}</code>")
    for tag, label in compare_tags:
        pre_val = pre_snap.get(tag, 0) or 0
        cur_val = get_latest_value(data, tag) or 0
        delta = cur_val - pre_val
        pct = (delta / abs(pre_val) * 100) if pre_val != 0 else 0
        if abs(pct) > 20:
            mark = " ⚡"
        elif abs(pct) > 10:
            mark = " ↗" if pct > 0 else " ↘"
        else:
            mark = ""
        lines.append(f"  <code>{label:<14} {pre_val:>8.3f} {cur_val:>8.3f} {delta:>+8.3f} {pct:>+6.1f}%{mark}</code>")
    lines.append("")

    # V20 핵심 판정
    pre_reward = pre_snap.get("Train/mean_reward", 0)
    cur_reward = get_latest_value(data, "Train/mean_reward") or 0
    reward_drop = cur_reward - pre_reward
    reward_drop_pct = (reward_drop / abs(pre_reward) * 100) if pre_reward != 0 else 0

    lines.append(f"<b>📋 V20 Ramp1 판정</b>")
    checks = []
    # 1) Critic shock
    if vf_ratio < 3:
        checks.append(f"  ✅ Critic stable (VF {vf_ratio:.1f}x < 3x)")
    else:
        checks.append(f"  ❌ Critic shock (VF {vf_ratio:.1f}x ≥ 3x)")

    # 2) Reward drop
    if reward_drop_pct > -30:
        checks.append(f"  ✅ Reward maintained ({reward_drop_pct:+.1f}% > -30%)")
    else:
        checks.append(f"  ❌ Reward crash ({reward_drop_pct:+.1f}% ≤ -30%)")

    # 3) Ep length stability
    pre_ep = pre_snap.get("Train/mean_episode_length", 0)
    cur_ep = get_latest_value(data, "Train/mean_episode_length") or 0
    ep_drop_pct = ((cur_ep - pre_ep) / abs(pre_ep) * 100) if pre_ep != 0 else 0
    if ep_drop_pct > -20:
        checks.append(f"  ✅ Survival stable ({ep_drop_pct:+.1f}% > -20%)")
    else:
        checks.append(f"  ❌ Survival dropping ({ep_drop_pct:+.1f}% ≤ -20%)")

    # 4) Noise std
    pre_noise = pre_snap.get("Policy/mean_noise_std", 0)
    cur_noise = get_latest_value(data, "Policy/mean_noise_std") or 0
    noise_delta = cur_noise - pre_noise
    if noise_delta < 0.1:
        checks.append(f"  ✅ Exploration stable (Δnoise={noise_delta:+.4f})")
    else:
        checks.append(f"  ⚠️ Exploration spike (Δnoise={noise_delta:+.4f})")

    for c in checks:
        lines.append(c)

    passed = sum(1 for c in checks if "✅" in c)
    total = len(checks)
    lines.append("")
    if passed == total:
        lines.append(f"  🎉 <b>Ramp1 전환 성공! ({passed}/{total} 통과)</b>")
    elif passed >= total - 1:
        lines.append(f"  🟡 <b>Ramp1 대체로 안정 ({passed}/{total} 통과) — 계속 모니터링</b>")
    else:
        lines.append(f"  🚨 <b>Ramp1 불안정! ({passed}/{total} 통과) — 정밀 점검 필요</b>")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Milestone Checkpoint Monitor")
    parser.add_argument("--poll", type=int, default=30, help="Polling interval in seconds")
    parser.add_argument("--run_dir", type=str, default=None, help="Specific run directory")
    args = parser.parse_args()

    milestone_keys = sorted(MILESTONES.keys())
    completed = set()  # 이미 보고한 milestones
    snapshots = {}  # {iter: snapshot_dict}

    print(f"📍 Milestone Monitor started | milestones={milestone_keys} | poll={args.poll}s")
    print(f"   V20 Ramp1: iter {RAMP1_START}~{RAMP1_END} | 핵심 관측: 1400→1550→1700")

    # 시작 알림
    send_telegram(
        f"📍 <b>Milestone Monitor 시작</b>\n"
        f"관측 포인트: {', '.join(str(m) for m in milestone_keys)}\n"
        f"핵심: Ramp1 (iter {RAMP1_START}) 전후 비교\n"
        f"V20 Soft-Ramp 커리큘럼 검증 모드"
    )

    while True:
        try:
            run_dir = args.run_dir if args.run_dir else find_latest_run()
            if not run_dir or not os.path.isdir(run_dir):
                time.sleep(args.poll)
                continue

            run_name = os.path.basename(run_dir)
            data = read_tfevents(run_dir)
            if not data:
                time.sleep(args.poll)
                continue

            reward_vals = data.get("Train/mean_reward", [])
            if not reward_vals:
                time.sleep(args.poll)
                continue

            current_iter = int(reward_vals[-1][0])

            # 각 milestone 확인
            for ms_iter in milestone_keys:
                if ms_iter in completed:
                    continue
                if current_iter < ms_iter:
                    continue

                # 마일스톤 도달!
                now = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"\n[{now}] 🎯 Milestone {ms_iter} reached (current iter: {current_iter})")

                # 스냅샷 캡처 & 저장
                snap = capture_snapshot(data, current_iter)
                snapshots[ms_iter] = snap
                fpath = save_snapshot(snap, ms_iter, run_name)
                print(f"  Snapshot saved: {fpath}")

                # 리포트 생성
                report = format_milestone_report(data, ms_iter, run_name)

                # Ramp1 전후 비교 (1550, 1700에서만)
                if ms_iter in (1550, 1700):
                    # 1400 스냅샷이 있으면 비교
                    pre_snap = snapshots.get(1400) or load_snapshot(1400, run_name)
                    if pre_snap:
                        comparison = format_ramp_comparison(data, pre_snap, current_iter, run_name)
                        report += "\n" + comparison
                    else:
                        report += "\n⚠️ Pre-Ramp1 스냅샷(iter 1400) 없음 — 비교 불가"

                # 전송
                full_msg = f"[V20] {report}"
                send_telegram(full_msg)
                completed.add(ms_iter)
                print(f"  Report sent for milestone {ms_iter}")

            # 모든 milestones 완료 시 종료
            if len(completed) >= len(milestone_keys):
                final_msg = (
                    f"📍 <b>Milestone Monitor 완료</b>\n"
                    f"모든 관측 포인트 ({', '.join(str(m) for m in milestone_keys)}) 보고 완료\n"
                    f"스냅샷 저장 위치: logs/milestone_snapshots/"
                )
                send_telegram(f"[V20] {final_msg}")
                print(f"\n✅ All milestones completed. Exiting.")
                break

        except Exception as e:
            now = datetime.datetime.now().strftime("%H:%M:%S")
            err = f"[{now}] Milestone monitor error: {e}\n{traceback.format_exc()[-300:]}"
            print(err)
            time.sleep(args.poll * 2)  # 에러 시 대기 시간 증가
            continue

        time.sleep(args.poll)


if __name__ == "__main__":
    main()
