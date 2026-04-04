"""Find CoM balance point: slide body forward/backward over fixed toes.

16 envs x 16 toe_shift values (-30mm ~ +30mm).
leg=-0.52, shoulder=0.04 (current init).
Body stays horizontal. Longest survivor = CoM balanced.

Usage:
  isaaclab.bat -p scripts/utils/find_com_balance.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless
"""

import argparse
import math
import os
import sys
from datetime import datetime

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, required=True)
parser.add_argument("--steps", type=int, default=300)
parser.add_argument("--leg", type=float, default=-0.52)
parser.add_argument("--shoulder", type=float, default=0.04)
parser.add_argument("--shift_lo", type=float, default=-30.0, help="toe shift min (mm)")
parser.add_argument("--shift_hi", type=float, default=30.0, help="toe shift max (mm)")
parser.add_argument("--num_envs", type=int, default=16)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
import spot_micro_rl.tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg


def compute_foot_for_shift(leg: float, shift_mm: float) -> float:
    """Compute foot angle that places toe at shift_mm from shoulder-vertical."""
    target_x = shift_mm / 1000.0
    val = -(target_x + 0.01 * math.cos(leg) + 0.12 * math.sin(leg)) / 0.115
    val = max(-1.0, min(1.0, val))
    total = math.asin(val)
    foot = total - leg
    return max(-0.07, min(1.81, foot))


def compute_fk(leg: float, foot: float):
    total = leg + foot
    toe_x = -0.01 * math.cos(leg) - 0.12 * math.sin(leg) - 0.115 * math.sin(total)
    toe_z = 0.01 * math.sin(leg) - 0.12 * math.cos(leg) - 0.115 * math.cos(total)
    return toe_x * 1000, -toe_z + 0.02


def quat_to_pitch(quat):
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    return torch.asin(torch.clamp(2 * (w * y - z * x), -1, 1))


def disable_events(env_cfg):
    if not hasattr(env_cfg, "events") or env_cfg.events is None:
        return
    for name in ["physics_material", "add_base_mass", "base_com",
                  "base_external_force_torque", "reset_base", "push_robot",
                  "reset_robot_joints"]:
        if hasattr(env_cfg.events, name):
            setattr(env_cfg.events, name, None)


