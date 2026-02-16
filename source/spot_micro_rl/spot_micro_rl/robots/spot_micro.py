# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""Configuration for Spot Micro robots."""

import os
import isaaclab.sim as sim_utils
from isaaclab.actuators import DCMotorCfg
from isaaclab.assets.articulation import ArticulationCfg

##
# Configuration
##

# Get project root directory (4 levels up from this file)
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, "..", "..", "..", ".."))
_URDF_PATH = os.path.join(_PROJECT_ROOT, "assets", "robots", "spot_micro", "spotmicroai_realistic_inertia.urdf")

SPOT_MICRO_CFG = ArticulationCfg(
    prim_path="{ENV_REGEX_NS}/Robot",
    spawn=sim_utils.UrdfFileCfg(
        asset_path=_URDF_PATH,
        fix_base=False,
        merge_fixed_joints=True,  # Merge toe fixed joints into foot links
        activate_contact_sensors=True,
        force_usd_conversion=False,  # USD conversion complete, reuse cache
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
            gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                stiffness=0.0,  # PhysX drive PD=0, DCMotor computes torque
                damping=0.0,    # PhysX drive PD=0, DCMotor computes torque
            ),
            target_type="position",  # Creates PhysX DriveAPI (required for actuators!)
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
        pos=(0.0, 0.0, 0.13),  # 크라우치: 발~어깨 0.127m + 약간 여유
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # 크라우치(웅크린) 자세: '>' 모양으로 다리 구부려 앉음
            # shoulder=0: 옆으로 벌리지 않음
            # leg=-1.0: upper leg 앞쪽으로 57도 기울임 (아래+앞)
            # foot=+2.0: 무릎 115도 구부림 (lower leg 뒤+아래로)
            # → 무릎이 앞쪽으로, 발이 뒤쪽으로 → 자연스러운 '>' 형태
            # 높이: upper=0.065m + lower=0.062m = 0.127m
            #
            # 서기 목표: leg→-0.5, foot→1.2 (높이 0.19m)
            # delta: leg +0.5 (upper leg 펴기), foot -0.8 (무릎 펴기)
            "front_left_shoulder": 0.0,
            "front_left_leg": -1.0,
            "front_left_foot": 2.0,
            "front_right_shoulder": 0.0,
            "front_right_leg": -1.0,
            "front_right_foot": 2.0,
            "rear_left_shoulder": 0.0,
            "rear_left_leg": -1.0,
            "rear_left_foot": 2.0,
            "rear_right_shoulder": 0.0,
            "rear_right_leg": -1.0,
            "rear_right_foot": 2.0,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.9,
    actuators={
        "legs": DCMotorCfg(
            # 12 leg joints (shoulder, leg, foot × 4)
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            # SpotMicro is ~5.6kg (1/10 of Anymal-C 50kg)
            # Scale effort proportionally: 80Nm * (5.6/50) ≈ 9Nm
            saturation_effort=15.0,   # Anymal 120 * (5.6/50) ≈ 13.4
            effort_limit=10.0,      # Anymal 80 * (5.6/50) ≈ 9
            velocity_limit=10.0,
            stiffness={".*": 10.0},   # Moderate: enough to stand, not so much that noise flips robot
            damping={".*": 1.0},     # Moderate damping for stability
        ),
    },
)
"""Configuration for Spot Micro robot."""
