"""
V17.1 Training Monitor - Detailed Analysis Script
TensorBoard 이벤트 파일에서 메트릭을 읽어 상세 분석 리포트를 생성합니다.
Usage: python scripts/analyze_training.py --run_dir <path> [--clip_num N]
"""

import argparse
import os

LIMB_SUFFIXES = ("fl", "fr", "rl", "rr")
LIMB_VALIDITY_THRESHOLDS = {
    "contact_target": 0.50,
    "propulsion_target": 0.30,
    "leg_lift_target": 0.18,
    "clearance_target": 0.03,
    "limb_usage_min": 0.30,
    "rear_usage_diff_max": 0.18,
    "front_usage_diff_max": 0.22,
    "rear_propulsion_diff_max": 0.20,
    "contact_ratio_min_any": 0.05,
    "contact_ratio_min_rear": 0.08,
    "collapse_swing_min": 0.95,
    "collapse_propulsion_max": 0.02,
}
LIMB_LABELS = {
    "fl": "front_left",
    "fr": "front_right",
    "rl": "rear_left",
    "rr": "rear_right",
}

def read_tfevents(run_dir):
    """TensorBoard 이벤트 파일에서 모든 스칼라 데이터를 읽습니다."""
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError:
        print("tensorboard not installed, trying manual parse...")
        return None

    event_files = [f for f in os.listdir(run_dir) if f.startswith("events.out.tfevents")]
    if not event_files:
        return None

    event_path = os.path.join(run_dir, event_files[0])
    ea = EventAccumulator(event_path)
    ea.Reload()

    data = {}
    for tag in ea.Tags().get("scalars", []):
        events = ea.Scalars(tag)
        data[tag] = [(e.step, e.value) for e in events]

    return data


def get_latest_metrics(data, n_recent=5, max_step=None):
    """최근 N개 이터레이션의 메트릭 평균을 구합니다."""
    latest = {}
    for tag, values in data.items():
        if max_step is not None:
            values = [(step, value) for step, value in values if int(step) <= int(max_step)]
        if len(values) >= n_recent:
            recent = values[-n_recent:]
            latest[tag] = {
                "current": recent[-1][1],
                "avg": sum(v for _, v in recent) / len(recent),
                "step": recent[-1][0],
            }
        elif values:
            latest[tag] = {
                "current": values[-1][1],
                "avg": values[-1][1],
                "step": values[-1][0],
            }
    return latest


def get_trend(data, tag, window=50, max_step=None):
    """메트릭의 최근 추세를 계산합니다 (상승/하락/정체)."""
    if tag not in data:
        return "insufficient_data", 0.0
    values = data[tag]
    if max_step is not None:
        values = [(step, value) for step, value in values if int(step) <= int(max_step)]
    if len(values) < window * 2:
        return "insufficient_data", 0.0

    first_half = values[-(window * 2):-window]
    second_half = values[-window:]

    avg_first = sum(v for _, v in first_half) / len(first_half)
    avg_second = sum(v for _, v in second_half) / len(second_half)

    change = avg_second - avg_first
    pct = (change / abs(avg_first) * 100) if avg_first != 0 else 0

    if pct > 5:
        trend = "IMPROVING ↑"
    elif pct < -5:
        trend = "DECLINING ↓"
    else:
        trend = "STABLE →"

    return trend, pct


def analyze_rewards(latest):
    """보상 구조를 분석하여 상위 기여/손실 보상을 식별합니다."""
    rewards = {}
    for tag, val in latest.items():
        if "Episode_Reward/" in tag:
            name = tag.replace("Episode_Reward/", "")
            rewards[name] = val["current"]

    # 양수 보상 (기여) 정렬
    positive = {k: v for k, v in rewards.items() if v > 0.01}
    negative = {k: v for k, v in rewards.items() if v < -0.01}

    positive_sorted = sorted(positive.items(), key=lambda x: x[1], reverse=True)
    negative_sorted = sorted(negative.items(), key=lambda x: x[1])

    return positive_sorted, negative_sorted, rewards


