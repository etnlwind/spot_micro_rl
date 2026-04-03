# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Sweep SpotMicro standing joint angles for planted-stand viability.

Purpose:
    With base z fixed, search for leg/foot angles that improve toe contact and
    reduce zero-action drift before returning to reward tuning.

Usage:
    C:\\IsaacLab\\isaaclab.bat -p scripts/utils/standing_joint_sweep.py --task Isaac-Velocity-Flat-SpotMicro-v0
"""

from __future__ import annotations

import argparse
import itertools
import traceback
from datetime import datetime
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Sweep standing joint angles for SpotMicro zero-action viability.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=64, help="Number of environments.")
parser.add_argument("--steps", type=int, default=20, help="Zero-action steps per candidate.")
parser.add_argument("--base_z", type=float, default=0.15, help="Fixed base z for this sweep.")
parser.add_argument(
    "--front_legs",
    type=float,
    nargs="*",
    default=[-0.74, -0.70, -0.66, -0.62],
    help="Candidate front leg joint angles.",
)
parser.add_argument(
    "--rear_legs",
    type=float,
    nargs="*",
    default=[-0.72, -0.68, -0.64, -0.60],
    help="Candidate rear leg joint angles.",
)
parser.add_argument(
    "--feet",
    type=float,
    nargs="*",
    default=[1.38, 1.44, 1.50, 1.56],
    help="Candidate foot joint angles used on all four legs.",
)
parser.add_argument("--fl_shoulder", type=float, nargs="*", default=None, help="Front-left shoulder candidates.")
parser.add_argument("--fr_shoulder", type=float, nargs="*", default=None, help="Front-right shoulder candidates.")
parser.add_argument("--rl_shoulder", type=float, nargs="*", default=None, help="Rear-left shoulder candidates.")
parser.add_argument("--rr_shoulder", type=float, nargs="*", default=None, help="Rear-right shoulder candidates.")
parser.add_argument("--fl_leg", type=float, nargs="*", default=None, help="Front-left leg candidates.")
parser.add_argument("--fr_leg", type=float, nargs="*", default=None, help="Front-right leg candidates.")
parser.add_argument("--rl_leg", type=float, nargs="*", default=None, help="Rear-left leg candidates.")
parser.add_argument("--rr_leg", type=float, nargs="*", default=None, help="Rear-right leg candidates.")
parser.add_argument("--fl_foot", type=float, nargs="*", default=None, help="Front-left foot candidates.")
parser.add_argument("--fr_foot", type=float, nargs="*", default=None, help="Front-right foot candidates.")
parser.add_argument("--rl_foot", type=float, nargs="*", default=None, help="Rear-left foot candidates.")
parser.add_argument("--rr_foot", type=float, nargs="*", default=None, help="Rear-right foot candidates.")
parser.add_argument("--contact_threshold", type=float, default=1.0)
parser.add_argument(
    "--log_file",
    type=str,
    default=None,
    help="Optional log file path. Defaults to logs/diagnostics/standing_joint_sweep_<timestamp>.log",
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
        log_path = Path("logs") / "diagnostics" / f"standing_joint_sweep_{timestamp}.log"
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


def _toe_contact_matrix(env, threshold: float) -> torch.Tensor:
    contact_sensor = env.scene.sensors.get("contact_forces", None)
    if contact_sensor is None:
        return torch.zeros((env.num_envs, 4), device=env.device)
    toe_ids = env._joint_sweep_toe_body_ids
    force_history = contact_sensor.data.net_forces_w_history[:, :, toe_ids].norm(dim=-1)
    return (force_history > threshold).float().mean(dim=1)


def _set_candidate_default_joint_pos(robot, pose: dict[str, float]):
    joint_names = [
        "front_left_shoulder", "front_left_leg", "front_left_foot",
        "front_right_shoulder", "front_right_leg", "front_right_foot",
        "rear_left_shoulder", "rear_left_leg", "rear_left_foot",
        "rear_right_shoulder", "rear_right_leg", "rear_right_foot",
    ]
    values = torch.tensor(
        [
            pose["front_left_shoulder"], pose["front_left_leg"], pose["front_left_foot"],
            pose["front_right_shoulder"], pose["front_right_leg"], pose["front_right_foot"],
            pose["rear_left_shoulder"], pose["rear_left_leg"], pose["rear_left_foot"],
            pose["rear_right_shoulder"], pose["rear_right_leg"], pose["rear_right_foot"],
        ],
        device=robot.device,
    )
    for i, name in enumerate(joint_names):
        joint_id = robot.find_joints(name)[0][0]
        robot.data.default_joint_pos[:, joint_id] = values[i]


def _summarize(env, terminated: torch.Tensor, time_outs: torch.Tensor, pose: dict[str, float], step_idx: int, threshold: float) -> str:
    robot = env.scene["robot"]
    roots_xy = robot.data.root_pos_w[:, :2] - env._joint_sweep_root_pos0[:, :2]
    drift_xy = torch.norm(roots_xy, dim=1)
    vel_xy = torch.norm(robot.data.root_lin_vel_b[:, :2], dim=1)
    ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
    height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    grav_xy = robot.data.projected_gravity_b[:, :2]
    toe_contact = _toe_contact_matrix(env, threshold)
    front_contact = toe_contact[:, :2].mean(dim=1)
    rear_contact = toe_contact[:, 2:].mean(dim=1)
    left_contact = toe_contact[:, [0, 2]].mean(dim=1)
    right_contact = toe_contact[:, [1, 3]].mean(dim=1)
    shoulder_pos_z = robot.data.body_pos_w[:, env._joint_sweep_shoulder_body_ids, 2] - env.scene.env_origins[:, 2].unsqueeze(1)
    front_height = shoulder_pos_z[:, :2].mean(dim=1)
    rear_height = shoulder_pos_z[:, 2:].mean(dim=1)
    left_height = shoulder_pos_z[:, [0, 2]].mean(dim=1)
    right_height = shoulder_pos_z[:, [1, 3]].mean(dim=1)
    pitch_proxy = front_height - rear_height
    roll_proxy = left_height - right_height
    return (
        f"fl_sh={pose['front_left_shoulder']:.3f} | fr_sh={pose['front_right_shoulder']:.3f}"
        f" | rl_sh={pose['rear_left_shoulder']:.3f} | rr_sh={pose['rear_right_shoulder']:.3f}"
        f" | fl_leg={pose['front_left_leg']:.3f} | fr_leg={pose['front_right_leg']:.3f}"
        f" | rl_leg={pose['rear_left_leg']:.3f} | rr_leg={pose['rear_right_leg']:.3f}"
        f" | fl_foot={pose['front_left_foot']:.3f} | fr_foot={pose['front_right_foot']:.3f}"
        f" | rl_foot={pose['rear_left_foot']:.3f} | rr_foot={pose['rear_right_foot']:.3f}"
        f" | step={step_idx}"
        f" | drift_xy_mean={drift_xy.mean().item():.4f}"
        f" | vel_xy_mean={vel_xy.mean().item():.4f}"
        f" | ang_xy_mean={ang_xy.mean().item():.4f}"
        f" | grav_x_mean={grav_xy[:, 0].mean().item():.4f}"
        f" | grav_y_mean={grav_xy[:, 1].mean().item():.4f}"
        f" | height_mean={height.mean().item():.4f}"
        f" | height_min={height.min().item():.4f}"
        f" | front_height_mean={front_height.mean().item():.4f}"
        f" | rear_height_mean={rear_height.mean().item():.4f}"
        f" | left_height_mean={left_height.mean().item():.4f}"
        f" | right_height_mean={right_height.mean().item():.4f}"
        f" | pitch_proxy_mean={pitch_proxy.mean().item():.4f}"
        f" | roll_proxy_mean={roll_proxy.mean().item():.4f}"
        f" | toe_contact_mean={toe_contact.mean().item():.4f}"
        f" | toe_contact_min={toe_contact.min().item():.4f}"
        f" | front_contact_mean={front_contact.mean().item():.4f}"
        f" | rear_contact_mean={rear_contact.mean().item():.4f}"
        f" | left_contact_mean={left_contact.mean().item():.4f}"
        f" | right_contact_mean={right_contact.mean().item():.4f}"
        f" | fl_contact_mean={toe_contact[:, 0].mean().item():.4f}"
        f" | fr_contact_mean={toe_contact[:, 1].mean().item():.4f}"
        f" | rl_contact_mean={toe_contact[:, 2].mean().item():.4f}"
        f" | rr_contact_mean={toe_contact[:, 3].mean().item():.4f}"
        f" | terminated_frac={terminated.float().mean().item():.4f}"
        f" | time_out_frac={time_outs.float().mean().item():.4f}"
    )


def _resolve_candidates() -> list[dict[str, float]]:
    fl_shoulder_pairs = [(v, v) for v in (args_cli.fl_shoulder or [-0.04])] if args_cli.fr_shoulder is None else list(
        itertools.product(args_cli.fl_shoulder or [-0.04], args_cli.fr_shoulder)
    )
    rl_shoulder_pairs = [(v, v) for v in (args_cli.rl_shoulder or [-0.04])] if args_cli.rr_shoulder is None else list(
        itertools.product(args_cli.rl_shoulder or [-0.04], args_cli.rr_shoulder)
    )
    if args_cli.fl_shoulder is None and args_cli.fr_shoulder is None:
        fl_shoulder_pairs = [(-0.04, 0.04)]
    if args_cli.rl_shoulder is None and args_cli.rr_shoulder is None:
        rl_shoulder_pairs = [(-0.04, 0.04)]

    front_leg_pairs = [(v, v) for v in args_cli.front_legs] if args_cli.fr_leg is None and args_cli.fl_leg is None else list(
        itertools.product(args_cli.fl_leg or args_cli.front_legs, args_cli.fr_leg or args_cli.front_legs)
    )
    rear_leg_pairs = [(v, v) for v in args_cli.rear_legs] if args_cli.rr_leg is None and args_cli.rl_leg is None else list(
        itertools.product(args_cli.rl_leg or args_cli.rear_legs, args_cli.rr_leg or args_cli.rear_legs)
    )
    front_foot_pairs = [(v, v) for v in args_cli.feet] if args_cli.fr_foot is None and args_cli.fl_foot is None else list(
        itertools.product(args_cli.fl_foot or args_cli.feet, args_cli.fr_foot or args_cli.feet)
    )
    rear_foot_pairs = [(v, v) for v in args_cli.feet] if args_cli.rr_foot is None and args_cli.rl_foot is None else list(
        itertools.product(args_cli.rl_foot or args_cli.feet, args_cli.rr_foot or args_cli.feet)
    )
    poses = []
    for values in itertools.product(
        fl_shoulder_pairs,
        rl_shoulder_pairs,
        front_leg_pairs,
        rear_leg_pairs,
        front_foot_pairs,
        rear_foot_pairs,
    ):
        poses.append(
            {
                "front_left_shoulder": values[0][0],
                "front_right_shoulder": values[0][1],
                "rear_left_shoulder": values[1][0],
                "rear_right_shoulder": values[1][1],
                "front_left_leg": values[2][0],
                "front_right_leg": values[2][1],
                "rear_left_leg": values[3][0],
                "rear_right_leg": values[3][1],
                "front_left_foot": values[4][0],
                "front_right_foot": values[4][1],
                "rear_left_foot": values[5][0],
                "rear_right_foot": values[5][1],
            }
        )
    return poses


def main():
    log, handle, log_path = _make_logger(args_cli.log_file)
    log(f"[INFO] log_file={log_path}")
    log(f"[INFO] task={args_cli.task}")
    log(f"[INFO] steps_per_candidate={args_cli.steps}")
    log(f"[INFO] base_z={args_cli.base_z}")
    log(f"[INFO] front_legs={args_cli.front_legs}")
    log(f"[INFO] rear_legs={args_cli.rear_legs}")
    log(f"[INFO] feet={args_cli.feet}")
    candidate_poses = _resolve_candidates()
    log(f"[INFO] candidate_count={len(candidate_poses)}")

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
    env._joint_sweep_toe_body_ids = torch.tensor(
        [robot.find_bodies(name)[0][0] for name in [
            "front_left_toe_link",
            "front_right_toe_link",
            "rear_left_toe_link",
            "rear_right_toe_link",
        ]],
        device=env.device,
        dtype=torch.long,
    )
    env._joint_sweep_shoulder_body_ids = torch.tensor(
        [robot.find_bodies(name)[0][0] for name in [
            "front_left_shoulder_link",
            "front_right_shoulder_link",
            "rear_left_shoulder_link",
            "rear_right_shoulder_link",
        ]],
        device=env.device,
        dtype=torch.long,
    )
    results: list[dict[str, float]] = []

    with torch.inference_mode():
        for pose in candidate_poses:
            try:
                env_ids = torch.arange(env.num_envs, device=env.device)
                _set_candidate_default_joint_pos(robot, pose)

                root_state = robot.data.default_root_state.clone()
                root_state[:, 0] = env.scene.env_origins[:, 0]
                root_state[:, 1] = env.scene.env_origins[:, 1]
                root_state[:, 2] = env.scene.env_origins[:, 2] + float(args_cli.base_z)
                root_state[:, 7:13] = 0.0
                joint_pos = robot.data.default_joint_pos.clone()
                joint_vel = robot.data.default_joint_vel.clone()

                robot.write_root_state_to_sim(root_state, env_ids=env_ids)
                robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=env_ids)
                robot.set_joint_position_target(joint_pos, env_ids=env_ids)
                env.episode_length_buf[env_ids] = 0
                env._joint_sweep_root_pos0 = root_state[:, :3].clone()

                terminated = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
                time_outs = torch.zeros_like(terminated)
                for step_idx in range(1, args_cli.steps + 1):
                    actions = torch.zeros((env.num_envs, env.action_manager.total_action_dim), device=env.device)
                    _, _, terminated, time_outs, _ = env.step(actions)
                    if step_idx == 1 or step_idx == args_cli.steps:
                        log(_summarize(env, terminated, time_outs, pose, step_idx, args_cli.contact_threshold))
                    if step_idx == args_cli.steps:
                        roots_xy = robot.data.root_pos_w[:, :2] - env._joint_sweep_root_pos0[:, :2]
                        drift_xy = torch.norm(roots_xy, dim=1)
                        vel_xy = torch.norm(robot.data.root_lin_vel_b[:, :2], dim=1)
                        ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
                        height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
                        shoulder_pos_z = robot.data.body_pos_w[:, env._joint_sweep_shoulder_body_ids, 2] - env.scene.env_origins[:, 2].unsqueeze(1)
                        toe_contact = _toe_contact_matrix(env, args_cli.contact_threshold)
                        front_contact = toe_contact[:, :2].mean(dim=1)
                        rear_contact = toe_contact[:, 2:].mean(dim=1)
                        pitch_proxy = shoulder_pos_z[:, :2].mean(dim=1) - shoulder_pos_z[:, 2:].mean(dim=1)
                        roll_proxy = shoulder_pos_z[:, [0, 2]].mean(dim=1) - shoulder_pos_z[:, [1, 3]].mean(dim=1)
                        results.append(
                            {
                                **{k: float(v) for k, v in pose.items()},
                                "toe_contact_mean": toe_contact.mean().item(),
                                "front_contact_mean": front_contact.mean().item(),
                                "rear_contact_mean": rear_contact.mean().item(),
                                "drift_xy_mean": drift_xy.mean().item(),
                                "vel_xy_mean": vel_xy.mean().item(),
                                "ang_xy_mean": ang_xy.mean().item(),
                                "height_mean": height.mean().item(),
                                "front_height_mean": shoulder_pos_z[:, :2].mean().item(),
                                "rear_height_mean": shoulder_pos_z[:, 2:].mean().item(),
                                "pitch_proxy_mean": pitch_proxy.mean().item(),
                                "roll_proxy_mean": roll_proxy.mean().item(),
                                "terminated_frac": terminated.float().mean().item(),
                            }
                        )
            except Exception:
                pose_desc = " ".join(f"{k}={v:.3f}" for k, v in pose.items())
                log(f"[ERROR] {pose_desc} failed")
                for line in traceback.format_exc().splitlines():
                    log(line)
                break

            if not simulation_app.is_running():
                break

    if results:
        ranked = sorted(
            results,
            key=lambda r: (
                -r["toe_contact_mean"],
                -r["rear_contact_mean"],
                r["terminated_frac"],
                r["drift_xy_mean"],
                r["ang_xy_mean"],
                -r["height_mean"],
            ),
        )
        log("[SUMMARY] top_candidates_by_contact_then_stability")
        for i, row in enumerate(ranked[:10], start=1):
            log(
                f"[SUMMARY] rank={i}"
                f" | fl_sh={row['front_left_shoulder']:.3f}"
                f" | fr_sh={row['front_right_shoulder']:.3f}"
                f" | rl_sh={row['rear_left_shoulder']:.3f}"
                f" | rr_sh={row['rear_right_shoulder']:.3f}"
                f" | fl_leg={row['front_left_leg']:.3f}"
                f" | fr_leg={row['front_right_leg']:.3f}"
                f" | rl_leg={row['rear_left_leg']:.3f}"
                f" | rr_leg={row['rear_right_leg']:.3f}"
                f" | fl_foot={row['front_left_foot']:.3f}"
                f" | fr_foot={row['front_right_foot']:.3f}"
                f" | rl_foot={row['rear_left_foot']:.3f}"
                f" | rr_foot={row['rear_right_foot']:.3f}"
                f" | toe_contact_mean={row['toe_contact_mean']:.4f}"
                f" | rear_contact_mean={row['rear_contact_mean']:.4f}"
                f" | drift_xy_mean={row['drift_xy_mean']:.4f}"
                f" | vel_xy_mean={row['vel_xy_mean']:.4f}"
                f" | ang_xy_mean={row['ang_xy_mean']:.4f}"
                f" | height_mean={row['height_mean']:.4f}"
                f" | front_height_mean={row['front_height_mean']:.4f}"
                f" | rear_height_mean={row['rear_height_mean']:.4f}"
                f" | pitch_proxy_mean={row['pitch_proxy_mean']:.4f}"
                f" | roll_proxy_mean={row['roll_proxy_mean']:.4f}"
                f" | terminated_frac={row['terminated_frac']:.4f}"
            )

    env.close()
    handle.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
