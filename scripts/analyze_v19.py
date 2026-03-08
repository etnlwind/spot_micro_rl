#!/usr/bin/env python3
"""V19 Training Analysis — Hard Phase Switch Curriculum (baseline for V20 comparison).

Phase 1 (STAND): iter 0~2000
Phase 2 (WALK):  iter 2000~2527 (중단됨)

핵심 분석:
  1. Phase 전환 구간 critic shock (value_loss spike)
  2. Reward 급락 및 회복 속도
  3. Raw gait metric 보존 여부
  4. Raw penalty metric 적응 여부
"""
import os
import sys

# ── 경로 설정 ──
LOG_DIR = os.path.join(os.path.dirname(__file__), "..",
                       "logs", "rsl_rl", "spot_micro_flat", "2026-03-08_15-14-15")
LOG_DIR = os.path.normpath(LOG_DIR)

if not os.path.exists(LOG_DIR):
    print(f"ERROR: V19 log directory not found: {LOG_DIR}")
    sys.exit(1)

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ea = EventAccumulator(LOG_DIR)
ea.Reload()

def get_scalars(tag):
    """TensorBoard에서 (step, value) 리스트 반환."""
    if tag not in ea.Tags()["scalars"]:
        return []
    return [(e.step, e.value) for e in ea.Scalars(tag)]

# ── V19 Phase 가중치 (weighted → raw 변환용) ──
PHASE1_WEIGHTS = {
    "standing_height": 40.0, "height_bonus": 25.0, "forward_velocity_bootstrap": 8.0,
    "forward_velocity": 2.0, "same_side_penalty": 0.0, "rear_both_ground": 0.0,
    "undesired_contacts": -20.0, "feet_below_knees": -30.0, "trot_gait": 5.0,
    "rear_joint_frozen": -10.0, "diagonal_coupling": 5.0, "gait_cycle_period": 0.0,
    "stride_length": 0.0, "foot_clearance": 2.0, "joint_vel_l2": -0.05,
    "action_rate_l2": -0.3, "flat_orientation_l2": -1.0, "shoulder_neutral": -1.0,
    "dof_acc_l2": -5.0e-07, "joint_oscillation": -5.0, "stance_propulsion": 8.0,
}
PHASE2_WEIGHTS = {
    "standing_height": 8.0, "height_bonus": 15.0, "forward_velocity_bootstrap": 4.0,
    "forward_velocity": 12.0, "same_side_penalty": -10.0, "rear_both_ground": -30.0,
    "undesired_contacts": -50.0, "feet_below_knees": -80.0, "trot_gait": 20.0,
    "rear_joint_frozen": -30.0, "diagonal_coupling": 15.0, "gait_cycle_period": 8.0,
    "stride_length": 6.0, "foot_clearance": 5.0, "joint_vel_l2": -0.5,
    "action_rate_l2": -1.0, "flat_orientation_l2": -3.0, "shoulder_neutral": -3.0,
    "dof_acc_l2": -2.0e-06, "joint_oscillation": -15.0, "stance_propulsion": 15.0,
}
# 비관리 항목 (상수)
CONSTANT_WEIGHTS = {
    "leg_lift": 15.0, "rear_forward_stride": 10.0,
}
PHASE_TRANSITION = 2000  # Hard switch point

def get_weight(term, step):
    """V19 phase에 따른 가중치 반환."""
    if term in CONSTANT_WEIGHTS:
        return CONSTANT_WEIGHTS[term]
    if step < PHASE_TRANSITION:
        return PHASE1_WEIGHTS.get(term, None)
    return PHASE2_WEIGHTS.get(term, None)


print("=" * 70)
print("  V19 Training Analysis — Hard Phase Switch Curriculum")
print(f"  Log: {LOG_DIR}")
print("=" * 70)

# ── 1. 전체 훈련 개요 ──
reward_data = get_scalars("Train/mean_reward")
ep_len_data = get_scalars("Train/mean_episode_length")
vl_data = get_scalars("Loss/value_function")
surr_data = get_scalars("Loss/surrogate")
noise_data = get_scalars("Policy/mean_noise_std")

last_iter = reward_data[-1][0] if reward_data else 0
print(f"\n{'─' * 70}")
print("1. 전체 훈련 개요")
print(f"{'─' * 70}")
print(f"  총 iteration: {last_iter}")
print(f"  최종 reward: {reward_data[-1][1]:.1f}")
print(f"  최종 ep_len: {ep_len_data[-1][1]:.1f}")
print(f"  최종 value_loss: {vl_data[-1][1]:.2f}")
print(f"  최종 noise_std: {noise_data[-1][1]:.4f}")

# Phase 1 마지막 값 (iter 2000 직전)
p1_end = [(s, v) for s, v in reward_data if s < PHASE_TRANSITION]
p2_start = [(s, v) for s, v in reward_data if s >= PHASE_TRANSITION]

