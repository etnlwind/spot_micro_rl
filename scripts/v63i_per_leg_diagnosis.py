"""V63.I per-leg 대각선 편향 진단 스크립트.

V63.I TensorBoard 로그에서 per-leg 메트릭을 추출해
Pair A (FL+RR) vs Pair B (FR+RL) 편차를 분석한다.

진단 목표:
1. 편향이 훈련 초기부터 있었는지, 중간에 발생했는지
2. 어떤 메트릭(contact, propulsion, joint error)에서 편향이 먼저 나타나는지
3. 물리적 원인(joint error 비대칭)인지 정책 원인(contact/propulsion 편향)인지
"""
import sys
from pathlib import Path
from collections import defaultdict

try:
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
except ImportError:
    print("tensorboard not found, trying tbparse...")
    EventAccumulator = None

LOG_DIR = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-10_02-14-50_V63.I")

# Per-leg metrics to extract
METRICS = {
    # Contact ratio per leg
    "contact_ratio_fl": "Episode_Reward/contact_ratio_fl",
    "contact_ratio_fr": "Episode_Reward/contact_ratio_fr",
    "contact_ratio_rl": "Episode_Reward/contact_ratio_rl",
    "contact_ratio_rr": "Episode_Reward/contact_ratio_rr",
    # Propulsion per leg
    "propulsion_fl": "Episode_Reward/propulsion_fl",
    "propulsion_fr": "Episode_Reward/propulsion_fr",
    "propulsion_rl": "Episode_Reward/propulsion_rl",
    "propulsion_rr": "Episode_Reward/propulsion_rr",
    # Leg lift per leg
    "leg_lift_fl": "Episode_Reward/leg_lift_fl",
    "leg_lift_fr": "Episode_Reward/leg_lift_fr",
    "leg_lift_rl": "Episode_Reward/leg_lift_rl",
    "leg_lift_rr": "Episode_Reward/leg_lift_rr",
    # Clearance per leg
    "clearance_fl": "Episode_Reward/clearance_fl",
    "clearance_fr": "Episode_Reward/clearance_fr",
    "clearance_rl": "Episode_Reward/clearance_rl",
    "clearance_rr": "Episode_Reward/clearance_rr",
    # Stance/swing time
    "stance_time_fl": "Episode_Reward/stance_time_fl",
    "stance_time_fr": "Episode_Reward/stance_time_fr",
    "stance_time_rl": "Episode_Reward/stance_time_rl",
    "stance_time_rr": "Episode_Reward/stance_time_rr",
    "swing_time_fl": "Episode_Reward/swing_time_fl",
    "swing_time_fr": "Episode_Reward/swing_time_fr",
    "swing_time_rl": "Episode_Reward/swing_time_rl",
    "swing_time_rr": "Episode_Reward/swing_time_rr",
    # Overall
    "mean_reward": "Train/mean_reward",
    "ep_len": "Train/mean_episode_length",
    "timeout": "Episode_Termination/time_out",
}


def load_tb_data(log_dir):
    """Load TensorBoard data using EventAccumulator."""
    ea = EventAccumulator(str(log_dir), size_guidance={"scalars": 0})
    ea.Reload()
    available_tags = ea.Tags().get("scalars", [])

    data = {}
    for key, tag in METRICS.items():
        if tag in available_tags:
            events = ea.Scalars(tag)
            steps = [e.step for e in events]
            values = [e.value for e in events]
            data[key] = {"steps": steps, "values": values}
        else:
            # Try without Episode_Reward/ prefix
            pass

    return data, available_tags


