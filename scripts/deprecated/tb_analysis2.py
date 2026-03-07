from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
import sys

logdir = 'd:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-07_07-33-36'
ea = EventAccumulator(logdir)
ea.Reload()

tags = ea.Tags().get('scalars', [])
print(f"Tags: {len(tags)}")

# Get latest step
for tag in ['Train/mean_reward', 'Train/mean_episode_length']:
    events = ea.Scalars(tag)
    if events:
        print(f"{tag}: {len(events)} steps, latest step={events[-1].step}, val={events[-1].value:.2f}")

# Key metrics at milestones
tags_to_check = [
    'Train/mean_reward', 'Train/mean_episode_length',
    'Episode_Reward/gait_cycle_period', 'Episode_Reward/stride_length',
    'Episode_Reward/rear_alternation', 'Episode_Reward/trot_gait',
    'Episode_Reward/rear_joint_velocity', 'Episode_Reward/forward_velocity',
    'Episode_Reward/forward_velocity_bootstrap',
    'Episode_Reward/joint_vel_l2', 'Episode_Reward/leg_lift',
    'Episode_Reward/diagonal_coupling',
    'Episode_Reward/foot_clearance',
    'Episode_Reward/standing_height', 'Episode_Reward/height_bonus',
    'Episode_Reward/same_side_penalty', 'Episode_Reward/rear_both_ground',
    'Episode_Reward/undesired_contacts', 'Episode_Reward/feet_below_knees',
    'Episode_Reward/rear_joint_frozen',
    'Episode_Reward/action_rate_l2', 'Episode_Reward/dof_acc_l2',
    'Episode_Reward/flat_orientation_l2', 'Episode_Reward/shoulder_neutral',
    'Episode_Reward/base_height_l2',
    'Episode_Termination/bad_orientation', 'Episode_Termination/time_out',
    'Metrics/base_velocity/error_vel_xy', 'Metrics/base_velocity/error_vel_yaw',
    'Policy/mean_noise_std',
]

# Find actual latest step
all_events = ea.Scalars('Train/mean_reward')
latest_step = all_events[-1].step

# Pick milestones
milestones = [3200, 3400, 3600, 3800, 4000, 4200, latest_step]
milestones = sorted(set(milestones))

header = f"{'Tag':<52}"
for m in milestones:
    header += f"{'@'+str(m):>10}"
print(header)
print('-' * (52 + 10 * len(milestones)))

for tag in tags_to_check:
    try:
        events = ea.Scalars(tag)
        vals = {e.step: e.value for e in events}
        row = f"{tag:<52}"
        for m in milestones:
            closest = min(vals.keys(), key=lambda s: abs(s - m))
            if abs(closest - m) <= 10:
                row += f"{vals[closest]:>10.4f}"
            else:
                row += " " * 10
        print(row)
    except Exception as e:
        print(f"{tag:<52} ERROR: {e}")
