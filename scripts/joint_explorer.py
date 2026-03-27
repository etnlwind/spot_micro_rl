"""Joint Explorer for SpotMicro — 관절별 동작 방향 확인.

공중 고정 상태에서 한 번에 한 관절씩 움직여서 방향을 시각적으로 확인.
각 관절을 standing pose 기준으로 +/- 방향으로 천천히 움직임.

Usage:
  C:\\IsaacLab\\isaaclab.bat -p scripts/joint_explorer.py
"""

from __future__ import annotations

import argparse
import math
import os
import torch

import isaacsim  # noqa: F401
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Joint explorer for SpotMicro")
parser.add_argument("--num_envs", type=int, default=1)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation, ArticulationCfg
from isaaclab.actuators import DCMotorCfg

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_URDF_PATH = os.path.join(_PROJECT_ROOT, "assets", "robots", "spot_micro", "spotmicroai_realistic_inertia.urdf")

STAND = {"shoulder": -0.04, "leg": -0.71, "foot": 1.31}

JOINT_NAMES = [
    "front_left_shoulder", "front_left_leg", "front_left_foot",
    "front_right_shoulder", "front_right_leg", "front_right_foot",
    "rear_left_shoulder", "rear_left_leg", "rear_left_foot",
    "rear_right_shoulder", "rear_right_leg", "rear_right_foot",
]

JOINT_STAND = [
    STAND["shoulder"], STAND["leg"], STAND["foot"],  # FL
    STAND["shoulder"], STAND["leg"], STAND["foot"],  # FR
    STAND["shoulder"], STAND["leg"], STAND["foot"],  # RL
    STAND["shoulder"], STAND["leg"], STAND["foot"],  # RR
]


def main():
    sim_cfg = sim_utils.SimulationCfg(dt=0.005, render_interval=2)
    sim = sim_utils.SimulationContext(sim_cfg)
    sim.set_camera_view(eye=[0.8, 0.8, 0.5], target=[0.0, 0.0, 0.2])

    ground_cfg = sim_utils.GroundPlaneCfg()
    ground_cfg.func("/World/defaultGroundPlane", ground_cfg)

    light_cfg = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 0.9))
    light_cfg.func("/World/Light", light_cfg)

    robot_cfg = ArticulationCfg(
        prim_path="/World/Robot",
        spawn=sim_utils.UrdfFileCfg(
            asset_path=_URDF_PATH,
            fix_base=True,
            merge_fixed_joints=True,
            activate_contact_sensors=True,
            joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
                gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                    stiffness=0.0, damping=0.0,
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
            pos=(0.0, 0.0, 0.35),
            joint_pos={name: JOINT_STAND[i] for i, name in enumerate(JOINT_NAMES)},
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

    sim.reset()
    robot.reset()

    dt = sim_cfg.dt
    amplitude = 0.3  # 테스트 진폭 (rad)
    cycle_time = 3.0  # 각 관절당 왕복 시간 (초)
    settle_time = 2.0  # 초기 안정화

    total_joints = 12
    steps_per_joint = int(cycle_time / dt)
    settle_steps = int(settle_time / dt)
    total_steps = settle_steps + steps_per_joint * total_joints

    print("=" * 60)
    print("SpotMicro Joint Explorer")
    print("=" * 60)
    print(f"  각 관절을 {cycle_time}초 동안 +/-{amplitude}rad 왕복")
    print(f"  Standing pose: shoulder={STAND['shoulder']}, leg={STAND['leg']}, foot={STAND['foot']}")
    print(f"  총 시간: {total_steps * dt:.0f}초")
    print("=" * 60)

    for step in range(total_steps):
        targets = torch.tensor([JOINT_STAND], device=sim.device)

        if step >= settle_steps:
            # 현재 테스트할 관절 인덱스
            joint_step = step - settle_steps
            joint_idx = joint_step // steps_per_joint
            if joint_idx >= total_joints:
                break

            # sin 파형으로 왕복
            progress = (joint_step % steps_per_joint) / steps_per_joint
            offset = amplitude * math.sin(2.0 * math.pi * progress)
            targets[0, joint_idx] = JOINT_STAND[joint_idx] + offset

            if joint_step % steps_per_joint == 0:
                print(f"\n>>> Testing: {JOINT_NAMES[joint_idx]} (joint {joint_idx})")
                print(f"    base={JOINT_STAND[joint_idx]:.2f}, range=[{JOINT_STAND[joint_idx]-amplitude:.2f}, {JOINT_STAND[joint_idx]+amplitude:.2f}]")

        robot.set_joint_position_target(targets)
        robot.write_data_to_sim()
        sim.step()
        robot.update(dt)

    print("\n[Done] Joint exploration completed.")
    simulation_app.close()


if __name__ == "__main__":
    main()
