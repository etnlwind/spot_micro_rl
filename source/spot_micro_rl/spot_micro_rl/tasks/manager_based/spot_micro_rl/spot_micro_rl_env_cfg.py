# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""SpotMicro Flat Environment Configuration"""

from isaaclab.utils import configclass
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
import isaaclab.envs.mdp as isaaclab_mdp
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg

from spot_micro_rl.robots import SPOT_MICRO_CFG
from . import mdp as custom_mdp


@configclass
class SpotMicroFlatEnvCfg(LocomotionVelocityRoughEnvCfg):
    def __post_init__(self):
        # post init of parent
        super().__post_init__()

        # Spot Micro 로봇으로 교체
        self.scene.robot = SPOT_MICRO_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
        
        # Flat terrain
        self.scene.terrain.terrain_type = "plane"
        self.scene.terrain.terrain_generator = None
        
        # Flat terrain에서는 curriculum 비활성화
        self.curriculum = None

        # Body link names 수정 - SpotMicro의 "base_link"
        base_cfg = SceneEntityCfg("robot", body_names=["base_link"])

        # Events 수정
        self.events.add_base_mass.params["asset_cfg"] = base_cfg
        # SpotMicro is only 5.6kg, mass perturbation must be small
        self.events.add_base_mass.params["mass_distribution_params"] = (0.0, 0.5)
        self.events.base_com.params["asset_cfg"] = base_cfg
        self.events.base_external_force_torque.params["asset_cfg"] = base_cfg
        # Reduce push velocity for small/light robot
        self.events.push_robot = None

        # Disable height scanner on flat terrain
        self.scene.height_scanner = None
        self.observations.policy.height_scan = None
        
        # Terminations: base_contact 비활성화
        self.terminations.base_contact = None

        # Rewards - body_names 패턴 업데이트
        # feet_air_time: foot_link
        self.rewards.feet_air_time.params["sensor_cfg"] = SceneEntityCfg("contact_forces", body_names=".*foot_link")
        self.rewards.feet_air_time.params["threshold"] = 0.1
        
        # undesired_contacts: base_link, shoulder_link, leg_link
        self.rewards.undesired_contacts.params["sensor_cfg"] = SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link")

        # ============================================================
        # 웅크린 자세(크라우치)에서 걷기 학습
        # ============================================================

        # -- 속도 추적 보상: 걷기 학습용
        self.rewards.track_lin_vel_xy_exp.weight = 15.0
        self.rewards.track_ang_vel_z_exp.weight = 5.0

        # -- 전진 속도 직접 보상
        self.rewards.forward_velocity = RewTerm(
            func=custom_mdp.forward_velocity_reward,
            weight=0.0,  # 0: 먼저 서기 학습, 나중에 점진적으로 증가
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # -- 안정성 페널티
        self.rewards.lin_vel_z_l2.weight = -2.0
        self.rewards.ang_vel_xy_l2.weight = -0.5
        self.rewards.dof_torques_l2.weight = -1e-5
        self.rewards.dof_acc_l2.weight = -2.5e-7
        self.rewards.action_rate_l2.weight = -0.1
        self.rewards.feet_air_time.weight = 20.0  # 다리 끄는거 방지

        # -- 관절 속도 억제
        self.rewards.joint_vel_l2 = RewTerm(
            func=isaaclab_mdp.joint_vel_l2,
            weight=-0.5,
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # -- 수평 유지 페널티
        self.rewards.flat_orientation_l2.weight = -30.0

        # -- 높이 페널티
        self.rewards.base_height_l2 = RewTerm(
            func=isaaclab_mdp.base_height_l2,
            weight=-30.0,
            params={"target_height": 0.21, "asset_cfg": SceneEntityCfg("robot")}
        )

        # -- 높이 × 수평 결합 보상
        self.rewards.standing_height = RewTerm(
            func=custom_mdp.standing_height_exp,
            weight=30.0,
            params={"target_height": 0.21, "sigma": 0.05,
                    "asset_cfg": SceneEntityCfg("robot")}
        )

        # -- 접촉 페널티: 무릎/배/어깨 접촉 페널티
        self.rewards.undesired_contacts.weight = -100.0

        # -- 무릎(leg_link) 높이 보상/페널티
        self.rewards.knee_height = RewTerm(
            func=custom_mdp.body_height_reward,
            weight=2.0,
            params={
                "target_height": 0.06,
                "penalty_below": 0.03,
                "asset_cfg": SceneEntityCfg("robot", body_names=".*leg_link"),
            }
        )

        # -- 발바닥 접지 보상: 걷기 시 비활성화
        self.rewards.feet_on_ground = RewTerm(
            func=custom_mdp.all_feet_on_ground,
            weight=0.0,
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "threshold": 1.0,
            }
        )

        # -- 발이 무릎보다 높으면 강하게 페널티
        self.rewards.feet_below_knees = RewTerm(
            func=custom_mdp.feet_below_knees,
            weight=-500.0,
            params={
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "knee_cfg": SceneEntityCfg("robot", body_names=".*leg_link"),
            }
        )

        # -- 앞/뒤 다리 대칭: 엉덩이가 처지지 않도록
        self.rewards.leg_pose_symmetry = RewTerm(
            func=custom_mdp.leg_pose_symmetry,
            weight=-5.0,
            params={
                "front_leg_cfg": SceneEntityCfg("robot", joint_names=["front_left_leg", "front_left_foot", "front_right_leg", "front_right_foot"]),
                "rear_leg_cfg": SceneEntityCfg("robot", joint_names=["rear_left_leg", "rear_left_foot", "rear_right_leg", "rear_right_foot"]),
            }
        )

        # -- 어깨 대칭
        self.rewards.shoulder_symmetry = RewTerm(
            func=custom_mdp.shoulder_stance_symmetry,
            weight=-10.0,
            params={
                "front_shoulder_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder"]),
                "rear_shoulder_cfg": SceneEntityCfg("robot", joint_names=["rear_left_shoulder", "rear_right_shoulder"]),
            }
        )

        # -- 어깨 중립
        self.rewards.shoulder_neutral = RewTerm(
            func=custom_mdp.shoulder_neutral_penalty,
            weight=-50.0,
            params={
                "shoulder_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder", "rear_left_shoulder", "rear_right_shoulder"]),
            }
        )

        # -- 높이 비례 보상
        self.rewards.height_bonus = RewTerm(
            func=custom_mdp.progressive_height_reward,
            weight=30.0,
            params={
                "min_height": 0.13,   # 크라우치 높이
                "max_height": 0.22,   # 최대 목표
                "asset_cfg": SceneEntityCfg("robot"),
            }
        )

        # -- 뒤집힘 종료 조건
        self.terminations.bad_orientation = DoneTerm(
            func=isaaclab_mdp.bad_orientation,
            params={"limit_angle": 1.5}  # ~86도
        )

        # -- Action scale
        self.actions.joint_pos.scale = 0.5

        # -- Episode length: 10초
        self.episode_length_s = 10.0

        # -- 속도 명령: 걷기 학습용
        self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.5)
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.5, 0.5)