if p1_end:
    p1_last_reward = p1_end[-1][1]
    p1_peak_reward = max(v for _, v in p1_end)
    print(f"\n  Phase 1 (STAND, 0~{PHASE_TRANSITION}):")
    print(f"    마지막 reward: {p1_last_reward:.1f}")
    print(f"    최대 reward: {p1_peak_reward:.1f}")

if p2_start:
    p2_first_reward = p2_start[0][1]
    p2_last_reward = p2_start[-1][1]
    p2_min_reward = min(v for _, v in p2_start)
    print(f"\n  Phase 2 (WALK, {PHASE_TRANSITION}~{last_iter}):")
    print(f"    첫 reward: {p2_first_reward:.1f}")
    print(f"    최저 reward: {p2_min_reward:.1f}")
    print(f"    마지막 reward: {p2_last_reward:.1f}")
    print(f"    reward 급락폭: {p1_last_reward:.1f} → {p2_min_reward:.1f} (Δ={p2_min_reward - p1_last_reward:.1f})")

# ── 2. Critic Shock 분석 ──
print(f"\n{'─' * 70}")
print("2. Critic Shock 분석 (Phase 전환 구간)")
print(f"{'─' * 70}")

# value_loss around transition
vl_pre = [(s, v) for s, v in vl_data if PHASE_TRANSITION - 50 <= s < PHASE_TRANSITION]
vl_post = [(s, v) for s, v in vl_data if PHASE_TRANSITION <= s < PHASE_TRANSITION + 200]

if vl_pre:
    vl_pre_avg = sum(v for _, v in vl_pre) / len(vl_pre)
    print(f"  전환 직전 (iter {PHASE_TRANSITION-50}~{PHASE_TRANSITION}) value_loss 평균: {vl_pre_avg:.2f}")
if vl_post:
    vl_post_max = max(v for _, v in vl_post)
    vl_post_max_iter = [s for s, v in vl_post if v == vl_post_max][0]
    print(f"  전환 직후 value_loss 최대: {vl_post_max:.2f} @ iter {vl_post_max_iter}")
    if vl_pre:
        print(f"  spike 배율: {vl_post_max / vl_pre_avg:.0f}x")

# value_loss 회복 시점 (pre 수준의 2배 이하로 돌아온 iter)
if vl_pre and vl_post:
    threshold = vl_pre_avg * 2
    recovered = [(s, v) for s, v in vl_data if s > PHASE_TRANSITION and v < threshold]
    if recovered:
        print(f"  회복 시점 (< {threshold:.1f}): iter {recovered[0][0]} ({recovered[0][0] - PHASE_TRANSITION} iter 후)")
    else:
        print(f"  아직 회복 안됨 (최종 value_loss={vl_data[-1][1]:.2f})")

# ── 3. Episode Length 분석 ──
print(f"\n{'─' * 70}")
print("3. Episode Length 분석")
print(f"{'─' * 70}")

ep_pre = [(s, v) for s, v in ep_len_data if PHASE_TRANSITION - 50 <= s < PHASE_TRANSITION]
ep_post = [(s, v) for s, v in ep_len_data if PHASE_TRANSITION <= s < PHASE_TRANSITION + 200]

if ep_pre:
    ep_pre_avg = sum(v for _, v in ep_pre) / len(ep_pre)
    print(f"  전환 직전 ep_len 평균: {ep_pre_avg:.1f}")
if ep_post:
    ep_post_min = min(v for _, v in ep_post)
    print(f"  전환 직후 ep_len 최저: {ep_post_min:.1f}")
    if ep_pre:
        print(f"  생존율 변화: {ep_post_min / ep_pre_avg * 100:.0f}%")

# ── 4. Raw Gait Metrics (Phase 전환 전후) ──
print(f"\n{'─' * 70}")
print("4. Raw Gait Metrics (Phase 전환 전후)")
print(f"{'─' * 70}")

GAIT_TERMS = ["forward_velocity", "trot_gait", "diagonal_coupling", "leg_lift", "foot_clearance"]

