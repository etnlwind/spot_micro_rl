"""V63.G 전용 모니터링 — 사용자 GUI 관찰 4가지 직접 측정."""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

W_ASYM_TARGET = 5.0
W_TRUE_TROT = 5.0
W_CLEARANCE_LIFT = 4.0  # V63.G.2 신규
W_INTRA_SYNC = 4.0      # V63.G only
W_PER_LEG_BAL = 2.0
W_LEG_USAGE_CV = -3.0
W_PHASE_CT = 4.0
W_PROPUL = 2.0
W_FEET_AIR = 4.0


def latest_run() -> Path | None:
    # V63.G, V63.G.1 등 모두 매치 (timestamp 최신 우선)
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.G*")), reverse=True)
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
        print("[FAIL] V63.G run folder not found")
        return 1

    ea = EventAccumulator(str(run), size_guidance={"scalars": 0})
    ea.Reload()

    if not ea.Tags().get("scalars"):
        print(f"=== Run: {run.name} ===")
        print("[WAIT]")
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

    print("\n=== [V63.G 4 핵심 reward — 사용자 지적 직접 측정] ===")

    _, asym = last(ea, "Episode_Reward/asymmetric_joint_target")
    asym_raw = asym / W_ASYM_TARGET if asym is not None else None
    if asym_raw is not None:
        print(f"  asym_target raw    = {asym_raw:+.4f}  (weighted {asym:.4f})  [윗다리 lift]")

    _, intra = last(ea, "Episode_Reward/intra_pair_sync")
    intra_raw = intra / W_INTRA_SYNC if intra is not None else None
    if intra_raw is not None:
        print(f"  intra_pair_sync raw= {intra_raw:+.4f}  (weighted {intra:.4f}) [V63.G only]")

    _, true_trot = last(ea, "Episode_Reward/true_trot_pattern")
    true_trot_raw = true_trot / W_TRUE_TROT if true_trot is not None else None
    if true_trot_raw is not None:
        print(f"  true_trot raw      = {true_trot_raw:+.4f}  (weighted {true_trot:.4f}) ★★ intra×inter")

    _, clift = last(ea, "Episode_Reward/clearance_lift")
    clift_raw = clift / W_CLEARANCE_LIFT if clift is not None else None
    if clift_raw is not None:
        print(f"  clearance_lift raw = {clift_raw:+.4f}  (weighted {clift:.4f}) ★★ V63.G.2 발 높이")

    _, plbal = last(ea, "Episode_Reward/per_leg_propulsion_balance")
    plbal_raw = plbal / W_PER_LEG_BAL if plbal is not None else None
    if plbal_raw is not None:
        print(f"  prop_balance raw   = {plbal_raw:+.4f}  (weighted {plbal:.4f})  [4발 균등 추진]")

    _, lcv = last(ea, "Episode_Reward/leg_usage_cv")
    lcv_raw = lcv / W_LEG_USAGE_CV if lcv is not None else None
    if lcv_raw is not None:
        print(f"  leg_usage_penalty  = {lcv_raw:+.4f}  (weighted {lcv:.4f})  ★ RR exploit 차단")

    print("\n=== [참고 reward] ===")
    for tag, lbl, w in [
        ("Episode_Reward/phase_contact", "phase_ct", W_PHASE_CT),
        ("Episode_Reward/propulsion", "propul", W_PROPUL),
        ("Episode_Reward/feet_air_time", "feet_air", W_FEET_AIR),
    ]:
        _, v = last(ea, tag)
        if v is not None:
            print(f"  {lbl:12s} = {v:9.4f}  (raw {v/w if w else v:+.4f})")

    print("\n=== [Termination %] ===")
    for tag_short, lbl in [
        ("time_out", "timeout"),
        ("bad_orientation", "bad_ori"),
        ("non_toe_contact", "non_toe"),
        ("base_contact", "base_ct"),
    ]:
        _, v = last(ea, f"Episode_Termination/{tag_short}")
        if v is not None:
            print(f"  {lbl:12s} = {v*100:8.2f}%")

    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 2500, 3000, 4000, 5000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n=== Trend (raw) ===")
    print(f"{'iter':>5}: {'reward':>7} {'ep_len':>7} {'asym':>7} {'intra':>7} {'pl_bal':>7} {'cv_pen':>7}")
    print("-" * 65)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        av = at_steps(ea, "Episode_Reward/asymmetric_joint_target", [t])[0]
        iv = at_steps(ea, "Episode_Reward/intra_pair_sync", [t])[0]
        plv = at_steps(ea, "Episode_Reward/per_leg_propulsion_balance", [t])[0]
        lcvv = at_steps(ea, "Episode_Reward/leg_usage_cv", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} "
            f"{f(av, '%7.4f', W_ASYM_TARGET)} {f(iv, '%7.4f', W_INTRA_SYNC)} "
            f"{f(plv, '%7.4f', W_PER_LEG_BAL)} {f(lcvv, '%7.4f', W_LEG_USAGE_CV)}"
        )

    print("\n=== 자동 판정 ===")
    if asym_raw is None or intra_raw is None:
        decision = "wait"
        print("  [WAIT] 데이터 부족")
    elif asym_raw >= 0.5 and intra_raw >= 0.7:
        decision = "real_trot_satisfied"
        print(f"  [REAL TROT ✓✓✓] asym={asym_raw:.3f}, intra_sync={intra_raw:.3f}")
    elif intra_raw >= 0.5:
        decision = "intra_sync_progress"
        print(f"  [INTRA SYNC 진전] intra_sync={intra_raw:.3f} (목표 0.7+)")
    elif asym_raw >= 0.3:
        decision = "watch"
        print(f"  [WATCH] asym={asym_raw:.3f}, intra_sync={intra_raw:.3f}")
    else:
        decision = "early"
        print(f"  [EARLY] 학습 초기")

    print(f"\n>>> DECISION: {decision.upper()} <<<")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
