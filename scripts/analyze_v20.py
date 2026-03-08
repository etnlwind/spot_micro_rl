#!/usr/bin/env python3
"""V20 Training Analysis — Soft-Ramp Curriculum (V19 대비 비교 포함).

Ramp 1 (STAND→WALK): iter 1500~3000  (alpha12: 0→1)
Ramp 2 (WALK→TROT):  iter 5500~8000  (alpha23: 0→1)
Metric gating: ep_len < 200이면 ramp pause

핵심 분석 (리뷰어 요청):
  1. Ramp 구간 value_loss peak — V19 대비 얼마나 줄었는지
  2. Raw gait 유지 — trot_gait, leg_lift, foot_clearance, forward_velocity
  3. Raw penalty 적응 — joint_vel_l2, dof_acc_l2, action_rate_l2
  4. Reward 안정성 — 급락폭, 회복 속도
"""
import os
import sys

# ── 경로 설정 ──
LOG_DIR = os.path.join(os.path.dirname(__file__), "..",
                       "logs", "rsl_rl", "spot_micro_flat", "2026-03-08_17-34-49")
LOG_DIR = os.path.normpath(LOG_DIR)

V19_LOG_DIR = os.path.join(os.path.dirname(__file__), "..",
                           "logs", "rsl_rl", "spot_micro_flat", "2026-03-08_15-14-15")
V19_LOG_DIR = os.path.normpath(V19_LOG_DIR)

if not os.path.exists(LOG_DIR):
    print(f"ERROR: V20 log directory not found: {LOG_DIR}")
    sys.exit(1)

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

ea = EventAccumulator(LOG_DIR)
ea.Reload()

# V19 비교용
v19_ea = None
if os.path.exists(V19_LOG_DIR):
    v19_ea = EventAccumulator(V19_LOG_DIR)
    v19_ea.Reload()

def get_scalars(acc, tag):
    if tag not in acc.Tags()["scalars"]:
        return []
    return [(e.step, e.value) for e in acc.Scalars(tag)]

# ── V20 Ramp 구간 정의 ──
RAMP1_START = 1500
RAMP1_END = 3000
RAMP2_START = 5500
RAMP2_END = 8000

# ── V20 Phase 가중치 (alpha 보간이므로 phase 경계에서의 기대값) ──
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
PHASE3_WEIGHTS = {
    "standing_height": 3.0, "height_bonus": 7.0, "forward_velocity_bootstrap": 0.0,
    "forward_velocity": 12.0, "same_side_penalty": -30.0, "rear_both_ground": -80.0,
    "undesired_contacts": -100.0, "feet_below_knees": -150.0, "trot_gait": 40.0,
    "rear_joint_frozen": -60.0, "diagonal_coupling": 25.0, "gait_cycle_period": 15.0,
    "stride_length": 12.0, "foot_clearance": 8.0, "joint_vel_l2": -1.0,
    "action_rate_l2": -3.0, "flat_orientation_l2": -7.0, "shoulder_neutral": -6.0,
    "dof_acc_l2": -5.0e-06, "joint_oscillation": -20.0, "stance_propulsion": 20.0,
}
CONSTANT_WEIGHTS = {"leg_lift": 15.0, "rear_forward_stride": 10.0}

def get_weight_v20(term, step):
    """V20 soft-ramp alpha 보간 가중치."""
    if term in CONSTANT_WEIGHTS:
        return CONSTANT_WEIGHTS[term]
    w1 = PHASE1_WEIGHTS.get(term)
    w2 = PHASE2_WEIGHTS.get(term)
    w3 = PHASE3_WEIGHTS.get(term)
    if w1 is None:
        return None
    # alpha12
    if step <= RAMP1_START:
        alpha12 = 0.0
    elif step >= RAMP1_END:
        alpha12 = 1.0
    else:
        alpha12 = (step - RAMP1_START) / (RAMP1_END - RAMP1_START)
    # alpha23
    if step <= RAMP2_START:
        alpha23 = 0.0
    elif step >= RAMP2_END:
        alpha23 = 1.0
    else:
        alpha23 = (step - RAMP2_START) / (RAMP2_END - RAMP2_START)
    # interpolate
    if alpha23 > 0:
        return w2 + alpha23 * (w3 - w2)
    return w1 + alpha12 * (w2 - w1)