def gait_quality_assessment(rewards):
    """걸음걸이 품질을 종합 평가합니다."""
    score = 0
    notes = []

    # 1. 트로트 패턴
    trot = rewards.get("trot_gait", 0)
    if trot > 5.0:
        score += 3
        notes.append("트로트 패턴 우수 (trot_gait={:.1f})".format(trot))
    elif trot > 1.0:
        score += 1
        notes.append("트로트 패턴 형성 중 (trot_gait={:.1f})".format(trot))
    else:
        notes.append("트로트 미형성 (trot_gait={:.2f})".format(trot))

    # 2. 대각선 커플링
    diag = rewards.get("diagonal_coupling", 0)
    if diag > 3.0:
        score += 2
        notes.append("대각선 커플링 양호 (diagonal={:.1f})".format(diag))
    elif diag > 0.5:
        score += 1
        notes.append("대각선 커플링 형성 중 (diagonal={:.2f})".format(diag))
    else:
        notes.append("대각선 커플링 부족 (diagonal={:.3f})".format(diag))

    # 3. 걸음 주기
    cycle = rewards.get("gait_cycle_period", 0)
    if cycle > 2.0:
        score += 2
        notes.append("걸음 주기 목표 달성 (cycle={:.1f})".format(cycle))
    elif cycle > 0.5:
        score += 1
        notes.append("걸음 주기 학습 중 (cycle={:.2f})".format(cycle))
    else:
        notes.append("걸음 주기 미활성 (cycle={:.4f})".format(cycle))

    # 4. 보폭 길이
    stride = rewards.get("stride_length", 0)
    if stride > 2.0:
        score += 2
        notes.append("보폭 길이 목표 달성 (stride={:.1f})".format(stride))
    elif stride > 0.5:
        score += 1
        notes.append("보폭 길이 학습 중 (stride={:.2f})".format(stride))
    else:
        notes.append("보폭 미발달 (stride={:.4f})".format(stride))

    # 5. 뒷다리 활성화
    rear_vel = rewards.get("rear_joint_velocity", 0)
    rear_frozen = rewards.get("rear_joint_frozen", 0)
    if rear_vel > 5.0 and rear_frozen > -5.0:
        score += 2
        notes.append("뒷다리 활발 (vel={:.1f}, frozen={:.1f})".format(rear_vel, rear_frozen))
    elif rear_vel > 1.0:
        score += 1
        notes.append("뒷다리 활성화 시작 (vel={:.1f})".format(rear_vel))
    else:
        notes.append("뒷다리 비활성 (vel={:.2f})".format(rear_vel))

    # 6. 안정성 (넘어짐 비율)
    # base_height, flat_orientation 으로 추정
    height = rewards.get("standing_height", 0)
    if height > 5.0:
        score += 2
        notes.append("안정적 기립 (height={:.1f})".format(height))
    elif height > 1.0:
        score += 1
        notes.append("기립 유지 학습 중 (height={:.2f})".format(height))
    else:
        notes.append("기립 불안정 (height={:.3f})".format(height))

    # 종합 등급
    if score >= 10:
        grade = "A (우수한 트로트 보행)"
    elif score >= 7:
        grade = "B (보행 형성, 개선 여지)"
    elif score >= 4:
        grade = "C (초기 보행 패턴)"
    elif score >= 2:
        grade = "D (기립/균형 학습 중)"
    else:
        grade = "F (초기 단계)"

    return grade, score, notes


def stability_assessment(latest):
    """안정성 지표를 분석합니다."""
    notes = []

    # Episode length
    ep_len = latest.get("Episode length/mean", {}).get("current", 0)
    max_ep = 10.0 * 50  # 10초 × 50Hz
    if ep_len > 0:
        survival_pct = (ep_len / max_ep) * 100
        notes.append("에피소드 길이: {:.0f} steps ({:.1f}% 생존율)".format(ep_len, survival_pct))

    # Termination
    timeout = latest.get("Episode_Termination/time_out", {}).get("current", 0)
    bad_orient = latest.get("Episode_Termination/bad_orientation", {}).get("current", 0)
    if timeout + bad_orient > 0:
        timeout_pct = timeout / (timeout + bad_orient) * 100 if (timeout + bad_orient) > 0 else 0
        notes.append("종료 원인: timeout={:.0f}% / bad_orientation={:.0f}%".format(timeout_pct, 100 - timeout_pct))

    # Velocity tracking
    vel_err = latest.get("Metrics/base_velocity/error_vel_xy", {}).get("current", 0)
    notes.append("속도 추적 오차: {:.4f} m/s".format(vel_err))

    return notes


