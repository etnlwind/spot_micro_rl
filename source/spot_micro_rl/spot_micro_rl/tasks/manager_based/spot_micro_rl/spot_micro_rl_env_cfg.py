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
    size=(4.0, 4.0),  # 8→4: 승급 기준 4m→2m (SpotMicro 체형에 맞게)
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

        # -- 속도 추적 보상: 제자리 트롯 드릴에서는 축소
        self.rewards.track_lin_vel_xy_exp.weight = 10.0  # 25→10: 전진보다 다리 들기 우선
        self.rewards.track_ang_vel_z_exp.weight = 5.0

        # -- 전진 속도 직접 보상 (제자리 트롯 드릴에서는 축소)
        self.rewards.forward_velocity = RewTerm(
            func=custom_mdp.forward_velocity_reward,
            weight=5.0,  # 30→5: 제자리 트롯 드릴 — 전진보다 다리 들기 우선
            params={"asset_cfg": SceneEntityCfg("robot"), "target_vel": 0.5},
        )

        # -- 정지 페널티: 제자리 트롯이므로 비활성화
        self.rewards.stationary_penalty = RewTerm(
            func=custom_mdp.stationary_penalty,
            weight=0.0,  # -10→0: 제자리 트롯 허용
            params={"asset_cfg": SceneEntityCfg("robot"), "threshold": 0.05},
        )

        # -- 안정성 페널티 (진동 방지 + 스무딩)
        self.rewards.lin_vel_z_l2.weight = -2.0
        self.rewards.ang_vel_xy_l2.weight = -0.5
        self.rewards.dof_torques_l2.weight = -1e-4  # 토크 억제 강화
        self.rewards.dof_acc_l2.weight = -2.5e-7  # 기본값 복원
        self.rewards.action_rate_l2.weight = -0.3  # -0.5→-0.3: 큰 다리 동작 허용
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

        # -- 관절 한계 접근 페널티: 다리 과도하게 구부리는 것 방지 (완화)
        self.rewards.dof_pos_limits = RewTerm(
            func=isaaclab_mdp.joint_pos_limits,
            weight=-20.0,  # -50→-20: leg 관절 자유 움직임 위해 완화
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
        # 제자리 트롯 드릴: 높이 들기 핵심 보상, 속도 게이팅 제거
        self.rewards.foot_clearance = RewTerm(
            func=custom_mdp.foot_clearance_reward,
            weight=50.0,  # 15→50: 발 높이 들기 핵심 보상
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.12,  # 0.06→0.12: 12cm까지 들어야 만점
                "min_vel": 0.001,  # 0.05→0.001: 제자리에서도 보상 (속도 게이팅 사실상 제거)
            },
        )

        # -- 트롯 걸음걸이 보상 (V6: 덧셈 방식, 4개 성분 독립 보상)
        # 1) 대각 페어A 동기화, 2) 대각 페어B 동기화,
        # 3) 페어 간 반위상, 4) 같은쪽 비동기 (벌레걸음 방지)
        # 덧셈 → 부분 진행도 보상 = 학습 가능한 그래디언트
        self.rewards.trot_gait = RewTerm(
            func=custom_mdp.trot_gait_reward,
            weight=150.0,  # 100→150: 제자리 트롯 드릴의 핵심 보상
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,  # 0.05→0.001: 제자리에서도 트롯 보상
            },
        )

        # -- 비-트로트 페널티 (V8): 바운딩(앞뒤 동기화) + 페이싱(좌우 동기화) 모두 감지
        # V6~V7.1: 바운딩만 감지해서 페이싱을 놓침 → V8: max(bounding, pacing)
        self.rewards.same_side_penalty = RewTerm(
            func=custom_mdp.same_side_penalty,
            weight=-80.0,  # -50→-80: 깨끗한 트롯 강제
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,  # 0.05→0.001: 제자리에서도 페널티
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
            weight=5.0,  # 10→5: 제자리 트롯에서는 보폭보다 높이 우선
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,  # 0.05→0.001: 제자리에서도 보상
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

        # -- 기본 자세에서 벗어나면 페널티: 제자리 트롯 드릴에서는 극소화
        self.rewards.joint_deviation = RewTerm(
            func=isaaclab_mdp.joint_deviation_l1,
            weight=-1.0,  # -15→-1: leg 관절 자유 움직임 허용 (핵심 변경)
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # -- ★ NEW: leg 관절 들어올리기 보상 (제자리 트롯 드릴 핵심)
        # 스윙 중 leg(hip) 관절이 수평에 가깝게 회전할수록 보상
        # 속도 게이팅 없음 → 제자리에서도 작동
        self.rewards.leg_lift = RewTerm(
            func=custom_mdp.leg_lift_reward,
            weight=60.0,  # 높은 가중치: 다리 높이 들기의 핵심 보상
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "leg_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_leg", "front_right_leg", "rear_left_leg", "rear_right_leg"]),
                "target_angle": 0.6,  # ~34도: 이 각도에서 만점
            },
        )

        # -- Action scale
        self.actions.joint_pos.scale = 1.0  # V6: 1.5→1.0: 지터 감소 + 제어 안정성

        # -- Episode length: 10초
        self.episode_length_s = 10.0

        # -- 속도 명령 설정
        self.commands.base_velocity.rel_standing_envs = 0.0  # 정지 명령 없앰 (모든 로봇이 항상 움직임)
        self.commands.base_velocity.rel_heading_envs = 1.0   # 방향 명령 활성화
        
        # -- 속도 명령: 제자리 트롯 드릴 (거의 정지~극저속)
        self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.15)  # (0.3,0.8)→(0.0,0.15): 제자리~극저속
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.5, 0.5)