def main():
    n = args_cli.num_envs
    steps = args_cli.steps
    leg = args_cli.leg
    sh = args_cli.shoulder

    # Log setup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "logs", "stance_search")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"com_balance_{timestamp}.log")
    log_f = open(log_path, "w", encoding="utf-8", buffering=1)

    def log(msg=""):
        print(msg, flush=True)
        try:
            log_f.write(msg + "\n")
        except Exception:
            pass

    try:
        _run(n, steps, leg, sh, log)
    except Exception as e:
        log(f"\n!!! ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        log_f.close()
        print(f"\nLog: {log_path}")


def _run(n, steps, leg, sh, log):
    # Generate toe_shift candidates
    shifts = [args_cli.shift_lo + i * (args_cli.shift_hi - args_cli.shift_lo) / (n - 1) for i in range(n)]

    log(f"=== CoM Balance Search ===")
    log(f"leg={leg:.3f} shoulder={sh:.3f} steps={steps}")
    log(f"toe_shift: {shifts[0]:.1f} ~ {shifts[-1]:.1f} mm ({n} candidates)")
    log()

    # Compute foot angles
    foots = [compute_foot_for_shift(leg, s) for s in shifts]

    log(f"{'idx':>4} {'shift':>7} {'foot':>7} {'toe_x':>7} {'fk_h':>7}")
    log("-" * 40)
    for i in range(n):
        tx, fh = compute_fk(leg, foots[i])
        log(f"{i:4d} {shifts[i]:+7.1f} {foots[i]:7.3f} {tx:+7.1f} {fh*1000:7.1f}")

    # Create env
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=n, use_fabric=True)
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
    joint_names = robot.joint_names
    device = env.unwrapped.device
    nj = len(joint_names)

    # Set poses
    joint_pos = torch.zeros(n, nj, device=device)
    for j, name in enumerate(joint_names):
        for ei in range(n):
            if "shoulder" in name:
                joint_pos[ei, j] = -sh if "left" in name else sh
            elif "leg" in name:
                joint_pos[ei, j] = leg
            elif "foot" in name:
                joint_pos[ei, j] = foots[ei]

    root_state = robot.data.default_root_state.clone()
    root_state[:, :] = 0.0
    root_state[:, 3] = 1.0
    for ei in range(n):
        _, fh = compute_fk(leg, foots[ei])
        root_state[ei, 0] = env.unwrapped.scene.env_origins[ei, 0]
        root_state[ei, 1] = env.unwrapped.scene.env_origins[ei, 1]
        root_state[ei, 2] = env.unwrapped.scene.env_origins[ei, 2] + fh - 0.004

    robot.write_root_state_to_sim(root_state)
    robot.write_joint_state_to_sim(joint_pos, torch.zeros_like(joint_pos))

    # Simulate
    log(f"\nRunning {steps} steps...")
    fall_rad = math.radians(30.0)
    ttf = torch.full((n,), float(steps), device=device)

    try:
        with torch.inference_mode():
            for step in range(1, steps + 1):
                env.step(torch.zeros(env.action_space.shape, device=device))
                heights = robot.data.root_pos_w[:, 2] - env.unwrapped.scene.env_origins[:, 2]
                pitch = quat_to_pitch(robot.data.root_quat_w)

                newly = (pitch.abs() > fall_rad) & (ttf == float(steps))
                ttf[newly] = float(step)

                if step <= 100 or step % 50 == 0:
                    alive = (ttf == float(steps)).sum().item()
                    # Log all heights and pitches
                    h_str = " ".join(f"{heights[i].item()*1000:6.1f}" for i in range(n))
                    p_str = " ".join(f"{math.degrees(pitch[i].item()):+5.1f}" for i in range(n))
                    log(f"  s{step:4d} alive={alive:2d} h=[{h_str}]")
                    log(f"         pitch=[{p_str}]")
    finally:
        env.close()

    # Results
    log(f"\n{'='*50}")
    log(f"=== RESULTS (ranked by time-to-fall) ===")
    log(f"{'='*50}")
    order = sorted(range(n), key=lambda i: ttf[i].item(), reverse=True)
    log(f"{'rank':>5} {'idx':>4} {'shift':>7} {'foot':>7} {'ttf':>6}")
    log("-" * 35)
    for rank, i in enumerate(order):
        marker = " <-- BEST" if rank == 0 else ""
        log(f"{rank+1:5d} {i:4d} {shifts[i]:+7.1f} {foots[i]:7.3f} {ttf[i].item():6.0f}{marker}")

    best = order[0]
    log(f"\n=== BEST ===")
    log(f"toe_shift = {shifts[best]:+.1f}mm")
    log(f"leg = {leg:.3f}, foot = {foots[best]:.3f}, shoulder = {sh:.3f}")
    tx, fh = compute_fk(leg, foots[best])
    log(f"FK height = {fh*1000:.1f}mm, toe_x = {tx:+.1f}mm")
    if shifts[best] < -1:
        log(f"-> Robot tips BACKWARD. Optimal: shift body {-shifts[best]:.0f}mm FORWARD (toes {shifts[best]:+.0f}mm behind shoulder)")
    elif shifts[best] > 1:
        log(f"-> Robot tips FORWARD. Optimal: shift body {shifts[best]:.0f}mm BACKWARD (toes {shifts[best]:+.0f}mm ahead of shoulder)")
    else:
        log(f"-> CoM is near body center. Current pose is well balanced.")


if __name__ == "__main__":
    main()
    simulation_app.close()