def smoothness_assessment(rewards):
    """동작 부드러움을 평가합니다."""
    notes = []

    action_rate = rewards.get("action_rate_l2", 0)
    joint_vel = rewards.get("joint_vel_l2", 0)
    dof_acc = rewards.get("dof_acc_l2", 0)

    # 스무스니스 점수 (페널티가 작을수록 좋음)
    total_penalty = abs(action_rate) + abs(joint_vel) + abs(dof_acc)

    if total_penalty < 10:
        notes.append("동작 매우 부드러움 (총 페널티: {:.1f})".format(total_penalty))
    elif total_penalty < 30:
        notes.append("동작 적당히 부드러움 (총 페널티: {:.1f})".format(total_penalty))
    elif total_penalty < 60:
        notes.append("동작 다소 거친 편 (총 페널티: {:.1f})".format(total_penalty))
    else:
        notes.append("동작 매우 거침 — 개선 필요 (총 페널티: {:.1f})".format(total_penalty))

    notes.append("  - action_rate: {:.2f}".format(action_rate))
    notes.append("  - joint_vel: {:.2f}".format(joint_vel))
    notes.append("  - dof_acc: {:.2f}".format(dof_acc))

    return notes


def _clip01(value):
    return max(0.0, min(1.0, float(value)))


def compute_limb_validity_metrics(rewards):
    usage_scores = {}
    contact_ratios = {}
    propulsion_scores = {}
    swing_times = {}
    for suffix in LIMB_SUFFIXES:
        contact_ratio = float(rewards.get(f"contact_ratio_{suffix}", 0.0) or 0.0)
        propulsion = float(rewards.get(f"propulsion_{suffix}", 0.0) or 0.0)
        leg_lift = float(rewards.get(f"leg_lift_{suffix}", 0.0) or 0.0)
        clearance = float(rewards.get(f"clearance_{suffix}", 0.0) or 0.0)
        swing_time = float(rewards.get(f"swing_time_{suffix}", 0.0) or 0.0)
        contact_score = _clip01(contact_ratio / LIMB_VALIDITY_THRESHOLDS["contact_target"])
        propulsion_score = _clip01(propulsion / LIMB_VALIDITY_THRESHOLDS["propulsion_target"])
        leg_lift_score = _clip01(leg_lift / LIMB_VALIDITY_THRESHOLDS["leg_lift_target"])
        clearance_score = _clip01(clearance / LIMB_VALIDITY_THRESHOLDS["clearance_target"])
        swing_activity_score = 0.5 * (leg_lift_score + clearance_score)
        support_gate = max(contact_score, propulsion_score)
        usage_scores[suffix] = (
            0.55 * contact_score
            + 0.35 * propulsion_score
            + 0.10 * swing_activity_score
        ) * support_gate
        contact_ratios[suffix] = contact_ratio
        propulsion_scores[suffix] = propulsion
        swing_times[suffix] = swing_time

    usage_values = list(usage_scores.values())
    limb_usage_min = min(usage_values) if usage_values else 0.0
    limb_usage_variance = 0.0
    if usage_values:
        mean_usage = sum(usage_values) / len(usage_values)
        limb_usage_variance = sum((value - mean_usage) ** 2 for value in usage_values) / len(usage_values)

    rear_usage_diff = abs(usage_scores.get("rl", 0.0) - usage_scores.get("rr", 0.0))
    front_usage_diff = abs(usage_scores.get("fl", 0.0) - usage_scores.get("fr", 0.0))
    rear_propulsion_diff = abs(propulsion_scores.get("rl", 0.0) - propulsion_scores.get("rr", 0.0))

    reasons = []
    collapse_reasons = []
    for suffix in LIMB_SUFFIXES:
        contact_ratio = contact_ratios.get(suffix, 0.0)
        swing_time = swing_times.get(suffix, 0.0)
        propulsion = propulsion_scores.get(suffix, 0.0)
        if (
            contact_ratio < LIMB_VALIDITY_THRESHOLDS["contact_ratio_min_any"]
            and swing_time > LIMB_VALIDITY_THRESHOLDS["collapse_swing_min"]
            and propulsion < LIMB_VALIDITY_THRESHOLDS["collapse_propulsion_max"]
        ):
            collapse_reasons.append(
                f"{LIMB_LABELS[suffix]}_contact_collapse(c={contact_ratio:.2f},s={swing_time:.2f},p={propulsion:.2f})"
            )

    if limb_usage_min < LIMB_VALIDITY_THRESHOLDS["limb_usage_min"]:
        reasons.append(f"limb_usage_min<{LIMB_VALIDITY_THRESHOLDS['limb_usage_min']:.2f}")
    if rear_usage_diff > LIMB_VALIDITY_THRESHOLDS["rear_usage_diff_max"]:
        reasons.append(f"rear_usage_diff>{LIMB_VALIDITY_THRESHOLDS['rear_usage_diff_max']:.2f}")
    if front_usage_diff > LIMB_VALIDITY_THRESHOLDS["front_usage_diff_max"]:
        reasons.append(f"front_usage_diff>{LIMB_VALIDITY_THRESHOLDS['front_usage_diff_max']:.2f}")
    if rear_propulsion_diff > LIMB_VALIDITY_THRESHOLDS["rear_propulsion_diff_max"]:
        reasons.append(f"rear_propulsion_diff>{LIMB_VALIDITY_THRESHOLDS['rear_propulsion_diff_max']:.2f}")
    if not collapse_reasons and min(contact_ratios.values(), default=0.0) < LIMB_VALIDITY_THRESHOLDS["contact_ratio_min_any"]:
        reasons.append(f"contact_ratio_any<{LIMB_VALIDITY_THRESHOLDS['contact_ratio_min_any']:.2f}")
    if not collapse_reasons and min(contact_ratios.get("rl", 0.0), contact_ratios.get("rr", 0.0)) < LIMB_VALIDITY_THRESHOLDS["contact_ratio_min_rear"]:
        reasons.append(f"rear_contact_ratio<{LIMB_VALIDITY_THRESHOLDS['contact_ratio_min_rear']:.2f}")

    all_reasons = collapse_reasons + reasons

    return {
        "usage_scores": usage_scores,
        "contact_ratios": contact_ratios,
        "propulsion_scores": propulsion_scores,
        "swing_times": swing_times,
        "limb_usage_min": limb_usage_min,
        "limb_usage_variance": limb_usage_variance,
        "rear_left_right_usage_diff": rear_usage_diff,
        "front_left_right_usage_diff": front_usage_diff,
        "rear_left_right_propulsion_diff": rear_propulsion_diff,
        "gate_pass": not all_reasons,
        "reason": "pass" if not all_reasons else "; ".join(all_reasons[:4]),
    }


