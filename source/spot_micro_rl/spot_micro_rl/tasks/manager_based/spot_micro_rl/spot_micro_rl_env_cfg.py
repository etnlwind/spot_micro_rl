# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""SpotMicro Environment Configuration (Flat + Rough)"""

from isaaclab.utils import configclass
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.sensors import RayCasterCfg, patterns
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
import isaaclab.envs.mdp as isaaclab_mdp
import isaaclab_tasks.manager_based.locomotion.velocity.mdp as velocity_mdp
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
import isaaclab.terrains as terrain_gen
from isaaclab.terrains.terrain_generator_cfg import TerrainGeneratorCfg

from spot_micro_rl.robots import SPOT_MICRO_CFG
from . import mdp as custom_mdp


# ============================================================
# SpotMicro용 러프 지형 설정
# ANYmal C 기준 지형을 SpotMicro 크기(~24cm)에 맞게 스케일링
# ANYmal C (~55cm) 대비 약 0.44배
# ============================================================
SPOT_MICRO_ROUGH_TERRAINS_CFG = TerrainGeneratorCfg(
    size=(8.0, 8.0),
    border_width=20.0,
    num_rows=10,
    num_cols=20,
    horizontal_scale=0.1,
    vertical_scale=0.005,
    slope_threshold=0.75,
    use_cache=False,
    sub_terrains={
        # 계단 (위로 올라가기)
        "pyramid_stairs": terrain_gen.MeshPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.02, 0.08),  # ANYmal: 0.05~0.23 → SpotMicro: 0.02~0.08
            step_width=0.2,  # ANYmal: 0.3 → SpotMicro: 0.2 (작은 발에 맞게)
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        # 역계단 (아래로 내려가기)
        "pyramid_stairs_inv": terrain_gen.MeshInvertedPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.02, 0.08),
            step_width=0.2,
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        # 무작위 장애물 박스
        "boxes": terrain_gen.MeshRandomGridTerrainCfg(
            proportion=0.2,
            grid_width=0.3,  # ANYmal: 0.45 → SpotMicro: 0.3
            grid_height_range=(0.02, 0.06),  # ANYmal: 0.05~0.2 → SpotMicro: 0.02~0.06
            platform_width=2.0,
        ),
        # 무작위 울퉁불퉁 지형
        "random_rough": terrain_gen.HfRandomUniformTerrainCfg(
            proportion=0.2,
            noise_range=(0.01, 0.04),  # ANYmal: 0.02~0.10 → SpotMicro: 0.01~0.04
            noise_step=0.01,  # ANYmal: 0.02 → SpotMicro: 0.01
            border_width=0.25,
        ),
        # 경사면 (위로)
        "hf_pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.1,
            slope_range=(0.0, 0.2),  # ANYmal: 0.0~0.4 → SpotMicro: 0.0~0.2
            platform_width=2.0,
            border_width=0.25,
        ),
        # 경사면 (아래로)
        "hf_pyramid_slope_inv": terrain_gen.HfInvertedPyramidSlopedTerrainCfg(
            proportion=0.1,
            slope_range=(0.0, 0.2),
            platform_width=2.0,
            border_width=0.25,
        ),
    },
)


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
            weight=30.0,  # V6: 40→30: 트롯 보상이 1위가 되도록 감소
            params={"asset_cfg": SceneEntityCfg("robot"), "target_vel": 0.5},
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
            weight=-50.0,  # V7: -30→-50: 엎드림 방지 강화
            params={"target_height": 0.24, "asset_cfg": SceneEntityCfg("robot")}  # V7: 0.22→0.24: 목표 높이 복원
        )

        # -- 높이 × 수평 결합 보상
        self.rewards.standing_height = RewTerm(
            func=custom_mdp.standing_height_exp,
            weight=40.0,  # V7: 20→40: 높이 보상 복원 (엎드림 방지)
            params={"target_height": 0.24, "sigma": 0.03,  # V7: 0.22→0.24, sigma 0.05→0.03: 높이 타이트하게
                    "asset_cfg": SceneEntityCfg("robot")}
        )

        # -- 접촉 페널티: 무릎/배/어깨 접촉 페널티
        self.rewards.undesired_contacts.weight = -300.0  # V7: -100→-300: 무릎으로 걷는 것 강력 방지

        # -- 무릎(leg_link) 높이 보상/페널티
        self.rewards.knee_height = RewTerm(
            func=custom_mdp.body_height_reward,
            weight=20.0,  # V7: 10→20: 무릎 높이 강력 강화 (무릎로 걷는 것 방지)
            params={
                "target_height": 0.12,  # V7: 0.10→0.12: 무릎는 바닥에서 멀리
                "penalty_below": 0.06,  # V7: 0.05→0.06: 낮은 무릎 페널티 강화
                "asset_cfg": SceneEntityCfg("robot", body_names=".*leg_link"),
            }
        )

        # -- 관절 한계 접근 페널티 (V7 신규): 다리 과도하게 구부리는 것 방지
        self.rewards.dof_pos_limits = RewTerm(
            func=isaaclab_mdp.joint_pos_limits,
            weight=-50.0,  # V7: -20→-50: 관절 한계 접근 페널티 강화
            params={"asset_cfg": SceneEntityCfg("robot")},
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
            weight=20.0,  # V7: 10→20: 높이 보상 강화
            params={
                "min_height": 0.15,  # V7: 0.13→0.15: 너무 낮으면 보상 없음
                "max_height": 0.25,  # V7: 0.23→0.25: 높이 서야 최대 보상
                "asset_cfg": SceneEntityCfg("robot"),
            }
        )

        # -- 뒤집힘 종료 조건
        self.terminations.bad_orientation = DoneTerm(
            func=isaaclab_mdp.bad_orientation,
            params={"limit_angle": 1.5}  # ~86도
        )

        # -- 발 높이 보상 (스윙 시 발을 높이 들어야 보상)
        # V6: 35→15 축소 (트롯 보상이 자연스럽게 발 들기 유도)
        self.rewards.foot_clearance = RewTerm(
            func=custom_mdp.foot_clearance_reward,
            weight=15.0,  # V6: 35→15: 트롯이 주도하도록 축소
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.06,
                "min_vel": 0.05,
            },
        )

        # -- 트롯 걸음걸이 보상 (V6: 덧셈 방식, 4개 성분 독립 보상)
        # 1) 대각 페어A 동기화, 2) 대각 페어B 동기화,
        # 3) 페어 간 반위상, 4) 같은쪽 비동기 (벌레걸음 방지)
        # 덧셈 → 부분 진행도 보상 = 학습 가능한 그래디언트
        self.rewards.trot_gait = RewTerm(
            func=custom_mdp.trot_gait_reward,
            weight=100.0,  # V6: 50→100: 압도적 1위 보상 (트롯이 왕)
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 비-트로트 페널티 (V8): 바운딩(앞뒤 동기화) + 페이싱(좌우 동기화) 모두 감지
        # V6~V7.1: 바운딩만 감지해서 페이싱을 놓침 → V8: max(bounding, pacing)
        self.rewards.same_side_penalty = RewTerm(
            func=custom_mdp.same_side_penalty,
            weight=-50.0,  # V8: -100→-50 복원 (이제 페이싱도 감지하므로 충분)
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 접촉 발 수 보상: V6에서 제거 (trot_gait + same_side_penalty가 대체)
        self.rewards.contact_count = RewTerm(
            func=custom_mdp.gait_contact_count_reward,
            weight=0.0,  # V6: 20→0: 트롯 보상에 통합
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 스윙 보폭 보상: 발이 공중에서 앞으로 이동한 거리 보상
        self.rewards.swing_stride = RewTerm(
            func=custom_mdp.swing_stride_reward,
            weight=10.0,  # V6: 30→10: 트롯 보상이 주도하도록 축소
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # -- 뒷발 스윙 보너스: V6에서 제거 (trot_gait가 자연스럽게 뒷발 스윙 유도)
        self.rewards.rear_swing = RewTerm(
            func=custom_mdp.rear_swing_bonus,
            weight=0.0,  # V6: 40→0: 제거 (벌레걸음 허용하는 단축키였음)
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.06,
                "min_vel": 0.05,
            },
        )

        # -- 기본 자세에서 벧어나면 페널티 (V7 신규): 다리 접힘 방지
        self.rewards.joint_deviation = RewTerm(
            func=isaaclab_mdp.joint_deviation_l1,
            weight=-15.0,  # V7: -5→-15: 기본 자세 유지 강화 (다리 접힘 방지)
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # -- Action scale
        self.actions.joint_pos.scale = 1.0  # V6: 1.5→1.0: 지터 감소 + 제어 안정성

        # -- Episode length: 10초
        self.episode_length_s = 10.0

        # -- 속도 명령 설정
        self.commands.base_velocity.rel_standing_envs = 0.0  # 정지 명령 없앰 (모든 로봇이 항상 움직임)
        self.commands.base_velocity.rel_heading_envs = 1.0   # 방향 명령 활성화
        
        # -- 속도 명령: 더 빠른 보행 유도
        self.commands.base_velocity.ranges.lin_vel_x = (0.3, 0.8)  # (0.2,0.5)→(0.3,0.8): 속도 범위 확대
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.5, 0.5)


# ============================================================
# SpotMicro Rough Terrain Environment Configuration
# SpotMicroFlatEnvCfg 상속 → 지형/높이스캐너/커리큘럼 복원
# ============================================================
@configclass
class SpotMicroRoughEnvCfg(SpotMicroFlatEnvCfg):
    """SpotMicro 러프 지형 환경 설정.
    
    SpotMicroFlatEnvCfg의 모든 보상 함수(V8 트롯 걸음걸이 등)를 유지하면서
    지형을 평지→러프로 변경, 높이 스캐너 활성화, 커리큘럼 활성화.
    """
    def __post_init__(self):
        # Flat config의 모든 설정 적용 (보상, 로봇, 제어주파수 등)
        super().__post_init__()

        # ============================================================
        # 1. 지형: 평지 → 러프 지형 (SpotMicro 크기에 맞게 스케일링)
        # ============================================================
        self.scene.terrain.terrain_type = "generator"
        self.scene.terrain.terrain_generator = SPOT_MICRO_ROUGH_TERRAINS_CFG
        self.scene.terrain.max_init_terrain_level = 5

        # ============================================================
        # 2. 높이 스캐너: 러프 지형에서 지형 인식 필수
        #    SpotMicro는 base_link (ANYmal은 base)
        #    GridPattern: 0.1m 해상도, 0.8×0.5m 영역 (SpotMicro 크기에 맞게 축소)
        # ============================================================
        self.scene.height_scanner = RayCasterCfg(
            prim_path="{ENV_REGEX_NS}/Robot/base_link",
            offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.0, 20.0)),
            ray_alignment="yaw",
            pattern_cfg=patterns.GridPatternCfg(resolution=0.1, size=[0.8, 0.5]),
            debug_vis=False,
            mesh_prim_paths=["/World/ground"],
        )
        # 높이 스캐너 업데이트 주기 설정
        self.scene.height_scanner.update_period = self.decimation * self.sim.dt

        # ============================================================
        # 3. 관측: height_scan 복원 (지형 높이 정보를 정책에 제공)
        # ============================================================
        self.observations.policy.height_scan = ObsTerm(
            func=velocity_mdp.height_scan,
            params={"sensor_cfg": SceneEntityCfg("height_scanner")},
            noise=Unoise(n_min=-0.1, n_max=0.1),
            clip=(-1.0, 1.0),
        )

        # ============================================================
        # 4. 커리큘럼: 지형 난이도 점진적 증가
        #    쉬운 지형에서 시작 → 성공 시 어려운 지형으로
        # ============================================================
        from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import CurriculumCfg
        self.curriculum = CurriculumCfg()

        # ============================================================
        # 5. 러프 지형용 보상 조정
        # ============================================================
        # 높이 보상: 울퉁불퉁한 지형에서는 목표 높이에 약간의 여유
        self.rewards.base_height_l2.weight = -30.0  # -50→-30: 지형 높낮이에 따른 변동 허용
        self.rewards.base_height_l2.params["target_height"] = 0.22  # 0.24→0.22: 러프에서 약간 낮아도 OK
        self.rewards.standing_height.params["target_height"] = 0.22
        self.rewards.standing_height.params["sigma"] = 0.05  # 0.03→0.05: 높이 허용 범위 완화
        self.rewards.standing_height.weight = 30.0  # 40→30

        # 수평 유지: 약간 완화 (울퉁불퉁한 지형에서 약간의 기울어짐 허용)
        self.rewards.flat_orientation_l2.weight = -15.0  # -20→-15

        # 높이 비례 보상: 최소 높이 약간 낮춤
        self.rewards.height_bonus.params["min_height"] = 0.13  # 0.15→0.13: 지형 특성상 약간 낮을 수 있음

        # 에피소드 길이: 러프 지형에서 20초 (더 많은 시간 필요)
        self.episode_length_s = 20.0

        # 속도 범위: 러프 지형에서는 약간 느리게 시작
        self.commands.base_velocity.ranges.lin_vel_x = (0.2, 0.6)  # (0.3,0.8)→(0.2,0.6): 러프에서 속도 낮춤

        # base_contact 종료 조건 복원 (러프 지형에서는 넘어짐 감지 중요)
        self.terminations.base_contact = DoneTerm(
            func=isaaclab_mdp.illegal_contact,
            params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link"), "threshold": 1.0},
        )

        # push_robot 이벤트 복원 (러프 지형에서 로버스트한 걸음걸이 학습)
        from isaaclab.managers import EventTermCfg as EventTerm
        self.events.push_robot = EventTerm(
            func=velocity_mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=(10.0, 15.0),
            params={"velocity_range": {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}},  # ANYmal 0.5→SpotMicro 0.3
        )


@configclass
class SpotMicroRoughEnvCfg_PLAY(SpotMicroRoughEnvCfg):
    """SpotMicro 러프 지형 플레이 설정."""
    def __post_init__(self):
        super().__post_init__()

        # 작은 씬
        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5
        # 랜덤 지형 레벨에서 시작 (커리큘럼 없이)
        self.scene.terrain.max_init_terrain_level = None
        # 지형 수 줄이기 (메모리 절약)
        if self.scene.terrain.terrain_generator is not None:
            self.scene.terrain.terrain_generator.num_rows = 5
            self.scene.terrain.terrain_generator.num_cols = 5
            self.scene.terrain.terrain_generator.curriculum = False

        # 노이즈 비활성화
        self.observations.policy.enable_corruption = False
        # 외부 힘/푸시 비활성화
        self.events.base_external_force_torque = None
        self.events.push_robot = None
