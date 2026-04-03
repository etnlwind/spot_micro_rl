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
        pos=(0.0, 0.0, 0.185),  # Phase 2 equilibrium 근처 시작 (낙하 에너지 최소화)
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # FK-calibrated: toe directly below shoulder (foot=1.35)
            # foot=1.32 → toe 2.8mm behind shoulder → 뒤로 주저앉음 경향
            # foot=1.35 → toe 0.1mm behind shoulder → 거의 정확히 아래
            # height = 0.210m, init_z = 0.185 (loaded eq 근처)
            "front_left_shoulder": -0.04,
            "front_left_leg": -0.70,
            "front_left_foot": 1.35,
            "front_right_shoulder": 0.04,
            "front_right_leg": -0.70,
            "front_right_foot": 1.35,
            "rear_left_shoulder": -0.04,
            "rear_left_leg": -0.70,
            "rear_left_foot": 1.35,
            "rear_right_shoulder": 0.04,
            "rear_right_leg": -0.70,
            "rear_right_foot": 1.35,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.7,  # foot 관절 최대 접힘 제한 (2.59×0.7=1.81rad)
    actuators={
        "legs": ImplicitActuatorCfg(
            # V58.B1 locomotion bootstrap: ImplicitActuator로 안정적 rollout 확보
            # bad_orientation 즉사 대신 실제 엎드림(min_height/base_contact) 기준으로 학습
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            effort_limit=15.0,
            stiffness={".*shoulder": 12.0, ".*leg": 28.0, ".*foot": 8.0},
            damping={".*shoulder": 4.0, ".*leg": 5.0, ".*foot": 2.0},
        ),
    },
)
"""Configuration for Spot Micro robot."""
