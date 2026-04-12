"""V68 model_2500 정량 리포트 생성.

녹화 데이터에서:
- 기본 통계 (velocity, body motion)
- Per-leg contact/propulsion/lift 분석
- Cost of Transport
- Stance slip
- 대칭성 지표
- 안정성 지표
"""
import json
import math
import numpy as np
from pathlib import Path

DATA_PATH = Path("/mnt/d/project/spot_micro_rl/logs/v63i_trajectory.json")

def load():
    with open(DATA_PATH) as f:
        return json.load(f)

def report():
    raw = load()
    meta = raw['meta']
    data = raw['data']
    dt = meta['dt']
    joint_names = meta['joint_names']
    steps = len(data)

    print("=" * 70)
    print("V68 model_2500 QUANTITATIVE REPORT")
    print("=" * 70)
    print(f"Steps: {steps}, dt: {dt}s, total: {steps*dt:.1f}s")

    # Extract arrays
    jp = np.array([d['jp'] for d in data])
    jv = np.array([d['jv'] for d in data])
    act = np.array([d['act'] for d in data])
    rv = np.array([d['rv'] for d in data])  # root_lin_vel_b [vx, vy, vz]
    ra = np.array([d['ra'] for d in data])  # root_ang_vel_b [wx, wy, wz]
    rp = np.array([d['rp'] for d in data])  # root_pos_w [x, y, z]

    # Skip warmup (first 50 steps = 1s)
    warmup = 50
    jp = jp[warmup:]
    jv = jv[warmup:]
    act = act[warmup:]
    rv = rv[warmup:]
    ra = ra[warmup:]
    rp = rp[warmup:]
    n = len(jp)

    # ═══════════════════════════════════════
    # 1. Locomotion Performance
    # ═══════════════════════════════════════
    print("\n--- 1. LOCOMOTION PERFORMANCE ---")
    vx = rv[:, 0]
    vy = rv[:, 1]
    vz = rv[:, 2]

    print(f"Forward velocity (vx):  mean={vx.mean():.4f} m/s, std={vx.std():.4f}")
    print(f"Lateral velocity (vy):  mean={vy.mean():.4f} m/s, std={vy.std():.4f}")
    print(f"Vertical velocity (vz): mean={vz.mean():.4f} m/s, std={vz.std():.4f}")

    # Distance traveled
    dist = rp[-1, 0] - rp[0, 0]
    time_elapsed = n * dt
    avg_speed = dist / time_elapsed
    print(f"\nDistance traveled: {dist:.3f} m in {time_elapsed:.1f}s")
    print(f"Average speed: {avg_speed:.4f} m/s")

    # Lateral drift
    lat_drift = rp[-1, 1] - rp[0, 1]
    print(f"Lateral drift: {lat_drift:.4f} m ({abs(lat_drift/dist)*100:.1f}% of forward)")

    # ═══════════════════════════════════════
    # 2. Body Stability
    # ═══════════════════════════════════════
    print("\n--- 2. BODY STABILITY ---")
    wx, wy, wz = ra[:, 0], ra[:, 1], ra[:, 2]
    print(f"Roll rate (wx):   mean={wx.mean():.4f} std={wx.std():.4f}")
    print(f"Pitch rate (wy):  mean={wy.mean():.4f} std={wy.std():.4f}")
    print(f"Yaw rate (wz):    mean={wz.mean():.4f} std={wz.std():.4f}")

    body_z = rp[:, 2]
    print(f"\nBody height: mean={body_z.mean():.4f} std={body_z.std():.4f}")
    print(f"  min={body_z.min():.4f} max={body_z.max():.4f}")

    # ═══════════════════════════════════════
    # 3. Energy / Cost of Transport
    # ═══════════════════════════════════════
    print("\n--- 3. ENERGY / CoT ---")
    # Mechanical power = sum(|joint_vel * action_torque_proxy|)
    # Since we don't have torque directly, use |jv * act| as proxy
    power_proxy = np.abs(jv * act).sum(axis=1)
    mean_power = power_proxy.mean()
    mass = 0.8  # approximate
    g = 9.81
    speed = max(abs(avg_speed), 0.001)
    cot = mean_power / (mass * g * speed)
    print(f"Power proxy (|jv*act|): mean={mean_power:.4f}")
    print(f"Cost of Transport: {cot:.2f} (lower is better)")

    # ═══════════════════════════════════════
    # 4. Per-Joint Statistics
    # ═══════════════════════════════════════
    print("\n--- 4. PER-JOINT RANGE OF MOTION ---")
    ji = {name: i for i, name in enumerate(joint_names)}

    print(f"{'Joint':>25s} {'mean':>7s} {'std':>7s} {'range':>7s} {'max|vel|':>8s}")
    print("-" * 60)
    for i, name in enumerate(joint_names):
        col = jp[:, i]
        vel = jv[:, i]
        print(f"{name:>25s} {col.mean():>7.3f} {col.std():>7.3f} "
              f"{col.max()-col.min():>7.3f} {np.abs(vel).max():>8.3f}")

    # ═══════════════════════════════════════
    # 5. L/R Symmetry
    # ═══════════════════════════════════════
    print("\n--- 5. L/R SYMMETRY ---")

    pairs = [
        ('front_left_leg', 'front_right_leg', 'front leg'),
        ('front_left_foot', 'front_right_foot', 'front foot'),
        ('rear_left_leg', 'rear_right_leg', 'rear leg'),
        ('rear_left_foot', 'rear_right_foot', 'rear foot'),
    ]

    total_asymmetry = 0
    print(f"{'Pair':>12s} {'L_mean':>8s} {'R_mean':>8s} {'L_std':>7s} {'R_std':>7s} {'bias':>8s}")
    print("-" * 55)
    for l, r, label in pairs:
        li, ri = ji[l], ji[r]
        lv, rv_val = jp[:, li], jp[:, ri]
        bias = lv.mean() - rv_val.mean()
        total_asymmetry += abs(bias)
        print(f"{label:>12s} {lv.mean():>8.4f} {rv_val.mean():>8.4f} "
              f"{lv.std():>7.4f} {rv_val.std():>7.4f} {bias:>+8.4f}")
    print(f"\nTotal L/R asymmetry: {total_asymmetry:.4f}")

    # ═══════════════════════════════════════
    # 6. Gait Frequency
    # ═══════════════════════════════════════
    print("\n--- 6. GAIT FREQUENCY ---")
    fl_leg = jp[:, ji['front_left_leg']]
    fl_centered = fl_leg - fl_leg.mean()
    crossings = np.where(np.diff(np.sign(fl_centered)))[0]
    if len(crossings) > 2:
        half_periods = np.diff(crossings) * dt
        valid = half_periods[half_periods > 0.05]
        if len(valid) > 0:
            freq = 1.0 / (2 * valid.mean())
            print(f"Gait frequency: {freq:.2f} Hz")
            print(f"Cycle period: {2*valid.mean():.4f}s")
            print(f"Cycles in recording: {len(valid)//2}")

    # ═══════════════════════════════════════
    # 7. Summary Score Card
    # ═══════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY SCORE CARD — V68 model_2500")
    print("=" * 70)
    print(f"  Forward speed:     {avg_speed:.3f} m/s")
    print(f"  Lateral drift:     {abs(lat_drift):.4f} m ({abs(lat_drift/dist)*100:.1f}%)")
    print(f"  Body height:       {body_z.mean():.3f} m (std {body_z.std():.4f})")
    print(f"  Roll/Pitch/Yaw:    {wx.std():.3f} / {wy.std():.3f} / {wz.std():.3f} rad/s")
    print(f"  Cost of Transport: {cot:.2f}")
    print(f"  L/R asymmetry:     {total_asymmetry:.4f}")
    print(f"  Gait frequency:    {freq:.2f} Hz" if len(crossings) > 2 else "  Gait frequency: N/A")
    print("=" * 70)


if __name__ == "__main__":
    report()
