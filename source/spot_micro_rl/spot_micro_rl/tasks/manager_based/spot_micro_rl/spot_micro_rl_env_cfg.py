# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""SpotMicro Environment Configuration (Flat + Rough)"""

# ── 훈련 버전 (Telegram/로그에 자동 표시, 코드 변경 시 여기만 수정) ──
TRAIN_VERSION = "V37.2"

from isaaclab.utils import configclass
from isaaclab.managers import ObservationTermCfg as ObsTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import TerminationTermCfg as DoneTerm
from isaaclab.managers import CurriculumTermCfg as CurrTerm
from isaaclab.sensors import RayCasterCfg, patterns
from isaaclab.utils.noise import AdditiveUniformNoiseCfg as Unoise
import isaaclab.envs.mdp as isaaclab_mdp
import isaaclab_tasks.manager_based.locomotion.velocity.mdp as velocity_mdp
from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import LocomotionVelocityRoughEnvCfg
import isaaclab.terrains as terrain_gen
from isaaclab.terrains.terrain_generator_cfg import TerrainGeneratorCfg

from spot_micro_rl.robots import SPOT_MICRO_CFG
from . import mdp as custom_mdp


# SpotMicro용 급경사 지형 설정 (Flat 모델 테스트용)
# 오르막/내리막 경사면 위주 지형 - height_scan 없는 flat 모델에서 사용
SPOT_MICRO_STEEP_SLOPES_CFG = TerrainGeneratorCfg(
    size=(4.0, 4.0),
    border_width=20.0,
    num_rows=5,
    num_cols=5,
    horizontal_scale=0.1,
    vertical_scale=0.005,
    slope_threshold=0.75,
    use_cache=False,
    curriculum=False,
    sub_terrains={
        # 급경사 오르막
        "hf_pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.35,
            slope_range=(0.15, 0.4),
            platform_width=2.0,
            border_width=0.25,
        ),
        # 급경사 내리막
        "hf_pyramid_slope_inv": terrain_gen.HfInvertedPyramidSlopedTerrainCfg(
            proportion=0.35,
            slope_range=(0.15, 0.4),
            platform_width=2.0,
            border_width=0.25,
        ),
        # 울퉁불퉁 + 경사 혼합
        "random_rough": terrain_gen.HfRandomUniformTerrainCfg(
            proportion=0.15,
            noise_range=(0.02, 0.06),
            noise_step=0.01,
            border_width=0.25,
        ),
        # 계단 (경사 시각적 확인용)
        "pyramid_stairs": terrain_gen.MeshPyramidStairsTerrainCfg(
            proportion=0.15,
            step_height_range=(0.03, 0.10),
            step_width=0.2,
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
    },
)