def analyze_diagonal_bias(data):
    """Analyze Pair A (FL+RR) vs Pair B (FR+RL) divergence."""

    print("=" * 70)
    print("V63.I PER-LEG DIAGONAL BIAS DIAGNOSIS")
    print("=" * 70)

    # 1. Contact ratio timeline
    print("\n--- 1. Contact Ratio Timeline (Pair A=FL+RR vs Pair B=FR+RL) ---")
    if all(f"contact_ratio_{x}" in data for x in ["fl", "fr", "rl", "rr"]):
        fl = data["contact_ratio_fl"]
        fr = data["contact_ratio_fr"]
        rl = data["contact_ratio_rl"]
        rr = data["contact_ratio_rr"]

        # Sample at key iterations
        checkpoints = [100, 300, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 4999]

        print(f"{'iter':>6}  {'FL':>6} {'FR':>6} {'RL':>6} {'RR':>6}  {'PairA':>6} {'PairB':>6} {'diff':>6}  {'L':>6} {'R':>6} {'LR_d':>6}")
        print("-" * 90)

        for cp in checkpoints:
            # Find closest step
            idx_fl = _find_closest(fl["steps"], cp)
            idx_fr = _find_closest(fr["steps"], cp)
            idx_rl = _find_closest(rl["steps"], cp)
            idx_rr = _find_closest(rr["steps"], cp)

            if idx_fl is None:
                continue

            v_fl = fl["values"][idx_fl]
            v_fr = fr["values"][idx_fr]
            v_rl = rl["values"][idx_rl]
            v_rr = rr["values"][idx_rr]

            pair_a = v_fl + v_rr
            pair_b = v_fr + v_rl
            pair_diff = pair_a - pair_b

            left = v_fl + v_rl
            right = v_fr + v_rr
            lr_diff = left - right

            actual_step = fl["steps"][idx_fl]
            print(f"{actual_step:>6}  {v_fl:>6.3f} {v_fr:>6.3f} {v_rl:>6.3f} {v_rr:>6.3f}"
                  f"  {pair_a:>6.3f} {pair_b:>6.3f} {pair_diff:>+6.3f}"
                  f"  {left:>6.3f} {right:>6.3f} {lr_diff:>+6.3f}")

    # 2. Propulsion per leg
    print("\n--- 2. Propulsion Timeline ---")
    if all(f"propulsion_{x}" in data for x in ["fl", "fr", "rl", "rr"]):
        fl = data["propulsion_fl"]
        fr = data["propulsion_fr"]
        rl = data["propulsion_rl"]
        rr = data["propulsion_rr"]

        print(f"{'iter':>6}  {'FL':>6} {'FR':>6} {'RL':>6} {'RR':>6}  {'PairA':>6} {'PairB':>6} {'diff':>6}")
        print("-" * 70)

        for cp in checkpoints:
            idx = _find_closest(fl["steps"], cp)
            if idx is None:
                continue
            v_fl = fl["values"][idx]
            v_fr = fr["values"][_find_closest(fr["steps"], cp)]
            v_rl = rl["values"][_find_closest(rl["steps"], cp)]
            v_rr = rr["values"][_find_closest(rr["steps"], cp)]

            pair_a = v_fl + v_rr
            pair_b = v_fr + v_rl
            step = fl["steps"][idx]
            print(f"{step:>6}  {v_fl:>6.3f} {v_fr:>6.3f} {v_rl:>6.3f} {v_rr:>6.3f}"
                  f"  {pair_a:>6.3f} {pair_b:>6.3f} {pair_a - pair_b:>+6.3f}")

    # 3. Leg lift per leg
    print("\n--- 3. Leg Lift Timeline ---")
    if all(f"leg_lift_{x}" in data for x in ["fl", "fr", "rl", "rr"]):
        fl = data["leg_lift_fl"]
        fr = data["leg_lift_fr"]
        rl = data["leg_lift_rl"]
        rr = data["leg_lift_rr"]

        print(f"{'iter':>6}  {'FL':>6} {'FR':>6} {'RL':>6} {'RR':>6}  {'PairA':>6} {'PairB':>6} {'diff':>6}")
        print("-" * 70)

        for cp in checkpoints:
            idx = _find_closest(fl["steps"], cp)
            if idx is None:
                continue
            v_fl = fl["values"][idx]
            v_fr = fr["values"][_find_closest(fr["steps"], cp)]
            v_rl = rl["values"][_find_closest(rl["steps"], cp)]
            v_rr = rr["values"][_find_closest(rr["steps"], cp)]

            pair_a = v_fl + v_rr
            pair_b = v_fr + v_rl
            step = fl["steps"][idx]
            print(f"{step:>6}  {v_fl:>6.3f} {v_fr:>6.3f} {v_rl:>6.3f} {v_rr:>6.3f}"
                  f"  {pair_a:>6.3f} {pair_b:>6.3f} {pair_a - pair_b:>+6.3f}")

    # 4. Stance time per leg
    print("\n--- 4. Stance Time Timeline ---")
    if all(f"stance_time_{x}" in data for x in ["fl", "fr", "rl", "rr"]):
        fl = data["stance_time_fl"]
        fr = data["stance_time_fr"]
        rl = data["stance_time_rl"]
        rr = data["stance_time_rr"]

        print(f"{'iter':>6}  {'FL':>6} {'FR':>6} {'RL':>6} {'RR':>6}  {'PairA':>6} {'PairB':>6} {'diff':>6}")
        print("-" * 70)

        for cp in checkpoints:
            idx = _find_closest(fl["steps"], cp)
            if idx is None:
                continue
            v_fl = fl["values"][idx]
            v_fr = fr["values"][_find_closest(fr["steps"], cp)]
            v_rl = rl["values"][_find_closest(rl["steps"], cp)]
            v_rr = rr["values"][_find_closest(rr["steps"], cp)]

            pair_a = v_fl + v_rr
            pair_b = v_fr + v_rl
            step = fl["steps"][idx]
            print(f"{step:>6}  {v_fl:>6.3f} {v_fr:>6.3f} {v_rl:>6.3f} {v_rr:>6.3f}"
                  f"  {pair_a:>6.3f} {pair_b:>6.3f} {pair_a - pair_b:>+6.3f}")

    # 5. Overall metrics
    print("\n--- 5. Overall ---")
    if "mean_reward" in data and "timeout" in data:
        rw = data["mean_reward"]
        to = data["timeout"]

        print(f"{'iter':>6}  {'reward':>8} {'timeout':>8}")
        print("-" * 30)
        for cp in checkpoints:
            idx_r = _find_closest(rw["steps"], cp)
            idx_t = _find_closest(to["steps"], cp)
            if idx_r is None:
                continue
            print(f"{rw['steps'][idx_r]:>6}  {rw['values'][idx_r]:>8.1f} {to['values'][idx_t]:>8.4f}")

    # 6. Summary analysis
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if all(f"contact_ratio_{x}" in data for x in ["fl", "fr", "rl", "rr"]):
        fl_vals = data["contact_ratio_fl"]["values"]
        fr_vals = data["contact_ratio_fr"]["values"]
        rl_vals = data["contact_ratio_rl"]["values"]
        rr_vals = data["contact_ratio_rr"]["values"]

        n = len(fl_vals)
        # First quartile (iter 0-1250)
        q1 = n // 4
        # Last quartile (iter 3750-5000)
        q3 = 3 * n // 4

        def avg_slice(vals, start, end):
            return sum(vals[start:end]) / max(1, end - start)

        print("\nContact ratio phase averages:")
        print(f"  Early (Q1):  FL={avg_slice(fl_vals,0,q1):.3f}  FR={avg_slice(fr_vals,0,q1):.3f}"
              f"  RL={avg_slice(rl_vals,0,q1):.3f}  RR={avg_slice(rr_vals,0,q1):.3f}")
        print(f"  Late  (Q4):  FL={avg_slice(fl_vals,q3,n):.3f}  FR={avg_slice(fr_vals,q3,n):.3f}"
              f"  RL={avg_slice(rl_vals,q3,n):.3f}  RR={avg_slice(rr_vals,q3,n):.3f}")

        early_a = avg_slice(fl_vals,0,q1) + avg_slice(rr_vals,0,q1)
        early_b = avg_slice(fr_vals,0,q1) + avg_slice(rl_vals,0,q1)
        late_a = avg_slice(fl_vals,q3,n) + avg_slice(rr_vals,q3,n)
        late_b = avg_slice(fr_vals,q3,n) + avg_slice(rl_vals,q3,n)

        print(f"\n  Early diagonal diff (PairA-PairB): {early_a - early_b:+.3f}")
        print(f"  Late  diagonal diff (PairA-PairB): {late_a - late_b:+.3f}")

        if abs(early_a - early_b) < 0.05 and abs(late_a - late_b) > 0.10:
            print("\n  >>> FINDING: Diagonal bias EMERGED during training (not from start)")
            print("  >>> Likely cause: POLICY learned preference, not physical asymmetry")
        elif abs(early_a - early_b) > 0.05:
            print("\n  >>> FINDING: Diagonal bias EXISTS from early training")
            print("  >>> Possible cause: Phase initialization bias OR physical asymmetry")
        else:
            print("\n  >>> FINDING: No significant diagonal bias detected")


def _find_closest(steps, target):
    """Find index of closest step to target."""
    if not steps:
        return None
    best_idx = 0
    best_diff = abs(steps[0] - target)
    for i, s in enumerate(steps):
        diff = abs(s - target)
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


if __name__ == "__main__":
    print(f"Loading TensorBoard data from: {LOG_DIR}")
    data, tags = load_tb_data(LOG_DIR)
    print(f"Loaded {len(data)} metrics from {len(tags)} available tags")

    # Show available per-leg tags
    per_leg_tags = [t for t in tags if any(x in t for x in ["_fl", "_fr", "_rl", "_rr"])]
    print(f"\nPer-leg tags found: {len(per_leg_tags)}")

    analyze_diagonal_bias(data)
