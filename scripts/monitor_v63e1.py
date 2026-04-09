"""V63.E.1 전용 모니터링 (V63.E old 폴더 회피).

glob pattern 문제 해결: V63.E.1 폴더만 정확히 매칭.
"""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

V63B_FA_FINAL = -0.0266
V63C_FA_FINAL = -0.0143
V63D_FA_FINAL = -0.0093
V63E_FA_FINAL = -0.0079  # iter 1206


def latest_run() -> Path | None:
    # V63.E.1 정확 매칭 (V63.E는 제외)
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.E.1")), reverse=True)
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
        print("[FAIL] V63.E.1 run folder not found")
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

    print("\n[양수 reward — weighted / raw]")
    for tag_short, w in [
        ("phase_joint_target_linear", 3.0),
        ("phase_contact", 6.0),
        ("propulsion", 2.0),
        ("feet_air_time", 4.0),
        ("forward_velocity", 3.0),
        ("flat_orientation_bonus", 3.0),
        ("track_lin_vel_xy_exp", 4.0),
    ]:
        _, v = last(ea, f"Episode_Reward/{tag_short}")
        if v is not None:
            raw = v / w if w else v
            print(f"  {tag_short:28s} = {v:9.4f}  (raw {raw:+.4f})")

    print("\n[Termination %]")
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

    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 2500, 3000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n[Trend — raw values]")
    print("iter :  reward  ep_len  joint_tgt  phase_ct  propul  feet_air  non_toe%")
    print("-" * 80)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        jt = at_steps(ea, "Episode_Reward/phase_joint_target_linear", [t])[0]
        pc = at_steps(ea, "Episode_Reward/phase_contact", [t])[0]
        pr = at_steps(ea, "Episode_Reward/propulsion", [t])[0]
        fa = at_steps(ea, "Episode_Reward/feet_air_time", [t])[0]
        nt = at_steps(ea, "Episode_Termination/non_toe_contact", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        jt_raw = f(jt, "%9.4f", 3.0)
        pc_raw = f(pc, "%8.4f", 6.0)
        pr_raw = f(pr, "%7.4f", 2.0)
        fa_raw = f(fa, "%8.4f", 4.0)
        nt_s = f(nt * 100 if nt is not None else None, "%7.2f%%")

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} {jt_raw} {pc_raw} {pr_raw} {fa_raw} {nt_s}"
        )

    # 판정
    print("\n=== 판정 ===")
    reward = last(ea, "Train/mean_reward")[1]
    ep_len = last(ea, "Train/mean_episode_length")[1]
    jt = last(ea, "Episode_Reward/phase_joint_target_linear")[1]
    fa = last(ea, "Episode_Reward/feet_air_time")[1]
    nt = last(ea, "Episode_Termination/non_toe_contact")[1]

    jt_raw = jt / 3.0 if jt is not None else None
    fa_raw = fa / 4.0 if fa is not None else None
    per_step = (reward / ep_len) if (reward is not None and ep_len) else None

    if per_step is not None:
        print(f"  per-step net reward: {per_step:.4f}")

    # Trend analysis: last 5 iters joint_target
    try:
        evs = ea.Scalars("Episode_Reward/phase_joint_target_linear")
        if len(evs) >= 5:
            recent = [e.value / 3.0 for e in evs[-5:]]
            trend = recent[-1] - recent[0]
            print(f"  joint_target 최근 5 iter trend: {recent[0]:.4f} → {recent[-1]:.4f} (Δ{trend:+.4f})")
    except:
        pass

    # Auto decision
    print("\n=== 자동 판정 ===")
    if jt_raw is None or fa_raw is None:
        print("  [UNKNOWN] 데이터 부족")
        decision = "wait"
    elif jt_raw >= 0.15 and fa_raw > -0.015:
        print(f"  [SATISFIED ✓] joint_target {jt_raw:.4f} ≥ 0.15, feet_air {fa_raw:+.4f} > -0.015")
        decision = "satisfied"
    elif jt_raw >= 0.05:
        print(f"  [WATCH] joint_target {jt_raw:.4f} — 경계 범위 (0.05~0.15), 계속 관찰")
        decision = "watch"
    else:
        print(f"  [UNSATISFIED ✗] joint_target {jt_raw:.4f} < 0.05")
        decision = "unsatisfied"

    print(f"\n>>> DECISION: {decision.upper()} <<<")

    # Curriculum progress (V63.E.1: 2500 iter)
    cur_iters = 2500
    frac = min(step / cur_iters, 1.0) if step else 0
    A_leg = 0.03 + (0.25 - 0.03) * frac
    A_foot = 0.05 + (0.35 - 0.05) * frac
    print(f"\n[Curriculum]")
    print(f"  frac: {frac:.3f},  A_leg: {A_leg:.4f} ({A_leg*57.3:.1f}°),  A_foot: {A_foot:.4f} ({A_foot*57.3:.1f}°)")

    # History comparison
    print("\n[feet_air_time raw 역사]")
    print(f"  V63.B  : {V63B_FA_FINAL:+.4f}")
    print(f"  V63.C  : {V63C_FA_FINAL:+.4f}")
    print(f"  V63.D  : {V63D_FA_FINAL:+.4f}")
    print(f"  V63.E  : {V63E_FA_FINAL:+.4f}")
    if fa_raw is not None:
        print(f"  V63.E.1: {fa_raw:+.4f}", end="")
        if fa_raw > 0:
            print("  ✓✓ 양수 전환 성공!")
        elif fa_raw > V63D_FA_FINAL:
            print("  (V63.D보다 나음)")
        else:
            print("  (V63.D 수준)")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
