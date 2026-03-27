"""Deterministic Trot via Gym Environment — same setup as RL training.

Uses the exact same Gym environment as training, but replaces RL policy
with a sinusoidal trot joint trajectory. This guarantees robot config,
actuators, and physics are identical to RL training.

Usage:
  C:\\IsaacLab\\isaaclab.bat -p scripts/rsl_rl/deterministic_trot.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=1
  C:\\IsaacLab\\isaaclab.bat -p scripts/rsl_rl/deterministic_trot.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=1 --video --video_length=500 --headless
"""

from __future__ import annotations

import argparse
import math
import sys

from isaaclab.app import AppLauncher

# CLI
parser = argparse.ArgumentParser(description="Deterministic trot via Gym env")
parser.add_argument("--video", action="store_true", default=False)
parser.add_argument("--video_length", type=int, default=500)
parser.add_argument("--disable_fabric", action="store_true", default=False)
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--task", type=str, default="Isaac-Velocity-Flat-SpotMicro-v0")
parser.add_argument("--seed", type=int, default=42)
# Trot params
parser.add_argument("--frequency", type=float, default=1.0, help="Trot Hz")
parser.add_argument("--amplitude", type=float, default=0.15, help="Leg swing amplitude")

AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
if args_cli.video:
    args_cli.enable_cameras = True

sys.argv = [sys.argv[0]] + hydra_args
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
import spot_micro_rl.tasks  # noqa: F401

from isaaclab_tasks.utils.hydra import hydra_task_config


@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg, agent_cfg):
    """Main: create env, run deterministic trot."""

    # Minimal env setup
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.episode_length_s = 20.0  # 긴 에피소드

    # 초기 노이즈 비활성화 (open-loop에서 안정적 서기 필요)
    env_cfg.events.reset_robot_joints.params["position_range"] = (0.0, 0.0)
    env_cfg.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
    try:
        env_cfg.events.base_external_force_torque.params["asset_cfg"].body_names = []
    except Exception:
        pass
    try:
        env_cfg.events.reset_base.params["pose_range"] = {}
        env_cfg.events.reset_base.params["velocity_range"] = {}
    except Exception:
        pass

    # velocity command를 0으로 (로봇을 밀지 않게)
    try:
        env_cfg.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
        env_cfg.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        env_cfg.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
    except Exception:
        pass

    # 액추에이터 변경 없음 — RL 훈련과 동일 (DCMotor stiffness=15, effort=15)

    # 카메라: 로봇 정 오른쪽 (Y축 음수 방향)
    env_cfg.viewer.eye = (0.0, -1.0, 0.25)
    env_cfg.viewer.lookat = (0.0, 0.0, 0.15)

    env_cfg.scene.robot.spawn.fix_base = False  # 바닥 서기 테스트

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    # Get action space info
    action_dim = env.action_space.shape[-1]  # should be 12
    print(f"\n{'='*60}")
    print(f"Deterministic Trot Controller")
    print(f"{'='*60}")
    print(f"  Task: {args_cli.task}")
    print(f"  Action dim: {action_dim}")
    print(f"  Frequency: {args_cli.frequency} Hz")
    print(f"  Amplitude: {args_cli.amplitude} rad")
    print(f"{'='*60}\n")

    # Joint order in action space (from env_cfg):
    # [FL_shoulder, FL_leg, FL_foot, FR_shoulder, FR_leg, FR_foot,
    #  RL_shoulder, RL_leg, RL_foot, RR_shoulder, RR_leg, RR_foot]
    #
    # Action = delta from default pose (action_space is typically [-1, 1] scaled)
    # Isaac Lab LocomotionVelocity: action = joint_pos target (after scaling)
    # Default pose: shoulder=-0.04, leg=-0.71, foot=1.31

    # Trot phase: FL+RR together, FR+RL together
    PHASE_OFFSETS = [0.0, math.pi, math.pi, 0.0]  # FL, FR, RL, RR

    obs, _ = env.reset()
    step = 0
    max_steps = args_cli.video_length if args_cli.video else 2000

    while step < max_steps and simulation_app.is_running():
        t = step * env.unwrapped.step_dt

        # Build action: 12-dim joint position offsets from default
        action = torch.zeros(args_cli.num_envs, action_dim, device=env.unwrapped.device)

        freq = args_cli.frequency
        amp = args_cli.amplitude

        # 이상적 trot: 4발 동일 축, 대각선 교대
        for leg_idx in range(4):
            phase = (2.0 * math.pi * freq * t + PHASE_OFFSETS[leg_idx]) % (2.0 * math.pi)
            base = leg_idx * 3

            action[:, base + 0] = 0.0                                   # shoulder 고정
            action[:, base + 1] = amp * math.sin(phase)                 # leg 스윙
            action[:, base + 2] = -amp * 0.4 * math.sin(phase)         # foot 보조

        # Scale action to [-1, 1] range if needed
        # Isaac Lab locomotion envs typically use action_scale to convert [-1,1] to joint pos delta
        # So we need to divide by action_scale
        # Default action_scale is usually ~0.25-0.5
        # For now, use raw values (they are small enough to be within [-1,1])

        obs, reward, terminated, truncated, info = env.step(action)
        step += 1

        if step % 200 == 0:
            robot = env.unwrapped.scene["robot"]
            pos = robot.data.root_pos_w[0]
            height = pos[2].item()
            joint_pos = robot.data.joint_pos[0]
            joint_names = robot.joint_names

            log_line = f"step {step} | root height={height:.4f}\n"
            log_line += f"  joint positions:\n"
            for j, jn in enumerate(joint_names):
                log_line += f"    {jn:<30} = {joint_pos[j].item():+.4f}\n"

            # body positions (all bodies)
            try:
                body_pos = robot.data.body_pos_w[0]
                body_names = robot.body_names
                log_line += f"  body world positions:\n"
                for i, name in enumerate(body_names):
                    x = body_pos[i][0].item()
                    y = body_pos[i][1].item()
                    z = body_pos[i][2].item()
                    log_line += f"    {name:<30} x={x:+.4f}  y={y:+.4f}  z={z:+.4f}\n"
            except Exception as e:
                log_line += f"  body_pos error: {e}\n"

            print(log_line)
            import os
            coord_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_trot_coords.txt")
            with open(coord_path, "a") as f:
                f.write(log_line + "\n")

    env.close()
    print("\n[Done] Deterministic trot completed.")


if __name__ == "__main__":
    main()
