# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Sweep SpotMicro standing base height for zero-action contact viability.

Purpose:
    Find a base init z that actually produces planted toe contact at reset,
    before changing reward terms again.

Usage:
    C:\\IsaacLab\\isaaclab.bat -p scripts/utils/standing_pose_sweep.py --task Isaac-Velocity-Flat-SpotMicro-v0
    C:\\IsaacLab\\isaaclab.bat -p scripts/utils/standing_pose_sweep.py --task Isaac-Velocity-Flat-SpotMicro-v0 --z_values 0.15 0.155 0.16 0.165 0.17
"""

from __future__ import annotations

import argparse
import traceback
from datetime import datetime
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Sweep standing base z for SpotMicro zero-action probe.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=64, help="Number of environments.")
parser.add_argument("--steps", type=int, default=20, help="Zero-action steps per candidate.")
parser.add_argument(
    "--z_values",
    type=float,
    nargs="*",
    default=[0.15, 0.155, 0.16, 0.165, 0.17, 0.175, 0.18, 0.185, 0.19],
    help="Candidate base init z values to sweep.",
)
parser.add_argument(
    "--contact_threshold",
    type=float,
    default=1.0,
    help="Toe contact threshold in Newtons.",
)
parser.add_argument(
    "--log_file",
    type=str,
    default=None,
    help="Optional path to save sweep logs. Defaults to logs/diagnostics/standing_pose_sweep_<timestamp>.log",
)
parser.add_argument("--disable_fabric", action="store_true", default=False)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg

import spot_micro_rl.tasks  # noqa: F401


def _make_logger(log_file_arg: str | None):
    if log_file_arg is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path("logs") / "diagnostics" / f"standing_pose_sweep_{timestamp}.log"
    else:
        log_path = Path(log_file_arg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")

    def log(line: str):
        print(line)
        handle.write(line + "\n")
        handle.flush()

    return log, handle, log_path


def _toe_contact_ratio(env, threshold: float) -> torch.Tensor:
    contact_sensor = env.scene.sensors.get("contact_forces", None)
    if contact_sensor is None:
        return torch.zeros(env.num_envs, device=env.device)
    force_history = contact_sensor.data.net_forces_w_history.norm(dim=-1)
    contacts = (force_history > threshold).float()
    return contacts.mean(dim=1).mean(dim=1)


def _summarize(env, terminated: torch.Tensor, time_outs: torch.Tensor, z_value: float, step_idx: int, threshold: float) -> str:
    robot = env.scene["robot"]
    roots_xy = robot.data.root_pos_w[:, :2] - env._pose_sweep_root_pos0[:, :2]
    drift_xy = torch.norm(roots_xy, dim=1)
    vel_xy = torch.norm(robot.data.root_lin_vel_b[:, :2], dim=1)
    ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
    height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    toe_contact = _toe_contact_ratio(env, threshold)
    return (
        f"z={z_value:.3f} | step={step_idx}"
        f" | drift_xy_mean={drift_xy.mean().item():.4f}"
        f" | vel_xy_mean={vel_xy.mean().item():.4f}"
        f" | ang_xy_mean={ang_xy.mean().item():.4f}"
        f" | height_mean={height.mean().item():.4f}"
        f" | height_min={height.min().item():.4f}"
        f" | toe_contact_mean={toe_contact.mean().item():.4f}"
        f" | toe_contact_min={toe_contact.min().item():.4f}"
        f" | terminated_frac={terminated.float().mean().item():.4f}"
        f" | time_out_frac={time_outs.float().mean().item():.4f}"
    )


def main():
    log, handle, log_path = _make_logger(args_cli.log_file)
    log(f"[INFO] log_file={log_path}")
    log(f"[INFO] task={args_cli.task}")
    log(f"[INFO] steps_per_candidate={args_cli.steps}")
    log(f"[INFO] z_values={args_cli.z_values}")

    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    env = gym.make(args_cli.task, cfg=env_cfg)
    env.reset()
    env = env.unwrapped
    robot = env.scene["robot"]

    with torch.inference_mode():
        for z_value in args_cli.z_values:
            try:
                env_ids = torch.arange(env.num_envs, device=env.device)
                root_state = robot.data.default_root_state.clone()
                root_state[:, 0] = env.scene.env_origins[:, 0]
                root_state[:, 1] = env.scene.env_origins[:, 1]
                root_state[:, 2] = env.scene.env_origins[:, 2] + float(z_value)
                root_state[:, 7:13] = 0.0
                joint_pos = robot.data.default_joint_pos.clone()
                joint_vel = robot.data.default_joint_vel.clone()

                robot.write_root_state_to_sim(root_state, env_ids=env_ids)
                robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=env_ids)
                robot.set_joint_position_target(joint_pos, env_ids=env_ids)
                env.episode_length_buf[env_ids] = 0
                env._pose_sweep_root_pos0 = root_state[:, :3].clone()

                terminated = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
                time_outs = torch.zeros_like(terminated)
                for step_idx in range(1, args_cli.steps + 1):
                    actions = torch.zeros((env.num_envs, env.action_manager.total_action_dim), device=env.device)
                    _, _, terminated, time_outs, _ = env.step(actions)
                    if step_idx == 1 or step_idx == args_cli.steps:
                        log(_summarize(env, terminated, time_outs, z_value, step_idx, args_cli.contact_threshold))
            except Exception:
                log(f"[ERROR] z={z_value:.3f} failed")
                for line in traceback.format_exc().splitlines():
                    log(line)
                break

            if not simulation_app.is_running():
                break

    env.close()

    handle.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
