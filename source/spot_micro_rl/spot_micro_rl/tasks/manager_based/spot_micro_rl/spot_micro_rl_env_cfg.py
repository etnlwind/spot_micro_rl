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

        # ============================================================
        # 제어 주파수: 50Hz→25Hz (진동 보행 물리적 차단)
        # decimation=8 → step_dt=0.04s → 25Hz
        # ============================================================
        self.decimation = 8
        
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

        # -- 속도 추적 보상: 걷기 학습 강화
        self.rewards.track_lin_vel_xy_exp.weight = 25.0  # 15→25: 속도 추적 보상 대폭 증가
        self.rewards.track_ang_vel_z_exp.weight = 5.0

        # -- 전진 속도 직접 보상 (정규화 + 자세 연동)
        self.rewards.forward_velocity = RewTerm(
            func=custom_mdp.forward_velocity_reward,
            weight=40.0,  # 전진이 모든 보상의 열쇠
            params={"asset_cfg": SceneEntityCfg("robot"), "target_vel": 0.5},  # 0.3→0.5: 목표 속도 증가
        )

        # -- 정지 페널티: 멈춰있으면 페널티 (완화)
        self.rewards.stationary_penalty = RewTerm(
            func=custom_mdp.stationary_penalty,
            weight=-10.0,  # -5→-10: 정지 페널티 강화 (제자리 트롯 방지)
            params={"asset_cfg": SceneEntityCfg("robot"), "threshold": 0.05},
        )

        # -- 안정성 페널티 (진동 방지 + 스무딩)
        self.rewards.lin_vel_z_l2.weight = -2.0
        self.rewards.ang_vel_xy_l2.weight = -0.5
        self.rewards.dof_torques_l2.weight = -1e-4  # 토크 억제 강화
        self.rewards.dof_acc_l2.weight = -2.5e-7  # 기본값 복원
        self.rewards.action_rate_l2.weight = -0.5  # 25Hz에서는 -0.5로 충분
        self.rewards.feet_air_time.weight = 10.0  # V3: 40→10: 시그널 과다 방지, 가중치 재배분
        self.rewards.feet_air_time.params["threshold"] = 0.01  # V3: 0.06→0.01: 1스텝(0.04s) > 0.01s → 드디어 보상 가능

        # -- 관절 속도 억제
        self.rewards.joint_vel_l2 = RewTerm(
            func=isaaclab_mdp.joint_vel_l2,
            weight=-0.05,  # V2: -0.1→-0.05: 관절 속도 페널티 완화 (자연스러운 다리 움직임 허용)
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # -- 수평 유지 페널티
        self.rewards.flat_orientation_l2.weight = -20.0  # -30→-20: 걷기 시 자연스러운 약간의 기울임 허용

        # -- 높이 페널티: 강아지처럼 높이 서야 함
        self.rewards.base_height_l2 = RewTerm(
            func=isaaclab_mdp.base_height_l2,
            weight=-50.0,  # -30→-50: 낮으면 강한 페널티 (벌레 자세 방지)
            params={"target_height": 0.24, "asset_cfg": SceneEntityCfg("robot")}  # 0.21→0.24: 더 높이 서기
        )

        # -- 높이 × 수평 결합 보상
        self.rewards.standing_height = RewTerm(
            func=custom_mdp.standing_height_exp,
            weight=40.0,  # V3: 30→40: 높이 서기 강화 (75%→목표 85%)
            params={"target_height": 0.24, "sigma": 0.03,  # 0.21→0.24, sigma 0.05→0.03: 더 정확한 높이 요구
                    "asset_cfg": SceneEntityCfg("robot")}
        )

        # -- 접촉 페널티: 무릎/배/어깨 접촉 페널티
        self.rewards.undesired_contacts.weight = -100.0

        # -- 무릎(leg_link) 높이 보상/페널티
        self.rewards.knee_height = RewTerm(
            func=custom_mdp.body_height_reward,
            weight=5.0,  # 2→5: 무릎 높이 강화
            params={
                "target_height": 0.08,  # 0.06→0.08: 무릎 더 높이
                "penalty_below": 0.04,  # 0.03→0.04
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

        # -- 앞/뒤 다리 대칭: 트롯에서는 대각선 쌍이 반대이므로 제거
        # 트롯 보행 시 앞다리≠뒷다리가 정상. 이 페널티가 보폭을 억제하고 있었음.
        self.rewards.leg_pose_symmetry = RewTerm(
            func=custom_mdp.leg_pose_symmetry,
            weight=0.0,  # -5.0→0.0: 비활성화 (트롯 걸음걸이와 충돌)
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
            weight=-25.0,  # -50→-25: 어깨 페널티 완화 (걷기 시 어깨 움직임 허용)
            params={
                "shoulder_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder", "rear_left_shoulder", "rear_right_shoulder"]),
            }
        )

        # -- 높이 비례 보상: 높을수록 보상
        self.rewards.height_bonus = RewTerm(
            func=custom_mdp.progressive_height_reward,
            weight=20.0,  # 10→20: 높이 보상 강화
            params={
                "min_height": 0.15,  # 0.13→0.15
                "max_height": 0.25,  # 0.22→0.25
                "asset_cfg": SceneEntityCfg("robot"),
            }
        )

        # -- 뒤집힘 종료 조건
        self.terminations.bad_orientation = DoneTerm(
            func=isaaclab_mdp.bad_orientation,
            params={"limit_angle": 1.5}  # ~86도
        )

        # -- 발 높이 보상 (스윙 시 발을 높이 들어야 보상, 벌레 셔플링 방지)
        # 전진 게이팅: 앞으로 움직일 때만 보상 (제자리 발 들기 방지)
        self.rewards.foot_clearance = RewTerm(
            func=custom_mdp.foot_clearance_reward,
            weight=20.0,  # 10→20: 발 높이 들기 강화
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.10,  # 0.05→0.10: 발을 10cm 이상 들어야 보상 (강아지 걸음)
                "min_vel": 0.05,
            },
        )

        # -- 트롯 걸음걸이 보상 (대각선 페어 엄격 교대)
        # 곱셈(AND): 페어A 동기화 × 페어B 동기화 × 반위상 = 완벽 트롯만 보상
        # 전진 게이팅: 앞으로 움직일 때만 보상 (제자리 트롯 방지)
        self.rewards.trot_gait = RewTerm(
            func=custom_mdp.trot_gait_reward,
            weight=50.0,  # V4: 25→50: 대각선 페어 교대 보상 대폭 강화
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 접촉 발 수 보상 (항상 2개 발이 바닥에 = 트롯 핵심)
        # 전진 게이팅: 앞으로 움직일 때만 보상
        self.rewards.contact_count = RewTerm(
            func=custom_mdp.gait_contact_count_reward,
            weight=20.0,  # V4: 10→20: 2발 접촉 강화 (대각 페어 보조)
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 스윙 보폭 보상: 발이 공중에서 앞으로 이동한 거리 보상 (큰 보폭 유도)
        self.rewards.swing_stride = RewTerm(
            func=custom_mdp.swing_stride_reward,
            weight=15.0,
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- Action scale
        self.actions.joint_pos.scale = 1.0  # 관절 이동 범위 확대 (큰 보폭 허용)

        # -- Episode length: 10초
        self.episode_length_s = 10.0

        # -- 속도 명령 설정
        self.commands.base_velocity.rel_standing_envs = 0.0  # 정지 명령 없앰 (모든 로봇이 항상 움직임)
        self.commands.base_velocity.rel_heading_envs = 1.0   # 방향 명령 활성화
        
        # -- 속도 명령: 더 빠른 보행 유도
        self.commands.base_velocity.ranges.lin_vel_x = (0.3, 0.8)  # (0.2,0.5)→(0.3,0.8): 속도 범위 확대
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.5, 0.5)
