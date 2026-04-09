"""V63.C 훈련 실시간 모니터링.

- 최신 V63.C run 폴더 탐색
- 주요 KPI snapshot + trend 출력
- 조기 경보/1차 판정/2차 판정 기준 비교
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

try:
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
except ImportError:
    print("[FAIL] tensorboard 모듈 필요", file=sys.stderr)
    sys.exit(1)


LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

KEY_METRICS = [
    ("Train/mean_reward", "reward"),
    ("Train/mean_episode_length", "ep_len"),
    ("Episode_Reward/phase_contact", "phase_ct"),
    ("Episode_Reward/propulsion", "propul"),
    ("Episode_Reward/feet_air_time", "feet_air"),
    ("Episode_Reward/forward_velocity", "fwd_vel"),
    ("Episode_Reward/track_lin_vel_xy_exp", "track_lin"),
    ("Episode_Reward/flat_orientation_bonus", "flat_bon"),
    ("Episode_Reward/phase_foot_reach", "foot_rch"),
    ("Episode_Reward/pair_lr_symmetry", "pair_sym"),
    ("Episode_Reward/stance_slip", "slip"),
    ("Episode_Reward/per_leg_contact_min", "leg_cmin"),
    ("Episode_Reward/per_leg_excess_swing", "leg_eswing"),
    ("Episode_Reward/pair_lock", "pair_lock"),
    ("Episode_Termination/time_out", "timeout%"),
    ("Episode_Termination/bad_orientation", "bad_ori%"),
    ("Episode_Termination/non_toe_contact", "non_toe%"),
    ("Episode_Termination/base_contact", "base_ct%"),
    ("Episode_Termination/min_height", "min_h%"),
    ("Episode_Termination/pair_lock", "pair_lk%"),
]


def latest_run() -> Path | None:
    candidates = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.C")), reverse=True)
    if not candidates:
        return None
    return Path(candidates[0])


def latest(ea: EventAccumulator, tag: str):
    try:
        evs = ea.Scalars(tag)
        return evs[-1].step, evs[-1].value
    except Exception:
        return None, None


def at_steps(ea: EventAccumulator, tag: str, targets: list[int], tolerance: int = 50):
    try:
        evs = ea.Scalars(tag)
    except Exception:
        return [(t, None) for t in targets]
    out = []
    for t in targets:
        if not evs:
            out.append((t, None))
            continue
        closest = min(evs, key=lambda e: abs(e.step - t))
        if abs(closest.step - t) <= tolerance:
            out.append((closest.step, closest.value))
        else:
            out.append((t, None))
    return out


def main() -> int:
    run = latest_run()
    if run is None:
        print("[FAIL] V63.C run folder not found")
        return 1

    print(f"=== Run: {run.name} ===")
    ea = EventAccumulator(str(run), size_guidance={"scalars": 0})
    ea.Reload()

    if not ea.Tags().get("scalars"):
        print("[WAIT] no scalars yet (훈련 초기, events.out.tfevents 미생성)")
        return 0

    # Current snapshot
    step, _ = latest(ea, "Train/mean_reward")
    if step is None:
        step = 0
    print(f"\n=== iter {step} ===\n")
    for tag, lbl in KEY_METRICS:
        s, v = latest(ea, tag)
        if v is None:
            continue
        print(f"  {lbl:12s} = {v:10.4f}")

    # Trend table
    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 3000, 4000, 5000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n=== Trend ===")
    print(
        "iter :  reward  ep_len  phase_ct  propul  foot_rch  feet_air  fwd_v    non_toe%"
    )
    print("-" * 90)
    for t in targets:
        def val(tag):
            res = at_steps(ea, tag, [t])
            return res[0][1]

        r = val("Train/mean_reward")
        if r is None:
            continue
        el = val("Train/mean_episode_length")
        pc = val("Episode_Reward/phase_contact")
        pr = val("Episode_Reward/propulsion")
        fr = val("Episode_Reward/phase_foot_reach")
        fa = val("Episode_Reward/feet_air_time")
        fv = val("Episode_Reward/forward_velocity")
        nt = val("Episode_Termination/non_toe_contact")

        def f(x, fmt):
            return (fmt % x) if x is not None else "  -"

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} {f(pc, '%8.3f')} "
            f"{f(pr, '%7.3f')} {f(fr, '%8.4f')} {f(fa, '%8.4f')} {f(fv, '%6.3f')} "
            f"{f(nt * 100 if nt is not None else None, '%6.2f%%')}"
        )

    # Judgement
    print("\n=== 판정 ===")
    curr = {
        "reward": latest(ea, "Train/mean_reward")[1],
        "ep_len": latest(ea, "Train/mean_episode_length")[1],
        "foot_rch": latest(ea, "Episode_Reward/phase_foot_reach")[1],
        "feet_air": latest(ea, "Episode_Reward/feet_air_time")[1],
        "propul": latest(ea, "Episode_Reward/propulsion")[1],
        "non_toe": latest(ea, "Episode_Termination/non_toe_contact")[1],
    }
    # per-step net reward (ep_reward / ep_len)
    if curr["reward"] is not None and curr["ep_len"] and curr["ep_len"] > 0:
        per_step = curr["reward"] / curr["ep_len"]
    else:
        per_step = None
    print(f"  per-step net reward: {per_step:.4f}" if per_step is not None else "  per-step net reward: -")

    if step < 200:
        print(f"  [WAIT] iter {step} — 조기 경보 시점(200) 미달")
    elif step < 500:
        print(f"  [EARLY_WARN @ iter {step}]")
        print(f"    per-step > +5       : {'PASS' if per_step and per_step > 5 else 'FAIL'} (current {per_step:.2f})" if per_step else "")
        print(f"    ep_len > 500        : {'PASS' if curr['ep_len'] and curr['ep_len'] > 500 else 'FAIL'} ({curr['ep_len']:.0f})" if curr['ep_len'] else "")
    else:
        print(f"  [1차 판정 @ iter {step}]")
        print(f"    ep_len > 800        : {'PASS' if curr['ep_len'] and curr['ep_len'] > 800 else 'FAIL'} ({curr['ep_len']:.0f})")
        fr_pass = curr["foot_rch"] is not None and curr["foot_rch"] > 2.5  # raw 0.5 × weight 5
        print(f"    foot_reach wgt>2.5  : {'PASS' if fr_pass else 'WATCH'} ({curr['foot_rch']:.3f})")
        nt_pass = curr["non_toe"] is None or curr["non_toe"] < 0.05
        print(f"    non_toe < 5%        : {'PASS' if nt_pass else 'WATCH'} ({(curr['non_toe'] or 0)*100:.1f}%)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
