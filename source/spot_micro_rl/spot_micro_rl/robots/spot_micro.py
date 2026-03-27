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
        force_usd_conversion=True,  # V48-C: URDF mass 변경 → USD 재변환 필요
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
        pos=(0.0, 0.0, 0.22),  # V48: leg=-0.97에 맞춘 높이 (V47 0.192보다 약간 높게)
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # V47-B: 발끝이 hip 수직선에 오도록 보정 (leg -0.71→-0.68)
            # 이전(leg=-0.71): toe가 hip보다 5.7mm 앞으로 말려있음 → 뒤로 기울어짐 유발
            # 보정(leg=-0.68): toe가 hip 수직선에 정확히 위치 → 자연스러운 neutral stand
            # foot=1.31 유지 (toe z=-192.5mm, 거의 동일)
            "front_left_shoulder": -0.04,
            "front_left_leg": -0.97,   # 실측 보정 2차: -0.89에서 toe +10mm → -0.97
            "front_left_foot": 1.31,
            "front_right_shoulder": -0.04,
            "front_right_leg": -0.97,
            "front_right_foot": 1.31,
            "rear_left_shoulder": -0.04,
            "rear_left_leg": -0.97,
            "rear_left_foot": 1.31,
            "rear_right_shoulder": -0.04,
            "rear_right_leg": -0.97,
            "rear_right_foot": 1.31,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.7,  # foot 관절 최대 접힘 제한 (2.59×0.7=1.81rad)
    actuators={
        "legs": DCMotorCfg(
            # 12 leg joints (shoulder, leg, foot × 4)
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            # V17.1: 과도한 토크/강성 완화 → 솟구침/곤두박질 방지
            saturation_effort=1.5,  # V48-D: MG996R stall=1.08Nm, +40% 마진
            effort_limit=1.5,       # V48-D: 실제 서보 토크 근사
            velocity_limit=10.0,     # V17.1: 8→10 (원래 값 복원, 느린 동작은 보상으로)
            stiffness={".*": 15.0},  # V17.1: 25→15 (10과 25의 중간)
            damping={".*": 1.5},     # V17.1: 2→1.5 (약간의 감쇠 유지)
        ),
    },
)
"""Configuration for Spot Micro robot."""