# ============================================================
# SpotMicro Flat Play (계단 지형 포함, height scanner 없음)
# - observation 48차원 유지 (flat 학습 모델과 호환)
# - 지형만 계단형으로 변경하여 시각적 확인용
# ============================================================
@configclass
class SpotMicroFlatEnvCfg_PLAY(SpotMicroFlatEnvCfg):
    """Flat 학습 모델을 계단 지형에서 테스트하기 위한 Play 설정."""
    def __post_init__(self):
        super().__post_init__()

        # 작은 씬
        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5

        # 지형: 평지 → 계단 지형 (height scanner 없이, observation 호환 유지)
        self.scene.terrain.terrain_type = "generator"
        self.scene.terrain.terrain_generator = TerrainGeneratorCfg(
            size=(8.0, 8.0),
            border_width=20.0,
            num_rows=5,
            num_cols=5,
            horizontal_scale=0.1,
            vertical_scale=0.005,
            slope_threshold=0.75,
            use_cache=False,
            curriculum=False,
            sub_terrains={
                "pyramid_stairs": terrain_gen.MeshPyramidStairsTerrainCfg(
                    proportion=0.4,
                    step_height_range=(0.02, 0.06),
                    step_width=0.2,
                    platform_width=3.0,
                    border_width=1.0,
                    holes=False,
                ),
                "pyramid_stairs_inv": terrain_gen.MeshInvertedPyramidStairsTerrainCfg(
                    proportion=0.3,
                    step_height_range=(0.02, 0.06),
                    step_width=0.2,
                    platform_width=3.0,
                    border_width=1.0,
                    holes=False,
                ),
                "flat": terrain_gen.MeshPlaneTerrainCfg(
                    proportion=0.3,
                    size=(8.0, 8.0),
                ),
            },
        )

        # 노이즈 비활성화
        self.observations.policy.enable_corruption = False
        # 외부 힘 비활성화
        self.events.base_external_force_torque = None


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
        self.scene.terrain.max_init_terrain_level = 5  # 점진적 커리큘럼

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
        # 5. 러프 지형용 보상 조정 (V3: 힘찬 걸음걸이)
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

        # ★ joint_deviation: -15→-3 (러프 지형에서 관절 편차 허용 대폭 완화)
        self.rewards.joint_deviation.weight = -3.0

        # ★ V12: forward_velocity: 60→35 (앞다리만으로 전진 불가하게 → 뒷다리 기여 강제)
        self.rewards.forward_velocity.weight = 35.0

        # ★ trot_gait: 120→180 (V7 min-heavy + 가중치 대폭 강화 → 트롯 필수)
        self.rewards.trot_gait.weight = 180.0

        # ★ V6: foot_clearance 25→35 (발을 확실히 높이 들기)
        self.rewards.foot_clearance.weight = 35.0
        self.rewards.foot_clearance.params["target_clearance"] = 0.10  # V6: 0.08→0.10 (목표 높이 10cm)

        # ★ V12: rear_swing 50→80 (뒷발 높이 들기 강화), target_clearance 0.08→0.12
        self.rewards.rear_swing.weight = 80.0
        self.rewards.rear_swing.params["min_vel"] = 0.05
        self.rewards.rear_swing.params["target_clearance"] = 0.12  # V12: 0.08→0.12 (더 높이 들어야)
        self.rewards.knee_height.weight = 20.0  # V8: 55→20 (비현실적 높이 페널티 완화)
        self.rewards.knee_height.params["target_height"] = 0.12  # V8: 0.17→0.12 (SpotMicro 체형에 현실적)
        self.rewards.knee_height.params["penalty_below"] = 0.06  # V8: 0.08→0.06

        # ★ V12: swing_stride 25→50 (전체 보폭 품질 강화)
        self.rewards.swing_stride.weight = 50.0

        # ★ V10: same_side_penalty -150→-200 (뒷다리 동기화 강력 억제)
        self.rewards.same_side_penalty.weight = -200.0

        # ★ V6: feet_air_time 강화 (긴 스윙 유도, 자잘한 걸음 방지)
        self.rewards.feet_air_time.weight = 20.0  # 10→20
        self.rewards.feet_air_time.params["threshold"] = 0.15  # 0.01→0.15: 150ms 이상 공중 유지해야 보상

        # ★ V6: action_rate 페널티 강화 (부드럽고 큰 동작 유도, 자잘한 진동 억제)
        self.rewards.action_rate_l2.weight = -1.5  # -0.5→-1.5

        # ★ V7: 오르막 등반 보너스 (terrain_levels 향상 목표)
        #   월드 Z 속도 > 0이면 오르막 등반 중 → 보상
        #   전진 게이팅 + 수평 보정으로 안정적 등반만 보상
        self.rewards.uphill_bonus = RewTerm(
            func=custom_mdp.uphill_bonus,
            weight=0.0,  # V8: 60→0 (평지 Z노이즈 공짜보상 제거, terrain_levels 집중)
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
                "max_climb_rate": 0.03,
            },
        )

        # ★ 지형 난이도 비례 보상 — 어려운 지형에서 살아남을수록 큰 보상
        self.rewards.terrain_progress = RewTerm(
            func=custom_mdp.terrain_progress_reward,
            weight=50.0,
            params={},
        )

        # ★ NEW: 거리 보상 — 원점에서 멀리 걸을수록 보상 (커리큘럼 승급 직접 유도)
        #   terrain_size=4 → 승급 기준 2m. target_distance=2.5로 설정.
        self.rewards.distance_walked = RewTerm(
            func=custom_mdp.distance_walked_reward,
            weight=30.0,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "target_distance": 2.5,
            },
        )

        # ★ NEW V10: 뒷다리 교대 보상 — 뒷다리가 번갈아 움직이도록 직접 유도
        #   RL과 RR이 서로 다른 접촉 상태일 때 보상 (하나 접지 + 하나 스윙)
        #   뒷다리가 둘 다 땅에 붙는 local minimum 탈출 핵심
        self.rewards.rear_alternation = RewTerm(
            func=custom_mdp.rear_alternation_reward,
            weight=150.0,  # V12: 300→150 (접촉 교대 달성됨, 예산을 stride로 이동)
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )

        # ★ NEW V11: 뒷다리 동시 접지 페널티 — 두 뒷다리가 동시에 땅에 있으면 직접 페널티
        #   rear_alternation의 보완 (채찍). 당근만으로 local minimum 탈출 불가하여 추가.
        self.rewards.rear_both_ground = RewTerm(
            func=custom_mdp.rear_both_ground_penalty,
            weight=-200.0,
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )

        # ★ NEW V12: 뒷발 전방 보폭 보상 — 뒷발이 들려서 앞으로 이동해야 보상
        #   높이 × 전방 속도의 곱: 둘 다 있어야 높은 보상 (토큰 교대 방지)
        self.rewards.rear_forward_stride = RewTerm(
            func=custom_mdp.rear_forward_stride_reward,
            weight=250.0,
            params={
                "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link"),
                "foot_cfg": SceneEntityCfg("robot", body_names=".*foot_link"),
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "target_clearance": 0.06,
                "min_vel": 0.05,
            },
        )

        # ★ NEW V9: foot 관절 과신전 페널티 — 발바닥이 앞을 향하는 비자연스러운 자세 방지
        # foot joint 범위: -0.1~2.59 rad. max_angle=1.5 rad 초과 시 2차 페널티.
        self.rewards.foot_extension = RewTerm(
            func=custom_mdp.foot_extension_penalty,
            weight=-30.0,
            params={
                "foot_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_foot", "front_right_foot", "rear_left_foot", "rear_right_foot"]),
                "max_angle": 1.5,
            },
        )

        # 에피소드 길이: 러프 지형에서 20초
        self.episode_length_s = 20.0

        # 속도 범위: 러프 지형에서 약간 느리게 시작
        self.commands.base_velocity.ranges.lin_vel_x = (0.2, 0.6)

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