reward_data = get_scalars(ea, "Train/mean_reward")
ep_len_data = get_scalars(ea, "Train/mean_episode_length")
vl_data = get_scalars(ea, "Loss/value_function")
noise_data = get_scalars(ea, "Policy/mean_noise_std")

last_iter = reward_data[-1][0] if reward_data else 0

print("=" * 70)
print("  V20 Training Analysis — Soft-Ramp Curriculum")
print(f"  Log: {LOG_DIR}")
print(f"  Current iter: {last_iter}")
print("=" * 70)

# ── 진행 상태 판단 ──
if last_iter < 100:
    print(f"\n  ⚠️ 데이터 부족 (iter {last_iter}). 최소 500 iter 이후 재실행 권장.")
    print("=" * 70)
    sys.exit(0)

# ── 1. 전체 훈련 개요 ──
print(f"\n{'─' * 70}")
print("1. 전체 훈련 개요")
print(f"{'─' * 70}")
print(f"  총 iteration: {last_iter}")
print(f"  최종 reward: {reward_data[-1][1]:.1f}")
print(f"  최종 ep_len: {ep_len_data[-1][1]:.1f}")
print(f"  최종 value_loss: {vl_data[-1][1]:.2f}")
if noise_data:
    print(f"  최종 noise_std: {noise_data[-1][1]:.4f}")

# Phase 상태 판단
if last_iter < RAMP1_START:
    phase_str = "Phase 1 (STAND) — ramp 시작 전"
elif last_iter < RAMP1_END:
    alpha = (last_iter - RAMP1_START) / (RAMP1_END - RAMP1_START)
    phase_str = f"Ramp 1→2 ({alpha:.0%}) — STAND→WALK 보간 중"
elif last_iter < RAMP2_START:
    phase_str = "Phase 2 (WALK) — ramp 2 대기"
elif last_iter < RAMP2_END:
    alpha = (last_iter - RAMP2_START) / (RAMP2_END - RAMP2_START)
    phase_str = f"Ramp 2→3 ({alpha:.0%}) — WALK→TROT 보간 중"
else:
    phase_str = "Phase 3 (TROT) — 최종"
print(f"  현재 상태: {phase_str}")

# ── 2. Ramp 1 구간 분석 (iter 1500~3000) — V19 비교 ──
print(f"\n{'─' * 70}")
print("2. Ramp 1 구간 분석 (STAND→WALK 전환) — V19 비교")
print(f"{'─' * 70}")

if last_iter >= RAMP1_START:
    # V20: ramp 구간 value_loss
    vl_ramp1 = [(s, v) for s, v in vl_data if RAMP1_START <= s <= min(RAMP1_END, last_iter)]
    vl_pre_ramp1 = [(s, v) for s, v in vl_data if RAMP1_START - 100 <= s < RAMP1_START]

    if vl_pre_ramp1:
        vl_pre_avg = sum(v for _, v in vl_pre_ramp1) / len(vl_pre_ramp1)
        print(f"  V20 ramp 직전 value_loss 평균: {vl_pre_avg:.2f}")
    if vl_ramp1:
        vl_ramp_max = max(v for _, v in vl_ramp1)
        vl_ramp_max_iter = [s for s, v in vl_ramp1 if v == vl_ramp_max][0]
        print(f"  V20 ramp 중 value_loss 최대: {vl_ramp_max:.2f} @ iter {vl_ramp_max_iter}")

    # V19 비교
    if v19_ea:
        v19_vl = get_scalars(v19_ea, "Loss/value_function")
        v19_vl_transition = [(s, v) for s, v in v19_vl if 2000 <= s < 2200]
        if v19_vl_transition:
            v19_peak = max(v for _, v in v19_vl_transition)
            print(f"\n  V19 hard switch value_loss peak: {v19_peak:.2f}")
            if vl_ramp1:
                ratio = vl_ramp_max / v19_peak * 100 if v19_peak > 0 else 0
                reduction = 100 - ratio
                print(f"  V20 vs V19 peak: {ratio:.0f}% ({reduction:+.0f}% 감소)")
                if reduction > 50:
                    print(f"  ✅ critic shock 대폭 감소!")
                elif reduction > 20:
                    print(f"  📈 critic shock 개선")
                elif reduction > 0:
                    print(f"  → 소폭 개선")
                else:
                    print(f"  ⚠️ 개선 없음 또는 악화")

    # Reward 변화
    rw_pre_ramp = [(s, v) for s, v in reward_data if RAMP1_START - 100 <= s < RAMP1_START]
    rw_ramp = [(s, v) for s, v in reward_data if RAMP1_START <= s <= min(RAMP1_END, last_iter)]

    if rw_pre_ramp and rw_ramp:
        rw_pre_avg = sum(v for _, v in rw_pre_ramp) / len(rw_pre_ramp)
        rw_ramp_min = min(v for _, v in rw_ramp)
        rw_drop = rw_ramp_min - rw_pre_avg
        print(f"\n  V20 reward 변화:")
        print(f"    ramp 직전 평균: {rw_pre_avg:.1f}")
        print(f"    ramp 중 최저: {rw_ramp_min:.1f}")
        print(f"    급락폭: {rw_drop:.1f}")

        # V19 비교
        if v19_ea:
            v19_rw = get_scalars(v19_ea, "Train/mean_reward")
            v19_pre = [(s, v) for s, v in v19_rw if 1900 <= s < 2000]
            v19_post = [(s, v) for s, v in v19_rw if 2000 <= s < 2200]
            if v19_pre and v19_post:
                v19_pre_avg = sum(v for _, v in v19_pre) / len(v19_pre)
                v19_min = min(v for _, v in v19_post)
                v19_drop = v19_min - v19_pre_avg
                print(f"\n  V19 reward 변화:")
                print(f"    전환 직전 평균: {v19_pre_avg:.1f}")
                print(f"    전환 직후 최저: {v19_min:.1f}")
                print(f"    급락폭: {v19_drop:.1f}")
                if abs(v19_drop) > 1:
                    improve = (1 - abs(rw_drop) / abs(v19_drop)) * 100
                    print(f"\n  급락폭 개선: {improve:+.0f}%")
