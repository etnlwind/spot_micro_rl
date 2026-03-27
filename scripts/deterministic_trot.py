"""Deterministic Trot Controller for SpotMicro in Isaac Lab.

Classical sinusoidal trot gait -- no RL, pure joint trajectory replay.
Uses Isaac Lab's Articulation API for reliable joint control.

Purpose:
  1. Validate URDF can physically produce natural trot
  2. Provide visual reference for RL training target
  3. Check joint limits and link proportions

Usage (Windows cmd):
  C:\\IsaacLab\\isaaclab.bat -p scripts/deterministic_trot.py
  C:\\IsaacLab\\isaaclab.bat -p scripts/deterministic_trot.py --headless --video --video_length=500

Params can be tuned via CLI:
  --frequency 1.5 --swing_amp 0.25 --lift_amp 0.15 --foot_amp 0.20
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import torch

# ── CLI args ──
parser = argparse.ArgumentParser(description="Deterministic trot for SpotMicro")
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--frequency", type=float, default=1.0, help="Trot frequency Hz")
parser.add_argument("--swing_amp", type=float, default=0.15, help="Leg swing amplitude rad")
parser.add_argument("--lift_amp", type=float, default=0.10, help="Leg lift amplitude rad")
parser.add_argument("--foot_amp", type=float, default=0.12, help="Foot swing amplitude rad")
parser.add_argument("--duration", type=float, default=10.0, help="Simulation duration seconds")
parser.add_argument("--video", action="store_true", help="Record video")
parser.add_argument("--video_length", type=int, default=500, help="Video length in steps")

# Isaac Lab app launcher
import isaacsim  # noqa: F401
from isaaclab.app import AppLauncher
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

# Isaac Lab imports (must be after AppLauncher)
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import ImplicitActuatorCfg, DCMotorCfg

# ── Robot config ──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_URDF_PATH = os.path.join(_PROJECT_ROOT, "assets", "robots", "spot_micro", "spotmicroai_realistic_inertia.urdf")

# Standing pose
STAND = {
    "shoulder": -0.04,
    "leg": -0.71,
    "foot": 1.31,
}

# Joint name order (must match URDF)
JOINT_NAMES = [
    "front_left_shoulder", "front_left_leg", "front_left_foot",
    "front_right_shoulder", "front_right_leg", "front_right_foot",
    "rear_left_shoulder", "rear_left_leg", "rear_left_foot",
    "rear_right_shoulder", "rear_right_leg", "rear_right_foot",
]

# Trot phase offsets: FL+RR in phase, FR+RL anti-phase
LEG_PHASE_OFFSETS = [0.0, math.pi, math.pi, 0.0]  # FL, FR, RL, RR


def compute_trot_targets(
    t: float,
    num_envs: int,
    device: str,
    frequency: float = 1.5,
    swing_amp: float = 0.25,
    lift_amp: float = 0.15,
    foot_amp: float = 0.20,
) -> torch.Tensor:
    """Compute 12-DOF joint position targets for trot gait.

    Trot: FL+RR swing together, FR+RL swing together.
    Stance: foot on ground, push backward.
    Swing: lift foot, swing forward.
    """
    targets = torch.zeros(num_envs, 12, device=device)
    base_phase = 2.0 * math.pi * frequency * t

    for leg_idx in range(4):
        phase = (base_phase + LEG_PHASE_OFFSETS[leg_idx]) % (2.0 * math.pi)
        joint_base = leg_idx * 3  # shoulder, leg, foot

        # Shoulder: stay near neutral
        targets[:, joint_base + 0] = STAND["shoulder"]

        swing_start = math.pi  # 50% duty factor

        if phase < swing_start:
            # ── Stance: foot on ground, push backward ──
            progress = phase / swing_start  # 0 → 1
            # Leg rotates backward (negative = backward for this URDF)
            targets[:, joint_base + 1] = STAND["leg"] - swing_amp * 0.5 * math.sin(math.pi * progress)
            # Foot stays relatively flat
            targets[:, joint_base + 2] = STAND["foot"] + foot_amp * 0.2 * math.sin(math.pi * progress)
        else:
            # ── Swing: lift and swing forward ──
            progress = (phase - swing_start) / (2.0 * math.pi - swing_start)  # 0 → 1
            # Leg lifts and swings forward
            targets[:, joint_base + 1] = STAND["leg"] + lift_amp * math.sin(math.pi * progress)
            # Foot curls up for clearance, then extends
            targets[:, joint_base + 2] = STAND["foot"] - foot_amp * math.sin(math.pi * progress)

    return targets


def main():
    """Run deterministic trot."""
    # ── Scene setup ──
    sim_cfg = sim_utils.SimulationCfg(dt=0.005, render_interval=2)
    sim = sim_utils.SimulationContext(sim_cfg)
    sim.set_camera_view(eye=[1.0, 1.0, 0.5], target=[0.0, 0.0, 0.15])

    # Ground
    ground_cfg = sim_utils.GroundPlaneCfg()
    ground_cfg.func("/World/defaultGroundPlane", ground_cfg)

    # Light
    light_cfg = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 0.9))
    light_cfg.func("/World/Light", light_cfg)

    # Robot — using implicit actuator (position control)
    robot_cfg = ArticulationCfg(
        prim_path="/World/Robot",
        spawn=sim_utils.UrdfFileCfg(
            asset_path=_URDF_PATH,
            fix_base=True,  # DEBUG: 공중 고정으로 다리 동작만 확인
            merge_fixed_joints=True,
            activate_contact_sensors=True,
            joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
                gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=0.0,
                    damping=0.0,
                ),
                target_type="position",
            ),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=False,
                max_depenetration_velocity=1.0,
            ),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=False,
                solver_position_iteration_count=4,
                solver_velocity_iteration_count=0,
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.35),  # 공중 고정 (fix_base=True), 다리 동작 확인용
            joint_pos={
                "front_left_shoulder": STAND["shoulder"],
                "front_left_leg": STAND["leg"],
                "front_left_foot": STAND["foot"],
                "front_right_shoulder": STAND["shoulder"],
                "front_right_leg": STAND["leg"],
                "front_right_foot": STAND["foot"],
                "rear_left_shoulder": STAND["shoulder"],
                "rear_left_leg": STAND["leg"],
                "rear_left_foot": STAND["foot"],
                "rear_right_shoulder": STAND["shoulder"],
                "rear_right_leg": STAND["leg"],
                "rear_right_foot": STAND["foot"],
            },
            joint_vel={".*": 0.0},
        ),
        actuators={
            "legs": DCMotorCfg(
                joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
                saturation_effort=15.0,
                effort_limit=15.0,
                velocity_limit=10.0,
                stiffness={".*": 15.0},
                damping={".*": 1.5},
            ),
        },
    )
    robot = Articulation(robot_cfg)

    # ── Simulation loop ──
    sim.reset()
    robot.reset()

    dt = sim_cfg.dt
    max_steps = int(args.duration / dt) if not args.video else args.video_length

    print("=" * 60)
    print("SpotMicro Deterministic Trot Controller")
    print("=" * 60)
    print(f"  Frequency:  {args.frequency} Hz")
    print(f"  Swing amp:  {args.swing_amp} rad ({args.swing_amp * 180 / math.pi:.1f} deg)")
    print(f"  Lift amp:   {args.lift_amp} rad ({args.lift_amp * 180 / math.pi:.1f} deg)")
    print(f"  Foot amp:   {args.foot_amp} rad ({args.foot_amp * 180 / math.pi:.1f} deg)")
    print(f"  Duration:   {max_steps * dt:.1f}s ({max_steps} steps)")
    print(f"  Standing:   shoulder={STAND['shoulder']}, leg={STAND['leg']}, foot={STAND['foot']}")
    print("=" * 60)

    for step in range(max_steps):
        t = step * dt

        # Settle for first 1.5s (stand still, let robot stabilize)
        if t < 1.5:
            targets = torch.zeros(1, 12, device=sim.device)
            for i in range(4):
                targets[:, i * 3 + 0] = STAND["shoulder"]
                targets[:, i * 3 + 1] = STAND["leg"]
                targets[:, i * 3 + 2] = STAND["foot"]
        else:
            targets = compute_trot_targets(
                t - 1.5, 1, sim.device,
                frequency=args.frequency,
                swing_amp=args.swing_amp,
                lift_amp=args.lift_amp,
                foot_amp=args.foot_amp,
            )

        # Apply targets
        robot.set_joint_position_target(targets)
        robot.write_data_to_sim()
        sim.step()
        robot.update(dt)

        if step % 200 == 0:
            pos = robot.data.root_pos_w[0]
            vel = robot.data.root_lin_vel_w[0]
            height = pos[2].item()
            fwd_vel = vel[0].item()
            print(f"  t={t:5.2f}s | height={height:.3f}m | fwd_vel={fwd_vel:.3f}m/s | pos=({pos[0].item():.2f}, {pos[1].item():.2f})")

    print("\n[Done] Deterministic trot completed.")
    simulation_app.close()


if __name__ == "__main__":
    main()
