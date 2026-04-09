"""V63.H 전용 모니터링.

V63.H reward 9개:
- swing_body_forward (+4) ★ swing 중 body 전진
- effective_stride (+5) ★ per-leg touchdown 거리
- clearance_lift (+3)
- true_trot_pattern (+3)
- shoulder_neutral (-2)
- per_leg_contact_min (-3)
- track_lin_vel_xy_exp, flat_orientation_bonus, flat_orientation_l2
"""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

W_SWING_FWD = 4.0
W_STRIDE = 5.0
W_CLEAR_LIFT = 3.0
W_TRUE_TROT = 3.0
W_SHOULDER = -2.0
W_PHASE_CT = 0  # 제거
W_TRACK_LIN = 4.0


def latest_run() -> Path | None:
    # V63.H, V63.H.1 등 모두 매치
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.H*")), reverse=True)
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
        print("[FAIL] V63.H run folder not found")
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

    print("\n=== [V63.H Dynamic Motion 핵심 reward] ===")
    _, sf = last(ea, "Episode_Reward/swing_body_forward")
    sf_raw = sf / W_SWING_FWD if sf is not None else None
    if sf_raw is not None:
        print(f"  swing_body_forward = {sf_raw:+.4f}  (weighted {sf:.4f}) ★ swing 중 body 전진")

    _, st = last(ea, "Episode_Reward/effective_stride")
    st_raw = st / W_STRIDE if st is not None else None
    if st_raw is not None:
        print(f"  effective_stride   = {st_raw:+.4f}  (weighted {st:.4f}) ★ per-leg touchdown 거리")

    _, cl = last(ea, "Episode_Reward/clearance_lift")
    cl_raw = cl / W_CLEAR_LIFT if cl is not None else None
    if cl_raw is not None:
        print(f"  clearance_lift     = {cl_raw:+.4f}  (weighted {cl:.4f})")

    _, tt = last(ea, "Episode_Reward/true_trot_pattern")
    tt_raw = tt / W_TRUE_TROT if tt is not None else None
    if tt_raw is not None:
        print(f"  true_trot_pattern  = {tt_raw:+.4f}  (weighted {tt:.4f})")

    _, sh = last(ea, "Episode_Reward/shoulder_neutral")
    if sh is not None:
        print(f"  shoulder_neutral   = {sh:+.4f} (penalty)")

    _, lcm = last(ea, "Episode_Reward/per_leg_contact_min")
    if lcm is not None:
        print(f"  per_leg_contact_min= {lcm:+.4f} (penalty)")

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

    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 3000, 5000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n=== Trend (raw) ===")
    print(f"{'iter':>5}: {'reward':>7} {'ep_len':>7} {'sw_fwd':>7} {'stride':>7} {'clear':>7} {'trot':>7}")
    print("-" * 65)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        sfv = at_steps(ea, "Episode_Reward/swing_body_forward", [t])[0]
        stv = at_steps(ea, "Episode_Reward/effective_stride", [t])[0]
        clv = at_steps(ea, "Episode_Reward/clearance_lift", [t])[0]
        ttv = at_steps(ea, "Episode_Reward/true_trot_pattern", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} "
            f"{f(sfv, '%7.4f', W_SWING_FWD)} {f(stv, '%7.4f', W_STRIDE)} "
            f"{f(clv, '%7.4f', W_CLEAR_LIFT)} {f(ttv, '%7.4f', W_TRUE_TROT)}"
        )

    # 판정
    print("\n=== 자동 판정 ===")
    if sf_raw is None or st_raw is None:
        print("  [WAIT]")
    elif sf_raw >= 0.4 and st_raw >= 0.5:
        print(f"  [DYNAMIC TROT ✓✓✓] sw_fwd={sf_raw:.3f}, stride={st_raw:.3f}")
    elif sf_raw >= 0.2:
        print(f"  [WATCH] sw_fwd={sf_raw:.3f}")
    else:
        print(f"  [EARLY] 학습 초기")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