# SpotMicro용 러프 지형 설정
# ANYmal C(~55cm) 대비 SpotMicro(~24cm)에 맞게 스케일 조정
SPOT_MICRO_ROUGH_TERRAINS_CFG = TerrainGeneratorCfg(
    size=(4.0, 4.0),  # 작은 지형 → 승급 기준 2m
    border_width=20.0,
    num_rows=10,
    num_cols=20,
    horizontal_scale=0.1,
    vertical_scale=0.005,
    slope_threshold=0.75,
    use_cache=False,
    sub_terrains={
        # 계단
        "pyramid_stairs": terrain_gen.MeshPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.02, 0.08),
            step_width=0.2,
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        # 역계단
        "pyramid_stairs_inv": terrain_gen.MeshInvertedPyramidStairsTerrainCfg(
            proportion=0.2,
            step_height_range=(0.02, 0.08),
            step_width=0.2,
            platform_width=3.0,
            border_width=1.0,
            holes=False,
        ),
        # 랜덤 박스 장애물
        "boxes": terrain_gen.MeshRandomGridTerrainCfg(
            proportion=0.2,
            grid_width=0.3,
            grid_height_range=(0.02, 0.06),
            platform_width=2.0,
        ),
        # 울퉁불퉁 지형
        "random_rough": terrain_gen.HfRandomUniformTerrainCfg(
            proportion=0.2,
            noise_range=(0.01, 0.04),
            noise_step=0.01,
            border_width=0.25,
        ),
        # 경사면 (위로)
        "hf_pyramid_slope": terrain_gen.HfPyramidSlopedTerrainCfg(
            proportion=0.1,
            slope_range=(0.0, 0.2),
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


# ============================================================
# V20: Soft-Ramp 리워드 커리큘럼 (STAND → WALK → TROT)
# 하드 Phase 전환 대신 선형 보간 ramp로 critic shock 방지
# ============================================================
@configclass
class SpotMicroRewardCurriculumCfg:
    """Soft-ramp 리워드 가중치 커리큘럼 (V20, V26 확장).

    Phase 1→2 (STAND→WALK): iter 1500~3000 선형 보간
    Phase 2→3 (WALK→TROT):  iter 5500~8000 선형 보간
    Metric gating: ep_len < 200이면 ramp 일시정지

    V28 변경 ("안 하면 벌점" → "제대로 하면 이득"):
      Layer B (Validity Floor) — V27.1b 대비 완화:
        single_limb_validity_penalty: -5 → -25 (iter 0~250, V27.1b -5→-35 0~200보다 약화)
        contact floor: -1 → -12 (iter 0~200, V27.1b -2→-20보다 약화)
        propulsion floor: -1 → -10 (iter 50~250, V27.1b -2→-15보다 약화)
      Layer C (Target-Band Incentive) — 신규:
        contact target band [0.20~0.45]: 0.5 → 5.0 (iter 100~300, ramp)
        propulsion target band [0.15~0.38]: 0.5 → 4.0 (iter 100~300)
        usage target band [0.20~0.45]: 0.0 → 3.0 (iter 200~450)
        four_limb_cooperation: 0.0 → 8.0 (iter 200~450, trigger band_hit >= 2/3)
      Layer C/B ramp 설계: iter 250+에서 Layer C 총합 > Layer B 총합
    """
    reward_weights = CurrTerm(
        func=custom_mdp.reward_weight_curriculum,
        params={
            "num_steps_per_env": 48,
            "ramp1_start": 1500,
            "ramp1_end": 3000,
            "ramp2_start": 5500,
            "ramp2_end": 8000,
            "validity_ramp_start": 0,   # Legacy — no-op
            "validity_ramp_end": 1,
            "validity_limb_usage_initial": 0.0,
            "validity_limb_usage_final": 0.0,
            "validity_rear_diff_initial": 0.0,
            "validity_rear_diff_final": 0.0,
            # V28 Layer B: existence floor ramp — V27.1b보다 완화 (Layer C 공간 확보)
            "floor_ramp_start": 0,
            "floor_ramp_end": 200,
            "floor_limb_usage_initial": -8.0,
            "floor_limb_usage_final": -25.0,
            "floor_per_leg_contact_initial": -1.0,   # V28: -2 → -1 (초반 추가 완화)
            "floor_per_leg_contact_final": -12.0,    # V28: -20 → -12 (Layer C 공간 확보)
            "floor_per_leg_propulsion_initial": -1.0,  # V28: -2 → -1
            "floor_per_leg_propulsion_final": -10.0,   # V28: -15 → -10
            # V28: propulsion floor 전용 ramp (iter 50~250, V27.1b 50~200보다 늦게)
            "propulsion_floor_ramp_start": 50,
            "propulsion_floor_ramp_end": 250,
            # Load sharing ramp (V27 동일 유지)
            "load_ramp_start": 50,
            "load_ramp_end": 150,
            "load_rear_usage_diff_final": -10.0,
            "load_front_usage_diff_final": -8.0,
            "load_rear_prop_diff_final": -20.0,
            "load_front_rear_balance_final": 0.0,
            "load_front_prop_diff_final": -20.0,
            # V28 Layer B: single_limb_validity_penalty ramp (iter 0~250, V27.1b 0~200보다 완화)
            "validity_gate_ramp_start": 0,
            "validity_gate_ramp_end": 250,
            "validity_gate_initial": -5.0,
            "validity_gate_final": -25.0,    # V28: -35 → -25 (Layer C에 유리한 공간)
            # V28 Layer C: contact + propulsion target-band reward ramp (iter 100~300)
            "band_ramp_start": 100,
            "band_ramp_end": 300,
            "band_contact_initial": 0.5,     # iter 100부터 약하게 시작
            "band_contact_final": 5.0,       # V26 iter200 실측 기반 (V29.2: band [0.20~0.75])
            "band_propulsion_initial": 0.5,
            "band_propulsion_final": 4.0,    # band [0.15~0.38]
            # V28 Layer C: usage band + cooperation ramp (iter 200~450, 후반 강화형)
            "coop_ramp_start": 200,
            "coop_ramp_end": 450,
            "coop_usage_initial": 0.0,
            "coop_usage_final": 3.0,         # usage band [0.20~0.45]
            "coop_reward_initial": 0.0,
            "coop_reward_final": 8.0,        # band_hit_count >= 2/3 trigger
            # V28.1: residency relay ramp (early triangle 600→800→1000, late ramp 800→1000→유지)
            # V29.2: 타이밍 지연 — gait 안정화 후 잔류 학습 (600/800/1000 → 800/1000/1200)
            "residency_relay_up_start": 800,
            "residency_relay_up_end": 1000,
            "residency_relay_down_end": 1200,
            "contact_residency_early_max": 3.0,   # early 최대 weight (600→800 peak)
            "contact_residency_late_max": 4.0,    # late 최대 weight (1000+ 유지)
            "prop_residency_early_max": 2.0,
            "prop_residency_late_max": 3.0,
            "usage_residency_early_max": 1.0,
            "usage_residency_late_max": 2.0,
            # V28.2: rear pair residency symmetry penalty 강화 (iter 400~700, 완충 포함)
            "rear_symmetry_ramp_start": 400,      # V28.1: 600 → V28.2: 400
            "rear_symmetry_ramp_end": 700,        # V28.1: 1000 → V28.2: 700
            "rear_symmetry_max": -28.0,           # V28.1: -8.0 → V28.2: -28.0 (3.5배)
            # V28.2: late-phase band exit penalty 강화 (iter 600~900)
            "exit_penalty_ramp_start": 600,       # V28.1: 800 → V28.2: 600
            "exit_penalty_ramp_end": 900,         # V28.1: 1200 → V28.2: 900
            "exit_penalty_max": -15.0,            # V28.1: -6.0 → V28.2: -15.0 (2.5배)
            # V28.2: cooperation min-leg factor 강화 (iter 600~800, 1.0 → 0.05)
            "coop_min_leg_ramp_start": 600,       # V28.1: 800 → V28.2: 600
            "coop_min_leg_ramp_end": 800,         # V28.1: 1000 → V28.2: 800
            "coop_min_leg_factor_target": 0.05,   # V28.1: 0.2 → V28.2: 0.05 (95% 감쇠)
            # V28.2: rear pair contact diff penalty (신규, current-step, iter 300~600)
            "rear_contact_diff_ramp_start": 300,
            "rear_contact_diff_ramp_end": 600,
            "rear_contact_diff_max": -15.0,       # threshold 0.10, max -15.0
            # V29: stride length reward ramp (iter 400~700)
            "stride_length_ramp_start": 200,      # V36: 400→200 (anti-shuffle 조기 활성화)
            "stride_length_ramp_end": 500,        # V36: 700→500
            "stride_length_max": 15.0,            # V36: 12→15 (보폭 보상 강화)
            # V29: swing quality gated velocity reward ramp (iter 600~900)
            "swing_gate_ramp_start": 600,
            "swing_gate_ramp_end": 900,
            "swing_gate_max": 15.0,               # 4발 min swing × 속도 (swing_gate_max=15)
            # V31: front swing ramp (iter 100~400) — 앞다리 swing 강제
            "front_swing_ramp_start": 100,
            "front_swing_ramp_end": 400,
            "front_swing_bonus_max": 0.0,          # V32: 비활성화 — feet_air_time으로 대체
            "front_alternation_max": 0.0,          # V31.1: 비활성화
            "front_both_ground_max": 0.0,          # V31.2: 비활성화
            "min_swing_ratio_max": 0.0,            # V31.2: 비활성화
            # V32: front joint-level 비활성화 — feet_air_time이 4발 공통 swing 유도
            "front_joint_velocity_max": 0.0,       # V32: 비활성화
            "front_joint_frozen_max": 0.0,         # V32: 비활성화
            # V35.5: boot stability ramp — 초기 penalty 완화 + 저속 명령
            "boot_ramp_end": 300,                  # iter 0~300: 부팅 구간
            "boot_undesired_contacts_floor": -20.0, # -100 → -20 (iter 0), iter 300에서 -100 복원
            "boot_vel_x_min": 0.01,                # 초기 속도 범위 (0.01, 0.05)
            "boot_vel_x_max": 0.05,
            "boot_vel_restore_iter": 500,          # iter 500에서 원래 속도 (0.1, 0.5) 복원
            # V37: anti-splay curriculum ramp — 보행 학습 후 splay 교정
            "splay_ramp_start": 500,               # iter 500부터 강화 시작
            "splay_ramp_end": 1500,                # iter 1500에서 최종값 도달 (V37: 1000 → 더 느리게)
            "splay_shoulder_initial": -6.0,        # 부팅 구간 유지
            "splay_shoulder_final": -10.0,         # V37(-15) → V37.2(-10) 완화
            "splay_stance_initial": -3.0,
            "splay_stance_final": -3.0,            # V37(-8) → V37.2 변경 없음 (단일 변수)
            "splay_height_initial": 0.23,
            "splay_height_final": 0.23,            # V37(0.22) → V37.2 변경 없음 (단일 변수)
            "update_interval": 10,
            "gait_gate_enabled": True,
            "gait_gate_min_ep_len": 200.0,
            "log_interval": 100,
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

        # 제어 주파수: 25Hz (decimation=8, step_dt=0.04s)
        # 느린 주파수로 진동 보행을 물리적으로 차단
        self.decimation = 8
        
        # V20: Soft-Ramp 리워드 커리큘럼 (STAND→WALK→TROT)
        self.curriculum = SpotMicroRewardCurriculumCfg()

        # Body link names 수정 - SpotMicro의 "base_link"
        base_cfg = SceneEntityCfg("robot", body_names=["base_link"])

        # Events 수정
        self.events.add_base_mass.params["asset_cfg"] = base_cfg
        # SpotMicro is only 5.6kg, so perturbation must be small
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

        toe_contact_sensor_cfg = SceneEntityCfg("contact_forces", body_names=".*toe_link")
        toe_body_cfg = SceneEntityCfg("robot", body_names=".*toe_link")

        # Rewards - body_names 패턴 업데이트
        # feet_air_time: toe_link
        self.rewards.feet_air_time.params["sensor_cfg"] = toe_contact_sensor_cfg
        self.rewards.feet_air_time.params["threshold"] = 0.1
        
        # undesired_contacts: base_link, shoulder_link, leg_link
        self.rewards.undesired_contacts.params["sensor_cfg"] = SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link")

        # ============================================================
        # 보상 설정
        # ============================================================

        # V35.3: 매 step 생존 보상 — 초기 부팅 안정성 확보
        self.rewards.alive_bonus = RewTerm(
            func=custom_mdp.alive_bonus,
            weight=10.0,  # V35.4: 2.0→10.0 (penalty와 경쟁 가능한 수준)
        )

        # 속도 추적 (V15c: 전체 스케일 1/3 축소)
        self.rewards.track_lin_vel_xy_exp.weight = 1.0
        self.rewards.track_ang_vel_z_exp.weight = 1.5

        # V15c: 전진 속도 (뒷다리 게이팅 ONLY)
        self.rewards.forward_velocity = RewTerm(
            func=custom_mdp.forward_velocity_rear_gated,
            weight=8.0,  # V15c: 25→8 (스케일 축소, 뒷다리 필수 유지)
            params={
                "rear_joint_cfg": SceneEntityCfg("robot", joint_names=["rear_left_shoulder", "rear_right_shoulder", "rear_left_leg", "rear_right_leg", "rear_left_foot", "rear_right_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "target_vel": 0.5,
                "rear_gate_threshold": 0.15,
            },
        )
        # 부트스트랩: 비활성화
        self.rewards.forward_velocity_bootstrap = RewTerm(
            func=custom_mdp.forward_velocity_reward,
            weight=0.0,
            params={"asset_cfg": SceneEntityCfg("robot"), "target_vel": 0.5},
        )

        # 정지 페널티 (제자리 트로트용으로 비활성화)
        self.rewards.stationary_penalty = RewTerm(
            func=custom_mdp.stationary_penalty,
            weight=0.0,
            params={"asset_cfg": SceneEntityCfg("robot"), "threshold": 0.05},
        )

        # 안정성 페널티
        self.rewards.lin_vel_z_l2.weight = -2.0   # V29: -0.7 → -2.0 (수직 진동 억제 강화)
        self.rewards.ang_vel_xy_l2.weight = -1.0   # V29: -0.2 → -1.0 (몸통 흔들림 억제 강화)
        self.rewards.dof_torques_l2.weight = -3e-5
        self.rewards.dof_acc_l2.weight = -5e-6  # V17: -8e-8→-5e-6 (가속도 페널티 강화)
        # V17: 액션 변화율 페널티 대폭 강화 (빠른 떨림 물리적 차단)
        self.rewards.action_rate_l2 = RewTerm(
            func=custom_mdp.action_rate_l2_clamped,
            weight=-3.0,  # V17: -0.1→-3.0 (빠른 떨림 억제)
            params={"max_value": 50.0},
        )
        # V32: feet_air_time을 4발 공통 swing 유도의 핵심 보상으로 강화
        # legged_gym 표준: threshold=0.5, weight=1.0 (15개 보상 기준)
        # 우리: 50+ 보상이므로 weight를 높여야 경쟁 가능
        self.rewards.feet_air_time.weight = 30.0   # V17: 8.0 → V32: 30.0
        self.rewards.feet_air_time.params["threshold"] = 0.25  # V36: 0.3→0.25 (anti-shuffle, 체공 달성 용이)

        # V17: 관절 속도 억제 대폭 강화 (빠른 진동 차단)
        self.rewards.joint_vel_l2 = RewTerm(
            func=isaaclab_mdp.joint_vel_l2,
            weight=-0.5,  # V17: -0.02→-0.5 (관절 속도 억제 강화)
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # 수평 유지
        self.rewards.flat_orientation_l2.weight = -7.0

        # 높이 페널티
        self.rewards.base_height_l2 = RewTerm(
            func=isaaclab_mdp.base_height_l2,
            weight=-15.0,
            params={"target_height": 0.23, "asset_cfg": SceneEntityCfg("robot")}  # V36: 0.24→0.23 (anti-splay)
        )

        # 높이 + 수평 결합 보상
        self.rewards.standing_height = RewTerm(
            func=custom_mdp.standing_height_exp,
            weight=10.0,  # V16: 12→10 (총 스케일 조정)
            params={"target_height": 0.23, "sigma": 0.03,  # V36: 0.24→0.23 (anti-splay)
                    "asset_cfg": SceneEntityCfg("robot")}
        )

        # 무릎/배/어깨 접촉 페널티
        self.rewards.undesired_contacts.weight = -100.0

        # 무릎 높이 보상
        self.rewards.knee_height = RewTerm(
            func=custom_mdp.body_height_reward,
            weight=7.0,
            params={
                "target_height": 0.12,
                "penalty_below": 0.06,
                "asset_cfg": SceneEntityCfg("robot", body_names=".*leg_link"),
            }
        )

        # 관절 한계 접근 페널티
        self.rewards.dof_pos_limits = RewTerm(
            func=isaaclab_mdp.joint_pos_limits,
            weight=-7.0,
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # 발바닥 접지 보상 (걷기 시 비활성화)
        self.rewards.feet_on_ground = RewTerm(
            func=custom_mdp.all_feet_on_ground,
            weight=0.0,
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "threshold": 1.0,
            }
        )

        # 발이 무릎보다 높으면 페널티
        self.rewards.feet_below_knees = RewTerm(
            func=custom_mdp.feet_below_knees,
            weight=-150.0,
            params={
                "foot_cfg": toe_body_cfg,
                "knee_cfg": SceneEntityCfg("robot", body_names=".*leg_link"),
            }
        )

        # 앞/뒤 다리 대칭 (트로트에선 대각선 쌍이 반대이므로 비활성화)
        self.rewards.leg_pose_symmetry = RewTerm(
            func=custom_mdp.leg_pose_symmetry,
            weight=0.0,
            params={
                "front_leg_cfg": SceneEntityCfg("robot", joint_names=["front_left_leg", "front_left_foot", "front_right_leg", "front_right_foot"]),
                "rear_leg_cfg": SceneEntityCfg("robot", joint_names=["rear_left_leg", "rear_left_foot", "rear_right_leg", "rear_right_foot"]),
            }
        )

        # 어깨 대칭
        self.rewards.shoulder_symmetry = RewTerm(
            func=custom_mdp.shoulder_stance_symmetry,
            weight=-3.0,
            params={
                "front_shoulder_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder"]),
                "rear_shoulder_cfg": SceneEntityCfg("robot", joint_names=["rear_left_shoulder", "rear_right_shoulder"]),
            }
        )

        # V23: 어깨 기구학 타깃 재정렬
        # 어깨 roll축(X): 음수=바깥 벌림, phase-1은 과도한 splay를 줄인 posture-first 설정 사용
        self.rewards.shoulder_neutral = RewTerm(
            func=custom_mdp.shoulder_neutral_penalty,
            weight=-6.0,  # V36: -4.0→-6.0 (anti-splay)
            params={
                "shoulder_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder", "rear_left_shoulder", "rear_right_shoulder"]),
                "target_angles": [-0.04, -0.04, -0.04, -0.04],
            }
        )

        # V23: body-frame 기준 너무 넓은 stance 억제
        self.rewards.stance_width_penalty = RewTerm(
            func=custom_mdp.stance_width_penalty,
            weight=-3.0,  # V36: -2.5→-3.0 (anti-splay)
            params={
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "front_max_width": 0.19,
                "rear_max_width": 0.21,
                "tolerance": 0.05,
            },
        )

        # 높이 비례 보상
        self.rewards.height_bonus = RewTerm(
            func=custom_mdp.progressive_height_reward,
            weight=7.0,
            params={
                "min_height": 0.15,
                "max_height": 0.25,
                "asset_cfg": SceneEntityCfg("robot"),
            }
        )

        # 뒤집힘 종료 조건
        self.terminations.bad_orientation = DoneTerm(
            func=isaaclab_mdp.bad_orientation,
            params={"limit_angle": 1.5}  # ~86도
        )

        # V17: 발 높이 보상 (target_clearance 낮춤 — 6cm 보폭)
        self.rewards.foot_clearance = RewTerm(
            func=custom_mdp.foot_clearance_reward,
            weight=8.0,
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.06,  # V17: 0.12→0.06 (작은 로봇 현실적 보폭)
                "min_vel": 0.001,
            },
        )

        # V16: 트로트 걸음걸이 (강화 — 대각선 패턴 핵심)
        self.rewards.trot_gait = RewTerm(
            func=custom_mdp.trot_gait_reward,
            weight=40.0,  # V16: 30→40 (trot 패턴 강화)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,
            },
        )

        # V16: 비트로트 페널티 (강화)
        self.rewards.same_side_penalty = RewTerm(
            func=custom_mdp.same_side_penalty,
            weight=-30.0,  # V16: -20→-30 (비트로트 강력 억제)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,
            },
        )

        # 접촉 발 수 보상 (트로트 보상에 통합, 비활성화)
        self.rewards.contact_count = RewTerm(
            func=custom_mdp.gait_contact_count_reward,
            weight=0.0,
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
            },
        )

        # 스윙 보폭 보상
        self.rewards.swing_stride = RewTerm(
            func=custom_mdp.swing_stride_reward,
            weight=4.0,  # V36: 2.0→4.0 (anti-shuffle, 스윙 보폭 강화)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.001,
            },
        )

        # V16: 뒷발 스윙 보너스 (V32: feet_air_time이 공통 swing 유도하므로 축소)
        self.rewards.rear_swing = RewTerm(
            func=custom_mdp.rear_swing_bonus,
            weight=8.0,  # V32: 15→8 (feet_air_time 30.0이 주도, rear bias 축소)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.08,  # V15: 8cm 목표
                "min_vel": 0.05,
            },
        )

        # 기본 자세 편차 페널티
        self.rewards.joint_deviation = RewTerm(
            func=isaaclab_mdp.joint_deviation_l1,
            weight=-0.3,
            params={"asset_cfg": SceneEntityCfg("robot")},
        )

        # V16: leg 관절 들어올리기 (대각 커플링에 비중 분배)
        self.rewards.leg_lift = RewTerm(
            func=custom_mdp.leg_lift_reward,
            weight=15.0,  # V16: 20→15 (diagonal coupling이 보완)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "leg_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_leg", "front_right_leg", "rear_left_leg", "rear_right_leg"]),
                "target_angle": 0.6,  # ~34도
            },
        )

        # ============================================================
        # V15: 뒷다리 활성화 보상 (from-scratch 학습에 맞는 보수적 가중치)
        # ============================================================

        # V16: 뒷다리 관절 속도 보상 (V32: feet_air_time이 주도하므로 축소)
        self.rewards.rear_joint_velocity = RewTerm(
            func=custom_mdp.rear_joint_velocity_reward,
            weight=12.0,  # V32: 20→12 (rear bias 축소, feet_air_time이 4발 공통 유도)
            params={
                "rear_joint_cfg": SceneEntityCfg("robot", joint_names=["rear_left_shoulder", "rear_right_shoulder", "rear_left_leg", "rear_right_leg", "rear_left_foot", "rear_right_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "vel_threshold": 0.5,
                "min_vel": 0.05,
            },
        )

        # V16: 뒷다리 관절 동결 페널티 (강화)
        self.rewards.rear_joint_frozen = RewTerm(
            func=custom_mdp.rear_joint_frozen_penalty,
            weight=-60.0,  # V16: -40→-60 (뒷다리 동결 강력 처벌)
            params={
                "rear_joint_cfg": SceneEntityCfg("robot", joint_names=["rear_left_shoulder", "rear_right_shoulder", "rear_left_leg", "rear_right_leg", "rear_left_foot", "rear_right_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "frozen_threshold": 0.3,
                "min_vel": 0.05,
            },
        )

        # V16: 뒷다리 교대 보상 (V32: feet_air_time이 공통 swing 유도하므로 축소)
        self.rewards.rear_alternation = RewTerm(
            func=custom_mdp.rear_alternation_reward,
            weight=15.0,  # V32: 30→15 (feet_air_time이 4발 교대를 유도, rear 독점 축소)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )

        # V16: 뒷다리 동시 접지 페널티 (강화)
        self.rewards.rear_both_ground = RewTerm(
            func=custom_mdp.rear_both_ground_penalty,
            weight=-80.0,  # V16: -50→-80 (뒷다리 고정 강력 처벌)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )

        # V15: 뒷발 전방 보폭 보상
        self.rewards.rear_forward_stride = RewTerm(
            func=custom_mdp.rear_forward_stride_reward,
            weight=10.0,
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "target_clearance": 0.06,
                "target_fwd_vel": 0.3,
                "min_vel": 0.05,
            },
        )

        # V28 Layer B: Symmetric existence floor penalties (V27.1b보다 완화 — Layer C 공간 확보)
        self.rewards.limb_usage_min_penalty = RewTerm(
            func=custom_mdp.limb_usage_min_penalty,
            weight=-8.0,  # V28: initial -8, curriculum이 -25.0까지 ramp (V27.1b 동일)
            params={
                "min_usage": 0.10,
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.per_leg_contact_floor = RewTerm(
            func=custom_mdp.per_leg_contact_floor_penalty,
            weight=-1.0,  # V28: initial -1 (V27.1b: -2), curriculum이 -12.0까지 ramp (iter 0~200)
            params={
                "floor": 0.15,  # V27: 0.15 유지 — 완전 붕괴 방지 기준
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.per_leg_propulsion_floor = RewTerm(
            func=custom_mdp.per_leg_propulsion_floor_penalty,
            weight=-1.0,  # V28: initial -1 (V27.1b: -2), curriculum이 -10.0까지 ramp (iter 50~250)
            params={
                "floor": 0.10,  # V27: 0.10 유지 — fake contact 차단 기준
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V27: Propulsion-based load sharing (iter 50~150 ramp)
        # usage_diff 비활성, propulsion_diff 강화 (max_diff 0.40 → 0.25)
        self.rewards.rear_left_right_usage_diff_penalty = RewTerm(
            func=custom_mdp.rear_left_right_usage_diff_penalty,
            weight=0.0,  # V27.1a: load ramp initial — curriculum이 -10.0까지 ramp (iter 50~150)
            params={
                "max_diff": 0.30,  # V27.1a: 0.40→0.30 (더 엄격)
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.front_left_right_usage_diff_penalty = RewTerm(
            func=custom_mdp.front_left_right_usage_diff_penalty,
            weight=0.0,  # V27.1a: load ramp initial — curriculum이 -8.0까지 ramp (iter 50~150)
            params={
                "max_diff": 0.30,  # V27.1a: 0.40→0.30 (더 엄격)
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.rear_left_right_propulsion_diff_penalty = RewTerm(
            func=custom_mdp.rear_left_right_propulsion_diff_penalty,
            weight=0.0,  # load ramp initial — curriculum이 -20.0까지 ramp
            params={
                "max_diff": 0.25,  # V27: 0.25 (V26: 0.40) — 더 엄격한 편중 기준
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.front_rear_support_balance_penalty = RewTerm(
            func=custom_mdp.front_rear_support_balance_penalty,
            weight=-8.0,  # V31: -4.0 → -8.0 강화 (V30에서 -4.0은 -0.77에 불과)
            params={
                "max_diff": 0.15,   # V31: 0.25 → 0.15 (더 강한 gradient — front swing 보상이 안정성 보상)
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        # V27 신규: 앞다리 추진 편중 억제 + single-limb collapse 강제 패널티
        self.rewards.front_left_right_propulsion_diff_penalty = RewTerm(
            func=custom_mdp.front_left_right_propulsion_diff_penalty,
            weight=0.0,  # load ramp initial — curriculum이 -20.0까지 ramp
            params={
                "max_diff": 0.25,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.single_limb_validity_penalty = RewTerm(
            func=custom_mdp.single_limb_validity_penalty,
            weight=-5.0,  # V28: initial weight (curriculum이 -25.0까지 ramp, iter 0~250)
            params={
                "floor": 0.10,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V28 Layer C: Target-Band Incentive — "정상 범위에 들어와야 이득이 되는 구조"
        # band 수치는 V26 iter 200 실측 기반: contact [0.20~0.45], propulsion [0.15~0.38]
        self.rewards.per_leg_contact_target_band = RewTerm(
            func=custom_mdp.per_leg_contact_target_band_reward,
            weight=3.0,  # V29.2: 0.5 → 3.0 (RL/RR이 band 안에 있을 때 강한 양의 신호)
            params={
                "band_low": 0.20,
                "band_high": 0.65,  # V31: 0.75 → 0.65 (FL/FR이 내려와야 band 진입 가능)
                "band_ramp_start": 0.05,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.per_leg_propulsion_target_band = RewTerm(
            func=custom_mdp.per_leg_propulsion_target_band_reward,
            weight=0.5,  # V28: initial 0.5, curriculum이 4.0까지 ramp (iter 100~300)
            params={
                "band_low": 0.15,
                "band_high": 0.38,
                "band_ramp_start": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.limb_usage_target_band = RewTerm(
            func=custom_mdp.limb_usage_target_band_reward,
            weight=0.0,  # V28: initial 0, curriculum이 3.0까지 ramp (iter 200~450)
            params={
                "band_low": 0.20,
                "band_high": 0.45,
                "band_ramp_start": 0.05,
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.four_limb_cooperation = RewTerm(
            func=custom_mdp.four_limb_cooperation_reward,
            weight=0.0,  # V28: initial 0, curriculum이 8.0까지 ramp (iter 200~450)
            params={
                "contact_band_low": 0.20,
                "propulsion_band_low": 0.15,
                "trigger_partial": 2,   # band_hit >= 2 → 0.5x
                "trigger_full": 3,      # band_hit >= 3 → 1.0x
                "min_vel": 0.05,
                "min_leg_factor_low": 1.0,  # V28.1: curriculum이 0.2까지 ramp (iter 800~1000)
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V28.1: Band residency rewards (relay: early 600→800→1000, late 800→1000→유지)
        self.rewards.contact_residency = RewTerm(
            func=custom_mdp.per_leg_contact_band_residency_reward,
            weight=0.0,  # curriculum relay ramp으로 제어
            params={
                "band_low": 0.20,   # V29.2: 0.25 → 0.20 (RL/RR 에피소드 초반 band 진입 가능)
                "band_high": 0.70,  # V31: 0.85 → 0.70 (FL/FR 0.82가 band 밖 → 접지 줄이는 인센티브)
                "ema_alpha": 0.05,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.prop_residency = RewTerm(
            func=custom_mdp.per_leg_propulsion_band_residency_reward,
            weight=0.0,
            params={
                "band_low": 0.15,
                "band_high": 0.70,  # V29.2: 0.65 → 0.70 (FL/FR prop 0.64~0.66 포함)
                "ema_alpha": 0.05,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )
        self.rewards.usage_residency = RewTerm(
            func=custom_mdp.limb_usage_band_residency_reward,
            weight=0.0,
            params={
                "band_low": 0.20,
                "band_high": 0.65,  # V29 신규: 상한 추가
                "ema_alpha": 0.05,
                "contact_target": 0.5,
                "propulsion_target": 0.30,
                "leg_lift_target": 0.18,
                "clearance_target": 0.03,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V28.1: Rear pair residency symmetry penalty (iter 600~1000 ramp)
        self.rewards.rear_pair_residency_symmetry = RewTerm(
            func=custom_mdp.rear_pair_residency_symmetry_penalty,
            weight=0.0,  # curriculum이 -28.0까지 ramp (V28.2: -8→-28, iter 400~700)
            params={
                "min_diff": 0.05,
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V28.2: Late-phase band exit penalty 강화 (iter 600~900 ramp)
        self.rewards.late_phase_band_exit = RewTerm(
            func=custom_mdp.late_phase_band_exit_penalty,
            weight=0.0,  # curriculum이 -15.0까지 ramp (iter 600~900)
            params={
                "residency_floor": 0.50,  # 600~800 분석 기반 최소 기대 residency
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V29: swing_gate_velocity (신규, iter 600~900 ramp)
        self.rewards.swing_gate_velocity = RewTerm(
            func=custom_mdp.swing_quality_gated_velocity,
            weight=0.0,  # curriculum이 15.0까지 ramp (iter 600~900)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_swing_ratio": 0.15,
                "min_vel": 0.05,
            },
        )

        # V31: Front swing rewards (앞다리 swing 강제 — rear 보상의 대칭 버전)
        self.rewards.front_swing = RewTerm(
            func=custom_mdp.front_swing_bonus,
            weight=0.0,  # curriculum이 12.0까지 ramp (iter 100~400)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "target_clearance": 0.05,  # rear(0.08)보다 낮음 — 앞다리는 높이 들 필요 없음
                "min_vel": 0.05,
            },
        )
        self.rewards.front_alternation = RewTerm(
            func=custom_mdp.front_alternation_reward,
            weight=0.0,  # curriculum이 20.0까지 ramp (iter 100~400)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )
        self.rewards.front_both_ground = RewTerm(
            func=custom_mdp.front_both_ground_penalty,
            weight=0.0,  # curriculum이 -40.0까지 ramp (iter 100~400)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_vel": 0.05,
            },
        )
        self.rewards.min_swing_ratio = RewTerm(
            func=custom_mdp.min_swing_ratio_penalty,
            weight=0.0,  # curriculum이 -20.0까지 ramp (iter 100~400)
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "min_swing": 0.20,  # 최소 20% swing 필요
                "min_vel": 0.05,
            },
        )

        # V31.2: Front joint velocity reward (rear_joint_velocity 미러)
        self.rewards.front_joint_velocity = RewTerm(
            func=custom_mdp.front_joint_velocity_reward,
            weight=0.0,  # curriculum이 15.0까지 ramp (iter 100~400)
            params={
                "front_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder", "front_left_leg", "front_right_leg", "front_left_foot", "front_right_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "vel_threshold": 0.5,
                "min_vel": 0.05,
            },
        )
        # V31.2: Front joint frozen penalty (rear_joint_frozen 미러)
        self.rewards.front_joint_frozen = RewTerm(
            func=custom_mdp.front_joint_frozen_penalty,
            weight=0.0,  # curriculum이 -40.0까지 ramp (iter 100~400)
            params={
                "front_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_shoulder", "front_right_shoulder", "front_left_leg", "front_right_leg", "front_left_foot", "front_right_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "frozen_threshold": 0.3,
                "min_vel": 0.05,
            },
        )

        # V28.2: Rear pair contact diff penalty (신규, current-step, iter 300~600 ramp)
        self.rewards.rear_pair_contact_diff = RewTerm(
            func=custom_mdp.rear_pair_contact_diff_penalty,
            weight=0.0,  # curriculum이 -15.0까지 ramp (iter 300~600)
            params={
                "diff_threshold": 0.10,  # 단일 threshold (V28.3에서 2단계 검토)
                "min_vel": 0.05,
                "asset_cfg": SceneEntityCfg("robot"),
            },
        )

        # V15: foot 관절 과신전 페널티
        self.rewards.foot_extension = RewTerm(
            func=custom_mdp.foot_extension_penalty,
            weight=-10.0,
            params={
                "foot_joint_cfg": SceneEntityCfg("robot", joint_names=["front_left_foot", "front_right_foot", "rear_left_foot", "rear_right_foot"]),
                "max_angle": 1.5,
            },
        )

        # ============================================================
        # V27: 대각선 관절 커플링 보상 — contact+propulsion combined soft gate
        # V26: contact만 gate → fake contact 허용. V27: propulsion도 gate에 포함.
        # min_contact 0.15→0.25, min_propulsion 0.10 추가 → 더 강한 차단
        # ============================================================
        self.rewards.diagonal_coupling = RewTerm(
            func=custom_mdp.diagonal_coupling_soft_gate_reward,
            weight=25.0,
            params={
                "pair_a_front_cfg": SceneEntityCfg("robot", joint_names=["front_left_leg", "front_left_foot"]),
                "pair_a_rear_cfg": SceneEntityCfg("robot", joint_names=["rear_right_leg", "rear_right_foot"]),
                "pair_b_front_cfg": SceneEntityCfg("robot", joint_names=["front_right_leg", "front_right_foot"]),
                "pair_b_rear_cfg": SceneEntityCfg("robot", joint_names=["rear_left_leg", "rear_left_foot"]),
                "asset_cfg": SceneEntityCfg("robot"),
                "vel_deadzone": 0.1,
                "min_vel": 0.05,
                "min_contact": 0.10,    # V28: 0.15→0.10 (추가 완화 — locomotion signal 보호)
                "min_propulsion": 0.04,  # V28: 0.05→0.04
            },
        )

        # ============================================================
        # V17: 걸음걸이 주기 보상 — 0.3~0.5초 사이클 유도
        # 같은 발이 연속 접지하는 간격을 측정, 목표 범위에 있으면 보상
        # ============================================================
        self.rewards.gait_cycle_period = RewTerm(
            func=custom_mdp.gait_cycle_period_reward,
            weight=15.0,
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "target_period_min": 0.3,
                "target_period_max": 0.5,
                "min_vel": 0.05,
            },
        )

        # ============================================================
        # V17: 보폭 길이 보상 — 발 XY 변위 ≥6cm 유도
        # 스윙 중 발의 전방 이동 거리를 측정, 큰 보폭일수록 보상
        # ============================================================
        self.rewards.stride_length = RewTerm(
            func=custom_mdp.stride_length_reward,
            weight=0.0,  # V29: curriculum ramp으로 제어 (iter 400~700), phase weights 참고
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "target_stride": 0.10,  # V29: 0.06 → 0.10 (보폭 목표 확대)
                "min_vel": 0.05,
            },
        )

        # ============================================================
        # V18.3: 스탠스 추진 보상 — 바닥을 밀어서 동체를 앞으로 보내는 메커니즘 보상
        # 스탠스 중 발이 동체 대비 뒤로 밀리면 = 실제로 바닥을 밀고 있음 → 보상
        # ============================================================
        self.rewards.stance_propulsion = RewTerm(
            func=custom_mdp.stance_propulsion_reward,
            weight=8.0,  # Phase 1 기본값, 커리큘럼에서 Phase별 조정
            params={
                "sensor_cfg": toe_contact_sensor_cfg,
                "foot_cfg": toe_body_cfg,
                "asset_cfg": SceneEntityCfg("robot"),
                "contact_threshold": 1.0,
                "target_push_vel": 0.3,
                "min_vel": 0.05,
            },
        )

        # ============================================================
        # V18.2: 관절 과속 진동 페널티
        # 고속 미세진동(~20 rad/s)을 직접 억제하여 "벌레 걸음" 데드락 방지
        # ============================================================
        self.rewards.joint_oscillation = RewTerm(
            func=custom_mdp.excessive_joint_oscillation_penalty,
            weight=-5.0,  # Phase 1 기본값, 커리큘럼에서 Phase별 조정
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "max_vel_per_joint": 5.0,
            },
        )

        # Action scale
        self.actions.joint_pos.scale = 1.0

        # 에피소드 10초
        self.episode_length_s = 10.0

        # 속도 명령
        self.commands.base_velocity.rel_standing_envs = 0.0
        self.commands.base_velocity.rel_heading_envs = 1.0
        
        # V17: 속도 범위 확대 + 최소속도 도입 (정지 방지)
        self.commands.base_velocity.ranges.lin_vel_x = (0.1, 0.5)  # V17: (0,0.3)→(0.1,0.5)
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-0.5, 0.5)


# SpotMicro Flat Play (계단 지형 포함, height scanner 없음)
# observation 48차원 유지 (flat 모델과 호환)
@configclass
class SpotMicroFlatEnvCfg_PLAY(SpotMicroFlatEnvCfg):
    """플랫 모델을 계단 지형에서 테스트하는 설정."""
    def __post_init__(self):
        super().__post_init__()

        # 작은 씬
        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5

        # 지형: 아우와일드 계단 지형
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


# SpotMicro 러프 지형 환경
# SpotMicroFlatEnvCfg를 상속하고 지형/높이스케너/커리큐럼을 추가
@configclass
class SpotMicroRoughEnvCfg(SpotMicroFlatEnvCfg):
    """러프 지형 환경. Flat의 보상 함수를 유지하면서 지형/스케너/커리큐럼 추가."""
    def __post_init__(self):
        # Flat config의 모든 설정 적용
        super().__post_init__()

        # 지형: 러프
        self.scene.terrain.terrain_type = "generator"
        self.scene.terrain.terrain_generator = SPOT_MICRO_ROUGH_TERRAINS_CFG
        self.scene.terrain.max_init_terrain_level = 5

        # 높이 스케너
        self.scene.height_scanner = RayCasterCfg(
            prim_path="{ENV_REGEX_NS}/Robot/base_link",
            offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.0, 20.0)),
            ray_alignment="yaw",
            pattern_cfg=patterns.GridPatternCfg(resolution=0.1, size=[0.8, 0.5]),
            debug_vis=False,
            mesh_prim_paths=["/World/ground"],
        )
        # 높이 스케너 업데이트 주기
        self.scene.height_scanner.update_period = self.decimation * self.sim.dt

        # 관측: height_scan 활성화
        self.observations.policy.height_scan = ObsTerm(
            func=velocity_mdp.height_scan,
            params={"sensor_cfg": SceneEntityCfg("height_scanner")},
            noise=Unoise(n_min=-0.1, n_max=0.1),
            clip=(-1.0, 1.0),
        )

        # 커리큐럼: 지형 난이도 점진적 증가
        from isaaclab_tasks.manager_based.locomotion.velocity.velocity_env_cfg import CurriculumCfg
        self.curriculum = CurriculumCfg()

        # 러프 지형용 보상 조정 (Flat→Rough 가중치 오버라이드)
        # ============================================================
        # 높이: 지형 높낮이에 따른 변동 허용
        self.rewards.base_height_l2.weight = -30.0
        self.rewards.base_height_l2.params["target_height"] = 0.22
        self.rewards.standing_height.params["target_height"] = 0.22
        self.rewards.standing_height.params["sigma"] = 0.05
        self.rewards.standing_height.weight = 30.0

        # 수평 유지: 울퉁불퉁한 지형에서 약간의 기울어짐 허용
        self.rewards.flat_orientation_l2.weight = -15.0

        # 높이 비례 보상: 최소 높이 약간 낮춤
        self.rewards.height_bonus.params["min_height"] = 0.13

        # 관절 편차: 뒷다리 관절 움직임 허용을 위해 완화
        self.rewards.joint_deviation.weight = -1.5

        # 전진 속도: 러프 지형에서 더 큰 가중치
        self.rewards.forward_velocity.weight = 35.0
        # 부트스트랩 비활성화 (러프 전이 시점에는 이미 걷기 학습 완료)
        self.rewards.forward_velocity_bootstrap.weight = 0.0

        # 트로트 가중치 강화
        self.rewards.trot_gait.weight = 180.0

        # 발 높이 들기: target_clearance 조정
        self.rewards.foot_clearance.weight = 35.0
        self.rewards.foot_clearance.params["target_clearance"] = 0.10

        # 뒷발 스윙 강화
        self.rewards.rear_swing.weight = 80.0
        self.rewards.rear_swing.params["target_clearance"] = 0.10

        # 뒷다리 관절 속도/동결: 러프에서 더 강한 가중치
        self.rewards.rear_joint_velocity.weight = 60.0
        self.rewards.rear_joint_frozen.weight = -150.0

        # 스윙 보폭 강화
        self.rewards.swing_stride.weight = 50.0

        # 동일측 동기화 억제 강화
        self.rewards.same_side_penalty.weight = -120.0

        # 공중 시간 보상 (150ms 이상 유지해야 보상)
        self.rewards.feet_air_time.weight = 20.0
        self.rewards.feet_air_time.params["threshold"] = 0.15

        # 동작 부드러움 페널티: 러프에서 강화
        self.rewards.action_rate_l2 = RewTerm(
            func=custom_mdp.action_rate_l2_clamped,
            weight=-1.2,
            params={"max_value": 50.0},
        )

        # 뒷다리 교대/동시접지: 러프에서 강화 + 민감한 contact_threshold
        self.rewards.rear_alternation.weight = 150.0
        self.rewards.rear_alternation.params["contact_threshold"] = 0.1
        self.rewards.rear_both_ground.weight = -250.0
        self.rewards.rear_both_ground.params["contact_threshold"] = 0.1

        # 뒷발 전방 보폭: 러프에서 강화 + 파라미터 조정
        self.rewards.rear_forward_stride.weight = 120.0
        self.rewards.rear_forward_stride.params["contact_threshold"] = 0.1
        self.rewards.rear_forward_stride.params["target_clearance"] = 0.08
        self.rewards.rear_forward_stride.params["target_fwd_vel"] = 0.3

        # 러프 지형 전용 보상
        # ============================================================

        # 오르막 등반 보너스 (비활성화)
        self.rewards.uphill_bonus = RewTerm(
            func=custom_mdp.uphill_bonus,
            weight=0.0,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "min_vel": 0.05,
                "max_climb_rate": 0.03,
            },
        )

        # 지형 난이도 비례 보상
        self.rewards.terrain_progress = RewTerm(
            func=custom_mdp.terrain_progress_reward,
            weight=50.0,
            params={},
        )

        # 거리 보상: 멀리 걸을수록 보상 (커리큘럼 승급 유도)
        self.rewards.distance_walked = RewTerm(
            func=custom_mdp.distance_walked_reward,
            weight=30.0,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "target_distance": 2.5,
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
            params={"velocity_range": {"x": (-0.3, 0.3), "y": (-0.3, 0.3)}},
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


@configclass
class SpotMicroFlatOnSteepSlopePlayCfg(SpotMicroFlatEnvCfg):
    """Flat 모델을 급경사 지형에서 테스트하는 플레이 환경.
    
    관측 공간은 Flat과 동일 (48차원, height_scan 없음),
    하지만 지형은 급경사 오르막/내리막을 사용.
    """
    def __post_init__(self):
        super().__post_init__()

        # 급경사 지형 적용 (height_scan은 여전히 None)
        self.scene.terrain.terrain_type = "generator"
        self.scene.terrain.terrain_generator = SPOT_MICRO_STEEP_SLOPES_CFG
        self.scene.terrain.max_init_terrain_level = None

        # 플레이 설정
        self.scene.num_envs = 50
        self.scene.env_spacing = 2.5

        # 노이즈 비활성화
        self.observations.policy.enable_corruption = False
        # 외부 힘/푸시 비활성화
        self.events.base_external_force_torque = None
        self.events.push_robot = None
