# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Search SpotMicro planted-stand pose with zero-action score optimization.

Purpose:
    Starting from the current best-known standing pose, run a coordinate search
    over base z and per-leg leg/foot angles. This is for finding a genuinely
    stable planted stand before policy training.
"""

from __future__ import annotations

import argparse
import json
import traceback
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Search a zero-action planted-stand pose for SpotMicro.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=64, help="Number of environments.")
parser.add_argument("--steps", type=int, default=60, help="Zero-action steps per evaluation.")
parser.add_argument("--contact_threshold", type=float, default=1.0)
parser.add_argument("--base_z", type=float, default=0.15)
parser.add_argument("--fl_leg", type=float, default=-0.66)
parser.add_argument("--fr_leg", type=float, default=-0.66)
parser.add_argument("--rl_leg", type=float, default=-0.68)
parser.add_argument("--rr_leg", type=float, default=-0.68)
parser.add_argument("--fl_foot", type=float, default=1.56)
parser.add_argument("--fr_foot", type=float, default=1.56)
parser.add_argument("--rl_foot", type=float, default=1.56)
parser.add_argument("--rr_foot", type=float, default=1.56)
parser.add_argument("--fl_shoulder", type=float, default=-0.04)
parser.add_argument("--fr_shoulder", type=float, default=0.04)
parser.add_argument("--rl_shoulder", type=float, default=-0.04)
parser.add_argument("--rr_shoulder", type=float, default=0.04)
parser.add_argument("--base_z_step", type=float, default=0.01, help="Initial search step for base z.")
parser.add_argument("--joint_step", type=float, default=0.04, help="Initial search step for leg/foot joints.")
parser.add_argument("--base_z_min_step", type=float, default=0.0025, help="Minimum base z step before stopping.")
parser.add_argument("--joint_min_step", type=float, default=0.01, help="Minimum joint step before stopping.")
parser.add_argument("--max_passes", type=int, default=6, help="Maximum outer passes over all coordinates.")
parser.add_argument(
    "--log_file",
    type=str,
    default=None,
    help="Optional log path. Defaults to logs/diagnostics/standing_pose_search_<timestamp>.log",
)
parser.add_argument(
    "--checkpoint_file",
    type=str,
    default=None,
    help="Optional checkpoint path. Defaults to logs/diagnostics/standing_pose_search_latest.json when log_file is provided.",
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


POSE_KEYS = [
    "base_z",
    "front_left_shoulder", "front_right_shoulder", "rear_left_shoulder", "rear_right_shoulder",
    "front_left_leg", "front_right_leg", "rear_left_leg", "rear_right_leg",
    "front_left_foot", "front_right_foot", "rear_left_foot", "rear_right_foot",
]


def _make_logger(log_file_arg: str | None):
    if log_file_arg is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path("logs") / "diagnostics" / f"standing_pose_search_{timestamp}.log"
    else:
        log_path = Path(log_file_arg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")

    def log(line: str):
        print(line)
        handle.write(line + "\n")
        handle.flush()

    return log, handle, log_path


def _resolve_checkpoint_path(log_path: Path, checkpoint_file_arg: str | None) -> Path:
    if checkpoint_file_arg is not None:
        return Path(checkpoint_file_arg)
    if log_path.name.endswith(".log"):
        return log_path.with_suffix(".json")
    return log_path.parent / f"{log_path.name}.json"


def _pose_from_args() -> dict[str, float]:
    return {
        "base_z": args_cli.base_z,
        "front_left_shoulder": args_cli.fl_shoulder,
        "front_right_shoulder": args_cli.fr_shoulder,
        "rear_left_shoulder": args_cli.rl_shoulder,
        "rear_right_shoulder": args_cli.rr_shoulder,
        "front_left_leg": args_cli.fl_leg,
        "front_right_leg": args_cli.fr_leg,
        "rear_left_leg": args_cli.rl_leg,
        "rear_right_leg": args_cli.rr_leg,
        "front_left_foot": args_cli.fl_foot,
        "front_right_foot": args_cli.fr_foot,
        "rear_left_foot": args_cli.rl_foot,
        "rear_right_foot": args_cli.rr_foot,
    }


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


def _toe_contact_matrix(env, threshold: float) -> torch.Tensor:
    contact_sensor = env.scene.sensors.get("contact_forces", None)
    if contact_sensor is None:
        return torch.zeros((env.num_envs, 4), device=env.device)
    force_history = contact_sensor.data.net_forces_w_history[:, :, env._pose_search_toe_body_ids].norm(dim=-1)
    return (force_history > threshold).float().mean(dim=1)


def _evaluate_pose(env, pose: dict[str, float]) -> dict[str, float]:
    robot = env.scene["robot"]
    env_ids = torch.arange(env.num_envs, device=env.device)
    _set_candidate_default_joint_pos(robot, pose)

    root_state = robot.data.default_root_state.clone()
    root_state[:, 0] = env.scene.env_origins[:, 0]
    root_state[:, 1] = env.scene.env_origins[:, 1]
    root_state[:, 2] = env.scene.env_origins[:, 2] + float(pose["base_z"])
    root_state[:, 7:13] = 0.0
    joint_pos = robot.data.default_joint_pos.clone()
    joint_vel = robot.data.default_joint_vel.clone()

    robot.write_root_state_to_sim(root_state, env_ids=env_ids)
    robot.write_joint_state_to_sim(joint_pos, joint_vel, env_ids=env_ids)
    robot.set_joint_position_target(joint_pos, env_ids=env_ids)
    env.episode_length_buf[env_ids] = 0
    env._pose_search_root_pos0 = root_state[:, :3].clone()

    terminated = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    time_outs = torch.zeros_like(terminated)
    for _ in range(args_cli.steps):
        actions = torch.zeros((env.num_envs, env.action_manager.total_action_dim), device=env.device)
        _, _, terminated, time_outs, _ = env.step(actions)
        if not simulation_app.is_running():
            break

    roots_xy = robot.data.root_pos_w[:, :2] - env._pose_search_root_pos0[:, :2]
    drift_xy = torch.norm(roots_xy, dim=1)
    vel_xy = torch.norm(robot.data.root_lin_vel_b[:, :2], dim=1)
    ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
    grav_xy = robot.data.projected_gravity_b[:, :2]
    height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    shoulder_pos_z = robot.data.body_pos_w[:, env._pose_search_shoulder_body_ids, 2] - env.scene.env_origins[:, 2].unsqueeze(1)
    toe_contact = _toe_contact_matrix(env, args_cli.contact_threshold)
    front_contact = toe_contact[:, :2].mean(dim=1)
    rear_contact = toe_contact[:, 2:].mean(dim=1)
    pitch_proxy = shoulder_pos_z[:, :2].mean(dim=1) - shoulder_pos_z[:, 2:].mean(dim=1)
    roll_proxy = shoulder_pos_z[:, [0, 2]].mean(dim=1) - shoulder_pos_z[:, [1, 3]].mean(dim=1)

    metrics = {
        **pose,
        "toe_contact_mean": toe_contact.mean().item(),
        "front_contact_mean": front_contact.mean().item(),
        "rear_contact_mean": rear_contact.mean().item(),
        "drift_xy_mean": drift_xy.mean().item(),
        "vel_xy_mean": vel_xy.mean().item(),
        "ang_xy_mean": ang_xy.mean().item(),
        "grav_x_mean": grav_xy[:, 0].mean().item(),
        "grav_y_mean": grav_xy[:, 1].mean().item(),
        "height_mean": height.mean().item(),
        "front_height_mean": shoulder_pos_z[:, :2].mean().item(),
        "rear_height_mean": shoulder_pos_z[:, 2:].mean().item(),
        "pitch_proxy_mean": pitch_proxy.mean().item(),
        "roll_proxy_mean": roll_proxy.mean().item(),
        "terminated_frac": terminated.float().mean().item(),
        "time_out_frac": time_outs.float().mean().item(),
        "mean_ep_len": env.episode_length_buf.float().mean().item(),
    }
    metrics["score"] = _score(metrics)
    return metrics


def _score(m: dict[str, float]) -> float:
    return (
        5.0 * m["toe_contact_mean"]
        + 3.0 * m["rear_contact_mean"]
        + 1.5 * m["height_mean"]
        + 0.5 * m["front_height_mean"]
        + 0.5 * m["rear_height_mean"]
        - 2.5 * m["terminated_frac"]
        - 1.2 * m["drift_xy_mean"]
        - 0.8 * m["vel_xy_mean"]
        - 0.6 * m["ang_xy_mean"]
        - 0.8 * abs(m["pitch_proxy_mean"])
        - 0.8 * abs(m["roll_proxy_mean"])
        - 0.4 * abs(m["grav_x_mean"])
        - 0.4 * abs(m["grav_y_mean"])
    )


def _format_metrics(prefix: str, m: dict[str, float]) -> str:
    return (
        f"{prefix}"
        f" | score={m['score']:.4f}"
        f" | base_z={m['base_z']:.3f}"
        f" | fl_leg={m['front_left_leg']:.3f} fr_leg={m['front_right_leg']:.3f}"
        f" | rl_leg={m['rear_left_leg']:.3f} rr_leg={m['rear_right_leg']:.3f}"
        f" | fl_foot={m['front_left_foot']:.3f} fr_foot={m['front_right_foot']:.3f}"
        f" | rl_foot={m['rear_left_foot']:.3f} rr_foot={m['rear_right_foot']:.3f}"
        f" | toe={m['toe_contact_mean']:.4f} rear={m['rear_contact_mean']:.4f}"
        f" | drift={m['drift_xy_mean']:.4f} vel={m['vel_xy_mean']:.4f} ang={m['ang_xy_mean']:.4f}"
        f" | h={m['height_mean']:.4f}"
        f" | fh={m['front_height_mean']:.4f} rh={m['rear_height_mean']:.4f}"
        f" | pitch={m['pitch_proxy_mean']:.4f} roll={m['roll_proxy_mean']:.4f}"
        f" | term={m['terminated_frac']:.4f}"
    )


def _write_checkpoint(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _clamp_candidate_value(key: str, value: float) -> float:
    if key == "base_z":
        return min(max(value, 0.10), 0.22)
    if "leg" in key:
        return min(max(value, -0.90), -0.45)
    if "foot" in key:
        return min(max(value, 1.20), 1.80)
    return value


def _adaptive_line_search(env, current: dict[str, float], best: dict[str, float], key: str, step_size: float, log):
    probes = []
    for direction in (-1.0, 1.0):
        candidate = deepcopy(current)
        candidate[key] = _clamp_candidate_value(key, candidate[key] + direction * step_size)
        metrics = _evaluate_pose(env, candidate)
        probes.append((direction, metrics))
        log(_format_metrics(f"[TRY] key={key} step={direction * step_size:+.4f}", metrics))

    direction, trial_best = max(probes, key=lambda item: item[1]["score"])
    if trial_best["score"] <= best["score"]:
        return current, best, False

    current = {k: trial_best[k] for k in POSE_KEYS}
    best = trial_best
    log(_format_metrics(f"[ACCEPT] key={key} step={direction * step_size:+.4f}", best))

    while simulation_app.is_running():
        candidate = deepcopy(current)
        candidate[key] = _clamp_candidate_value(key, candidate[key] + direction * step_size)
        if candidate[key] == current[key]:
            break
        metrics = _evaluate_pose(env, candidate)
        log(_format_metrics(f"[EXTEND] key={key} step={direction * step_size:+.4f}", metrics))
        if metrics["score"] <= best["score"]:
            break
        current = {k: metrics[k] for k in POSE_KEYS}
        best = metrics
        log(_format_metrics(f"[ACCEPT] key={key} extend", best))

    return current, best, True


def main():
    log, handle, log_path = _make_logger(args_cli.log_file)
    checkpoint_path = _resolve_checkpoint_path(log_path, args_cli.checkpoint_file)
    log(f"[INFO] log_file={log_path}")
    log(f"[INFO] checkpoint_file={checkpoint_path}")
    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    env = None
    best = None
    current = None
    step_sizes = None
    try:
        env = gym.make(args_cli.task, cfg=env_cfg)
        env.reset()
        env = env.unwrapped
        robot = env.scene["robot"]
        env._pose_search_toe_body_ids = torch.tensor(
            [robot.find_bodies(name)[0][0] for name in [
                "front_left_toe_link", "front_right_toe_link", "rear_left_toe_link", "rear_right_toe_link"
            ]],
            device=env.device,
            dtype=torch.long,
        )
        env._pose_search_shoulder_body_ids = torch.tensor(
            [robot.find_bodies(name)[0][0] for name in [
                "front_left_shoulder_link", "front_right_shoulder_link", "rear_left_shoulder_link", "rear_right_shoulder_link"
            ]],
            device=env.device,
            dtype=torch.long,
        )

        current = _pose_from_args()
        best = _evaluate_pose(env, current)
        log(_format_metrics("[INIT]", best))
        _write_checkpoint(
            checkpoint_path,
            {"status": "running", "phase": "init", "best": best, "current": current},
        )

        coordinate_order = [
            "rear_left_leg",
            "rear_right_leg",
            "rear_left_foot",
            "rear_right_foot",
            "front_left_leg",
            "front_right_leg",
            "front_left_foot",
            "front_right_foot",
            "base_z",
        ]
        step_sizes = {
            "base_z": args_cli.base_z_step,
            "front_left_leg": args_cli.joint_step,
            "front_right_leg": args_cli.joint_step,
            "rear_left_leg": args_cli.joint_step,
            "rear_right_leg": args_cli.joint_step,
            "front_left_foot": args_cli.joint_step,
            "front_right_foot": args_cli.joint_step,
            "rear_left_foot": args_cli.joint_step,
            "rear_right_foot": args_cli.joint_step,
        }
        min_steps = {
            "base_z": args_cli.base_z_min_step,
            "front_left_leg": args_cli.joint_min_step,
            "front_right_leg": args_cli.joint_min_step,
            "rear_left_leg": args_cli.joint_min_step,
            "rear_right_leg": args_cli.joint_min_step,
            "front_left_foot": args_cli.joint_min_step,
            "front_right_foot": args_cli.joint_min_step,
            "rear_left_foot": args_cli.joint_min_step,
            "rear_right_foot": args_cli.joint_min_step,
        }

        for pass_idx in range(1, args_cli.max_passes + 1):
            log(f"[PASS] index={pass_idx}")
            improved_in_pass = False
            active = False
            for key in coordinate_order:
                if step_sizes[key] < min_steps[key]:
                    continue
                active = True
                current, best, improved = _adaptive_line_search(env, current, best, key, step_sizes[key], log)
                _write_checkpoint(
                    checkpoint_path,
                    {
                        "status": "running",
                        "phase": "search",
                        "pass_idx": pass_idx,
                        "active_key": key,
                        "best": best,
                        "current": current,
                        "step_sizes": step_sizes,
                    },
                )
                if improved:
                    improved_in_pass = True
                else:
                    step_sizes[key] *= 0.5
                    log(f"[SHRINK] key={key} new_step={step_sizes[key]:.4f}")
            if not active:
                log("[PASS] all_steps_below_min")
                break
            if not improved_in_pass:
                log("[PASS] no_improvement")

        log(_format_metrics("[BEST]", best))
        _write_checkpoint(
            checkpoint_path,
            {"status": "completed", "phase": "done", "best": best, "current": current, "step_sizes": step_sizes},
        )
    except Exception:
        log("[ERROR] standing_pose_search crashed")
        for line in traceback.format_exc().splitlines():
            log(line)
        if best is not None:
            log(_format_metrics("[BEST_SO_FAR]", best))
            _write_checkpoint(
                checkpoint_path,
                {
                    "status": "error",
                    "phase": "exception",
                    "best": best,
                    "current": current,
                    "step_sizes": step_sizes,
                },
            )
        raise
    finally:
        if best is not None:
            log(_format_metrics("[FINAL_BEST_SO_FAR]", best))
        if env is not None:
            env.close()
        handle.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
