# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Evaluate one zero-action standing actuator candidate for SpotMicro."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Evaluate one SpotMicro zero-action actuator candidate.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=16, help="Number of environments.")
parser.add_argument("--steps", type=int, default=120, help="Zero-action steps.")
parser.add_argument("--contact_threshold", type=float, default=1.0)
parser.add_argument("--stiffness", type=float, required=True)
parser.add_argument("--damping", type=float, required=True)
parser.add_argument("--out_json", type=str, required=True)
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
from spot_micro_rl.robots import SPOT_MICRO_CFG


def _set_actuator_gains(stiffness: float, damping: float):
    SPOT_MICRO_CFG.actuators["legs"].stiffness = {".*": float(stiffness)}
    SPOT_MICRO_CFG.actuators["legs"].damping = {".*": float(damping)}


def _toe_contact(env, threshold: float) -> torch.Tensor:
    contact_sensor = env.scene.sensors["contact_forces"]
    forces = contact_sensor.data.net_forces_w_history[:, 0, env._toe_body_ids]
    return (torch.norm(forces, dim=-1) > threshold).float()


def _score(m: dict[str, float]) -> float:
    return (
        2.0 * m["toe_contact_mean"]
        + 1.5 * m["toe_contact_20"]
        + 0.8 * m["mean_ep_len"] / max(args_cli.steps, 1)
        - 8.0 * m["overshoot"]
        - 2.0 * m["terminated_frac"]
        - 1.2 * m["drift_20"]
        - 0.8 * m["ang_20"]
        - 0.4 * m["drift_final"]
        - 0.2 * m["ang_final"]
    )


def main():
    _set_actuator_gains(args_cli.stiffness, args_cli.damping)
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
    env._toe_body_ids = torch.tensor(
        [
            robot.find_bodies(name)[0][0]
            for name in ["front_left_toe_link", "front_right_toe_link", "rear_left_toe_link", "rear_right_toe_link"]
        ],
        device=env.device,
        dtype=torch.long,
    )
    root_pos0 = robot.data.root_pos_w.clone()

    height_series = []
    ang_series = []
    drift_series = []
    toe_series = []
    terminated = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    time_outs = torch.zeros_like(terminated)

    with torch.inference_mode():
        for _ in range(args_cli.steps):
            actions = torch.zeros((env.num_envs, env.action_manager.total_action_dim), device=env.device)
            _, _, terminated, time_outs, _ = env.step(actions)
            height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
            roots_xy = robot.data.root_pos_w[:, :2] - root_pos0[:, :2]
            drift_xy = torch.norm(roots_xy, dim=1)
            ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
            toe_contact = _toe_contact(env, args_cli.contact_threshold).mean(dim=1)
            height_series.append(height.mean().item())
            drift_series.append(drift_xy.mean().item())
            ang_series.append(ang_xy.mean().item())
            toe_series.append(toe_contact.mean().item())
            if not simulation_app.is_running():
                break

    env.close()

    init_height = height_series[0]
    peak_height = max(height_series)
    metrics = {
        "stiffness": float(args_cli.stiffness),
        "damping": float(args_cli.damping),
        "init_height": float(init_height),
        "peak_height": float(peak_height),
        "height_20": float(height_series[min(19, len(height_series) - 1)]),
        "overshoot": float(max(0.0, peak_height - init_height)),
        "toe_contact_mean": float(sum(toe_series) / len(toe_series)),
        "toe_contact_20": float(toe_series[min(19, len(toe_series) - 1)]),
        "drift_20": float(drift_series[min(19, len(drift_series) - 1)]),
        "ang_20": float(ang_series[min(19, len(ang_series) - 1)]),
        "drift_final": float(drift_series[-1]),
        "ang_final": float(ang_series[-1]),
        "terminated_frac": float(terminated.float().mean().item()),
        "time_out_frac": float(time_outs.float().mean().item()),
        "mean_ep_len": float(env.episode_length_buf.float().mean().item()),
    }
    metrics["score"] = _score(metrics)

    out_path = Path(args_cli.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(metrics, sort_keys=True))


if __name__ == "__main__":
    main()
    simulation_app.close()
