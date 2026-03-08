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
        pos=(0.0, 0.0, 0.20),  # 서있는 자세 높이
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # leg=-0.5: upper leg 약간 기울임, foot=+1.2: 무릎 구부림
            # 높이 약 0.19m의 자연스러운 서있는 자세
            # V19: 어깨 -0.1 rad (~5.7° outward splay) — SpotMicro 곤충형 기구학 반영
            "front_left_shoulder": -0.1,
            "front_left_leg": -0.5,
            "front_left_foot": 1.2,
            "front_right_shoulder": -0.1,
            "front_right_leg": -0.5,
            "front_right_foot": 1.2,
            "rear_left_shoulder": -0.1,
            "rear_left_leg": -0.5,
            "rear_left_foot": 1.2,
            "rear_right_shoulder": -0.1,
            "rear_right_leg": -0.5,
            "rear_right_foot": 1.2,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.7,  # foot 관절 최대 접힘 제한 (2.59×0.7=1.81rad)
    actuators={
        "legs": DCMotorCfg(
            # 12 leg joints (shoulder, leg, foot × 4)
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            # V17.1: 과도한 토크/강성 완화 → 솟구침/곤두박질 방지
            saturation_effort=15.0,  # V17.1: 20→15 (원래 값 복원)
            effort_limit=15.0,       # V17 유지
            velocity_limit=10.0,     # V17.1: 8→10 (원래 값 복원, 느린 동작은 보상으로)
            stiffness={".*": 15.0},  # V17.1: 25→15 (10과 25의 중간)
            damping={".*": 1.5},     # V17.1: 2→1.5 (약간의 감쇠 유지)
        ),
    },
)
"""Configuration for Spot Micro robot."""
