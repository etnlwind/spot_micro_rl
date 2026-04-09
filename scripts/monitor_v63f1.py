"""V63.F.1 전용 모니터링.

V63.F 대비 변경:
- joint_target weight: 8.0 → 5.0 (dominant 해제)
- phase_contact weight: 3.0 → 6.0 (복원)
- propulsion weight: 1.0 → 2.0
- anti_phase_contact: metric(1e-4) → REWARD(3.0) 승격 ← 핵심
- clearance/leg_usage_cv: 1e-4 metric 유지

판정 기준 강화:
- joint_target raw ≥ 0.5 AND anti_phase raw ≥ 0.3 → SATISFIED
- joint_target raw < 0.05 → UNSATISFIED (재시작)
- 그 외 WATCH
"""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

# V63.F.1 weights
W_JOINT = 5.0
W_PHASE_CT = 6.0
W_PROPUL = 2.0
W_FEET_AIR = 4.0
W_ANTI_PHASE = 3.0  # 승격
W_CLEARANCE = 1e-4
W_LEG_CV = 1e-4

V63F_PEAK = 0.7473  # V63.F joint_target peak
V63F_ANTI_PHASE_FINAL = 0.043  # V63.F exploit 상태


def latest_run() -> Path | None:
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.F.1")), reverse=True)
    return Path(cands[0]) if cands else None


def last(ea, tag):
    try:
        evs = ea.Scalars(tag)
        return evs[-1].step, evs[-1].value
    except Exception:
        return None, None


def at_steps(ea, tag, targets, tol=100):
    try:
        evs = ea.Scalars(tag)
    except Exception:
        return [None] * len(targets)
    out = []
    for t in targets:
        if not evs:
            out.append(None)
            continue
        closest = min(evs, key=lambda e: abs(e.step - t))
        out.append(closest.value if abs(closest.step - t) <= tol else None)
    return out


