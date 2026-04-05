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
        merge_fixed_joints=False,  # toe_link를 독립 rigid body로 유지해 toe contact reporting을 보장
        activate_contact_sensors=True,
        force_usd_conversion=True,  # V48-C: URDF mass 변경 → USD 재변환 필요
        joint_drive=sim_utils.UrdfConverterCfg.JointDriveCfg(
            gains=sim_utils.UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
                stiffness=0.0,  # URDF drive PD는 비활성화하고 actuator 설정값을 사용
                damping=0.0,    # ImplicitActuator가 런타임에 stiffness/damping을 설정
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
        pos=(0.0, 0.0, 0.222),  # V59: FK=228mm - 6mm (4발 접지 보장, shoulder 벌림 보정)
        # rot default = (1,0,0,0) — no rotation needed, URDF now has +X forward
        joint_pos={
            # V59: spot_mini_mini 기본 자세 (INIT_LEG=-0.658, INIT_FOOT=pi/3)
            # mike4192 실물 standing height = 155mm (loaded equilibrium)
            "front_left_shoulder": -0.15,
            "front_left_leg": -0.66,
            "front_left_foot": 1.05,
            "front_right_shoulder": 0.15,
            "front_right_leg": -0.66,
            "front_right_foot": 1.05,
            "rear_left_shoulder": -0.15,
            "rear_left_leg": -0.66,
            "rear_left_foot": 1.05,
            "rear_right_shoulder": 0.15,
            "rear_right_leg": -0.66,
            "rear_right_foot": 1.05,
        },
        joint_vel={".*": 0.0},
    ),
    soft_joint_pos_limit_factor=0.7,  # foot 관절 최대 접힘 제한 (2.59×0.7=1.81rad)
    actuators={
        "legs": ImplicitActuatorCfg(
            # V59: stand-first bootstrap용 ImplicitActuator
            # merge_fixed_joints=False에서 toe contact reporting이 정상 동작하는 설정
            joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
            # effort_limit_sim은 일단 두지 않고, stand manifold 형성 후 제한 토크를 재도입
            stiffness=20.0,
            damping=0.5,
        ),
    },
)
"""Configuration for Spot Micro robot."""
