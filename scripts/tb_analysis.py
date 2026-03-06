from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
ea = EventAccumulator('d:/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-03-07_01-09-47')
ea.Reload()

tags_to_check = [
    'Train/mean_reward', 'Train/mean_episode_length',
    'Episode_Reward/gait_cycle_period', 'Episode_Reward/stride_length',
    'Episode_Reward/rear_alternation', 'Episode_Reward/trot_gait',
    'Episode_Reward/rear_joint_velocity', 'Episode_Reward/forward_velocity',
    'Episode_Reward/forward_velocity_bootstrap',
    'Episode_Reward/joint_vel_l2', 'Episode_Reward/leg_lift',
    'Episode_Reward/diagonal_coupling',
    'Episode_Reward/foot_clearance',
    'Episode_Termination/bad_orientation', 'Episode_Termination/time_out',
    'Metrics/base_velocity/error_vel_xy',
    'Policy/mean_noise_std',
]
milestones = [601, 620, 640, 660, 680, 695]
header = f"{'Tag':<52}"
for m in milestones:
    header += f"{'@'+str(m):>10}"
print(header)
print('-' * 112)
for tag in tags_to_check:
    try:
        events = ea.Scalars(tag)
        vals = {e.step: e.value for e in events}
        row = f"{tag:<52}"
        for m in milestones:
            closest = min(vals.keys(), key=lambda s: abs(s - m))
            if abs(closest - m) <= 5:
                row += f"{vals[closest]:>10.4f}"
            else:
                row += " " * 10
        print(row)
    except Exception as e:
        print(f"{tag:<52} ERROR: {e}")
