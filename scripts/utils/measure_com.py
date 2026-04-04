"""Measure CoM position vs toe positions. One-shot, no simulation loop needed.

Spawns robot in init pose, reads:
  - Center of Mass (world frame)
  - All toe positions (world frame)
  - Support polygon center
  - CoM offset from support center

Usage:
  isaaclab.bat -p scripts/utils/measure_com.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless
"""

import argparse
import math
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, required=True)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
import spot_micro_rl.tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg


def disable_events(env_cfg):
    if not hasattr(env_cfg, "events") or env_cfg.events is None:
        return
    for name in ["physics_material", "add_base_mass", "base_com",
                  "base_external_force_torque", "reset_base", "push_robot",
                  "reset_robot_joints"]:
        if hasattr(env_cfg.events, name):
            setattr(env_cfg.events, name, None)


def main():
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=1, use_fabric=True)
    env_cfg.terminations = None
    env_cfg.rewards = None
    env_cfg.commands.base_velocity.rel_standing_envs = 1.0
    env_cfg.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
    disable_events(env_cfg)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env.reset()

    robot = env.unwrapped.scene["robot"]
    device = env.unwrapped.device
    origin = env.unwrapped.scene.env_origins[0]

    # Apply actual init pose (not zeros)
    joint_names = robot.joint_names
    nj = len(joint_names)
    init_jp = torch.zeros(1, nj, device=device)
    for j, name in enumerate(joint_names):
        if "shoulder" in name:
            init_jp[0, j] = -0.04 if "left" in name else 0.04
        elif "leg" in name:
            init_jp[0, j] = -0.52
        elif "foot" in name:
            init_jp[0, j] = 0.87

    root_state = robot.data.default_root_state.clone()
    root_state[:, :] = 0.0
    root_state[:, 3] = 1.0  # identity quat
    root_state[0, 0] = origin[0]
    root_state[0, 1] = origin[1]
    root_state[0, 2] = origin[2] + 0.229  # FK height for leg=-0.52, foot=0.87

    robot.write_root_state_to_sim(root_state)
    robot.write_joint_state_to_sim(init_jp, torch.zeros_like(init_jp))

    # Step once to initialize physics
    env.step(torch.zeros(env.action_space.shape, device=device))

    # Write results to file (stdout gets buried in IsaacSim warnings)
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "logs", "stance_search", "measure_com_result.txt")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_f = open(out_path, "w", encoding="utf-8")

    def log(msg=""):
        print(msg, flush=True)
        out_f.write(msg + "\n")
        out_f.flush()

    log("=== Robot Measurement ===")

    # Joint info
    joint_names = robot.joint_names
    joint_pos = robot.data.joint_pos[0]
    log(f"\nJoint positions (init pose):")
    for i, name in enumerate(joint_names):
        log(f"  {name}: {joint_pos[i].item():.4f} ({math.degrees(joint_pos[i].item()):+.1f} deg)")

    # Body positions
    body_names = robot.body_names
    log(f"\nBodies ({len(body_names)}): {body_names}")

    body_pos = robot.data.body_pos_w[0]  # (num_bodies, 3)
    log(f"\nBody positions (world frame, relative to env origin):")
    for i, name in enumerate(body_names):
        pos = body_pos[i] - origin
        log(f"  {name:>30}: x={pos[0].item()*1000:+7.1f} y={pos[1].item()*1000:+7.1f} z={pos[2].item()*1000:+7.1f} mm")

    # Root (body) position
    root_pos = robot.data.root_pos_w[0] - origin
    log(f"\nRoot (base_link) position: x={root_pos[0].item()*1000:+7.1f} y={root_pos[1].item()*1000:+7.1f} z={root_pos[2].item()*1000:+7.1f} mm")

    # Find toe bodies
    toe_names = [n for n in body_names if "toe" in n]
    toe_indices = [body_names.index(n) for n in toe_names]
    log(f"\nToe bodies: {toe_names}")

    toe_positions = []
    for name, idx in zip(toe_names, toe_indices):
        pos = body_pos[idx] - origin
        toe_positions.append(pos)
        log(f"  {name}: x={pos[0].item()*1000:+7.1f} y={pos[1].item()*1000:+7.1f} z={pos[2].item()*1000:+7.1f} mm")

    # Support polygon center (average of toe X positions)
    toe_x_avg = sum(p[0].item() for p in toe_positions) / len(toe_positions)
    toe_y_avg = sum(p[1].item() for p in toe_positions) / len(toe_positions)
    log(f"\nSupport polygon center: x={toe_x_avg*1000:+.1f} y={toe_y_avg*1000:+.1f} mm")

    # CoM - try multiple methods
    log(f"\n--- Center of Mass ---")

    # Method 1: root_com_pos_w if available
    if hasattr(robot.data, "root_com_pos_w"):
        com = robot.data.root_com_pos_w[0] - origin
        log(f"root_com_pos_w: x={com[0].item()*1000:+.1f} y={com[1].item()*1000:+.1f} z={com[2].item()*1000:+.1f} mm")

    # Method 2: body_com_pos_w (per-body CoM)
    if hasattr(robot.data, "body_com_pos_w"):
        body_com = robot.data.body_com_pos_w[0]  # (num_bodies, 3)
        log(f"\nPer-body CoM positions:")
        for i, name in enumerate(body_names):
            pos = body_com[i] - origin
            log(f"  {name:>30}: x={pos[0].item()*1000:+7.1f} y={pos[1].item()*1000:+7.1f} z={pos[2].item()*1000:+7.1f} mm")

    # Method 3: compute from body masses if available
    if hasattr(robot.data, "body_mass"):
        masses = robot.data.body_mass[0]  # (num_bodies,)
        total_mass = masses.sum().item()
        log(f"\nBody masses (total={total_mass:.4f} kg):")
        for i, name in enumerate(body_names):
            log(f"  {name:>30}: {masses[i].item():.6f} kg")

        # Weighted average CoM
        if hasattr(robot.data, "body_com_pos_w"):
            weighted_com = torch.zeros(3, device=device)
            for i in range(len(body_names)):
                weighted_com += masses[i] * (body_com[i] - origin)
            weighted_com /= total_mass
            log(f"\nWeighted CoM: x={weighted_com[0].item()*1000:+.1f} y={weighted_com[1].item()*1000:+.1f} z={weighted_com[2].item()*1000:+.1f} mm")

            # THE KEY RESULT
            com_x = weighted_com[0].item()
            offset_x = (com_x - toe_x_avg) * 1000  # mm
            log(f"\n{'='*50}")
            log(f"=== KEY RESULT ===")
            log(f"{'='*50}")
            log(f"CoM X:              {com_x*1000:+.1f} mm")
            log(f"Support center X:   {toe_x_avg*1000:+.1f} mm")
            log(f"Offset (CoM - toe): {offset_x:+.1f} mm")
            if offset_x > 1:
                log(f"-> CoM is {offset_x:.1f}mm AHEAD of support center")
                log(f"-> Shift body BACKWARD by {offset_x:.1f}mm to balance")
            elif offset_x < -1:
                log(f"-> CoM is {-offset_x:.1f}mm BEHIND support center")
                log(f"-> Shift body FORWARD by {-offset_x:.1f}mm to balance")
            else:
                log(f"-> CoM is balanced over support center")

    log(f"\nResults saved to: {out_path}")
    out_f.close()
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
