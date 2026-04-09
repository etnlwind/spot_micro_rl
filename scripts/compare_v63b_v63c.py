"""V63.B(실패)와 V63.C(진행 중) 주요 지표 비교.

V63.B의 문제점:
- foot_reach raw: iter 500 peak 0.54 → iter 3305 하락 0.354 (trade-off 실패)
- feet_air_time raw: -0.11 지속 음수 (발 거의 안 듦)
- propulsion은 계속 상승, foot_reach 희생

V63.C의 같은 시점 대비.
"""
from __future__ import annotations

import glob
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

LOGS = Path("/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat")

V63B_RUN = LOGS / "2026-04-08_16-34-59_V63.B"


def latest_v63c() -> Path | None:
    cands = sorted(glob.glob(str(LOGS / "2026-04-0*_V63.C")), reverse=True)
    return Path(cands[0]) if cands else None


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


def last(ea, tag):
    try:
        evs = ea.Scalars(tag)
        return evs[-1].step, evs[-1].value
    except Exception:
        return None, None


def main():
    v63c_run = latest_v63c()
    if not v63c_run:
        print("V63.C run not found")
        return

    v63b = EventAccumulator(str(V63B_RUN), size_guidance={"scalars": 0})
    v63b.Reload()
    v63c = EventAccumulator(str(v63c_run), size_guidance={"scalars": 0})
    v63c.Reload()

    v63c_step, _ = last(v63c, "Train/mean_reward")
    if v63c_step is None:
        print("V63.C 데이터 없음")
        return

    print(f"V63.C current iter: {v63c_step}")
    print(f"V63.B run:  {V63B_RUN.name}")
    print(f"V63.C run:  {v63c_run.name}\n")

    # V63.B weight
    WB = {"phase_contact": 10, "propulsion": 8, "feet_air_time": 4, "phase_foot_reach": 1}
    # V63.C weight
    WC = {"phase_contact": 6, "propulsion": 4, "feet_air_time": 6, "phase_foot_reach": 5}

    # raw = weighted / weight
    def raw(ea, tag, weight, step):
        val = at_steps(ea, tag, [step], tol=200)[0]
        return val / weight if val is not None and weight else None

    metrics = [
        ("phase_contact", "phase_ct"),
        ("propulsion", "propul"),
        ("feet_air_time", "feet_air"),
        ("phase_foot_reach", "foot_reach"),
    ]

    # V63.B snapshots at key iterations
    v63b_checkpoints = [500, 1000, 2000, 3305]
    v63b_nontoe = at_steps(v63b, "Episode_Termination/non_toe_contact", v63b_checkpoints, tol=100)
    v63b_eplen = at_steps(v63b, "Train/mean_episode_length", v63b_checkpoints, tol=100)

    print("=" * 80)
    print("[V63.B RAW 값 trend — '안 좋았던 지표']")
    print("=" * 80)
    print(f"{'iter':>6} | {'ep_len':>8} | {'phase_ct':>9} | {'propul':>8} | {'feet_air':>9} | {'foot_rch':>9} | {'non_toe%':>9}")
    print("-" * 80)
    for t in v63b_checkpoints:
        row = [t]
        for tag, _ in metrics:
            full_tag = f"Episode_Reward/{tag}"
            r = raw(v63b, full_tag, WB[tag], t)
            row.append(r)
        el = at_steps(v63b, "Train/mean_episode_length", [t], 100)[0]
        nt = at_steps(v63b, "Episode_Termination/non_toe_contact", [t], 100)[0]
        el_s = f"{el:8.0f}" if el is not None else "    -"
        cells = []
        for r in row[1:]:
            cells.append(f"{r:9.4f}" if r is not None else "       -")
        nt_s = f"{nt*100:8.2f}%" if nt is not None else "       -"
        print(f"{t:6d} | {el_s} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {nt_s}")

    print()
    print("=" * 80)
    print("[V63.C 현재 iter raw 값]")
    print("=" * 80)
    print(f"{'iter':>6} | {'ep_len':>8} | {'phase_ct':>9} | {'propul':>8} | {'feet_air':>9} | {'foot_rch':>9} | {'non_toe%':>9}")
    print("-" * 80)
    el_c = last(v63c, "Train/mean_episode_length")[1]
    nt_c = last(v63c, "Episode_Termination/non_toe_contact")[1]
    raw_c = {}
    for tag, _ in metrics:
        _, val = last(v63c, f"Episode_Reward/{tag}")
        raw_c[tag] = val / WC[tag] if val is not None else None
    cells = []
    for tag, _ in metrics:
        r = raw_c[tag]
        cells.append(f"{r:9.4f}" if r is not None else "       -")
    el_s = f"{el_c:8.0f}" if el_c is not None else "    -"
    nt_s = f"{nt_c*100:8.2f}%" if nt_c is not None else "       -"
    print(f"{v63c_step:6d} | {el_s} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {nt_s}")

    # === 직접 비교 ===
    print()
    print("=" * 80)
    print("[V63.B vs V63.C 직접 비교 — 같은 iter 근처]")
    print("=" * 80)
    # Compare at closest iter
    compare_iter = min(v63b_checkpoints, key=lambda x: abs(x - v63c_step))
    print(f"비교 iter: V63.B @ {compare_iter} vs V63.C @ {v63c_step}\n")

    for tag, lbl in metrics:
        full_tag = f"Episode_Reward/{tag}"
        rb = raw(v63b, full_tag, WB[tag], compare_iter)
        rc = raw_c[tag]
        if rb is None or rc is None:
            continue
        delta = rc - rb
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
        print(f"  {lbl:12s}: V63.B {rb:8.4f}  →  V63.C {rc:8.4f}  {arrow} ({delta:+.4f})")

    el_b = at_steps(v63b, "Train/mean_episode_length", [compare_iter], 100)[0]
    if el_b and el_c:
        print(f"  {'ep_len':12s}: V63.B {el_b:8.0f}  →  V63.C {el_c:8.0f}  ({el_c - el_b:+.0f})")

    nt_b = at_steps(v63b, "Episode_Termination/non_toe_contact", [compare_iter], 100)[0]
    if nt_b is not None and nt_c is not None:
        print(f"  {'non_toe%':12s}: V63.B {nt_b*100:7.2f}%  →  V63.C {nt_c*100:7.2f}%  ({(nt_c-nt_b)*100:+.2f}%p)")

    # === V63.B의 문제 요약 ===
    print()
    print("=" * 80)
    print("[V63.B 실패 요약]")
    print("=" * 80)
    print("1. foot_reach raw: iter 500 peak → 이후 하락 (weight 1.0 너무 약함)")
    fr_500 = raw(v63b, "Episode_Reward/phase_foot_reach", 1.0, 500)
    fr_3305 = raw(v63b, "Episode_Reward/phase_foot_reach", 1.0, 3305)
    if fr_500 is not None and fr_3305 is not None:
        print(f"   - iter 500:  {fr_500:.4f}")
        print(f"   - iter 3305: {fr_3305:.4f}  (하락 {fr_3305 - fr_500:+.4f})")

    print("2. feet_air_time raw: 처음부터 끝까지 음수 (발 거의 안 들음)")
    for t in [500, 1500, 3305]:
        fa = raw(v63b, "Episode_Reward/feet_air_time", 4.0, t)
        if fa is not None:
            print(f"   - iter {t}: {fa:.4f}")

    print("3. propulsion raw: 꾸준히 상승 (foot_reach 희생하며 drag-with-timing 수렴)")
    for t in [500, 1500, 3305]:
        pr = raw(v63b, "Episode_Reward/propulsion", 8.0, t)
        if pr is not None:
            print(f"   - iter {t}: {pr:.4f}")


if __name__ == "__main__":
    main()
