"""V63.D 훈련 실시간 모니터링.

- 최신 V63.D run 폴더 자동 탐색
- 핵심 KPI snapshot + trend
- V63.B/C 실패 지표와 직접 비교 (feet_air_time 양수 전환 확인)
- 판정 기준 자동 체크
"""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

# V63.D weight (raw 계산용)
WEIGHTS = {
    "phase_contact": 4.0,
    "propulsion": 4.0,
    "feet_air_time": 4.0,
    "phase_joint_target": 10.0,
    "forward_velocity": 3.0,
    "flat_orientation_bonus": 3.0,
}


def latest_run() -> Path | None:
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.D")), reverse=True)
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
        print("[FAIL] V63.D run folder not found")
        return 1

    ea = EventAccumulator(str(run), size_guidance={"scalars": 0})
    ea.Reload()

    if not ea.Tags().get("scalars"):
        print(f"=== Run: {run.name} ===")
        print("[WAIT] scalars 아직 생성 안 됨 (훈련 매우 초기)")
        return 0

    step, _ = last(ea, "Train/mean_reward")
    if step is None:
        print("[WAIT] mean_reward 없음")
        return 0

    print(f"=== Run: {run.name} ===")
    print(f"=== iter {step} ===\n")

    # Current snapshot
    key = [
        ("Train/mean_reward", "reward"),
        ("Train/mean_episode_length", "ep_len"),
    ]
    for tag, lbl in key:
        s, v = last(ea, tag)
        if v is not None:
            print(f"  {lbl:20s} = {v:10.4f}")

    print("\n[주요 Reward — weighted / raw]")
    for tag_short, w in [
        ("phase_joint_target", 10.0),
        ("phase_contact", 4.0),
        ("propulsion", 4.0),
        ("feet_air_time", 4.0),
        ("forward_velocity", 3.0),
        ("flat_orientation_bonus", 3.0),
        ("track_lin_vel_xy_exp", 4.0),
    ]:
        _, v = last(ea, f"Episode_Reward/{tag_short}")
        if v is not None:
            raw = v / w if w else v
            print(f"  {tag_short:25s} = {v:9.4f}  (raw {raw:+.4f})")

    print("\n[Penalty]")
    for tag_short in [
        "pair_lr_symmetry",
        "stance_slip",
        "per_leg_contact_min",
        "per_leg_excess_swing",
        "pair_lock",
    ]:
        _, v = last(ea, f"Episode_Reward/{tag_short}")
        if v is not None:
            print(f"  {tag_short:25s} = {v:9.4f}")

    print("\n[Termination %]")
    for tag_short, lbl in [
        ("time_out", "timeout"),
        ("bad_orientation", "bad_ori"),
        ("non_toe_contact", "non_toe"),
        ("base_contact", "base_ct"),
        ("min_height", "min_h"),
        ("pair_lock", "pair_lk"),
    ]:
        _, v = last(ea, f"Episode_Termination/{tag_short}")
        if v is not None:
            print(f"  {lbl:20s} = {v*100:8.2f}%")

    # Trend
    targets = [100, 200, 300, 500, 800, 1200, 1500, 2000, 3000, 4000, 5000]
    targets = [t for t in targets if t <= step + 100]
    if step > 0 and step not in targets:
        targets.append(step)
    targets = sorted(set(targets))

    print("\n[Trend — raw (joint_tgt, phase_ct, propul, feet_air)]")
    print("iter :  reward  ep_len  joint_tgt  phase_ct  propul  feet_air  non_toe%")
    print("-" * 80)
    for t in targets:
        r = at_steps(ea, "Train/mean_reward", [t])[0]
        if r is None:
            continue
        el = at_steps(ea, "Train/mean_episode_length", [t])[0]
        jt = at_steps(ea, "Episode_Reward/phase_joint_target", [t])[0]
        pc = at_steps(ea, "Episode_Reward/phase_contact", [t])[0]
        pr = at_steps(ea, "Episode_Reward/propulsion", [t])[0]
        fa = at_steps(ea, "Episode_Reward/feet_air_time", [t])[0]
        nt = at_steps(ea, "Episode_Termination/non_toe_contact", [t])[0]

        def f(x, fmt, div=1):
            if x is None:
                return "    -  "
            return fmt % (x / div)

        jt_raw = f(jt, "%9.4f", 10.0)
        pc_raw = f(pc, "%8.4f", 4.0)
        pr_raw = f(pr, "%7.4f", 4.0)
        fa_raw = f(fa, "%8.4f", 4.0)
        nt_s = f(nt * 100 if nt is not None else None, "%7.2f%%")

        print(
            f"{t:5d}: {f(r, '%7.1f')} {f(el, '%7.1f')} {jt_raw} {pc_raw} {pr_raw} {fa_raw} {nt_s}"
        )

    # === 판정 ===
    print("\n=== 판정 ===")
    reward, _ = last(ea, "Train/mean_reward")[::-1]
    reward = last(ea, "Train/mean_reward")[1]
    ep_len = last(ea, "Train/mean_episode_length")[1]
    jt = last(ea, "Episode_Reward/phase_joint_target")[1]
    fa = last(ea, "Episode_Reward/feet_air_time")[1]
    nt = last(ea, "Episode_Termination/non_toe_contact")[1]

    jt_raw = jt / 10.0 if jt is not None else None
    fa_raw = fa / 4.0 if fa is not None else None

    if ep_len:
        per_step = reward / ep_len if reward is not None else None
        print(f"  per-step net reward: {per_step:.4f}" if per_step is not None else "")

    if step < 200:
        print(f"  [WAIT] iter {step} — 조기 경보(200) 대기")
    elif step < 500:
        print(f"  [조기 경보 @ iter {step}]")
        if ep_len is not None:
            print(f"    ep_len > 500         : {'PASS' if ep_len > 500 else 'FAIL'} ({ep_len:.0f})")
    elif step < 1500:
        print(f"  [1차 판정 @ iter {step}]")
        if ep_len is not None:
            print(f"    ep_len > 800         : {'PASS' if ep_len > 800 else 'FAIL'} ({ep_len:.0f})")
        if jt_raw is not None:
            marker = "PASS" if jt_raw > 0.4 else "WATCH"
            print(f"    joint_target raw>0.4 : {marker} ({jt_raw:.4f})")
        if fa_raw is not None:
            marker = "PASS ✓✓" if fa_raw > 0 else "FAIL ⚠️"
            print(f"    feet_air raw > 0     : {marker} ({fa_raw:+.4f})  ← V63.B/C 절대 못했던 것")
        if nt is not None:
            print(f"    non_toe < 5%         : {'PASS' if nt < 0.05 else 'WATCH'} ({nt*100:.2f}%)")
    else:
        print(f"  [2차 판정 @ iter {step}]")
        if jt_raw is not None:
            marker = "PASS" if jt_raw > 0.7 else "WATCH"
            print(f"    joint_target raw>0.7 : {marker} ({jt_raw:.4f})")
        if fa_raw is not None:
            marker = "PASS" if fa_raw > 0.02 else "WATCH"
            print(f"    feet_air raw > 0.02  : {marker} ({fa_raw:+.4f})")

    # V63.B 비교 (feet_air)
    print("\n[V63.B/C 실패 지표와 비교]")
    v63b_fa_final = -0.0266  # V63.B iter 3305 feet_air raw
    v63c_fa_final = -0.0143  # V63.C iter 832
    if fa_raw is not None:
        print(f"  V63.B (iter 3305) feet_air raw: {v63b_fa_final:+.4f}  (계속 음수)")
        print(f"  V63.C (iter  832) feet_air raw: {v63c_fa_final:+.4f}  (계속 음수)")
        print(f"  V63.D (iter {step:>4}) feet_air raw: {fa_raw:+.4f}", end="")
        if fa_raw > 0:
            print("  ✓✓ 양수 전환 성공!")
        elif fa_raw > v63c_fa_final:
            print("  (아직 음수지만 V63.C보다 나음)")
        else:
            print("  (여전히 V63.C 수준)")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