def main() -> int:
    run = latest_run()
    if run is None:
        print("[FAIL] V63.F.1 run folder not found")
        return 1

    ea = EventAccumulator(str(run), size_guidance={"scalars": 0})
    ea.Reload()

    if not ea.Tags().get("scalars"):
        print(f"=== Run: {run.name} ===")
        print("[WAIT] scalars 미생성")
        return 0

    step, _ = last(ea, "Train/mean_reward")
    if step is None:
        print("[WAIT]")
        return 0

    print(f"=== Run: {run.name} ===")
    print(f"=== iter {step} ===\n")

    reward_val = last(ea, "Train/mean_reward")[1]
    ep_len_val = last(ea, "Train/mean_episode_length")[1]
    print(f"  Train/mean_reward         = {reward_val:10.4f}")
    print(f"  Train/mean_episode_length = {ep_len_val:10.4f}")

    print("\n=== [주요 reward — weighted / raw] ===")
    _, jt = last(ea, "Episode_Reward/phase_joint_target_linear")
    jt_raw = jt / W_JOINT if jt is not None else None
    if jt_raw is not None:
        print(f"  joint_target raw  = {jt_raw:+.4f}  (weighted {jt:.4f})")

    _, ap = last(ea, "Episode_Reward/metric_anti_phase")
    ap_raw = ap / W_ANTI_PHASE if ap is not None else None
    if ap_raw is not None:
        print(f"  anti_phase raw    = {ap_raw:+.4f}  (weighted {ap:.4f}) ★ 핵심")

    _, pc = last(ea, "Episode_Reward/phase_contact")
    pc_raw = pc / W_PHASE_CT if pc is not None else None
    if pc_raw is not None:
        print(f"  phase_contact raw = {pc_raw:+.4f}")

    _, pr = last(ea, "Episode_Reward/propulsion")
    pr_raw = pr / W_PROPUL if pr is not None else None
    if pr_raw is not None:
        print(f"  propulsion raw    = {pr_raw:+.4f}")

    _, fa = last(ea, "Episode_Reward/feet_air_time")
    fa_raw = fa / W_FEET_AIR if fa is not None else None
    if fa_raw is not None:
        print(f"  feet_air raw      = {fa_raw:+.4f}")

    print("\n=== [관찰 metrics] ===")
    _, cl = last(ea, "Episode_Reward/metric_clearance")
    cl_raw = cl / W_CLEARANCE if cl is not None else None
    if cl_raw is not None:
        print(f"  clearance raw    = {cl_raw:+.4f} m")

    _, lcv = last(ea, "Episode_Reward/metric_leg_usage_cv")
    lcv_raw = lcv / W_LEG_CV if lcv is not None else None
    if lcv_raw is not None:
        print(f"  leg_usage_cv raw = {lcv_raw:+.4f}")

    print("\n=== [Termination %] ===")
    for tag_short, lbl in [
        ("time_out", "timeout"),
        ("bad_orientation", "bad_ori"),
        ("non_toe_contact", "non_toe"),
        ("base_contact", "base_ct"),
        ("min_height", "min_h"),
    ]:
        _, v = last(ea, f"Episode_Termination/{tag_short}")
        if v is not None:
            print(f"  {lbl:12s} = {v*100:8.2f}%")

    # Trend
    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 2500, 3000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n=== Trend (raw) ===")
    print(f"{'iter':>5}: {'reward':>7} {'ep_len':>7} {'joint_tgt':>9} {'anti_ph':>8} {'clear':>7} {'leg_cv':>7}")
    print("-" * 70)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        jtv = at_steps(ea, "Episode_Reward/phase_joint_target_linear", [t])[0]
        apv = at_steps(ea, "Episode_Reward/metric_anti_phase", [t])[0]
        clv = at_steps(ea, "Episode_Reward/metric_clearance", [t])[0]
        lcvv = at_steps(ea, "Episode_Reward/metric_leg_usage_cv", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} "
            f"{f(jtv, '%9.4f', W_JOINT)} {f(apv, '%8.4f', W_ANTI_PHASE)} "
            f"{f(clv, '%7.4f', W_CLEARANCE)} {f(lcvv, '%7.4f', W_LEG_CV)}"
        )

    # 판정
    print("\n=== 자동 판정 ===")
    if jt_raw is None or ap_raw is None:
        decision = "wait"
        print("  [WAIT] 데이터 부족")
    elif jt_raw >= 0.5 and ap_raw >= 0.3:
        decision = "strong_satisfied_real"
        print(f"  [REAL TROT SATISFIED ✓✓✓] jt={jt_raw:.4f}, anti_phase={ap_raw:.4f}")
    elif jt_raw >= 0.5 and ap_raw >= 0.15:
        decision = "watch_high_real"
        print(f"  [WATCH++] jt={jt_raw:.4f}, anti_phase={ap_raw:.4f} (trot 진전)")
    elif jt_raw >= 0.5 and ap_raw < 0.1:
        decision = "exploit_detected"
        print(f"  [EXPLOIT DETECTED] jt={jt_raw:.4f} OK, but anti_phase={ap_raw:.4f} (< 0.1)")
    elif jt_raw >= 0.25:
        decision = "watch"
        print(f"  [WATCH] jt={jt_raw:.4f}, anti_phase={ap_raw:.4f}")
    elif jt_raw >= 0.05:
        decision = "watch_low"
        print(f"  [WATCH-] jt={jt_raw:.4f} (초기 단계)")
    else:
        decision = "unsatisfied"
        print(f"  [UNSATISFIED] jt={jt_raw:.4f} < 0.05")

    print(f"\n>>> DECISION: {decision.upper()} <<<")

    if jt_raw is not None and ap_raw is not None:
        print(f"\n[V63.F vs V63.F.1 비교]")
        print(f"  V63.F (iter 1465) : jt=0.6964  anti_phase=0.0430  (exploit)")
        print(f"  V63.F.1 (iter {step:>4}): jt={jt_raw:.4f}  anti_phase={ap_raw:.4f}")
        if ap_raw > V63F_ANTI_PHASE_FINAL:
            print(f"  ✓ anti_phase 개선 +{ap_raw - V63F_ANTI_PHASE_FINAL:.4f}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