for term in GAIT_TERMS:
    tag = f"Episode_Reward/{term}"
    data = get_scalars(tag)
    if not data:
        continue

    # Phase 1 마지막 50 iter 평균
    pre_data = [(s, v) for s, v in data if PHASE_TRANSITION - 100 <= s < PHASE_TRANSITION]
    post_data = [(s, v) for s, v in data if PHASE_TRANSITION <= s < PHASE_TRANSITION + 200]

    if pre_data and post_data:
        # weighted → raw 변환
        pre_weighted_avg = sum(v for _, v in pre_data) / len(pre_data)
        post_weighted_avg = sum(v for _, v in post_data[:50]) / min(50, len(post_data))

        w_pre = get_weight(term, PHASE_TRANSITION - 1)
        w_post = get_weight(term, PHASE_TRANSITION)

        if w_pre and abs(w_pre) > 1e-8:
            raw_pre = pre_weighted_avg / w_pre
        else:
            raw_pre = 0.0
        if w_post and abs(w_post) > 1e-8:
            raw_post = post_weighted_avg / w_post
        else:
            raw_post = 0.0

        delta = raw_post - raw_pre
        pct = (delta / abs(raw_pre) * 100) if abs(raw_pre) > 1e-8 else 0
        status = "✅ 유지" if abs(pct) < 10 else ("⚠️ 하락" if pct < -10 else "📈 상승")

        print(f"  {term}:")
        print(f"    weighted: {pre_weighted_avg:.4f} → {post_weighted_avg:.4f}")
        print(f"    raw:      {raw_pre:.4f} → {raw_post:.4f} (Δ={delta:+.4f}, {pct:+.1f}%) {status}")

# ── 5. Raw Penalty Metrics (Phase 전환 전후) ──
print(f"\n{'─' * 70}")
print("5. Raw Penalty Metrics (Phase 전환 전후)")
print(f"{'─' * 70}")

PENALTY_TERMS = ["joint_vel_l2", "dof_acc_l2", "action_rate_l2", "flat_orientation_l2", "shoulder_neutral"]

for term in PENALTY_TERMS:
    tag = f"Episode_Reward/{term}"
    data = get_scalars(tag)
    if not data:
        continue

    pre_data = [(s, v) for s, v in data if PHASE_TRANSITION - 100 <= s < PHASE_TRANSITION]
    post_data = [(s, v) for s, v in data if PHASE_TRANSITION <= s < PHASE_TRANSITION + 200]

    if pre_data and post_data:
        pre_weighted_avg = sum(v for _, v in pre_data) / len(pre_data)
        post_weighted_avg = sum(v for _, v in post_data[:50]) / min(50, len(post_data))

        w_pre = get_weight(term, PHASE_TRANSITION - 1)
        w_post = get_weight(term, PHASE_TRANSITION)

        if w_pre and abs(w_pre) > 1e-8:
            raw_pre = pre_weighted_avg / w_pre
        else:
            raw_pre = 0.0
        if w_post and abs(w_post) > 1e-8:
            raw_post = post_weighted_avg / w_post
        else:
            raw_post = 0.0

        delta = raw_post - raw_pre
        # penalty는 raw 값이 줄어야 개선
        pct = (delta / abs(raw_pre) * 100) if abs(raw_pre) > 1e-8 else 0
        status = "✅ 개선" if pct < -5 else ("⚠️ 악화" if pct > 10 else "→ 유지")

        print(f"  {term}:")
        print(f"    weighted: {pre_weighted_avg:.6f} → {post_weighted_avg:.6f}")
        print(f"    raw:      {raw_pre:.6f} → {raw_post:.6f} (Δ={delta:+.6f}, {pct:+.1f}%) {status}")

# ── 6. Reward 회복 속도 ──
print(f"\n{'─' * 70}")
print("6. Phase 전환 후 Reward 회복 추이")
print(f"{'─' * 70}")

if p2_start:
    milestones = [0, 50, 100, 200, 300, 500]
    for m in milestones:
        target_iter = PHASE_TRANSITION + m
        nearby = [(s, v) for s, v in reward_data if abs(s - target_iter) <= 5]
        if nearby:
            closest = min(nearby, key=lambda x: abs(x[0] - target_iter))
            print(f"  iter {closest[0]:5d} (+{closest[0]-PHASE_TRANSITION:4d}): reward={closest[1]:8.1f}")

# ── 7. 종합 판정 ──
print(f"\n{'─' * 70}")
print("7. V19 종합 판정")
print(f"{'─' * 70}")

if p1_end and p2_start and vl_post:
    shock_magnitude = max(v for _, v in vl_post)
    reward_drop = p2_min_reward - p1_last_reward
    final_reward = reward_data[-1][1]
    recovery_ratio = (final_reward - p2_min_reward) / abs(reward_drop) * 100 if abs(reward_drop) > 1 else 0

    print(f"  Critic shock 규모: value_loss {shock_magnitude:.0f}")
    print(f"  Reward 급락: {reward_drop:.0f}")
    print(f"  회복률 (마지막 기준): {recovery_ratio:.0f}%")
    print(f"  ep_len 유지: {'예' if ep_post_min >= 240 else '아니오'}")
    print()
    if shock_magnitude > 500:
        print("  ❌ 심각한 critic shock — hard switch의 전형적인 문제")
    elif shock_magnitude > 100:
        print("  ⚠️ 중간 수준 critic shock")
    else:
        print("  ✅ critic shock 경미")

print(f"\n{'=' * 70}")
print("  V19 분석 완료")
print(f"{'=' * 70}")