def generate_report(run_dir, clip_num=0, iteration=None):
    """상세 분석 리포트를 생성합니다."""

    print("=" * 80)
    print("V17.1 TRAINING ANALYSIS REPORT")
    print("=" * 80)
    print(f"Run: {os.path.basename(run_dir)}")
    print(f"Clip: #{clip_num}")
    print()

    # Read data
    data = read_tfevents(run_dir)
    if not data:
        print("ERROR: Cannot read TensorBoard data!")
        return

    latest = get_latest_metrics(data, n_recent=10, max_step=iteration)

    # Current iteration
    reward_data = data.get("Episode_Reward/track_lin_vel_xy_exp", [])
    if iteration is not None:
        reward_data = [(step, value) for step, value in reward_data if int(step) <= int(iteration)]
    if reward_data:
        current_iter = reward_data[-1][0]
        print(f"Current Iteration: {current_iter:,} / 15,000")
    else:
        current_iter = 0
        print("Current Iteration: Unknown")

    # Total reward
    mean_reward = latest.get("Train/mean_reward", {}).get("current", 0)
    print(f"Mean Reward: {mean_reward:.1f}")

    reward_trend, reward_pct = get_trend(data, "Train/mean_reward", max_step=iteration)
    print(f"Reward Trend: {reward_trend} ({reward_pct:+.1f}%)")
    print()

    # ============================================================
    # 1. 안정성 분석
    # ============================================================
    print("-" * 60)
    print("1. 안정성 분석")
    print("-" * 60)
    stability_notes = stability_assessment(latest)
    for note in stability_notes:
        print(f"  {note}")
    print()

    # ============================================================
    # 2. 보상 구조 분석
    # ============================================================
    print("-" * 60)
    print("2. 보상 구조 분석")
    print("-" * 60)
    positive, negative, all_rewards = analyze_rewards(latest)
    limb_metrics = compute_limb_validity_metrics(all_rewards)

    print("\n  [TOP 10 양수 보상 (기여)]")
    for i, (name, val) in enumerate(positive[:10]):
        trend, pct = get_trend(data, f"Episode_Reward/{name}", max_step=iteration)
        print(f"    {i+1:2d}. {name:30s} = {val:+8.3f}  {trend}")

    print("\n  [TOP 10 음수 보상 (페널티)]")
    for i, (name, val) in enumerate(negative[:10]):
        trend, pct = get_trend(data, f"Episode_Reward/{name}", max_step=iteration)
        print(f"    {i+1:2d}. {name:30s} = {val:+8.3f}  {trend}")

    print()

    # ============================================================
    # 3. Limb Validity 평가
    # ============================================================
    print("-" * 60)
    print("3. Limb Validity 평가")
    print("-" * 60)
    print(f"\n  Limb Validity Gate: {'PASS' if limb_metrics['gate_pass'] else 'FAIL'}")
    print(f"  Reason: {limb_metrics['reason']}")
    print(f"  limb_usage_min                = {limb_metrics['limb_usage_min']:.3f}")
    print(f"  limb_usage_variance           = {limb_metrics['limb_usage_variance']:.3f}")
    print(f"  rear_left_right_usage_diff    = {limb_metrics['rear_left_right_usage_diff']:.3f}")
    print(f"  front_left_right_usage_diff   = {limb_metrics['front_left_right_usage_diff']:.3f}")
    print(f"  rear_left_right_prop_diff     = {limb_metrics['rear_left_right_propulsion_diff']:.3f}")
    print()
    print("  [Per-Limb Raw KPI]")
    for suffix in LIMB_SUFFIXES:
        print(
            "    {suffix:>2s} | usage={usage:.3f} contact={contact:.3f} propulsion={propulsion:.3f} lift={lift:.3f} clearance={clearance:.3f}".format(
                suffix=suffix,
                usage=limb_metrics["usage_scores"].get(suffix, 0.0),
                contact=limb_metrics["contact_ratios"].get(suffix, 0.0),
                propulsion=limb_metrics["propulsion_scores"].get(suffix, 0.0),
                lift=float(all_rewards.get(f"leg_lift_{suffix}", 0.0) or 0.0),
                clearance=float(all_rewards.get(f"clearance_{suffix}", 0.0) or 0.0),
            )
        )
    print()

    # ============================================================
    # 4. 걸음걸이 품질 평가
    # ============================================================
    print("-" * 60)
    print("4. 걸음걸이 품질 평가")
    print("-" * 60)
    grade, score, gait_notes = gait_quality_assessment(all_rewards)
    print(f"\n  종합 등급: {grade} (점수: {score}/13)")
    print()
    for note in gait_notes:
        print(f"  - {note}")
    print()

    # ============================================================
    # 5. 동작 부드러움 평가
    # ============================================================
    print("-" * 60)
    print("5. 동작 부드러움 평가")
    print("-" * 60)
    smooth_notes = smoothness_assessment(all_rewards)
    for note in smooth_notes:
        print(f"  {note}")
    print()

    # ============================================================
    # 6. 주요 추세 (핵심 메트릭 변화)
    # ============================================================
    print("-" * 60)
    print("6. 핵심 메트릭 추세")
    print("-" * 60)
    key_metrics = [
        "Train/mean_reward",
        "Episode length/mean",
        "Episode_Reward/trot_gait",
        "Episode_Reward/diagonal_coupling",
        "Episode_Reward/gait_cycle_period",
        "Episode_Reward/stride_length",
        "Episode_Reward/standing_height",
        "Episode_Reward/rear_joint_velocity",
        "Episode_Reward/action_rate_l2",
        "Episode_Reward/joint_vel_l2",
    ]
    for metric in key_metrics:
        name = metric.split("/")[-1]
        trend, pct = get_trend(data, metric, max_step=iteration)
        val = latest.get(metric, {}).get("current", 0)
        print(f"  {name:30s} = {val:+10.3f}  {trend} ({pct:+.1f}%)")
    print()

    # ============================================================
    # 7. 종합 진단 & 권장 사항
    # ============================================================
    print("-" * 60)
    print("7. 종합 진단 & 권장 사항")
    print("-" * 60)

    ep_len = latest.get("Episode length/mean", {}).get("current", 0)
    max_ep = 10.0 * 50
    survival = ep_len / max_ep if max_ep > 0 else 0

    recommendations = []

    # 생존율 기반 진단
    if survival < 0.1:
        recommendations.append("CRITICAL: 생존율 10% 미만 — 로봇이 거의 즉시 넘어짐")
        if abs(all_rewards.get("dof_acc_l2", 0)) > 10:
            recommendations.append("  → dof_acc 패널티 매우 큼 — stiffness 또는 effort를 낮추는 것 고려")
        if abs(all_rewards.get("joint_vel_l2", 0)) > 15:
            recommendations.append("  → joint_vel 패널티 매우 큼 — velocity_limit 조정 또는 weight 낮추기 고려")
    elif survival < 0.3:
        recommendations.append("WARNING: 생존율 30% 미만 — 아직 불안정하지만 학습 중")
    elif survival < 0.7:
        recommendations.append("GOOD: 생존율 30-70% — 정상적인 학습 진행 중")
    else:
        recommendations.append("EXCELLENT: 생존율 70%+ — 안정적 보행 달성!")

    # 걸음걸이 진단
    if score < 4 and current_iter > 3000:
        recommendations.append("WARNING: iter 3000+ 인데 걸음걸이 점수 낮음 — 보상 가중치 조정 필요 가능성")

    if not limb_metrics["gate_pass"]:
        recommendations.append("WARNING: limb validity gate fail — reward가 높아도 3족 exploit 후보로 제외해야 함")
        recommendations.append(f"  → fail reason: {limb_metrics['reason']}")

    # 부드러움 진단
    total_smooth_penalty = abs(all_rewards.get("action_rate_l2", 0)) + abs(all_rewards.get("joint_vel_l2", 0))
    if total_smooth_penalty > 40:
        recommendations.append("NOTE: 스무스니스 페널티가 전체 보상에서 지배적 — weight 조정 고려")

    # 진행 속도
    if current_iter > 0:
        progress_pct = current_iter / 15000 * 100
        recommendations.append(f"\n진행률: {progress_pct:.1f}% ({current_iter:,}/15,000)")

    for rec in recommendations:
        print(f"  {rec}")

    print()
    print("=" * 80)
    print("END OF REPORT")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Training Analysis")
    parser.add_argument("--run_dir", required=True, help="Training run directory")
    parser.add_argument("--clip_num", type=int, default=0, help="Clip number")
    parser.add_argument("--iteration", type=int, default=None, help="Use metrics up to this iteration only")
    args = parser.parse_args()

    generate_report(args.run_dir, args.clip_num, iteration=args.iteration)
