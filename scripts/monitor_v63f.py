"""V63.F 전용 모니터링 — Codex 신뢰 지표 위주 + 3 metrics."""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

W_JOINT = 8.0
W_PHASE_CT = 3.0
W_PROPUL = 1.0
W_FEET_AIR = 4.0
W_METRIC = 1e-4

V63B_JT_PEAK = 0.54
V63E1_JT_LAST = 0.1507  # iter 1177 실제


def latest_run() -> Path | None:
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.F")), reverse=True)
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
        print("[FAIL] V63.F run folder not found")
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

    print("\n=== [Codex 신뢰 높은 지표] ===")
    _, v = last(ea, "Episode_Reward/phase_joint_target_linear")
    jt_raw = v / W_JOINT if v is not None else None
    if jt_raw is not None:
        print(f"  joint_target raw       = {jt_raw:+.4f}  (weighted {v:.4f})")

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

    print("\n=== [V63.F 3 Metrics] ===")
    metric_vals = {}
    for tag_short, lbl in [
        ("metric_clearance", "clearance"),
        ("metric_anti_phase", "anti_phase"),
        ("metric_leg_usage_cv", "leg_usage_cv"),
    ]:
        _, v = last(ea, f"Episode_Reward/{tag_short}")
        if v is not None:
            raw = v / W_METRIC
            metric_vals[lbl] = raw
            print(f"  {lbl:15s}: raw = {raw:+.4f}  (weighted {v:.4e})")
        else:
            metric_vals[lbl] = None
            print(f"  {lbl:15s}: MISSING")

    print("\n=== [참고 지표] ===")
    for tag_short, lbl, w in [
        ("phase_contact", "phase_ct", W_PHASE_CT),
        ("propulsion", "propul", W_PROPUL),
        ("feet_air_time", "feet_air", W_FEET_AIR),
    ]:
        _, v = last(ea, f"Episode_Reward/{tag_short}")
        if v is not None:
            raw = v / w if w else v
            print(f"  {lbl:12s}: raw = {raw:+.4f}")

    # Trend
    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 2500, 3000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n=== Trend ===")
    print(f"{'iter':>5}: {'reward':>7} {'ep_len':>7} {'joint_tgt':>9} {'clear':>7} {'anti_ph':>8} {'leg_cv':>7} {'non_toe%':>9}")
    print("-" * 80)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        jt = at_steps(ea, "Episode_Reward/phase_joint_target_linear", [t])[0]
        cl = at_steps(ea, "Episode_Reward/metric_clearance", [t])[0]
        ap = at_steps(ea, "Episode_Reward/metric_anti_phase", [t])[0]
        lcv = at_steps(ea, "Episode_Reward/metric_leg_usage_cv", [t])[0]
        nt = at_steps(ea, "Episode_Termination/non_toe_contact", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} "
            f"{f(jt, '%9.4f', W_JOINT)} {f(cl, '%7.4f', W_METRIC)} "
            f"{f(ap, '%8.4f', W_METRIC)} {f(lcv, '%7.4f', W_METRIC)} "
            f"{f(nt*100 if nt is not None else None, '%7.2f%%')}"
        )

    # Decision
    print("\n=== 자동 판정 ===")
    try:
        evs = ea.Scalars("Episode_Reward/phase_joint_target_linear")
        if len(evs) >= 10:
            recent = [e.value / W_JOINT for e in evs[-10:]]
            trend = recent[-1] - recent[0]
            peak_so_far = max(e.value / W_JOINT for e in evs)
            print(f"  최근 10 iter trend: {recent[0]:.4f} → {recent[-1]:.4f} (Δ{trend:+.4f})")
            print(f"  peak so far: {peak_so_far:.4f}")
    except:
        pass

    if jt_raw is None:
        decision = "wait"
        print("  [WAIT] 데이터 부족")
    elif jt_raw >= 0.5:
        decision = "strong_satisfied"
        print(f"  [STRONG SATISFIED ✓✓] {jt_raw:.4f} ≥ 0.5")
    elif jt_raw >= 0.25:
        decision = "satisfied"
        print(f"  [SATISFIED ✓] {jt_raw:.4f} ≥ 0.25")
    elif jt_raw >= 0.15:
        decision = "watch_high"
        print(f"  [WATCH+] {jt_raw:.4f} — V63.E.1 수준 근접")
    elif jt_raw >= 0.05:
        decision = "watch"
        print(f"  [WATCH] {jt_raw:.4f}")
    else:
        decision = "unsatisfied"
        print(f"  [UNSATISFIED] {jt_raw:.4f} < 0.05")

    print(f"\n>>> DECISION: {decision.upper()} <<<")

    if jt_raw is not None:
        print(f"\n[V63 비교]")
        print(f"  V63.B peak     : {V63B_JT_PEAK:.4f} (foot target 1D)")
        print(f"  V63.E.1 마지막 : {V63E1_JT_LAST:.4f} (iter 1177)")
        print(f"  V63.F 현재     : {jt_raw:.4f} (iter {step})")
        if jt_raw > V63E1_JT_LAST:
            print(f"  ✓ V63.E.1 초과")
        else:
            print(f"  ⚠ V63.E.1 미달 ({V63E1_JT_LAST - jt_raw:+.4f})")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
