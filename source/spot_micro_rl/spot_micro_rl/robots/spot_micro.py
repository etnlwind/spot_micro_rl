# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""Configuration for Spot Micro robots."""

import os
import isaaclab.sim as sim_utils
from isaaclab.actuators import DCMotorCfg, ImplicitActuatorCfg, IdealPDActuatorCfg
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
            max_depenetration_velocity=0.2,  # 부드러운 착지 (1.0→0.2)
        ),
        articulation_props=sim_utils.ArticulationRootPropertiesCfg(
            enabled_self_collisions=False,
            solver_position_iteration_count=4,
            solver_velocity_iteration_count=4,  # V57: 0→4 (접촉 충격 해석 활성화)
        ),
    ),
    init_state=ArticulationCfg.InitialStateCfg(
        pos=(0.0, 0.0, 0.229),  # V59: FK=0.229 정확히 (낙하 0)
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # V59: 대칭 Z-bend (foot=-2*leg), toe under shoulder
            "front_left_shoulder": -0.05,
            "front_left_leg": -0.52,
            "front_left_foot": 1.04,
            "front_right_shoulder": 0.05,
            "front_right_leg": -0.52,
            "front_right_foot": 1.04,
            "rear_left_shoulder": -0.05,
            "rear_left_leg": -0.52,
            "rear_left_foot": 1.04,
            "rear_right_shoulder": 0.05,
            "rear_right_leg": -0.52,
            "rear_right_foot": 1.04,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.7,  # foot 관절 최대 접힘 제한 (2.59×0.7=1.81rad)
    actuators={
        "legs": DCMotorCfg(
            # V59: STS3215 실제 서보 스펙 기반
            # URDF mass 실물 기준 수정 (5.3kg→1.4kg) 후 3Nm으로 서기 검증됨
            # stand test: h=149mm, pitch=-3°, 500 step 안정
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            effort_limit=3.0,        # STS3215 (30kg·cm @ 12V = 3.0 Nm)
            saturation_effort=3.0,
            stiffness=5.0,           # 0.6rad error에서 3Nm 포화
            damping=0.5,             # Go2 표준
            velocity_limit=19.0,     # STS3215 (~19 rad/s)
        ),
    },
)
"""Configuration for Spot Micro robot."""
