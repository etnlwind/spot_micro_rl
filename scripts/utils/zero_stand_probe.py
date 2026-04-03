# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Zero-action stand probe for SpotMicro stand-first diagnostics.

Purpose:
    Separate "default pose / contact physics are unstable" from
    "policy actions destroy an otherwise stable stand".

Usage examples:
    C:\\IsaacLab\\isaaclab.bat -p scripts/utils/zero_stand_probe.py --task Isaac-Velocity-Flat-SpotMicro-v0 --num_envs 64 --steps 300
    C:\\IsaacLab\\isaaclab.bat -p scripts/utils/zero_stand_probe.py --task Isaac-Velocity-Flat-SpotMicro-v0 --num_envs 1 --steps 500 --video
"""

import argparse
from datetime import datetime
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Zero-action stand probe for Isaac Lab environments.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=64, help="Number of environments to simulate.")
parser.add_argument("--steps", type=int, default=300, help="Number of environment steps to run.")
parser.add_argument("--report_every", type=int, default=10, help="Print metrics every N environment steps.")
parser.add_argument(
    "--log_file",
    type=str,
    default=None,
    help="Optional path to save probe logs. Defaults to logs/diagnostics/zero_stand_probe_<timestamp>.log",
)
parser.add_argument(
    "--capture_path",
    type=str,
    default="logs/diagnostics/zero_probe_side",
    help="Output prefix or directory used to save numbered side-frame PNGs.",
)
parser.add_argument(
    "--camera_view",
    type=str,
    default="side",
    choices=["overview", "side", "front", "rear", "top"],
    help="Camera view preset used for the first-frame capture.",
)
parser.add_argument(
    "--camera_zoom",
    type=float,
    default=1.0,
    help="Camera distance scale for the first-frame capture.",
)
parser.add_argument(
    "--capture_frames",
    type=int,
    default=20,
    help="Number of initial rendered frames to save as numbered PNGs.",
)
parser.add_argument(
    "--contact_threshold",
    type=float,
    default=1.0,
    help="Contact threshold in Newtons for toe contact detection.",
)
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch
import numpy as np
from PIL import Image

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg

import spot_micro_rl.tasks  # noqa: F401


def _make_logger(log_file_arg: str | None):
    if log_file_arg is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path("logs") / "diagnostics" / f"zero_stand_probe_{timestamp}.log"
    else:
        log_path = Path(log_file_arg)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")

    def log(line: str):
        print(line)
        handle.write(line + "\n")
        handle.flush()

    return log, log_path, handle


def _camera_offsets(view_name: str, zoom: float = 1.0):
    offsets = {
        "overview": ((3.0, -3.0, 2.2), (0.0, 0.0, 0.35)),
        "side": ((2.6, -0.45, 0.62), (0.0, 0.0, 0.26)),
        "front": ((0.0, 2.0, 0.50), (0.0, 0.0, 0.28)),
        "rear": ((0.0, -2.0, 0.50), (0.0, 0.0, 0.28)),
        "top": ((0.0, -0.001, 2.8), (0.0, 0.0, 0.0)),
    }
    eye_off, look_off = offsets.get(view_name, offsets["side"])
    eye_off = tuple(v * zoom for v in eye_off)
    return eye_off, look_off


def _capture_frame_sequence(env, capture_path: str, camera_view: str, camera_zoom: float, frame_idx: int):
    robot = env.unwrapped.scene["robot"]
    root_pos = robot.data.root_pos_w[0]
    eye_off, look_off = _camera_offsets(camera_view, camera_zoom)
    eye = (
        float(root_pos[0]) + eye_off[0],
        float(root_pos[1]) + eye_off[1],
        float(root_pos[2]) + eye_off[2],
    )
    lookat = (
        float(root_pos[0]) + look_off[0],
        float(root_pos[1]) + look_off[1],
        float(root_pos[2]) + look_off[2],
    )
    env.unwrapped.sim.set_camera_view(eye, lookat)
    rgb = env.render()
    if isinstance(rgb, tuple):
        rgb = rgb[0]
    array = np.asarray(rgb)
    if array.ndim == 4:
        array = array[0]
    capture_root = Path(capture_path)
    if capture_root.suffix.lower() == ".png":
        stem = capture_root.stem
        parent = capture_root.parent
    else:
        stem = capture_root.name
        parent = capture_root.parent
    if str(parent) == ".":
        parent = Path(".")
    parent.mkdir(parents=True, exist_ok=True)
    out_path = parent / f"{stem}_{frame_idx:04d}.png"
    Image.fromarray(array.astype(np.uint8)).save(out_path, format="PNG")
    return out_path, eye, lookat


def _toe_contact_ratio(contact_sensor: object, threshold: float) -> torch.Tensor:
    """Return per-env mean toe contact ratio over the available history window."""
    force_history = contact_sensor.data.net_forces_w_history.norm(dim=-1)
    contacts = (force_history > threshold).float()
    return contacts.mean(dim=1).mean(dim=1)


def _joint_stat(robot, joint_ids: dict[str, int], name: str) -> torch.Tensor | None:
    joint_id = joint_ids.get(name)
    if joint_id is None:
        return None
    return robot.data.joint_pos[:, joint_id]


def _summarize(env, terminated: torch.Tensor, time_outs: torch.Tensor, step_idx: int, threshold: float) -> str:
    robot = env.scene["robot"]
    roots_xy = robot.data.root_pos_w[:, :2] - env._zero_probe_root_pos0[:, :2]
    drift_xy = torch.norm(roots_xy, dim=1)
    vel_xy = torch.norm(robot.data.root_lin_vel_b[:, :2], dim=1)
    ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
    grav_xy = torch.norm(robot.data.projected_gravity_b[:, :2], dim=1)
    height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]

    contact_sensor = env.scene.sensors.get("contact_forces", None)
    toe_contact = _toe_contact_ratio(contact_sensor, threshold) if contact_sensor is not None else None
    joint_ids = getattr(env, "_zero_probe_joint_ids", {})

    parts = [
        f"step={step_idx}",
        f"mean_ep_len={env.episode_length_buf.float().mean().item():.2f}",
        f"drift_xy_mean={drift_xy.mean().item():.4f}",
        f"drift_xy_max={drift_xy.max().item():.4f}",
        f"vel_xy_mean={vel_xy.mean().item():.4f}",
        f"vel_xy_max={vel_xy.max().item():.4f}",
        f"ang_xy_mean={ang_xy.mean().item():.4f}",
        f"ang_xy_max={ang_xy.max().item():.4f}",
        f"grav_xy_mean={grav_xy.mean().item():.4f}",
        f"grav_xy_max={grav_xy.max().item():.4f}",
        f"height_mean={height.mean().item():.4f}",
        f"height_min={height.min().item():.4f}",
        f"terminated_frac={terminated.float().mean().item():.4f}",
        f"time_out_frac={time_outs.float().mean().item():.4f}",
    ]
    if toe_contact is not None:
        parts.append(f"toe_contact_mean={toe_contact.mean().item():.4f}")
        parts.append(f"toe_contact_min={toe_contact.min().item():.4f}")
    joint_names = [
        "front_left_shoulder", "front_left_leg", "front_left_foot",
        "front_right_shoulder", "front_right_leg", "front_right_foot",
        "rear_left_shoulder", "rear_left_leg", "rear_left_foot",
        "rear_right_shoulder", "rear_right_leg", "rear_right_foot",
    ]
    for name in joint_names:
        values = _joint_stat(robot, joint_ids, name)
        if values is not None:
            parts.append(f"{name}_pos={values.mean().item():.4f}")

    # Per-joint applied torque
    try:
        torque_data = getattr(robot.data, "applied_torque", None)
        if torque_data is not None:
            for name in joint_names:
                jid = joint_ids.get(name)
                if jid is not None:
                    torque = torque_data[:, jid]
                    parts.append(f"{name}_torque={torque.mean().item():.4f}")
    except Exception:
        pass

    # Per-joint PD internals: computed_torque, joint_pos_target, joint_vel, joint_vel_target
    try:
        computed_data = getattr(robot.data, "computed_torque", None)
        pos_target_data = getattr(robot.data, "joint_pos_target", None)
        vel_data = getattr(robot.data, "joint_vel", None)
        vel_target_data = getattr(robot.data, "joint_vel_target", None)
        effort_target_data = getattr(robot.data, "joint_effort_target", None)
        # Only print for front_left_foot (index 8) to keep output manageable
        fl_foot_id = joint_ids.get("front_left_foot")
        if fl_foot_id is not None:
            if computed_data is not None:
                parts.append(f"FL_foot_computed_torque={computed_data[:, fl_foot_id].mean().item():.4f}")
            if pos_target_data is not None:
                parts.append(f"FL_foot_pos_target={pos_target_data[:, fl_foot_id].mean().item():.4f}")
            if vel_data is not None:
                parts.append(f"FL_foot_vel={vel_data[:, fl_foot_id].mean().item():.4f}")
            if vel_target_data is not None:
                parts.append(f"FL_foot_vel_target={vel_target_data[:, fl_foot_id].mean().item():.4f}")
            if effort_target_data is not None:
                parts.append(f"FL_foot_effort_target={effort_target_data[:, fl_foot_id].mean().item():.4f}")
    except Exception:
        pass

    # Per-toe contact force (normal z)
    try:
        if contact_sensor is not None:
            forces = contact_sensor.data.net_forces_w[:, :, 2]
            toe_names = ["FL_toe", "FR_toe", "RL_toe", "RR_toe"]
            for i, tname in enumerate(toe_names):
                if i < forces.shape[1]:
                    parts.append(f"{tname}_fz={forces[:, i].mean().item():.4f}")
    except Exception:
        pass

    # Per-toe position (z height from ground)
    try:
        foot_body_ids = getattr(env, "_zero_probe_foot_body_ids", None)
        if foot_body_ids is None:
            _, foot_body_ids_list = robot.find_bodies(".*toe_link")
            env._zero_probe_foot_body_ids = foot_body_ids_list
            foot_body_ids = foot_body_ids_list
        if foot_body_ids is not None:
            foot_pos_z = robot.data.body_pos_w[:, foot_body_ids, 2]
            env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
            foot_height = foot_pos_z - env_origins_z
            toe_names = ["FL_toe", "FR_toe", "RL_toe", "RR_toe"]
            for i, tname in enumerate(toe_names):
                if i < foot_height.shape[1]:
                    parts.append(f"{tname}_z={foot_height[:, i].mean().item():.4f}")
    except Exception:
        pass

    return " | ".join(parts)


def main():
    log, log_path, log_handle = _make_logger(args_cli.log_file)
    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env.reset()
    env.unwrapped._zero_probe_root_pos0 = env.unwrapped.scene["robot"].data.root_pos_w.clone()
    robot = env.unwrapped.scene["robot"]
    env.unwrapped._zero_probe_joint_ids = {name: idx for idx, name in enumerate(robot.joint_names)}

    log(f"[INFO] log_file={log_path}")
    log(f"[INFO] task={args_cli.task}")
    log(f"[INFO] num_envs={env.unwrapped.num_envs}")
    log(f"[INFO] action_space={env.action_space.shape}")
    log(f"[INFO] step_dt={env.unwrapped.step_dt:.4f}")

    # Debug: print default_joint_pos and action offset
    try:
        default_pos = robot.data.default_joint_pos[0]
        log(f"[DEBUG] joint_names={robot.joint_names}")
        log(f"[DEBUG] default_joint_pos={[f'{v:.4f}' for v in default_pos.tolist()]}")
        # Check action manager offset
        action_mgr = env.unwrapped.action_manager
        for term_name, term in action_mgr._terms.items():
            if hasattr(term, '_offset'):
                log(f"[DEBUG] action_term={term_name} offset={[f'{v:.4f}' for v in term._offset[0].tolist()]}")
            if hasattr(term, '_scale'):
                log(f"[DEBUG] action_term={term_name} scale={term._scale}")
    except Exception as e:
        log(f"[DEBUG] error getting action info: {e}")

    eye = lookat = None
    captured_paths: list[Path] = []

    with torch.inference_mode():
        for step_idx in range(1, args_cli.steps + 1):
            actions = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
            _, _, terminated, time_outs, _ = env.step(actions)
            if step_idx <= args_cli.capture_frames:
                frame_path, eye, lookat = _capture_frame_sequence(
                    env,
                    args_cli.capture_path,
                    args_cli.camera_view,
                    args_cli.camera_zoom,
                    step_idx,
                )
                captured_paths.append(frame_path)
            if step_idx == 1 or step_idx % args_cli.report_every == 0 or step_idx == args_cli.steps:
                log(_summarize(env.unwrapped, terminated, time_outs, step_idx, args_cli.contact_threshold))
            if not simulation_app.is_running():
                break

    if captured_paths:
        log(f"[INFO] capture_count={len(captured_paths)}")
        log(f"[INFO] first_capture={captured_paths[0]}")
        log(f"[INFO] last_capture={captured_paths[-1]}")
        if eye is not None and lookat is not None:
            log(f"[INFO] camera_view={args_cli.camera_view} eye={eye} lookat={lookat}")

    env.close()
    log_handle.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
