"""V63.I Trajectory 분석 + 대칭화 + Reference 생성.

녹화된 trajectory에서:
1. 좋은 보행 구간 필터링
2. Phase-normalized joint trajectory 추출
3. 대칭화 (FL/RR pair ↔ FR/RL pair 평균)
4. Reference trajectory 생성
"""
import json
import math
import numpy as np
from pathlib import Path

DATA_PATH = Path("/mnt/d/project/spot_micro_rl/logs/v63i_trajectory.json")

def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)

def analyze():
    raw = load_data()
    meta = raw['meta']
    data = raw['data']
    dt = meta['dt']
    joint_names = meta['joint_names']

    print(f"Loaded {len(data)} steps, dt={dt}s")
    print(f"Joint order: {joint_names}")
    print(f"Total time: {len(data)*dt:.1f}s")

    # Joint name → index
    ji = {name: i for i, name in enumerate(joint_names)}

    # Extract arrays
    steps = len(data)
    jp = np.array([d['jp'] for d in data])  # (steps, 12)
    jv = np.array([d['jv'] for d in data])
    act = np.array([d['act'] for d in data])
    rv = np.array([d['rv'] for d in data])  # root vel body frame
    ra = np.array([d['ra'] for d in data])  # root ang vel

    # ═══════════════════════════════════════
    # 1. Overall statistics
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("1. OVERALL STATISTICS")
    print("=" * 60)

    vx = rv[:, 0]
    vy = rv[:, 1]
    print(f"Forward vel:  mean={vx.mean():.4f} std={vx.std():.4f}")
    print(f"Lateral vel:  mean={vy.mean():.4f} std={vy.std():.4f}")
    print(f"Roll rate:    mean={ra[:, 0].mean():.4f} std={ra[:, 0].std():.4f}")
    print(f"Pitch rate:   mean={ra[:, 1].mean():.4f} std={ra[:, 1].std():.4f}")
    print(f"Yaw rate:     mean={ra[:, 2].mean():.4f} std={ra[:, 2].std():.4f}")

    # ═══════════════════════════════════════
    # 2. Per-joint statistics
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("2. PER-JOINT STATISTICS (position)")
    print("=" * 60)
    print(f"{'Joint':>25s} {'mean':>8s} {'std':>8s} {'min':>8s} {'max':>8s} {'range':>8s}")
    print("-" * 70)
    for i, name in enumerate(joint_names):
        col = jp[:, i]
        print(f"{name:>25s} {col.mean():>8.4f} {col.std():>8.4f} {col.min():>8.4f} {col.max():>8.4f} {col.max()-col.min():>8.4f}")

    # ═══════════════════════════════════════
    # 3. L/R comparison
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("3. L/R JOINT COMPARISON")
    print("=" * 60)

    lr_pairs = [
        ('front_left_shoulder', 'front_right_shoulder', 'shoulder', True),  # sign flip
        ('front_left_leg', 'front_right_leg', 'leg', False),
        ('front_left_foot', 'front_right_foot', 'foot', False),
        ('rear_left_shoulder', 'rear_right_shoulder', 'r_shoulder', True),
        ('rear_left_leg', 'rear_right_leg', 'r_leg', False),
        ('rear_left_foot', 'rear_right_foot', 'r_foot', False),
    ]

    print(f"{'Pair':>12s} {'L_mean':>8s} {'R_mean':>8s} {'L_std':>8s} {'R_std':>8s} {'L_range':>8s} {'R_range':>8s} {'bias':>8s}")
    print("-" * 80)
    for l_name, r_name, label, flip in lr_pairs:
        li, ri = ji[l_name], ji[r_name]
        lj, rj = jp[:, li], jp[:, ri]
        if flip:
            rj_comp = -rj  # shoulder uses opposite sign
        else:
            rj_comp = rj
        bias = lj.mean() - rj_comp.mean()
        print(f"{label:>12s} {lj.mean():>8.4f} {rj.mean():>8.4f} {lj.std():>8.4f} {rj.std():>8.4f} "
              f"{lj.max()-lj.min():>8.4f} {rj.max()-rj.min():>8.4f} {bias:>+8.4f}")

    # ═══════════════════════════════════════
    # 4. Phase detection (from joint periodicity)
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("4. PHASE/FREQUENCY DETECTION")
    print("=" * 60)

    # Use FL leg joint (most periodic) for frequency detection
    fl_leg = jp[:, ji['front_left_leg']]
    # Simple zero-crossing detection on detrended signal
    fl_centered = fl_leg - fl_leg.mean()
    crossings = np.where(np.diff(np.sign(fl_centered)))[0]
    if len(crossings) > 2:
        periods = np.diff(crossings) * dt
        half_periods = periods[periods > 0.05]  # filter noise
        avg_half_period = half_periods.mean()
        freq = 1.0 / (2 * avg_half_period)
        print(f"FL leg frequency: {freq:.2f} Hz (half-period: {avg_half_period:.4f}s)")
        print(f"Full cycle: {2*avg_half_period:.4f}s ({int(2*avg_half_period/dt)} steps)")

    # ═══════════════════════════════════════
    # 5. Phase-normalized trajectory
    # ═══════════════════════════════════════
    print("\n" + "=" * 60)
    print("5. PHASE-NORMALIZED TRAJECTORY (1 cycle)")
    print("=" * 60)

    if len(crossings) > 4:
        # Use middle cycles for stability
        mid = len(crossings) // 2
        cycle_start = crossings[mid]
        # Find next full cycle (2 half-periods)
        cycle_end = crossings[mid + 2] if mid + 2 < len(crossings) else crossings[-1]
        cycle_len = cycle_end - cycle_start

        print(f"Extracting cycle: step {cycle_start}~{cycle_end} ({cycle_len} steps, {cycle_len*dt:.3f}s)")

        cycle_jp = jp[cycle_start:cycle_end]
        cycle_jv = jv[cycle_start:cycle_end]
        cycle_act = act[cycle_start:cycle_end]

        # Phase normalize to 0~1
        phases = np.linspace(0, 1, cycle_len, endpoint=False)

        print(f"\nPhase-normalized joint trajectory (10 samples):")
        print(f"{'phase':>6s}", end="")
        for name in joint_names:
            short = name.replace('front_', 'f').replace('rear_', 'r').replace('left_', 'l').replace('right_', 'r').replace('shoulder', 'sh').replace('foot', 'ft')
            print(f" {short:>8s}", end="")
        print()

        for i in range(0, cycle_len, max(1, cycle_len // 10)):
            print(f"{phases[i]:>6.2f}", end="")
            for j in range(12):
                print(f" {cycle_jp[i, j]:>8.4f}", end="")
            print()

        # ═══════════════════════════════════════
        # 6. Symmetrized reference
        # ═══════════════════════════════════════
        print("\n" + "=" * 60)
        print("6. SYMMETRIZED REFERENCE TRAJECTORY")
        print("=" * 60)

        # Pair A: FL(phase 0) + RR(phase 0) — same phase
        # Pair B: FR(phase 0.5) + RL(phase 0.5) — half cycle offset
        # Symmetrize: average Pair A leg with Pair B leg (shifted by half cycle)

        half = cycle_len // 2

        # For leg/foot joints (same sign convention):
        # FL_leg at phase φ should = FR_leg at phase φ+0.5 (in ideal trot)
        # Symmetrized: avg(FL_leg(φ), FR_leg(φ+0.5))

        sym_jp = np.zeros_like(cycle_jp)

        for phase_idx in range(cycle_len):
            shifted_idx = (phase_idx + half) % cycle_len

            # Shoulder: L uses -sign, R uses +sign → average magnitudes
            # FL shoulder
            fl_sh = cycle_jp[phase_idx, ji['front_left_shoulder']]
            fr_sh_shifted = cycle_jp[shifted_idx, ji['front_right_shoulder']]
            avg_sh_mag = (abs(fl_sh) + abs(fr_sh_shifted)) / 2
            sym_jp[phase_idx, ji['front_left_shoulder']] = -avg_sh_mag
            sym_jp[phase_idx, ji['front_right_shoulder']] = avg_sh_mag

            # FL leg (phase φ) ↔ FR leg (phase φ+0.5)
            fl_leg_val = cycle_jp[phase_idx, ji['front_left_leg']]
            fr_leg_shifted = cycle_jp[shifted_idx, ji['front_right_leg']]
            avg_leg = (fl_leg_val + fr_leg_shifted) / 2
            sym_jp[phase_idx, ji['front_left_leg']] = avg_leg
            sym_jp[shifted_idx, ji['front_right_leg']] = avg_leg

            # FL foot ↔ FR foot (same)
            fl_ft_val = cycle_jp[phase_idx, ji['front_left_foot']]
            fr_ft_shifted = cycle_jp[shifted_idx, ji['front_right_foot']]
            avg_ft = (fl_ft_val + fr_ft_shifted) / 2
            sym_jp[phase_idx, ji['front_left_foot']] = avg_ft
            sym_jp[shifted_idx, ji['front_right_foot']] = avg_ft

            # Rear: same logic
            rl_sh = cycle_jp[phase_idx, ji['rear_left_shoulder']]
            rr_sh_shifted = cycle_jp[shifted_idx, ji['rear_right_shoulder']]
            avg_rsh_mag = (abs(rl_sh) + abs(rr_sh_shifted)) / 2
            sym_jp[phase_idx, ji['rear_left_shoulder']] = -avg_rsh_mag
            sym_jp[phase_idx, ji['rear_right_shoulder']] = avg_rsh_mag

            rl_leg_val = cycle_jp[phase_idx, ji['rear_left_leg']]
            rr_leg_shifted = cycle_jp[shifted_idx, ji['rear_right_leg']]
            avg_rleg = (rl_leg_val + rr_leg_shifted) / 2
            sym_jp[phase_idx, ji['rear_left_leg']] = avg_rleg
            sym_jp[shifted_idx, ji['rear_right_leg']] = avg_rleg

            rl_ft_val = cycle_jp[phase_idx, ji['rear_left_foot']]
            rr_ft_shifted = cycle_jp[shifted_idx, ji['rear_right_foot']]
            avg_rft = (rl_ft_val + rr_ft_shifted) / 2
            sym_jp[phase_idx, ji['rear_left_foot']] = avg_rft
            sym_jp[shifted_idx, ji['rear_right_foot']] = avg_rft

        # Compute symmetry error before/after
        orig_lr_diff = 0
        sym_lr_diff = 0
        for l_name, r_name, _, flip in lr_pairs:
            li, ri = ji[l_name], ji[r_name]
            if flip:
                orig_lr_diff += np.abs(cycle_jp[:, li] + cycle_jp[:, ri]).mean()
                sym_lr_diff += np.abs(sym_jp[:, li] + sym_jp[:, ri]).mean()
            else:
                # Compare with half-cycle shift
                orig_lr_diff += np.abs(cycle_jp[:, li] - np.roll(cycle_jp[:, ri], half, axis=0)).mean()
                sym_lr_diff += np.abs(sym_jp[:, li] - np.roll(sym_jp[:, ri], half, axis=0)).mean()

        print(f"L/R asymmetry before symmetrization: {orig_lr_diff:.4f}")
        print(f"L/R asymmetry after symmetrization:  {sym_lr_diff:.4f}")
        print(f"Reduction: {(1 - sym_lr_diff/orig_lr_diff)*100:.1f}%")

        # Save reference
        ref = {
            'joint_names': joint_names,
            'frequency_hz': freq,
            'cycle_steps': int(cycle_len),
            'dt': dt,
            'phase_normalized_joint_pos': sym_jp.tolist(),
            'original_joint_pos': cycle_jp.tolist(),
        }

        ref_path = DATA_PATH.parent / 'ideal_trot_reference.json'
        with open(ref_path, 'w') as f:
            json.dump(ref, f)
        print(f"\nReference saved to {ref_path} ({ref_path.stat().st_size/1024:.1f} KB)")
        print(f"Cycle: {cycle_len} steps at {dt}s = {cycle_len*dt:.3f}s ({freq:.2f} Hz)")


if __name__ == "__main__":
    analyze()