else:
    print(f"  아직 Ramp 1 시작 전 (현재 iter {last_iter}, 시작: {RAMP1_START})")

# ── 3. Raw Gait Metrics ──
print(f"\n{'─' * 70}")
print("3. Raw Gait Metrics")
print(f"{'─' * 70}")

GAIT_TERMS = ["forward_velocity", "trot_gait", "diagonal_coupling", "leg_lift", "foot_clearance"]

# 분석 window 결정
if last_iter >= RAMP1_START:
    window_label = f"Ramp 1 전후 ({RAMP1_START-100}~{min(RAMP1_END, last_iter)})"
    pre_range = (RAMP1_START - 100, RAMP1_START)
    post_range = (RAMP1_START, min(RAMP1_START + 200, last_iter))
else:
    # Phase 1만 있는 경우 — 초기 vs 최근
    mid = max(50, last_iter // 2)
    window_label = f"Phase 1 초기 vs 최근 (0~{mid} vs {mid}~{last_iter})"
    pre_range = (0, mid)
    post_range = (mid, last_iter)

print(f"  분석 window: {window_label}")

for term in GAIT_TERMS:
    tag = f"Episode_Reward/{term}"
    data = get_scalars(ea, tag)
    if not data:
        continue

    pre_data = [(s, v) for s, v in data if pre_range[0] <= s < pre_range[1]]
    post_data = [(s, v) for s, v in data if post_range[0] <= s <= post_range[1]]

    if pre_data and post_data:
        pre_weighted = sum(v for _, v in pre_data) / len(pre_data)
        post_weighted = sum(v for _, v in post_data) / len(post_data)

        # weighted → raw
        pre_step = (pre_range[0] + pre_range[1]) // 2
        post_step = (post_range[0] + post_range[1]) // 2
        w_pre = get_weight_v20(term, pre_step)
        w_post = get_weight_v20(term, post_step)

        raw_pre = pre_weighted / w_pre if w_pre and abs(w_pre) > 1e-8 else 0.0
        raw_post = post_weighted / w_post if w_post and abs(w_post) > 1e-8 else 0.0

        delta = raw_post - raw_pre
        pct = (delta / abs(raw_pre) * 100) if abs(raw_pre) > 1e-8 else 0
        status = "✅ 유지" if abs(pct) < 10 else ("⚠️ 하락" if pct < -10 else "📈 상승")

        print(f"  {term}:")
        print(f"    raw: {raw_pre:.4f} → {raw_post:.4f} (Δ={delta:+.4f}, {pct:+.1f}%) {status}")

# ── 4. Raw Penalty Metrics ──
print(f"\n{'─' * 70}")
print("4. Raw Penalty Metrics")
print(f"{'─' * 70}")

PENALTY_TERMS = ["joint_vel_l2", "dof_acc_l2", "action_rate_l2", "flat_orientation_l2", "shoulder_neutral"]

for term in PENALTY_TERMS:
    tag = f"Episode_Reward/{term}"
    data = get_scalars(ea, tag)
    if not data:
        continue

    pre_data = [(s, v) for s, v in data if pre_range[0] <= s < pre_range[1]]
    post_data = [(s, v) for s, v in data if post_range[0] <= s <= post_range[1]]

    if pre_data and post_data:
        pre_weighted = sum(v for _, v in pre_data) / len(pre_data)
        post_weighted = sum(v for _, v in post_data) / len(post_data)

        pre_step = (pre_range[0] + pre_range[1]) // 2
        post_step = (post_range[0] + post_range[1]) // 2
        w_pre = get_weight_v20(term, pre_step)
        w_post = get_weight_v20(term, post_step)

        raw_pre = pre_weighted / w_pre if w_pre and abs(w_pre) > 1e-8 else 0.0
        raw_post = post_weighted / w_post if w_post and abs(w_post) > 1e-8 else 0.0

        delta = raw_post - raw_pre
        pct = (delta / abs(raw_pre) * 100) if abs(raw_pre) > 1e-8 else 0
        status = "✅ 개선" if pct < -5 else ("⚠️ 악화" if pct > 10 else "→ 유지")

        print(f"  {term}:")
        print(f"    raw: {raw_pre:.6f} → {raw_post:.6f} (Δ={delta:+.6f}, {pct:+.1f}%) {status}")

# ── 5. Episode Length 안정성 ──
print(f"\n{'─' * 70}")
print("5. Episode Length 안정성")
print(f"{'─' * 70}")

ep_pre = [(s, v) for s, v in ep_len_data if pre_range[0] <= s < pre_range[1]]
ep_post = [(s, v) for s, v in ep_len_data if post_range[0] <= s <= post_range[1]]

if ep_pre:
    ep_pre_avg = sum(v for _, v in ep_pre) / len(ep_pre)
    print(f"  pre 평균: {ep_pre_avg:.1f}")
if ep_post:
    ep_post_avg = sum(v for _, v in ep_post) / len(ep_post)
    ep_post_min = min(v for _, v in ep_post)
    print(f"  post 평균: {ep_post_avg:.1f}")
    print(f"  post 최저: {ep_post_min:.1f}")
    if ep_pre:
        pct = ep_post_min / ep_pre_avg * 100
        print(f"  생존율: {pct:.0f}%")

# ── 6. Ramp 2 구간 분석 (iter 5500~8000) ──
print(f"\n{'─' * 70}")
print("6. Ramp 2 구간 분석 (WALK→TROT 전환)")
print(f"{'─' * 70}")

if last_iter >= RAMP2_START:
    vl_ramp2 = [(s, v) for s, v in vl_data if RAMP2_START <= s <= min(RAMP2_END, last_iter)]
    vl_pre_ramp2 = [(s, v) for s, v in vl_data if RAMP2_START - 100 <= s < RAMP2_START]

    if vl_pre_ramp2:
        vl_pre_avg2 = sum(v for _, v in vl_pre_ramp2) / len(vl_pre_ramp2)
        print(f"  ramp 직전 value_loss 평균: {vl_pre_avg2:.2f}")
    if vl_ramp2:
        vl_ramp2_max = max(v for _, v in vl_ramp2)
        print(f"  ramp 중 value_loss 최대: {vl_ramp2_max:.2f}")
        if vl_pre_ramp2:
            print(f"  spike 배율: {vl_ramp2_max / vl_pre_avg2:.1f}x")

    rw_pre_r2 = [(s, v) for s, v in reward_data if RAMP2_START - 100 <= s < RAMP2_START]
    rw_ramp2 = [(s, v) for s, v in reward_data if RAMP2_START <= s <= min(RAMP2_END, last_iter)]
    if rw_pre_r2 and rw_ramp2:
        rw_pre_avg2 = sum(v for _, v in rw_pre_r2) / len(rw_pre_r2)
        rw_ramp2_min = min(v for _, v in rw_ramp2)
        print(f"  reward: {rw_pre_avg2:.1f} → 최저 {rw_ramp2_min:.1f} (Δ={rw_ramp2_min - rw_pre_avg2:.1f})")
else:
    print(f"  아직 Ramp 2 시작 전 (현재 iter {last_iter}, 시작: {RAMP2_START})")

# ── 7. 리뷰어 성공 기준 체크 ──
print(f"\n{'─' * 70}")
print("7. 리뷰어 성공 기준 체크")
print(f"{'─' * 70}")

print("  기대 성공 패턴:")
print("    ① ramp 구간 reward 급락폭 < V19의 50%")
print("    ② value_loss spike < 150")
print("    ③ ep_len 유지")
print("    ④ raw gait metrics 유지")
print("    ⑤ raw penalty metrics 점진 개선")

if last_iter >= RAMP1_START + 100:
    checks = []
    # ① reward 급락폭
    rw_pre = [(s, v) for s, v in reward_data if RAMP1_START - 100 <= s < RAMP1_START]
    rw_post = [(s, v) for s, v in reward_data if RAMP1_START <= s < RAMP1_START + 200]
    if rw_pre and rw_post:
        drop_v20 = min(v for _, v in rw_post) - sum(v for _, v in rw_pre) / len(rw_pre)
        # V19 drop was about -830 (502 → -331)
        v19_drop = -830  # approximate from V19 data
        if v19_ea:
            v19_rw = get_scalars(v19_ea, "Train/mean_reward")
            v19_pre = [(s, v) for s, v in v19_rw if 1900 <= s < 2000]
            v19_post = [(s, v) for s, v in v19_rw if 2000 <= s < 2200]
            if v19_pre and v19_post:
                v19_drop = min(v for _, v in v19_post) - sum(v for _, v in v19_pre) / len(v19_pre)
        ratio = abs(drop_v20) / abs(v19_drop) * 100 if abs(v19_drop) > 1 else 0
        ok = ratio < 50
        checks.append(("① reward 급락폭 < V19의 50%", ok, f"V20: {drop_v20:.0f}, V19: {v19_drop:.0f} ({ratio:.0f}%)"))

    # ② value_loss spike
    vl_ramp = [(s, v) for s, v in vl_data if RAMP1_START <= s < min(RAMP1_END, last_iter)]
    if vl_ramp:
        peak = max(v for _, v in vl_ramp)
        ok = peak < 150
        checks.append(("② value_loss spike < 150", ok, f"{peak:.1f}"))

    # ③ ep_len 유지
    ep_ramp = [(s, v) for s, v in ep_len_data if RAMP1_START <= s <= min(RAMP1_END, last_iter)]
    if ep_ramp:
        ep_min = min(v for _, v in ep_ramp)
        ok = ep_min >= 200
        checks.append(("③ ep_len >= 200", ok, f"최저 {ep_min:.0f}"))

    for label, passed, detail in checks:
        icon = "✅" if passed else "❌"
        print(f"\n  {icon} {label}")
        print(f"     {detail}")
else:
    print(f"\n  데이터 부족 (iter {last_iter}) — Ramp 1 시작({RAMP1_START}) + 100 iter 이후 재실행")

# ── 8. Reward 추이 (주요 milestone) ──
print(f"\n{'─' * 70}")
print("8. Reward 추이 (주요 milestone)")
print(f"{'─' * 70}")

milestones = [0, 100, 500, 1000, 1500, 1750, 2000, 2250, 2500, 3000, 4000, 5000, 5500, 6000, 7000, 8000, 10000, 15000]
for m in milestones:
    if m > last_iter:
        break
    nearby = [(s, v) for s, v in reward_data if abs(s - m) <= 10]
    if nearby:
        closest = min(nearby, key=lambda x: abs(x[0] - m))
        # phase indicator
        if closest[0] < RAMP1_START:
            phase = "P1"
        elif closest[0] < RAMP1_END:
            phase = "R1→2"
        elif closest[0] < RAMP2_START:
            phase = "P2"
        elif closest[0] < RAMP2_END:
            phase = "R2→3"
        else:
            phase = "P3"
        print(f"  iter {closest[0]:5d} [{phase:5s}]: reward={closest[1]:8.1f}")

print(f"\n{'=' * 70}")
print("  V20 분석 완료")
print(f"{'=' * 70}")
