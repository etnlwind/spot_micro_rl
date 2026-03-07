"""Combine TensorBoard data from all training runs to show full progression."""
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

runs = [
    'd:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-06_20-27-43',
    'd:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-07_01-09-47',
    'd:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-07_04-22-15',
    'd:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-07_07-33-36',
]

# Merge all data
merged = {}
for r in runs:
    try:
        ea = EventAccumulator(r)
        ea.Reload()
        for tag in ea.Tags().get('scalars', []):
            if tag not in merged:
                merged[tag] = {}
            for e in ea.Scalars(tag):
                merged[tag][e.step] = e.value
    except:
        pass

tags_to_check = [
    'Train/mean_reward', 'Train/mean_episode_length',
    'Episode_Reward/gait_cycle_period', 'Episode_Reward/stride_length',
    'Episode_Reward/rear_alternation', 'Episode_Reward/trot_gait',
    'Episode_Reward/rear_joint_velocity', 'Episode_Reward/forward_velocity',
    'Episode_Reward/forward_velocity_bootstrap',
    'Episode_Reward/joint_vel_l2', 'Episode_Reward/leg_lift',
    'Episode_Reward/diagonal_coupling',
    'Episode_Reward/standing_height', 'Episode_Reward/height_bonus',
    'Episode_Reward/action_rate_l2',
    'Episode_Termination/bad_orientation', 'Episode_Termination/time_out',
    'Metrics/base_velocity/error_vel_xy',
    'Policy/mean_noise_std',
]

milestones = [0, 200, 600, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4488]
# Mark phases
print("Phase:   |--- Phase 1 (STAND) ---|------------ Phase 2 (WALK) ------------|")
print(f"Iter:    ", end="")
for m in milestones:
    print(f"{m:>8}", end="")
print()
print("-" * (9 + 8 * len(milestones)))

for tag in tags_to_check:
    if tag not in merged:
        continue
    vals = merged[tag]
    name = tag.split('/')[-1]
    if len(name) > 28:
        name = name[:28]
    row = f"{name:>28} "
    for m in milestones:
        if not vals:
            row += " " * 8
            continue
        closest = min(vals.keys(), key=lambda s: abs(s - m))
        if abs(closest - m) <= 15:
            row += f"{vals[closest]:>8.3f}"
        else:
            row += " " * 8
    print(row)
