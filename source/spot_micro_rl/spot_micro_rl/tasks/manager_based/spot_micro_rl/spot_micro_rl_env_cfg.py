# Copyright (c) 2022-2024, The Isaac Lab Project Developers.
# All rights reserved.

"""SpotMicro Environment Configuration (Flat + Rough)"""

# ── 훈련 버전 (Telegram/로그에 자동 표시, 코드 변경 시 여기만 수정) ──
TRAIN_VERSION = "V66"

# ── 기능 플래그 ──
# 새 버전: TRAIN_VERSION만 변경. 구조가 완전히 바뀔 때만 플래그 False.
#
# _CLEAN_REWARDS = 50개 reward → 15개 clean 구조 (V42에서 도입)
#   True:  50개 비활성화, 15~17개만 재정의, 8192 envs, phase clock, boot curriculum
#   False: 기존 50개 reward 그대로 (V41 이하)
#
# _CONNECTED_TROT = 서기→전진→걷기 순차 학습 커리큘럼 (V43에서 도입, _CLEAN_REWARDS 필요)
#   True:  per-leg propulsion gating, boot standing rewards, walking reward 순차 활성화,
#          adaptive pose safety (V43-D gating, V43-E boot standing, V44 adaptive safety)
#   False: V42 기본 independent reward (순차 학습 없음)
#
_CLEAN_REWARDS = False   # V47: V38.3 순정 reward 구조 사용
_CONNECTED_TROT = False  # V47: V43+ 구조 사용 안 함
_USE_BOOT_STANDING = True

_IS_V54 = TRAIN_VERSION.startswith("V54")
_IS_V55 = TRAIN_VERSION.startswith("V55")
_IS_V56 = TRAIN_VERSION.startswith("V56")
_IS_V57 = TRAIN_VERSION.startswith("V57")
_IS_V58 = TRAIN_VERSION.startswith("V58")
_IS_V59 = TRAIN_VERSION.startswith("V59")
_IS_V60 = TRAIN_VERSION.startswith("V60")
_IS_V61 = TRAIN_VERSION.startswith("V61")
_IS_V62 = TRAIN_VERSION.startswith("V62")
_IS_V63B = TRAIN_VERSION.startswith("V63.B")
_IS_V63C = TRAIN_VERSION.startswith("V63.C")
_IS_V63D = TRAIN_VERSION.startswith("V63.D")
_IS_V63E = TRAIN_VERSION.startswith("V63.E")
_IS_V63F = TRAIN_VERSION.startswith("V63.F")
_IS_V63G = TRAIN_VERSION.startswith("V63.G")
_IS_V63H = TRAIN_VERSION.startswith("V63.H")
_IS_V63I = TRAIN_VERSION.startswith("V63.I")
_IS_V63J = TRAIN_VERSION.startswith("V63.J")
_IS_V64 = TRAIN_VERSION.startswith("V64")
_IS_V65 = TRAIN_VERSION.startswith("V65")
_IS_V66 = TRAIN_VERSION.startswith("V66")
# V64/V65/V66는 V63.I 구조 위에 구축
if _IS_V64 or _IS_V65 or _IS_V66:
    _IS_V63I = True
# V63.J는 V63.I 구조를 물려받음 (per_leg_contact_min 0.40, stance_ratio_balance)
if _IS_V63J:
    _IS_V63I = True
# V63.I/J는 V63.H 구조를 그대로 물려받고 exploit 차단 reward만 추가
if _IS_V63I or _IS_V63J:
    _IS_V63H = True
# V63.B/C/D/E/F/G/H/I/J + V64 모두 V62 reward 구조를 베이스로 사용.
if _IS_V63B or _IS_V63C or _IS_V63D or _IS_V63E or _IS_V63F or _IS_V63G or _IS_V63H or _IS_V63I or _IS_V63J or _IS_V64 or _IS_V65 or _IS_V66:
    _IS_V62 = True
_V59_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V59 and "." in TRAIN_VERSION else ("A" if _IS_V59 else "")
_V60_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V60 and "." in TRAIN_VERSION else ("A" if _IS_V60 else "")
_V55_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V55 and "." in TRAIN_VERSION else ("A1" if _IS_V55 else "")
_V56_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V56 and "." in TRAIN_VERSION else ("M1" if _IS_V56 else "")
_V57_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V57 and "." in TRAIN_VERSION else ("A1" if _IS_V57 else "")
_V58_TRACK = TRAIN_VERSION.split(".", 1)[1] if _IS_V58 and "." in TRAIN_VERSION else ("A1" if _IS_V58 else "")
_V55_PHASE_TRACKS = {"B1", "B1.1", "B1.1A", "B1.1B", "B1.2", "B2", "B3"}
_V56_PHASE_TRACKS = {"M1"}

# V54: clean phase-centric handoff
# V55.A*: baseline recovery / release-shock ablations (phase OFF)
# V55.B*: baseline + phase auxiliary
# V56.M*: mechanics-first correction on top of validated phase coexistence baseline
_PHASE_CLOCK = _IS_V54 or (_IS_V55 and _V55_TRACK in _V55_PHASE_TRACKS) or (_IS_V56 and _V56_TRACK in _V56_PHASE_TRACKS)
_PHASE_AUXILIARY = (_IS_V55 and _V55_TRACK in _V55_PHASE_TRACKS) or (_IS_V56 and _V56_TRACK in _V56_PHASE_TRACKS)

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
            "coop_reward_final": 16.0,       # V52.1: 8→16 (4족 협동 보상 2배, net -1.80/step)
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
            # V38: anti-splay L2 ramp 고정 (CaT로 대체, weight escalation 중단)
            "splay_ramp_start": 500,               # ramp 구간 유지하되 initial==final
            "splay_ramp_end": 1500,
            "splay_shoulder_initial": -6.0,        # V37.2(-10) -> V38 고정(-6)
            "splay_shoulder_final": -6.0,          # 고정 — CaT가 splay 교정 담당
            "splay_stance_initial": -3.0,
            "splay_stance_final": -3.0,
            "splay_height_initial": 0.23,
            "splay_height_final": 0.23,
            # V38.3: Soft CaT (prob 3.75x — V38.2 too conservative)
            "cat_ramp_start": 800,
            "cat_ramp_end": 3000,
            "cat_threshold": 0.3,
            "cat_margin": 0.3,
            "cat_probability_final": 0.002,  # V40-A2: 0.003→0.002 (sweet spot 탐색)
            "update_interval": 10,
            "gait_gate_enabled": True,
            "gait_gate_min_ep_len": 200.0,  # 원래 값 유지 (ep_len 기반)
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

        # V39 phase clock 제거 — V40은 V38.3 구성 복귀 (observation 48차원)

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
        self.rewards.pitch_ang_vel_l2 = RewTerm(
            func=custom_mdp.pitch_ang_vel_l2,
            weight=0.0,
            params={"asset_cfg": SceneEntityCfg("robot"), "min_vel": 0.05},
        )
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

        # 높이 페널티 — V50: -15→-20 (walking phase에서도 높이 유지 강화)
        self.rewards.base_height_l2 = RewTerm(
            func=isaaclab_mdp.base_height_l2,
            weight=-20.0,
            params={"target_height": 0.23, "asset_cfg": SceneEntityCfg("robot")}
        )

        # 높이 + 수평 결합 보상 — V50: 10→15 (walking phase 높이 positive gradient 강화)
        self.rewards.standing_height = RewTerm(
            func=custom_mdp.standing_height_exp,
            weight=15.0,
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
            weight=-1.5,  # V52.1: -3.0→-1.5 (앞다리 사용 시 penalty 과다 방지, shoulder_neutral이 splay 보조)
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

        # V52: 최소 높이 termination — 엎드리기/크롤링 전략 차단
        self.terminations.min_height = DoneTerm(
            func=custom_mdp.min_height_termination,
            params={
                "asset_cfg": SceneEntityCfg("robot"),
                "min_height": 0.15,  # init(0.22)에서 70mm 여유, 정상 보행 진동 안전
            },
        )

        # V38.2: Soft CaT — 종료 확률이 splay deviation에 비례
        self.terminations.shoulder_splay = DoneTerm(
            func=custom_mdp.shoulder_splay_termination,
            params={
                "shoulder_cfg": SceneEntityCfg("robot", joint_names=[
                    "front_left_shoulder", "front_right_shoulder",
                    "rear_left_shoulder", "rear_right_shoulder",
                ]),
                "target_angles": [-0.04, -0.04, -0.04, -0.04],
                "threshold": 0.3,
                "margin": 0.3,
                "probability": 0.0,  # curriculum ramp controls this
            },
        )

        # V39 phase_contact 제거 — V40은 CaT prob 단일 변수 실험

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
            weight=20.0,  # V52.1: 15→20 (앞다리 lift 보상 강화, net -1.80/step)
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

        # ══════════════════════════════════════════════════════════
        # Boot Standing: 높이+자세 gradient reward (V47에서 검증)
        # 플래그 _USE_BOOT_STANDING으로 제어 (버전 문자열 하드코딩 제거)
        # ══════════════════════════════════════════════════════════
        if _USE_BOOT_STANDING:
            toe_cfg_boot = SceneEntityCfg("contact_forces", body_names=".*toe_link")

            # boot_standing_reward: 높이 + 자세 gradient (V43-E에서 검증)
            self.rewards.boot_standing = RewTerm(
                func=custom_mdp.boot_standing_reward,
                weight=15.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "target_height": 0.23,
                    "height_k": 500.0,  # V50.1: 100→500 (높이 gradient 강화)
                },
            )
            # boot_foot_contact: 4발 접지율 (V43-E에서 검증)
            self.rewards.boot_contact = RewTerm(
                func=custom_mdp.boot_foot_contact,
                weight=5.0,
                params={
                    "sensor_cfg": toe_cfg_boot,
                    "contact_threshold": 1.0,
                },
            )

            # 기존 reward_weight_curriculum에 boot ramp-down 파라미터 추가
            # V50.2: boot_standing은 floor까지만 감소 (walking phase에서도 높이 압력 유지)
            self.curriculum.reward_weights.params["boot_standing_initial"] = 20.0
            self.curriculum.reward_weights.params["boot_standing_floor"] = 10.0   # V50.2: walking 대비 ~16% 높이 압력 상시 유지
            self.curriculum.reward_weights.params["boot_contact_initial"] = 5.0
            self.curriculum.reward_weights.params["boot_ramp_down_iters"] = 1500

        # ══════════════════════════════════════════════════════════
        # V55: baseline recovery / phase probe 공통 설정
        # A1: baseline recovery
        # B1/B2/B3: baseline + phase auxiliary (handoff 없음)
        # ══════════════════════════════════════════════════════════
        if _IS_V55:
            self.curriculum.reward_weights.params["v55_track"] = _V55_TRACK
            if _V55_TRACK == "A5.5":
                # A5.5: keep A5.4 behavior, but relax min_height termination first
                # to test whether min_height is a collapse amplifier at gait_gate release.
                self.terminations.min_height.params["min_height"] = 0.12
            elif _V55_TRACK in {"A5.6", "A6", "B1", "B1.1", "B1.1A", "B1.1B", "B1.2", "B2", "B3"}:
                # A5.6: same as A5.5, but lower the threshold one more step to see
                # whether release-collapse depth and recovery improve further.
                self.terminations.min_height.params["min_height"] = 0.10
            if _V55_TRACK in {"A5.3", "A5.4", "A7"}:
                # A5.3/A5.4/A7: STAND에서는 legacy phase table의 보수적 forward(2/8)를 사용하고,
                # gait_gate release 이후에만 16/12로 점진 ramp 한다.
                self.curriculum.reward_weights.params["v55_release_forward_ramp_iters"] = 500
                self.curriculum.reward_weights.params["v55_release_forward_velocity_pre"] = 2.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_post"] = 16.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_pre"] = 8.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_post"] = 12.0
            elif _V55_TRACK in {"A5.5", "A5.6", "A6", "B1", "B1.1", "B1.1A", "B1.1B", "B1.2", "B2", "B3"}:
                self.curriculum.reward_weights.params["v55_release_forward_ramp_iters"] = 500
                self.curriculum.reward_weights.params["v55_release_forward_velocity_pre"] = 2.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_post"] = 16.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_pre"] = 8.0
                self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_post"] = 12.0
            else:
                self.rewards.forward_velocity.weight = 16.0
                self.rewards.forward_velocity_bootstrap.weight = 12.0
                self.curriculum.reward_weights.params["v55_forward_velocity_weight"] = 16.0
                self.curriculum.reward_weights.params["v55_forward_velocity_bootstrap_weight"] = 12.0

            # V55에서는 V54 handoff를 쓰지 않는다.
            self.curriculum.reward_weights.params["phase_contact_target"] = 0.0
            self.curriculum.reward_weights.params["phase_clearance_target"] = 0.0
            self.curriculum.reward_weights.params["phase_ramp_in_iters"] = 0
            self.curriculum.reward_weights.params["phase_table_enabled"] = True

            if _V55_TRACK == "A5.1":
                # A5.1: keep A5 baseline, but soften the iter-500 gait-gate shock
                # only for the two directly observed posture/splay shock sources.
                self.curriculum.reward_weights.params["v55_release_soft_ramp_iters"] = 500
                self.curriculum.reward_weights.params["v55_release_shoulder_neutral_pre"] = -1.0
                self.curriculum.reward_weights.params["v55_release_shoulder_neutral_post"] = -6.0
                self.curriculum.reward_weights.params["v55_release_stance_width_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_stance_width_post"] = -3.0

            elif _V55_TRACK in {"A5.2", "A5.4", "A5.5", "A5.6", "A6", "B1", "B1.1", "B2", "B3"}:
                # A5.2: expand release-shock mitigation to the next most likely
                # gait-gate jump group while preserving the A5 baseline core.
                # A5.4: keep the same 7-term release soft-ramp, but combine it with
                # the conservative STAND forward policy + post-release forward ramp.
                # A5.5: keep A5.4 and only relax min_height termination to test
                # whether it is the collapse amplifier at iter-500 release.
                # A5.6: keep A5.5 and lower min_height one more step (0.12 -> 0.10).
                # A6: keep A5.6, but make the posture/usage gate slightly stricter
                # before B1 so RL floor-lock and shoulder_splay can be reduced first.
                # B1/B2/B3: inherit the same release soft-ramp baseline so phase
                # effects are tested on top of the A6-quality baseline rather than
                # a reverted A5-era baseline.
                self.curriculum.reward_weights.params["v55_release_soft_ramp_iters"] = 500
                self.curriculum.reward_weights.params["v55_release_shoulder_neutral_pre"] = -1.0
                self.curriculum.reward_weights.params["v55_release_shoulder_neutral_post"] = (
                    -10.0 if _V55_TRACK == "B1.1B" else
                    -9.0 if _V55_TRACK in {"B1.1", "B1.1A", "B1.2", "B2"} else
                    -8.0 if _V55_TRACK in {"A6", "B1", "B3"} else
                    -6.0
                )
                self.curriculum.reward_weights.params["v55_release_stance_width_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_stance_width_post"] = (
                    -5.0 if _V55_TRACK == "B1.1B" else
                    -4.5 if _V55_TRACK in {"B1.1", "B1.1A", "B1.2", "B2"} else
                    -4.0 if _V55_TRACK in {"A6", "B1", "B3"} else
                    -3.0
                )
                self.curriculum.reward_weights.params["v55_release_rear_prop_diff_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_rear_prop_diff_post"] = -20.0
                self.curriculum.reward_weights.params["v55_release_front_prop_diff_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_front_prop_diff_post"] = -20.0
                self.curriculum.reward_weights.params["v55_release_rear_usage_diff_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_rear_usage_diff_post"] = -10.0
                self.curriculum.reward_weights.params["v55_release_front_usage_diff_pre"] = 0.0
                self.curriculum.reward_weights.params["v55_release_front_usage_diff_post"] = -8.0
                self.curriculum.reward_weights.params["v55_release_per_leg_contact_floor_pre"] = -1.0
                self.curriculum.reward_weights.params["v55_release_per_leg_contact_floor_post"] = -12.0
                if _V55_TRACK == "B2":
                    self.curriculum.reward_weights.params["v55_trot_gait_weight"] = 2.0
                    self.curriculum.reward_weights.params["v55_diagonal_coupling_weight"] = 2.0
                    self.curriculum.reward_weights.params["v55_stance_propulsion_weight"] = 6.0

            if _V55_TRACK in {"A6", "B1", "B1.1", "B1.1A", "B1.1B", "B1.2", "B2", "B3"}:
                # A6: posture-first correction before B1 entry.
                # Keep the A5.6 release behavior, but slightly strengthen
                # height/support pressure so RL floor-lock and shoulder_splay
                # can improve without directly forcing extra limb-usage penalties.
                # B1/B2/B3 inherit the same baseline gate so phase is evaluated
                # on top of the improved A6-quality baseline.
                self.rewards.base_height_l2.weight = -23.0
                self.rewards.front_rear_support_balance_penalty.weight = (
                    -11.5 if _V55_TRACK == "B1.1B" else
                    -10.5 if _V55_TRACK in {"B1.1", "B1.1A", "B1.2", "B2"} else
                    -9.6
                )

            if _V55_TRACK in {"B1", "B1.1"}:
                # B1: additive probe. Baseline structure는 최대한 유지하고 phase를 약하게 추가한다.
                # B1.1: keep the same weak probe, but tighten only the posture gate
                # to reduce shoulder_splay/front-heavy drift without changing phase strength.
                self.rewards.trot_gait.weight = 5.0
                self.rewards.diagonal_coupling.weight = 5.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 20.0
                self.rewards.leg_lift.weight = 20.0
                self.rewards.rear_alternation.weight = 15.0
                self.rewards.rear_joint_velocity.weight = 12.0
                self.rewards.stance_propulsion.weight = 8.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 6.0
                phase_contact_weight = 1.5
                phase_clearance_weight = 0.5
            elif _V55_TRACK == "B2":
                # B2: soft replacement. 기존 구조축은 약하게 남기고 phase 비중을 올린다.
                self.rewards.trot_gait.weight = 2.0
                self.rewards.diagonal_coupling.weight = 2.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 15.0
                self.rewards.leg_lift.weight = 12.0
                self.rewards.rear_alternation.weight = 8.0
                self.rewards.rear_joint_velocity.weight = 8.0
                self.rewards.stance_propulsion.weight = 6.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 4.0
                phase_contact_weight = 3.0
                phase_clearance_weight = 1.0
            elif _V55_TRACK == "B1.1A":
                # B1.1A: middle coexistence test. Keep B1.1 heuristic strength
                # and posture gate, and raise phase only to 2.0 / 0.75 first.
                self.rewards.trot_gait.weight = 5.0
                self.rewards.diagonal_coupling.weight = 5.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 20.0
                self.rewards.leg_lift.weight = 20.0
                self.rewards.rear_alternation.weight = 15.0
                self.rewards.rear_joint_velocity.weight = 12.0
                self.rewards.stance_propulsion.weight = 8.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 6.0
                phase_contact_weight = 2.0
                phase_clearance_weight = 0.75
            elif _V55_TRACK == "B1.1B":
                # B1.1B: keep B1.1A phase strength, and tighten only the posture gate
                # one more step to suppress late shoulder_splay drift.
                self.rewards.trot_gait.weight = 5.0
                self.rewards.diagonal_coupling.weight = 5.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 20.0
                self.rewards.leg_lift.weight = 20.0
                self.rewards.rear_alternation.weight = 15.0
                self.rewards.rear_joint_velocity.weight = 12.0
                self.rewards.stance_propulsion.weight = 8.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 6.0
                phase_contact_weight = 2.0
                phase_clearance_weight = 0.75
            elif _V55_TRACK == "B1.2":
                # B1.2: phase 3.0 coexistence test. Keep B1.1 heuristic strength
                # and posture gate, and only raise phase to the B2 level.
                self.rewards.trot_gait.weight = 5.0
                self.rewards.diagonal_coupling.weight = 5.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 20.0
                self.rewards.leg_lift.weight = 20.0
                self.rewards.rear_alternation.weight = 15.0
                self.rewards.rear_joint_velocity.weight = 12.0
                self.rewards.stance_propulsion.weight = 8.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 6.0
                phase_contact_weight = 3.0
                phase_clearance_weight = 1.0
            elif _V55_TRACK == "B3":
                # B3: hard phase test. phase가 주도권을 가지도록 직접 heuristic을 크게 줄인다.
                self.rewards.trot_gait.weight = 0.0
                self.rewards.diagonal_coupling.weight = 0.0
                self.rewards.gait_cycle_period.weight = 0.0
                self.rewards.feet_air_time.weight = 10.0
                self.rewards.leg_lift.weight = 8.0
                self.rewards.rear_alternation.weight = 5.0
                self.rewards.rear_joint_velocity.weight = 4.0
                self.rewards.stance_propulsion.weight = 4.0
                self.rewards.foot_clearance.weight = 2.0
                self.rewards.rear_swing.weight = 3.0
                phase_contact_weight = 5.0
                phase_clearance_weight = 1.5
            else:
                phase_contact_weight = 0.0
                phase_clearance_weight = 0.0
        elif _IS_V56:
            # V56.M1: keep the validated B1.1B coexistence baseline fixed,
            # and add only a direct pitch angular-velocity penalty.
            self.curriculum.reward_weights.params["v55_track"] = _V56_TRACK
            self.terminations.min_height.params["min_height"] = 0.10

            self.curriculum.reward_weights.params["v55_release_forward_ramp_iters"] = 500
            self.curriculum.reward_weights.params["v55_release_forward_velocity_pre"] = 2.0
            self.curriculum.reward_weights.params["v55_release_forward_velocity_post"] = 16.0
            self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_pre"] = 8.0
            self.curriculum.reward_weights.params["v55_release_forward_velocity_bootstrap_post"] = 12.0

            self.curriculum.reward_weights.params["phase_contact_target"] = 0.0
            self.curriculum.reward_weights.params["phase_clearance_target"] = 0.0
            self.curriculum.reward_weights.params["phase_ramp_in_iters"] = 0
            self.curriculum.reward_weights.params["phase_table_enabled"] = True

            self.curriculum.reward_weights.params["v55_release_soft_ramp_iters"] = 500
            self.curriculum.reward_weights.params["v55_release_shoulder_neutral_pre"] = -1.0
            self.curriculum.reward_weights.params["v55_release_shoulder_neutral_post"] = -10.0
            self.curriculum.reward_weights.params["v55_release_stance_width_pre"] = 0.0
            self.curriculum.reward_weights.params["v55_release_stance_width_post"] = -5.0
            self.curriculum.reward_weights.params["v55_release_rear_prop_diff_pre"] = 0.0
            self.curriculum.reward_weights.params["v55_release_rear_prop_diff_post"] = -20.0
            self.curriculum.reward_weights.params["v55_release_front_prop_diff_pre"] = 0.0
            self.curriculum.reward_weights.params["v55_release_front_prop_diff_post"] = -20.0
            self.curriculum.reward_weights.params["v55_release_rear_usage_diff_pre"] = 0.0
            self.curriculum.reward_weights.params["v55_release_rear_usage_diff_post"] = -10.0
            self.curriculum.reward_weights.params["v55_release_front_usage_diff_pre"] = 0.0
            self.curriculum.reward_weights.params["v55_release_front_usage_diff_post"] = -8.0
            self.curriculum.reward_weights.params["v55_release_per_leg_contact_floor_pre"] = -1.0
            self.curriculum.reward_weights.params["v55_release_per_leg_contact_floor_post"] = -12.0

            self.rewards.base_height_l2.weight = -23.0
            self.rewards.front_rear_support_balance_penalty.weight = -11.5
            self.rewards.pitch_ang_vel_l2.weight = -2.0

            self.rewards.trot_gait.weight = 5.0
            self.rewards.diagonal_coupling.weight = 5.0
            self.rewards.gait_cycle_period.weight = 0.0
            self.rewards.feet_air_time.weight = 20.0
            self.rewards.leg_lift.weight = 20.0
            self.rewards.rear_alternation.weight = 15.0
            self.rewards.rear_joint_velocity.weight = 12.0
            self.rewards.stance_propulsion.weight = 8.0
            self.rewards.foot_clearance.weight = 2.0
            self.rewards.rear_swing.weight = 6.0
            phase_contact_weight = 2.0
            phase_clearance_weight = 0.75
        else:
            phase_contact_weight = 0.0
            phase_clearance_weight = 0.0

        # ══════════════════════════════════════════════════════════
        # V54: Phase Clock 기반 구조 전환
        # phase_contact(주연) + phase_clearance + velocity tracking
        # 충돌 gait reward 비활성화 → ~17개 reward
        # ══════════════════════════════════════════════════════════
        if _PHASE_CLOCK:
            toe_cfg_phase = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_body_cfg_phase = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── Phase Clock ──
            self.rewards.phase_contact = RewTerm(
                func=custom_mdp.phase_contact_reward,
                weight=phase_contact_weight,
                params={
                    "sensor_cfg": toe_cfg_phase,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "contact_threshold": 1.0,
                    "standing_vel_threshold": 0.08,
                    "aggregation_mode": "mean_min" if _PHASE_AUXILIARY else "floor",
                    "ema_alpha": 0.90,
                    "min_target": 0.60,
                },
            )
            self.rewards.phase_clearance = RewTerm(
                func=custom_mdp.phase_foot_clearance,
                weight=phase_clearance_weight,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "foot_cfg": foot_body_cfg_phase,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "target_clearance": 0.04,
                    "standing_vel_threshold": 0.08,
                },
            )

            # ── Phase Clock observation ──
            self.observations.policy.phase_clock = ObsTerm(
                func=custom_mdp.phase_clock_obs,
                params={"frequency": 2.0},
            )

            # ── V55: baseline ecology 유지 + phase auxiliary만 추가 ──
            if _PHASE_AUXILIARY:
                pass
            else:
                # ── Velocity Tracking (phase 보조) ──
                self.rewards.track_lin_vel_xy_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.weight = 3.0

                # ── 자세/높이 (V50+ 검증 유지) ──
                self.rewards.standing_height.weight = 15.0
                self.rewards.flat_orientation_l2.weight = -8.0
                self.rewards.base_height_l2.weight = -15.0

                # ── Penalty 축소 (V52 실측: movement penalty 14.36/step 과도) ──
                self.rewards.action_rate_l2.weight = -0.3
                self.rewards.dof_acc_l2.weight = -2.0e-5
                self.rewards.joint_vel_l2.weight = -0.1
                self.rewards.shoulder_neutral.weight = -4.0
                self.rewards.stance_width_penalty.weight = -1.5

                # ── Minimal Bridge: outcome-based, phase와 비충돌 ──
                self.rewards.stride_length.weight = 5.0
                self.rewards.forward_velocity_bootstrap.weight = 5.0

                # ── Boot-only Bridge / soft handoff ──
                self.curriculum.reward_weights.params["boot_leg_lift_initial"] = 15.0
                self.curriculum.reward_weights.params["boot_rear_vel_initial"] = 12.0
                self.curriculum.reward_weights.params["boot_bridge_ramp_down_iters"] = 500
                self.curriculum.reward_weights.params["phase_contact_target"] = 20.0
                self.curriculum.reward_weights.params["phase_clearance_target"] = 5.0
                self.curriculum.reward_weights.params["phase_ramp_in_iters"] = 500
                self.curriculum.reward_weights.params["phase_table_enabled"] = False
                self.curriculum.reward_weights.params["stride_length_max"] = 0.0
                self.curriculum.reward_weights.params["swing_gate_max"] = 0.0
                self.curriculum.reward_weights.params["front_swing_bonus_max"] = 0.0
                self.curriculum.reward_weights.params["front_alternation_max"] = 0.0
                self.curriculum.reward_weights.params["front_both_ground_max"] = 0.0
                self.curriculum.reward_weights.params["min_swing_ratio_max"] = 0.0
                self.curriculum.reward_weights.params["front_joint_velocity_max"] = 0.0
                self.curriculum.reward_weights.params["front_joint_frozen_max"] = 0.0

                # ── 충돌 gait reward 비활성화 ──
                _phase_remove = [
                    "per_leg_contact_target_band", "per_leg_propulsion_target_band",
                    "limb_usage_target_band", "late_phase_band_exit",
                    "per_leg_contact_floor", "per_leg_propulsion_floor",
                    "contact_residency", "usage_residency", "prop_residency",
                    "rear_pair_residency_symmetry", "rear_pair_residency_gap",
                    "residency_ema_contact_fl", "residency_ema_contact_fr",
                    "residency_ema_contact_rl", "residency_ema_contact_rr",
                    "residency_ema_prop_rl", "residency_ema_prop_rr",
                    "diagonal_coupling", "trot_gait", "gait_cycle_period",
                    "front_leg_lift", "rear_alternation", "rear_swing",
                    "rear_forward_stride",
                    "swing_stride", "swing_gate_velocity",
                    "forward_velocity",
                    "four_limb_cooperation", "front_rear_symmetry",
                    "front_rear_support_balance_penalty",
                    "front_left_right_propulsion_diff_penalty",
                    "front_left_right_usage_diff_penalty",
                    "rear_left_right_propulsion_diff_penalty",
                    "rear_left_right_usage_diff_penalty",
                    "limb_usage_min_penalty", "single_limb_validity_penalty",
                    "rear_pair_contact_diff",
                    "feet_air_time", "foot_clearance",
                    "height_walking_gate", "height_bonus", "knee_height",
                    "front_swing", "front_alternation",
                    "front_joint_velocity", "front_joint_frozen",
                    "rear_joint_frozen", "rear_both_ground", "front_both_ground",
                    "min_swing_ratio", "stationary_penalty",
                    "leg_pose_symmetry", "same_side_penalty",
                    "feet_below_knees", "feet_on_ground",
                    "shoulder_symmetry", "foot_extension",
                    "stance_propulsion",
                ]
                for name in _phase_remove:
                    if hasattr(self.rewards, name):
                        setattr(self.rewards, name, None)

        # ══════════════════════════════════════════════════════════
        # V42: Clean Reward Restart — 16개 reward만 사용
        # 기존 50+ reward 전부 비활성화 후 16개만 설정
        # ══════════════════════════════════════════════════════════
        if _CLEAN_REWARDS:
            # num_envs 8192 (탐색 다양성)
            self.scene.num_envs = 8192

            # Phase clock observation 복원 (8-dim)
            self.observations.policy.phase_clock = ObsTerm(
                func=custom_mdp.phase_clock_obs,
                params={"frequency": 2.0},
            )

            # CaT DoneTerm 제거
            self.terminations.shoulder_splay = None

            # ── 기존 reward 전부 비활성화 ──
            for attr in list(vars(self.rewards).keys()):
                if not attr.startswith('_'):
                    try:
                        setattr(self.rewards, attr, None)
                    except Exception:
                        pass

            toe_contact_cfg = SceneEntityCfg("contact_forces", body_names=".*toe_link")

            # ── V42 reward: 16개만 설정 ──

            # [생존/안정] 4개
            self.rewards.alive_bonus = RewTerm(
                func=custom_mdp.alive_bonus, weight=10.0,
            )
            self.rewards.base_height_l2 = RewTerm(
                func=velocity_mdp.base_height_l2,
                weight=-15.0,
                params={"asset_cfg": SceneEntityCfg("robot"), "target_height": 0.23},
            )
            self.rewards.flat_orientation_l2 = RewTerm(
                func=velocity_mdp.flat_orientation_l2,
                weight=-7.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.undesired_contacts = RewTerm(
                func=velocity_mdp.undesired_contacts,
                weight=-100.0,
                params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link"), "threshold": 1.0},
            )

            # [전진/추진] 3개
            self.rewards.forward_velocity = RewTerm(
                func=custom_mdp.forward_velocity_reward,
                weight=8.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.track_lin_vel_xy_exp = RewTerm(
                func=velocity_mdp.track_lin_vel_xy_exp,
                weight=1.0,
                params={"command_name": "base_velocity", "std": 0.5},
            )
            self.rewards.track_ang_vel_z_exp = RewTerm(
                func=velocity_mdp.track_ang_vel_z_exp,
                weight=0.5,
                params={"command_name": "base_velocity", "std": 0.5},
            )

            # [Gait 패턴] 4개
            self.rewards.feet_air_time = RewTerm(
                func=velocity_mdp.feet_air_time,
                weight=20.0,
                params={"sensor_cfg": toe_contact_cfg, "command_name": "base_velocity", "threshold": 0.25},
            )
            self.rewards.gait_phase = RewTerm(
                func=custom_mdp.phase_contact_reward,
                weight=15.0,
                params={"sensor_cfg": toe_contact_cfg, "frequency": 2.0, "duty_factor": 0.5, "contact_threshold": 1.0},
            )
            self.rewards.diagonal_coupling = RewTerm(
                func=custom_mdp.diagonal_joint_coupling_reward,
                weight=10.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.stride_length = RewTerm(
                func=custom_mdp.stride_length_reward,
                weight=5.0,
                params={"sensor_cfg": toe_contact_cfg, "asset_cfg": SceneEntityCfg("robot"), "min_vel": 0.05},
            )

            # [정규화] 5개
            self.rewards.action_rate_l2 = RewTerm(
                func=velocity_mdp.action_rate_l2, weight=-0.5,
            )
            self.rewards.dof_acc_l2 = RewTerm(
                func=velocity_mdp.joint_acc_l2, weight=-0.001,
            )
            self.rewards.joint_vel_l2 = RewTerm(
                func=isaaclab_mdp.joint_vel_l2,
                weight=-0.05,
            )
            self.rewards.dof_pos_limits = RewTerm(
                func=velocity_mdp.joint_pos_limits,
                weight=-5.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.joint_default_pose = RewTerm(
                func=velocity_mdp.joint_deviation_l1,
                weight=-0.5,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )

            # ── V43-D: 5-Phase Boot-First Curriculum ──
            # Phase 1 (0~300): Boot only — contacts ramp + velocity ramp, walking reward OFF
            # Phase 2 (300~800): Direction — forward_velocity + stance_propulsion ramp
            # Phase 3 (500~1500): Propulsion gating — gate_alpha 0→1
            # Phase 4 (800~2000): Walking — gait_phase + stride_length ramp
            # Phase 5 (1000~2500): Refinement — feet_air_time ramp + pose -0.3→-2.0
            self.rewards.curriculum = RewTerm(
                func=custom_mdp.v42_boot_curriculum,
                weight=1.0,
                params={
                    "boot_ramp_end": 300,
                    "boot_contact_initial": -20.0,
                    "boot_contact_final": -100.0,
                    "boot_vel_low_initial": 0.01,
                    "boot_vel_high_initial": 0.05,
                    "boot_vel_low_final": 0.1,
                    "boot_vel_high_final": 0.5,
                    "gate_ramp_start": 500,
                    "gate_ramp_end": 1500,
                    "pose_ramp_start": 0,
                    "pose_ramp_end": 0,
                    "pose_weight_initial": -3.0,
                    "pose_weight_final": -3.0,
                    "walk_ramp_config": {
                        "forward_velocity":    {"target": 8.0,  "start": 300,  "end": 800},
                        "stance_propulsion":   {"target": 8.0,  "start": 300,  "end": 800},
                        "diagonal_coupling":   {"target": 10.0, "start": 800,  "end": 2000},
                        "gait_phase":          {"target": 15.0, "start": 800,  "end": 2000},
                        "stride_length":       {"target": 5.0,  "start": 800,  "end": 2000},
                        "leg_lift":            {"target": 15.0, "start": 800,  "end": 2000},
                        "rear_alternation":    {"target": 15.0, "start": 800,  "end": 2000},
                        "rear_joint_velocity": {"target": 12.0, "start": 800,  "end": 2000},
                        "rear_swing":          {"target": 8.0,  "start": 800,  "end": 2000},
                        "swing_stride":        {"target": 4.0,  "start": 800,  "end": 2000},
                        "foot_clearance":      {"target": 8.0,  "start": 800,  "end": 2000},
                        "trot_gait":           {"target": 40.0, "start": 800,  "end": 2000},
                        "feet_air_time":       {"target": 20.0, "start": 1000, "end": 2500},
                    },
                    "boot_ramp_config": {
                        "boot_standing": {"initial": 15.0, "ramp_down_start": 200, "ramp_down_end": 500},
                        "boot_contact":  {"initial": 5.0,  "ramp_down_start": 300, "ramp_down_end": 600},
                    },
                    "pose_safety_threshold_dev": 999.0,
                    "pose_safety_threshold_ep": 0.0,
                    "pose_safety_fallback": -2.0,
                    "pose_safety_ema_alpha": 0.03,
                    "log_interval": 100,
                },
            )

            # ── V43/V44: Connected Trot — 독립 reward를 연결된 reward로 교체 ──
            if _CONNECTED_TROT:
                toe_cfg_v43 = SceneEntityCfg("contact_forces", body_names=".*toe_link")

                toe_body_v43 = SceneEntityCfg("robot", body_names=".*toe_link")

                # forward_velocity → forward_velocity_gated (per-leg propulsion gating)
                # V43-B: gate_alpha=0.0 (boot phase에서 gating 비활성), curriculum이 0→1 ramp
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_gated,
                    weight=8.0,
                    params={
                        "asset_cfg": SceneEntityCfg("robot"),
                        "sensor_cfg": toe_cfg_v43,
                        "foot_cfg": toe_body_v43,
                        "target_vel": 0.3,
                        "propulsion_threshold": 0.1,
                        "gate_alpha": 0.0,
                    },
                )

                # gait_phase → gait_phase_contact (per-leg 접지+추진 연결)
                # V43-B: push_alpha=0.0 (boot=contact only), curriculum이 0→1 ramp
                self.rewards.gait_phase = RewTerm(
                    func=custom_mdp.gait_phase_contact_reward,
                    weight=15.0,
                    params={
                        "sensor_cfg": toe_cfg_v43,
                        "foot_cfg": toe_body_v43,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "frequency": 2.0,
                        "duty_factor": 0.5,
                        "contact_threshold": 1.0,
                        "min_push": 0.05,
                        "push_alpha": 0.0,
                    },
                )

                # stance_propulsion 추가 (접지 추진 핵심)
                self.rewards.stance_propulsion = RewTerm(
                    func=custom_mdp.stance_propulsion_reward,
                    weight=8.0,
                    params={
                        "sensor_cfg": toe_cfg_v43,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "target_push_vel": 0.3,
                        "min_vel": 0.05,
                    },
                )

                # V44: diagonal_coupling 복원 (V43에서 제거했지만 coupling=0.0 → 재추가)
                # V42 블록의 weight=10 정의 유지, walking reward 초기화 블록에서 weight=0 설정
                # curriculum walk_ramp에서 iter 800~2000에 0→10 순차 활성화

                # joint_vel_l2 제거 (dof_acc와 중복)
                self.rewards.joint_vel_l2 = None

                # V46-B: joint_default_pose 제거 → shoulder_neutral로 교체 (shoulder만 제어, leg 자유)
                self.rewards.joint_default_pose = None
                self.rewards.shoulder_neutral = RewTerm(
                    func=custom_mdp.shoulder_neutral_penalty,
                    weight=-3.0,
                    params={
                        "shoulder_cfg": SceneEntityCfg("robot", joint_names=[
                            "front_left_shoulder", "front_right_shoulder",
                            "rear_left_shoulder", "rear_right_shoulder"]),
                        "target_angles": [-0.04, -0.04, -0.04, -0.04],
                    },
                )

                # V46-A: V38.3 gait reward 8개 추가 (보행 품질 복원)
                toe_contact_cfg_gait = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                toe_body_cfg_gait = SceneEntityCfg("robot", body_names=".*toe_link")

                self.rewards.leg_lift = RewTerm(
                    func=custom_mdp.leg_lift_reward,
                    weight=15.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "leg_joint_cfg": SceneEntityCfg("robot", joint_names=[
                            "front_left_leg", "front_right_leg", "rear_left_leg", "rear_right_leg"]),
                        "target_angle": 0.6,
                    },
                )
                self.rewards.rear_alternation = RewTerm(
                    func=custom_mdp.rear_alternation_reward,
                    weight=15.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_joint_velocity = RewTerm(
                    func=custom_mdp.rear_joint_velocity_reward,
                    weight=12.0,
                    params={
                        "rear_joint_cfg": SceneEntityCfg("robot", joint_names=[
                            "rear_left_shoulder", "rear_right_shoulder",
                            "rear_left_leg", "rear_right_leg",
                            "rear_left_foot", "rear_right_foot"]),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "vel_threshold": 0.5,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_swing = RewTerm(
                    func=custom_mdp.rear_swing_bonus,
                    weight=8.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "foot_cfg": toe_body_cfg_gait,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "target_clearance": 0.08,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.swing_stride = RewTerm(
                    func=custom_mdp.swing_stride_reward,
                    weight=4.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "foot_cfg": toe_body_cfg_gait,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.001,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=8.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "foot_cfg": toe_body_cfg_gait,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "target_clearance": 0.06,
                        "min_vel": 0.001,
                    },
                )
                self.rewards.trot_gait = RewTerm(
                    func=custom_mdp.trot_gait_reward,
                    weight=40.0,
                    params={
                        "sensor_cfg": toe_contact_cfg_gait,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.001,
                    },
                )

                # Walking reward 초기 weight=0 (curriculum이 순차 활성화)
                # [기존 V43-E]
                self.rewards.forward_velocity.weight = 0.0    # iter 300~800 → 8.0
                self.rewards.stance_propulsion.weight = 0.0    # iter 300~800 → 8.0
                self.rewards.diagonal_coupling.weight = 0.0    # iter 800~2000 → 10.0
                self.rewards.gait_phase.weight = 0.0           # iter 800~2000 → 15.0
                self.rewards.stride_length.weight = 0.0        # iter 800~2000 → 5.0
                self.rewards.feet_air_time.weight = 0.0        # iter 1000~2500 → 20.0
                # [V46-A 추가 gait reward]
                self.rewards.leg_lift.weight = 0.0             # iter 800~2000 → 15.0
                self.rewards.rear_alternation.weight = 0.0     # iter 800~2000 → 15.0
                self.rewards.rear_joint_velocity.weight = 0.0  # iter 800~2000 → 12.0
                self.rewards.rear_swing.weight = 0.0           # iter 800~2000 → 8.0
                self.rewards.swing_stride.weight = 0.0         # iter 800~2000 → 4.0
                self.rewards.foot_clearance.weight = 0.0       # iter 800~2000 → 8.0
                self.rewards.trot_gait.weight = 0.0            # iter 800~2000 → 40.0

                # V43-E: Boot standing rewards (curriculum이 ramp down)
                toe_cfg_boot = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.boot_standing = RewTerm(
                    func=custom_mdp.boot_standing_reward,
                    weight=15.0,
                    params={
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_height": 0.23,
                        "height_k": 100.0,
                    },
                )
                self.rewards.boot_contact = RewTerm(
                    func=custom_mdp.boot_foot_contact,
                    weight=5.0,
                    params={
                        "sensor_cfg": toe_cfg_boot,
                        "contact_threshold": 1.0,
                    },
                )

        # ══════════════════════════════════════════════════════════
        # V57.A1: Clean phase-centric reboot
        # - legacy gait-gate / phase-table OFF
        # - small reward stack only
        # - phase reward is primary timing signal
        # - no only_positive_rewards in the first pass
        # ══════════════════════════════════════════════════════════
        if _IS_V57 and _V57_TRACK in {"A1", "A1B"}:
            # V57.A1 reset: keep the clean reward stack fixed, but make the
            # control/command setup less aggressive for boot viability.
            self.decimation = 4
            self.commands.base_velocity.rel_standing_envs = 0.5 if _V57_TRACK == "A1B" else 0.25
            self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.5)
            # Clean bootstrap should start from a symmetric stand instead of a
            # heavily randomized asymmetric landing.
            self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            self.curriculum.reward_weights = None
            self.terminations.min_height.params["min_height"] = 0.10
            self.terminations.shoulder_splay = None

            self.observations.policy.phase_clock = ObsTerm(
                func=custom_mdp.phase_clock_obs,
                params={"frequency": 2.0},
            )

            keep_reward_names = {
                "alive_bonus",
                "track_lin_vel_xy_exp",
                "track_ang_vel_z_exp",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "flat_orientation_l2",
                "base_height_l2",
                "standing_height",
                "action_rate_l2",
                "dof_acc_l2",
                "undesired_contacts",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            self.rewards.alive_bonus = RewTerm(
                func=custom_mdp.alive_bonus,
                weight=1.0,
            )
            self.rewards.track_lin_vel_xy_exp.weight = 1.0
            self.rewards.track_ang_vel_z_exp.weight = 0.5
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -0.1
            self.rewards.flat_orientation_l2.weight = -1.0
            self.rewards.base_height_l2.weight = -1.0
            self.rewards.base_height_l2.params["target_height"] = 0.22
            self.rewards.standing_height.weight = 2.0 if _V57_TRACK == "A1B" else 0.0
            self.rewards.standing_height.params["target_height"] = 0.22
            self.rewards.action_rate_l2.weight = -0.5
            self.rewards.dof_acc_l2.weight = -2.5e-7
            self.rewards.undesired_contacts.weight = -1.0

            toe_cfg_phase = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_body_cfg_phase = SceneEntityCfg("robot", body_names=".*toe_link")
            self.rewards.phase_contact = RewTerm(
                func=custom_mdp.phase_contact_reward,
                weight=1.0,
                params={
                    "sensor_cfg": toe_cfg_phase,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "contact_threshold": 1.0,
                    "standing_vel_threshold": 0.08,
                    "aggregation_mode": "mean",
                    "ema_alpha": 0.0,
                    "min_target": 0.60,
                },
            )
            self.rewards.phase_clearance = RewTerm(
                func=custom_mdp.phase_foot_clearance,
                weight=0.5,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "foot_cfg": foot_body_cfg_phase,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "target_clearance": 0.04,
                    "standing_vel_threshold": 0.08,
                },
            )
            self.rewards.joint_deviation = RewTerm(
                func=isaaclab_mdp.joint_deviation_l1,
                weight=-0.01,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )

        # ══════════════════════════════════════════════════════════
        # V57.B1: Stand-first bootstrap
        # - no locomotion command
        # - no phase reward
        # - first learn to stand high, level, and on four feet
        # ══════════════════════════════════════════════════════════
        if _IS_V57 and _V57_TRACK == "B1":
            self.actions.joint_pos.scale = 0.25  # standing: 초기 random action ±0.25 rad (1.0은 즉시 넘어짐)
            self.action_warmup_steps = 8
            self.decimation = 4
            self.commands.base_velocity.rel_standing_envs = 1.0
            self.commands.base_velocity.rel_heading_envs = 0.0
            self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
            self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
            self.commands.base_velocity.debug_vis = False
            # Stand-first validation must start from a fixed planted pose, not
            # the parent locomotion domain-randomized root state.
            self.events.physics_material = None
            self.events.add_base_mass = None
            self.events.base_com = None
            self.events.reset_base = None
            self.events.base_external_force_torque = None
            self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            self.curriculum.reward_weights = None
            self.terminations.min_height.params["min_height"] = 0.12  # IdealPD zero-action eq=0.124, 아래는 넘어진 것
            self.terminations.bad_orientation.params["limit_angle"] = 0.7  # standing: 40°
            self.terminations.shoulder_splay = None
            self.observations.policy.phase_clock = None

            keep_reward_names = {
                "alive_bonus",
                "standing_height",
                "feet_on_ground",
                "stationary_reward",
                "contact_switch_penalty",
                "contact_foot_velocity_penalty",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "flat_orientation_l2",
                "base_height_l2",
                "action_rate_l2",
                "joint_vel_l2",
                "dof_acc_l2",
                "undesired_contacts",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            self.rewards.alive_bonus = RewTerm(
                func=custom_mdp.alive_bonus,
                weight=1.0,
            )
            self.rewards.standing_height = RewTerm(
                func=custom_mdp.standing_height_exp,
                weight=5.0,
                params={
                    "target_height": 0.18,  # ImplicitActuator loaded eq=0.144, 목표는 그 위
                    "sigma": 0.03,
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )
            self.rewards.feet_on_ground = RewTerm(
                func=custom_mdp.all_feet_on_ground,
                weight=2.0,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*toe_link"),
                    "threshold": 1.0,
                },
            )
            self.rewards.contact_switch_penalty = RewTerm(
                func=custom_mdp.contact_switch_penalty,
                weight=-2.0,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*toe_link"),
                    "threshold": 1.0,
                },
            )
            self.rewards.contact_foot_velocity_penalty = RewTerm(
                func=custom_mdp.contact_foot_velocity_penalty,
                weight=-1.0,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*toe_link"),
                    "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                    "threshold": 1.0,
                },
            )
            self.rewards.stationary_penalty = None
            self.rewards.stationary_reward = RewTerm(
                func=custom_mdp.stationary_reward,
                weight=1.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "threshold": 0.05,
                },
            )
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -0.5
            self.rewards.flat_orientation_l2.weight = -2.0
            self.rewards.base_height_l2.weight = -1.5
            self.rewards.base_height_l2.params["target_height"] = 0.18  # standing_height와 동일
            self.rewards.action_rate_l2.weight = -0.5
            self.rewards.joint_vel_l2.weight = -0.1
            self.rewards.dof_acc_l2.weight = -2.5e-7
            self.rewards.undesired_contacts.weight = -1.0

        # ══════════════════════════════════════════════════════════
        # V58: Isaac Lab 표준 locomotion — 77개 heuristic 탈피
        # 표준 10개 reward, ImplicitActuator, velocity tracking
        # ══════════════════════════════════════════════════════════
        if _IS_V58 and _V58_TRACK in {"B1", "B2", "B3", "B4"}:
            # ── Control ──
            self.action_warmup_steps = 5  # 0.1초 최소 접촉 후 policy 즉시 제어
            self.actions.joint_pos.scale = 0.30  # B1 검증 수준
            self.decimation = 4
            self.episode_length_s = 20.0

            # ── Commands: 보수적 locomotion bootstrap ──
            self.commands.base_velocity.rel_standing_envs = 0.2
            self.commands.base_velocity.rel_heading_envs = 0.5
            self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.3)
            self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            self.commands.base_velocity.ranges.ang_vel_z = (-0.2, 0.2)

            # ── Events: 표준 구조를 유지하되 bootstrap-friendly로 보수화 ──
            self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)  # 안정 init pose에서 시작 (0.8→foot=1.08=L자)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            # push_robot은 SpotMicro가 가벼워서 일단 비활성 유지 (V58.1에서 검토)

            # ── Terminations: 실제 엎드림/base contact 중심 ──
            self.terminations.min_height.params["min_height"] = 0.16  # settling ~0.19, 30mm 여유
            self.terminations.bad_orientation.params["limit_angle"] = 0.51  # 29도 즉시 사망
            self.terminations.shoulder_splay = None
            # body/윗다리 접촉은 즉시 사망. foot_link는 L L 앉기 병변을 위해 별도 delayed termination으로 처리.
            self.terminations.base_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link"),
                    "threshold": 1.0,
                },
            )

            # ── Curriculum: 없음 ──
            self.curriculum.reward_weights = None

            # ── Observations: phase clock OFF ──
            self.observations.policy.phase_clock = None

            # ── Rewards: 표준 10개만 유지 ──
            keep_reward_names = {
                "track_lin_vel_xy_exp",
                "track_ang_vel_z_exp",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "dof_acc_l2",
                "action_rate_l2",
                "feet_air_time",
                "undesired_contacts",
                "flat_orientation_l2",
                "dof_torques_l2",
                "standing_height",
                "excessive_contact",
                "moving_height_l2",
                "joint_default_pos",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            # toe_link가 실제로 병합되지 않고 별도 body로 존재 (진단 확인)
            # .*foot_link는 foot body 접촉만 감지, toe sphere 접촉은 .*toe_link로 감지
            toe_sensor = SceneEntityCfg("contact_forces", body_names=".*toe_link")

            # [주연] velocity tracking
            self.rewards.track_lin_vel_xy_exp.weight = 1.0
            self.rewards.track_lin_vel_xy_exp.params["std"] = 0.5
            self.rewards.track_ang_vel_z_exp.weight = 0.5
            self.rewards.track_ang_vel_z_exp.params["std"] = 0.5

            # [조연] feet air time
            self.rewards.feet_air_time.weight = 0.05
            self.rewards.feet_air_time.params["sensor_cfg"] = toe_sensor
            self.rewards.feet_air_time.params["threshold"] = 0.5

            # [penalty — Isaac Lab 표준 수준]
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -0.05   # 표준 (V57.B1은 -0.5로 10배 과다였음)
            self.rewards.dof_acc_l2.weight = -2.5e-7     # 표준
            self.rewards.action_rate_l2.weight = -0.01   # 표준 (V57.B1은 -0.5로 50배 과다였음)
            self.rewards.undesired_contacts.weight = -1.0
            self.rewards.undesired_contacts.params["sensor_cfg"] = SceneEntityCfg(
                "contact_forces", body_names="base_link|.*shoulder_link|.*leg_link"
            )

            # [SpotMicro 전용] torques + flat orientation + standing height
            self.rewards.dof_torques_l2 = RewTerm(
                func=velocity_mdp.joint_torques_l2,
                weight=-1.0e-5,
            )
            self.rewards.flat_orientation_l2.weight = -0.5  # 표준은 0.0, SpotMicro는 가벼워서 필요
            self.rewards.standing_height = RewTerm(
                func=custom_mdp.standing_height_exp,
                weight=0.5,  # standing env에서만 약하게 anti-crouch
                params={
                    "target_height": 0.18,
                    "sigma": 0.05,
                    "standing_vel_threshold": 0.05,
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )

            if _V58_TRACK == "B2":
                # V58.B2: drag propulsion 제거, 발 들기와 upright gait 품질 강화
                self.rewards.feet_air_time.weight = 0.20
                self.rewards.feet_air_time.params["threshold"] = 0.2
                self.rewards.standing_height.weight = 1.0

            if _V58_TRACK == "B4":
                # V58.B4: 3-Phase 자동 커리큘럼
                # Phase 1 (iter 0~500):    standing only, 균형 학습
                # Phase 2 (iter 500~1500): standing 50% + 느린 전진 0~0.2
                # Phase 3 (iter 1500~):    standing 20% + 전진 0~0.4

                # Phase 1 초기값 (curriculum이 runtime에서 업데이트)
                self.commands.base_velocity.rel_standing_envs = 1.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
                self.rewards.standing_height.weight = 2.0
                self.rewards.feet_air_time.weight = 0.125
                # 이상적 자세 유지: 모든 관절이 init pose에서 벗어나면 penalty
                # splay/웅크림/비대칭 모두 하나의 항으로 억제
                self.rewards.joint_default_pos = RewTerm(
                    func=custom_mdp.joint_default_pos_l2,
                    weight=-2.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # 3-Phase auto curriculum (env._b4_phase_update에서 처리)
                self._b4_phase2_iter = 500
                self._b4_phase3_iter = 1500

                # Posture termination
                self.terminations.posture_violation = DoneTerm(
                    func=custom_mdp.delayed_posture_termination,
                    params={
                        "min_height": 0.17,
                        "max_tilt": 0.31,  # 18도
                        "violation_duration": 3.0,
                        "grace_period": 1.5,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )

        # ══════════════════════════════════════════════════════════
        # V59/V60: stand-first 기본자세 학습
        # V59.A/B 목표: 초기 대칭 Z-bend 근처에서 최소한의 동작으로 넘어지지 않고 서기
        # V59.C 목표: stand manifold를 유지한 채 작은 보행으로 전환
        # V60.A 목표: 본격 전진 학습
        # ══════════════════════════════════════════════════════════
        if _IS_V59 or _IS_V60:
            # ── Control ──
            self.action_warmup_steps = 5
            self.actions.joint_pos.scale = 0.04  # stand-first: toe 고정 상태에서 body correction만 가능하도록 더 축소
            self.decimation = 4
            self.episode_length_s = 20.0

            # ── Commands: stand-only ──
            self.commands.base_velocity.heading_command = False
            self.commands.base_velocity.rel_standing_envs = 1.0
            self.commands.base_velocity.rel_heading_envs = 0.0
            self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
            self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

            # ── Events: standing-ready 초기 조건 고정 ──
            self.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            self.events.reset_base.params["pose_range"]["x"] = (0.0, 0.0)
            self.events.reset_base.params["pose_range"]["y"] = (0.0, 0.0)
            self.events.reset_base.params["pose_range"]["yaw"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["x"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["y"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["z"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["roll"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["pitch"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["yaw"] = (0.0, 0.0)
            self.events.add_base_mass = None
            self.events.base_com = None
            self.events.base_external_force_torque = None
            self.events.push_robot = None

            # ── Terminations: 기울거나 주저앉으면 즉사 ──
            self.terminations.min_height.params["min_height"] = 0.14  # loaded eq=150mm, 주저앉으면 즉사
            # bad_orientation: 20도 제한 + 초반 3초 유예 (착지 충격)
            self.terminations.bad_orientation = DoneTerm(
                func=custom_mdp.bad_orientation_grace,
                params={
                    "limit_angle": 0.52,    # 30도
                    "grace_steps": 150,     # 3초 (decimation=4, dt=0.005, 150*0.02=3s)
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )
            self.terminations.shoulder_splay = None
            self.terminations.posture_violation = None
            # 발 떼면 즉사 (grace 3초 후)
            toe_term_sensor = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.terminations.feet_lifted = DoneTerm(
                func=custom_mdp.feet_lifted_termination,
                params={
                    "sensor_cfg": toe_term_sensor,
                    "threshold": 1.0,
                    "grace_steps": 25,  # 0.5초 유예: 초기 착지 직후를 제외하면 toe 이탈을 빠르게 실패로 처리
                    "consecutive_steps": 8,  # 순간 contact dropout은 무시하고 연속 이탈만 실패로 처리
                },
            )
            self.terminations.base_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link"),
                    "threshold": 1.0,
                },
            )

            # ── Curriculum: 없음 ──
            self.curriculum.reward_weights = None

            # ── Observations: phase clock OFF ──
            self.observations.policy.phase_clock = None

            # ── Rewards: toe 고정 + 몸체 수평 이동으로 균형 ──
            keep_reward_names = {
                "track_lin_vel_xy_exp",
                "track_ang_vel_z_exp",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "action_rate_l2",
                "flat_orientation_l2",
                "dof_torques_l2",
                "flat_orientation_bonus",
                "feet_on_ground",
                "feet_lift_penalty",
                "contact_foot_velocity_penalty",
                "standing_height",
                "joint_default_pos",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            # ── 서기 목표: 목표 높이 유지 + 발 접지 + 수평 + 최소 부하/움직임 ──
            # "멈춰" 명령 시 이 상태를 유지해야 함

            # [핵심1] 수평 유지
            self.rewards.flat_orientation_bonus = RewTerm(
                func=custom_mdp.flat_orientation_bonus,
                weight=5.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.flat_orientation_l2.weight = -3.0

            # [핵심2] 목표 높이(~205mm, stiffness=20 loaded stand) 유지 + heartbeat 리포트용
            self.rewards.standing_height = RewTerm(
                func=custom_mdp.standing_height_exp,
                weight=3.0,
                params={
                    "target_height": 0.205,
                    "sigma": 0.03,
                    "standing_vel_threshold": None,
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )

            # [핵심3] 가만히 서 있기 (vel=0 tracking)
            self.rewards.track_lin_vel_xy_exp.weight = 2.0
            self.rewards.track_lin_vel_xy_exp.params["std"] = 0.25
            self.rewards.track_ang_vel_z_exp.weight = 1.0
            self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

            # [핵심4] 발을 지면에 유지
            toe_sensor = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.rewards.feet_on_ground = RewTerm(
                func=custom_mdp.all_feet_on_ground,
                weight=6.0,
                params={
                    "sensor_cfg": toe_sensor,
                    "threshold": 1.0,
                },
            )

            # [핵심5] 관절 init pose 유지 — 다리 접기/벌리기 방지
            self.rewards.joint_default_pos = RewTerm(
                func=custom_mdp.joint_default_pos_l2,
                weight=-4.0,  # 관절 deviation에 비례하는 penalty
                params={"asset_cfg": SceneEntityCfg("robot")},
            )

            # [핵심6] 발 떼면 벌 (grace 후 termination도 있으니 적당히)
            self.rewards.feet_lift_penalty = RewTerm(
                func=custom_mdp.feet_lift_penalty,
                weight=-20.0,  # 1발만 들어도 즉시 크게 불리
                params={
                    "sensor_cfg": toe_sensor,
                    "threshold": 1.0,
                },
            )

            # [핵심7] 접촉 중 toe 미끄럼 금지 — 붙인 상태에서 body만 조정하도록 유도
            self.rewards.contact_foot_velocity_penalty = RewTerm(
                func=custom_mdp.contact_foot_velocity_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor,
                    "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                    "threshold": 1.0,
                },
            )

            # [핵심8] 최소 움직임
            self.rewards.action_rate_l2.weight = -0.5

            # [핵심9] 부하 최소화
            self.rewards.dof_torques_l2 = RewTerm(
                func=velocity_mdp.joint_torques_l2,
                weight=-0.02,
            )

            # [보조] 흔들림
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -1.0

            if _IS_V60 and _V60_TRACK == "A":
                # ── V60.A: from-scratch 보행 학습 ──
                # 서기 선행 없이 처음부터 동적 균형 + 보행을 동시에 배움
                self.actions.joint_pos.scale = 0.25  # Isaac Lab 표준

                self.commands.base_velocity.rel_standing_envs = 0.2  # 20% 서기, 80% 보행
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (-0.3, 0.3)

                # 발 들기 제약 완전 제거 (보행 학습에 필수)
                self.terminations.feet_lifted = None

                # 접지 제약 제거 + 보행 reward 추가
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.contact_foot_velocity_penalty.weight = -1.0  # 미끄럼만 약하게

                # 전진 추종 (핵심 목표)
                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                # 전진 직접 보상
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=3.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # 발 들기 보상 (보행 패턴 유도)
                toe_sensor_walk = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=2.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_walk,
                        "threshold": 0.3,
                    },
                )

                # 안정성 (서기보다 약하게, 넘어지지만 않으면 됨)
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.standing_height.weight = 2.0
                self.rewards.joint_default_pos.weight = -1.0  # 관절 자유도 확보
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V59 and _V59_TRACK == "C":
                # ── V59.C: stand 성공 정책 위에 작은 swing/전진만 얹는 보수적 전환 ──
                self.actions.joint_pos.scale = 0.05

                self.commands.base_velocity.rel_standing_envs = 0.8
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.08)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted.params["grace_steps"] = 40
                self.terminations.feet_lifted.params["consecutive_steps"] = 10

                self.rewards.track_lin_vel_xy_exp.weight = 3.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.2
                self.rewards.feet_on_ground.weight = 5.0
                self.rewards.feet_lift_penalty.weight = -15.0
                self.rewards.contact_foot_velocity_penalty.weight = -3.0

            if _IS_V60 and _V60_TRACK == "B":
                # ── V60.B: V60.A resume — RR 비대칭 exploit 교정 ──
                # V60.A의 안정성+tracking 유지, 비대칭 사용 직접 벌함
                self.actions.joint_pos.scale = 0.25  # V60.A 유지

                self.commands.base_velocity.rel_standing_envs = 0.1  # 0.2→0.1 (보행 비중 증가)
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (-0.3, 0.3)

                # feet_lifted termination 제거 (V60.A와 동일)
                self.terminations.feet_lifted = None

                # ── V60.A에서 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.contact_foot_velocity_penalty.weight = -1.0

                # 전진 추종
                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                # 전진 직접 보상 (강화)
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # 발 들기 보상 (강화: threshold 낮춤, weight 상향)
                toe_sensor_b = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=4.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_b,
                        "threshold": 0.1,
                    },
                )

                # 발 높이 보상 (보조: 1-2mm 미세 진동 → 실제 보행으로)
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_b,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── 비대칭 exploit 교정 (핵심) ──
                # [1] 최소 접지 비율 penalty — 한 다리 비사용 직접 벌함
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_b,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                # [2] 과다 swing penalty — 영구 공중부양 직접 벌함
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_b,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )

                # 안정성 (V60.A 유지)
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.standing_height.weight = 2.0
                self.rewards.joint_default_pos.weight = -0.5
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "C":
                # ── V60.C: V60.B resume — RR exploit 강력 교정 ──
                # V60.B에서 penalty -3.0이 부족 → Codex 권장 -10으로 상향
                # rear pair balance penalty 추가로 RR 표적 타격
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.1
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (-0.3, 0.3)

                self.terminations.feet_lifted = None

                # ── V60.B에서 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.contact_foot_velocity_penalty.weight = -1.0

                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                toe_sensor_c = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=4.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_c,
                        "threshold": 0.1,
                    },
                )

                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_c,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── 비대칭 exploit 강력 교정 (V60.B -3→-10) ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-10.0,
                    params={
                        "sensor_cfg": toe_sensor_c,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-10.0,
                    params={
                        "sensor_cfg": toe_sensor_c,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                # [신규] rear pair 불균형 직접 벌칙
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": toe_sensor_c,
                        "contact_threshold": 1.0,
                    },
                )

                # 안정성 유지
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.standing_height.weight = 2.0
                self.rewards.joint_default_pos.weight = -0.5
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "D":
                # ── V60.D: 정적 4발 접지 해를 깨고 실제 swing 유도 ──
                # V60.C의 대칭성 교정 유지 + static bias 약화 + gait incentive 강화
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.1
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (-0.3, 0.3)

                self.terminations.feet_lifted = None

                # ── 유지: 추종성 + 전진 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── 강화: gait incentive (핵심 변경) ──
                toe_sensor_d = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=8.0,  # V60.C 4→8
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_d,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=6.0,  # V60.C 2→6
                    params={
                        "sensor_cfg": toe_sensor_d,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── 유지: 대칭성 교정 (V60.C 그대로) ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-10.0,
                    params={
                        "sensor_cfg": toe_sensor_d,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-10.0,
                    params={
                        "sensor_cfg": toe_sensor_d,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": toe_sensor_d,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 약화: static bias (핵심 변경) ──
                self.rewards.contact_foot_velocity_penalty.weight = -0.3  # V60.C -1.0→-0.3
                self.rewards.joint_default_pos.weight = -0.2  # V60.C -0.5→-0.2

                # ── 유지: 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.standing_height.weight = 2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "E":
                # ── V60.E: rear swing 생성에만 집중 ──
                # V60.D에서 앞다리 swing은 나왔으나 뒷다리 완전 고착
                # rear 전용 clearance 보상 + static bias 제거 + yaw OFF
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0  # 100% 보행
                self.commands.base_velocity.ranges.lin_vel_x = (0.05, 0.3)  # 최소 전진
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)  # yaw OFF

                self.terminations.feet_lifted = None

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait incentive: 전체 + rear 전용 ──
                toe_sensor_e = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=8.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_e,
                        "threshold": 0.1,
                    },
                )
                # front clearance 유지 (약화)
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=3.0,  # V60.D 6→3
                    params={
                        "sensor_cfg": toe_sensor_e,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                # [핵심 신규] rear 전용 clearance 보상
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=6.0,
                    params={
                        "sensor_cfg": toe_sensor_e,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── 대칭성 penalty 완화 (V60.C -10 → -6) ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-6.0,
                    params={
                        "sensor_cfg": toe_sensor_e,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-6.0,
                    params={
                        "sensor_cfg": toe_sensor_e,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": toe_sensor_e,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 제거/최소화 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0  # 완전 제거
                self.rewards.joint_default_pos.weight = -0.1  # 최소
                self.rewards.standing_height.weight = 1.0  # V60.D 2→1

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "F":
                # ── V60.F: 정적 접지 해 자체를 이득 아니게 만드는 구조 전환 ──
                # "rear를 더 밀자"가 아니라 "정적 해가 더 이상 싸지 않게" 설계
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.3)  # 최소 전진 상향
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)  # yaw OFF

                self.terminations.feet_lifted = None

                # ── 추종성 (tracking 약간 약화, forward 유지) ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0  # 5→4
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait incentive: 전체 air_time + rear 전용 ──
                toe_sensor_f = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=8.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_f,
                        "threshold": 0.1,
                    },
                )
                # [핵심 신규] rear 비접촉 시간 직접 보상
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=6.0,
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                # rear clearance 유지
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=6.0,
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                # front clearance 제거 (front는 이미 swing 중)
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── 대칭 penalty 대폭 완화 ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,  # -6→-3
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,  # -6→-3
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,  # -5→-2
                    params={
                        "sensor_cfg": toe_sensor_f,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 완전 제거 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0   # 완전 제거
                self.rewards.standing_height.weight = 0.0      # 완전 제거

                # ── 안정성 (최소) ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "G":
                # ── V60.G: front/rear pair balance + diagonal coupling ──
                # "한쪽만 들면 손해, 균형 있게 교대하면 이득"
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)  # yaw OFF

                self.terminations.feet_lifted = None

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait: 전역 air_time + 전역 clearance (균형) ──
                toe_sensor_g = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=8.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_g,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=3.0,  # 전역 균형
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── rear 전용 보상 대폭 약화 (V60.F에서 과다) ──
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=1.0,  # V60.F 6→1 (보조)
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=1.0,  # V60.F 6→1 (보조)
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── [핵심 신규] front/rear 균형 + diagonal coupling ──
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=2.0,  # 약하게 시작
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 대칭 penalty 유지 ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_g,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 완전 제거 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.standing_height.weight = 0.0

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "H":
                # ── V60.H: 대각선 교대 구조 직접 유도 ──
                # V60.G에서 4발 swing 균형은 개선됐으나 diagonal_coupling_raw=0
                # 핵심: diagonal_coupling 강화, balance penalty 완화
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait: 전역 (V60.G에서 약화) ──
                toe_sensor_h = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,  # V60.G 8→5
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_h,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,  # V60.G 3→2
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # rear 전용 보상 제거
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── [핵심] diagonal coupling 강화 ──
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=8.0,  # V60.G 2→8
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                    },
                )

                # ── balance penalty 완화 ──
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-2.0,  # V60.G -5→-2
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-2.0,  # V60.G -5→-2
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 대칭 penalty 유지 ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_h,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 완전 제거 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.standing_height.weight = 0.0

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "I":
                # ── V60.I: phase-conditioned diagonal alternation ──
                # obs 차원 유지 (phase_clock=None 그대로), reward 내부에서 phase 계산
                # 핵심: phase_contact_reward로 "올바른 위상에 올바른 pair가 swing" 유도
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait: V60.H 유지 ──
                toe_sensor_i = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_i,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # rear 전용 OFF
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── [핵심] velocity-adaptive phase diagonal event reward ──
                # 속도 연동 cadence + touchdown event 시점만 보상 (sparse)
                # 고정 2Hz 강제가 아닌 약한 diagonal event bias
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=3.0,  # 보조 (Codex: 2~4)
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )

                # diagonal_coupling 유지 (V60.H)
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=8.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                    },
                )

                # ── balance penalty 완화 (Codex: -2→-1) ──
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,  # V60.H -2→-1
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,  # V60.H -2→-1
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 대칭 penalty 유지 ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_i,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 완전 제거 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.standing_height.weight = 0.0

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "J":
                # ── V60.J: diagonal 구조 선명화 + clearance/stride 강화 ──
                # V60.I의 trot 구조 유지, anti-phase 직접 보상 + clearance/stride 추가
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.3)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # ── 유지: V60.I 기반 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                toe_sensor_j = SceneEntityCfg("contact_forces", body_names=".*toe_link")

                # ── gait: V60.I 유지 ──
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_j,
                        "threshold": 0.1,
                    },
                )
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=3.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=8.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                    },
                )

                # ── [변경A] clearance 강화 ──
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=4.0,  # V60.I 2→4
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.03,  # V60.I 0.02→0.03
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── [변경B] anti-phase 직접 보상 (신규) ──
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=3.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )

                # ── [변경C] stride/전진 보행 보상 (신규) ──
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # rear 전용 OFF
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── balance/대칭 penalty: V60.I 유지 ──
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_j,
                        "contact_threshold": 1.0,
                    },
                )

                # ── static bias 완전 제거 ──
                self.rewards.contact_foot_velocity_penalty.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.standing_height.weight = 0.0

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "K":
                # ── V60.K: Quality Recovery — 자세 정상화 + exploit 금지 ──
                # GUI에서 확인된 문제: RR 끌기, RL 무릎 접지, 앞다리 모으기
                # diagonal 강화보다 자세 품질 복원이 우선
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.25)  # 보수화
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0

                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait: swing 바닥 유지 ──
                toe_sensor_k = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_k,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # diagonal 보조만 (V60.I 수준으로 약화)
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=4.0,  # V60.I 8→4
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                    },
                )

                # phase/pair/stride 제거 (quality recovery 우선)
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=0.0,  # OFF
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                # rear 전용 OFF
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── [신규A] 자세 복원 ──
                self.rewards.standing_height.weight = 1.5  # crawl 방지
                self.rewards.joint_default_pos.weight = -0.5  # 관절 극단 방지

                # ── [신규B] toe 외 접촉 금지 ──
                leg_contact_sensor = SceneEntityCfg(
                    "contact_forces", body_names=".*foot_link|.*leg_link"
                )
                self.rewards.non_toe_contact = RewTerm(
                    func=custom_mdp.non_toe_contact_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": leg_contact_sensor,
                        "threshold": 1.0,
                    },
                )

                # ── [신규C] 끌림 방지 ──
                self.rewards.contact_drag = RewTerm(
                    func=custom_mdp.contact_drag_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "contact_threshold": 1.0,
                    },
                )

                # ── [신규D] 다리 모으기 방지 ──
                self.rewards.stance_width_min = RewTerm(
                    func=custom_mdp.stance_width_min_penalty,
                    weight=-3.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "min_width": 0.10,
                    },
                )

                # ── [신규E] contact velocity 복원 ──
                self.rewards.contact_foot_velocity_penalty.weight = -0.3

                # ── balance/대칭 penalty 유지 ──
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_k,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "K2":
                # ── V60.K2: Quality Recovery v2 — trailing 직접 억제 + posture 과교정 완화 ──
                # K의 방향은 유지하되, RR trailing posture를 직접 벌하고
                # standing/joint 복원은 한 단계 완화하여 "서기만 하는" 회귀를 줄인다.
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.25)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # 추종성 유지
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                toe_sensor_k2 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_k2,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # diagonal은 보조만
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=4.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                    },
                )

                # phase/pair/stride/rear 특화 OFF
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # posture recovery 완화: 품질 회복은 하되 gait 자유도는 남긴다
                self.rewards.standing_height.weight = 1.0
                self.rewards.standing_height.params["target_height"] = 0.18
                self.rewards.standing_height.params["sigma"] = 0.05
                self.rewards.joint_default_pos.weight = -0.3

                # toe 외 접촉 금지
                leg_contact_sensor = SceneEntityCfg(
                    "contact_forces", body_names=".*foot_link|.*leg_link"
                )
                self.rewards.non_toe_contact = RewTerm(
                    func=custom_mdp.non_toe_contact_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": leg_contact_sensor,
                        "threshold": 1.0,
                    },
                )

                # toe dragging + rear trailing posture 직접 억제
                self.rewards.contact_drag = RewTerm(
                    func=custom_mdp.contact_drag_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.rear_trailing = RewTerm(
                    func=custom_mdp.rear_trailing_penalty,
                    weight=-4.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "max_rear_back": 0.06,
                    },
                )

                # 다리 모으기 방지 + 미끄럼 약하게 복원
                self.rewards.stance_width_min = RewTerm(
                    func=custom_mdp.stance_width_min_penalty,
                    weight=-3.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "min_width": 0.10,
                    },
                )
                self.rewards.contact_foot_velocity_penalty.weight = -0.3

                # balance/대칭 penalty 유지
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_k2,
                        "contact_threshold": 1.0,
                    },
                )

                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0

            if _IS_V60 and _V60_TRACK == "K3":
                # ── V60.K3: Quality Recovery v3 — RL/RR rear pair usage floor 추가 ──
                # K2에서 RR trailing은 건드렸지만 RL이 stance anchor로 고착되는
                # 새 exploit가 드러났다. rear pair 둘 다 최소한은 swing하도록 직접 묶는다.
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.25)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                toe_sensor_k3 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                leg_contact_sensor = SceneEntityCfg(
                    "contact_forces", body_names=".*foot_link|.*leg_link"
                )

                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_k3,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=4.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                    },
                )

                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                self.rewards.standing_height.weight = 1.0
                self.rewards.standing_height.params["target_height"] = 0.18
                self.rewards.standing_height.params["sigma"] = 0.05
                self.rewards.joint_default_pos.weight = -0.3

                self.rewards.non_toe_contact = RewTerm(
                    func=custom_mdp.non_toe_contact_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": leg_contact_sensor,
                        "threshold": 1.0,
                    },
                )
                self.rewards.contact_drag = RewTerm(
                    func=custom_mdp.contact_drag_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.rear_trailing = RewTerm(
                    func=custom_mdp.rear_trailing_penalty,
                    weight=-4.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "max_rear_back": 0.06,
                    },
                )
                self.rewards.stance_width_min = RewTerm(
                    func=custom_mdp.stance_width_min_penalty,
                    weight=-3.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "min_width": 0.10,
                    },
                )
                self.rewards.contact_foot_velocity_penalty.weight = -0.3

                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-4.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.rear_leg_min_swing = RewTerm(
                    func=custom_mdp.rear_leg_min_swing_penalty,
                    weight=-6.0,
                    params={
                        "sensor_cfg": toe_sensor_k3,
                        "contact_threshold": 1.0,
                        "min_swing_ratio": 0.05,
                    },
                )

                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "L":
                # ── V60.L: Minimal Quality Recovery — early checkpoint + minimal constraints ──
                # 10000대 회귀를 전제로, policy를 무너뜨린 강한 자세/usage 제약은 빼고
                # 실제 GUI pathology였던 non-toe contact와 rear trailing만 직접 억제한다.
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.25)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                toe_sensor_l = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                leg_contact_sensor = SceneEntityCfg(
                    "contact_forces", body_names=".*foot_link|.*leg_link"
                )

                # 기본 locomotion 바닥 유지
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_l,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=4.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                    },
                )

                # 최근 shaping은 OFF
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # 강한 posture/usage 회복 제약은 끈다
                self.rewards.standing_height.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.stance_width_min = RewTerm(
                    func=custom_mdp.stance_width_min_penalty,
                    weight=0.0,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "min_width": 0.10,
                    },
                )

                # 최소 exploit 금지 2개만 직접 적용
                self.rewards.non_toe_contact = RewTerm(
                    func=custom_mdp.non_toe_contact_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": leg_contact_sensor,
                        "threshold": 1.0,
                    },
                )
                self.rewards.rear_trailing = RewTerm(
                    func=custom_mdp.rear_trailing_penalty,
                    weight=-2.5,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "max_rear_back": 0.06,
                    },
                )
                self.rewards.contact_drag = RewTerm(
                    func=custom_mdp.contact_drag_penalty,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.contact_foot_velocity_penalty.weight = -0.3

                # 기존 exploit 방지 바닥은 유지
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_l,
                        "contact_threshold": 1.0,
                    },
                )

                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V60 and _V60_TRACK == "M":
                # ── V60.M: pair-lock exploit 직접 차단 ──
                # V60.L 기반 + diagonal_pair_lock_penalty + pair_lock_termination
                # FL+RR만 영구 swing하는 패턴을 penalty + hard termination으로 끊음
                self.actions.joint_pos.scale = 0.25

                self.commands.base_velocity.rel_standing_envs = 0.0
                self.commands.base_velocity.ranges.lin_vel_x = (0.12, 0.25)
                self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
                self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

                self.terminations.feet_lifted = None

                # [신규] pair-lock termination
                toe_term_m = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.terminations.pair_lock = DoneTerm(
                    func=custom_mdp.prolonged_pair_lock_termination,
                    params={
                        "sensor_cfg": toe_term_m,
                        "contact_threshold": 1.0,
                        "gap_threshold": 0.50,
                        "grace_steps": 50,
                        "consecutive_steps": 20,
                    },
                )

                # ── 추종성 유지 ──
                self.rewards.feet_on_ground.weight = 0.0
                self.rewards.feet_lift_penalty.weight = 0.0
                self.rewards.track_lin_vel_xy_exp.weight = 4.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
                self.rewards.track_ang_vel_z_exp.weight = 2.0
                self.rewards.track_ang_vel_z_exp.params["std"] = 0.25
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=5.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # ── gait 유지 (V60.L 동일) ──
                toe_sensor_m = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=5.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_m,
                        "threshold": 0.1,
                    },
                )
                self.rewards.foot_clearance = RewTerm(
                    func=custom_mdp.foot_clearance_reward,
                    weight=2.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.diagonal_coupling = RewTerm(
                    func=custom_mdp.simple_diagonal_coupling_reward,
                    weight=4.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                    },
                )

                # ── exploit 억제 (V60.L 유지) ──
                self.rewards.non_toe_contact = RewTerm(
                    func=custom_mdp.non_toe_contact_penalty,
                    weight=-5.0,
                    params={
                        "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link|.*leg_link"),
                        "threshold": 1.0,
                    },
                )
                self.rewards.rear_trailing = RewTerm(
                    func=custom_mdp.rear_trailing_penalty,
                    weight=-2.5,
                    params={
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "max_rear_back": 0.06,
                    },
                )

                # ── [신규 핵심] pair-lock penalty ──
                self.rewards.pair_lock = RewTerm(
                    func=custom_mdp.diagonal_pair_lock_penalty,
                    weight=-6.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                        "gap_threshold": 0.45,
                    },
                )

                # OFF 항목들
                self.rewards.phase_diagonal_event = RewTerm(
                    func=custom_mdp.adaptive_phase_diagonal_event_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "vel_scale": 4.0,
                        "min_frequency": 1.0,
                        "max_frequency": 4.0,
                        "duty_factor": 0.55,
                        "min_vel": 0.05,
                        "command_name": "base_velocity",
                    },
                )
                self.rewards.pair_separation = RewTerm(
                    func=custom_mdp.diagonal_pair_separation_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                        "asset_cfg": SceneEntityCfg("robot"),
                    },
                )
                self.rewards.forward_step = RewTerm(
                    func=custom_mdp.forward_step_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_air_time = RewTerm(
                    func=custom_mdp.rear_feet_air_time_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "asset_cfg": SceneEntityCfg("robot"),
                        "contact_threshold": 1.0,
                        "threshold": 0.1,
                        "min_vel": 0.05,
                    },
                )
                self.rewards.rear_clearance = RewTerm(
                    func=custom_mdp.rear_foot_clearance_reward,
                    weight=0.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                        "asset_cfg": SceneEntityCfg("robot"),
                        "target_clearance": 0.02,
                        "contact_threshold": 1.0,
                        "min_vel": 0.05,
                    },
                )

                # ── static bias OFF ──
                self.rewards.standing_height.weight = 0.0
                self.rewards.joint_default_pos.weight = 0.0
                self.rewards.contact_foot_velocity_penalty.weight = -0.3

                # ── 대칭 penalty 유지 ──
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.15,
                    },
                )
                self.rewards.per_leg_excess_swing = RewTerm(
                    func=custom_mdp.per_leg_excess_swing_penalty,
                    weight=-3.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                        "max_swing_ratio": 0.70,
                    },
                )
                self.rewards.rear_lr_balance = RewTerm(
                    func=custom_mdp.rear_left_right_balance_penalty,
                    weight=-2.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_swing_balance = RewTerm(
                    func=custom_mdp.front_rear_swing_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                    },
                )
                self.rewards.fr_contact_balance = RewTerm(
                    func=custom_mdp.front_rear_contact_balance_penalty,
                    weight=-1.0,
                    params={
                        "sensor_cfg": toe_sensor_m,
                        "contact_threshold": 1.0,
                    },
                )

                # ── 안정성 ──
                self.rewards.flat_orientation_bonus.weight = 3.0
                self.rewards.flat_orientation_l2.weight = -2.0
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

            if _IS_V59 and _V59_TRACK == "D":
                # ── V59.D: 보수적 걷기 전환 ──
                # 서기 policy를 깨뜨리지 않으면서 점진적으로 걷기를 얹음
                # 핵심: 서기 reward 유지 + 걷기 reward 추가 + 제약 점진 완화

                self.actions.joint_pos.scale = 0.25  # Isaac Lab 표준

                self.commands.base_velocity.rel_standing_envs = 0.0  # 100% 보행 명령
                self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.2)
                self.commands.base_velocity.ranges.ang_vel_z = (-0.1, 0.1)

                # feet_lifted: 제거하지 않고 대폭 완화 (보행 중 발 들기 허용)
                self.terminations.feet_lifted.params["grace_steps"] = 100
                self.terminations.feet_lifted.params["consecutive_steps"] = 50
                # min_height 완화
                self.terminations.min_height.params["min_height"] = 0.10
                # base_contact 확대 (몸통/다리 접촉 방지)
                self.terminations.base_contact = DoneTerm(
                    func=isaaclab_mdp.illegal_contact,
                    params={
                        "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link"),
                        "threshold": 1.0,
                    },
                )

                # [걷기 추가] feet_air_time: 발 들면 보상
                toe_sensor_d = SceneEntityCfg("contact_forces", body_names=".*toe_link")
                self.rewards.feet_air_time = RewTerm(
                    func=velocity_mdp.feet_air_time,
                    weight=2.0,
                    params={
                        "command_name": "base_velocity",
                        "sensor_cfg": toe_sensor_d,
                        "threshold": 0.3,
                    },
                )

                # [걷기 강화] 전진 추종 (std 극소 — 안 움직이면 큰 손해)
                self.rewards.track_lin_vel_xy_exp.weight = 5.0
                self.rewards.track_lin_vel_xy_exp.params["std"] = 0.05

                # [걷기 강화] 직접 전진 보상 (대폭 상향)
                self.rewards.forward_velocity = RewTerm(
                    func=custom_mdp.forward_velocity_reward,
                    weight=8.0,
                    params={"asset_cfg": SceneEntityCfg("robot")},
                )

                # [서기 유지] 수평, 높이 — 대폭 약화 (걷기 우선)
                self.rewards.flat_orientation_bonus.weight = 2.0
                self.rewards.flat_orientation_l2.weight = -1.0
                self.rewards.standing_height.weight = 1.0

                # [서기 제약 완화] 제거하지 않고 줄임
                self.rewards.feet_on_ground.weight = 0.0      # 걷기엔 발 들어야 함
                self.rewards.feet_lift_penalty.weight = 0.0    # 걷기엔 발 들어야 함
                self.rewards.contact_foot_velocity_penalty.weight = -0.5
                self.rewards.joint_default_pos.weight = -1.0   # -4→-1
                self.rewards.action_rate_l2.weight = -0.05
                self.rewards.dof_torques_l2.weight = -1e-4

        # ══════════════════════════════════════════════════════════
        # V61: From-Scratch Phase Clock + 단순 Reward
        # V60에서 13버전 동안 배운 교훈:
        # - reward shaping만으로는 trot이 자연 발생하지 않음
        # - policy에게 phase를 직접 보여줘야 함
        # - exploit 방지는 termination이 penalty보다 효과적
        # - reward는 적을수록 exploit이 적음
        # ══════════════════════════════════════════════════════════
        if _IS_V61:
            # ── Control ──
            self.action_warmup_steps = 5
            self.actions.joint_pos.scale = 0.25
            self.decimation = 4
            self.episode_length_s = 20.0

            # ── Commands: 직진 보행 (yaw OFF, from-scratch) ──
            self.commands.base_velocity.heading_command = False
            self.commands.base_velocity.rel_standing_envs = 0.0  # phase obs와 all-stance reward 모순 방지
            self.commands.base_velocity.rel_heading_envs = 0.0
            self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.25)
            self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

            # ── Events: 약간의 초기 랜덤 (from-scratch) ──
            self.events.reset_robot_joints.params["position_range"] = (0.9, 1.1)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            self.events.reset_base.params["pose_range"]["x"] = (-0.1, 0.1)
            self.events.reset_base.params["pose_range"]["y"] = (-0.1, 0.1)
            self.events.reset_base.params["pose_range"]["yaw"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["x"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["y"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["z"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["roll"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["pitch"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["yaw"] = (0.0, 0.0)
            self.events.add_base_mass = None
            self.events.base_com = None
            self.events.base_external_force_torque = None
            self.events.push_robot = None

            # ── Terminations: exploit은 즉사로 ──
            self.terminations.min_height.params["min_height"] = 0.14
            self.terminations.bad_orientation = DoneTerm(
                func=custom_mdp.bad_orientation_grace,
                params={
                    "limit_angle": 0.52,
                    "grace_steps": 150,
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )
            self.terminations.shoulder_splay = None
            self.terminations.posture_violation = None
            self.terminations.feet_lifted = None
            self.terminations.base_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link"),
                    "threshold": 1.0,
                },
            )
            # [V60.K 교훈] 비-toe 접촉 즉사
            self.terminations.non_toe_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link|.*leg_link"),
                    "threshold": 1.0,
                },
            )
            # [V60.L 교훈] pair-lock 즉사
            toe_term_v61 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.terminations.pair_lock = DoneTerm(
                func=custom_mdp.prolonged_pair_lock_termination,
                params={
                    "sensor_cfg": toe_term_v61,
                    "contact_threshold": 1.0,
                    "gap_threshold": 0.50,
                    "grace_steps": 100,
                    "consecutive_steps": 30,
                },
            )

            # ── Curriculum: 없음 ──
            self.curriculum.reward_weights = None

            # ── Observations: phase clock ON (8차원 추가) ──
            self.observations.policy.phase_clock = ObsTerm(
                func=custom_mdp.phase_clock_obs,
                params={"frequency": 2.0},
            )

            # ── Rewards: 14개 (양수 6 + 음수 8, V60 대비 대폭 축소) ──
            # 기존 reward 전부 끄고 다시 정의
            keep_reward_names = {
                "track_lin_vel_xy_exp",
                "track_ang_vel_z_exp",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "action_rate_l2",
                "flat_orientation_l2",
                "dof_torques_l2",
                "flat_orientation_bonus",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            # [주연] phase-conditioned contact — THE gait driver
            toe_sensor_v61 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.rewards.phase_contact = RewTerm(
                func=custom_mdp.phase_contact_reward,
                weight=10.0,
                params={
                    "sensor_cfg": toe_sensor_v61,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "contact_threshold": 1.0,
                    "standing_vel_threshold": 0.02,  # [V61.C fix] 0.08→0.02: 저속 정적 해 exploit 방지 (Codex 리뷰)
                },
            )

            # 속도 추종
            self.rewards.track_lin_vel_xy_exp.weight = 4.0
            self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
            self.rewards.track_ang_vel_z_exp.weight = 1.0
            self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

            # 전진
            self.rewards.forward_velocity = RewTerm(
                func=custom_mdp.forward_velocity_reward,
                weight=3.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )

            # 수평
            self.rewards.flat_orientation_bonus = RewTerm(
                func=custom_mdp.flat_orientation_bonus,
                weight=3.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.flat_orientation_l2.weight = -2.0

            # 발 들기 백업
            self.rewards.feet_air_time = RewTerm(
                func=velocity_mdp.feet_air_time,
                weight=2.0,
                params={
                    "command_name": "base_velocity",
                    "sensor_cfg": toe_sensor_v61,
                    "threshold": 0.1,
                },
            )

            # [핵심] 대각 쌍 propulsion — trot 직접 유도
            # FL+RR이 동시에 밀거나, FR+RL이 동시에 밀면 보상.
            # 한쪽만 밀면 min=0 → 앞다리 참여 강제, 뒷다리만 밀기 불가.
            self.rewards.propulsion = RewTerm(
                func=custom_mdp.diagonal_pair_propulsion_reward,
                weight=8.0,
                params={
                    "sensor_cfg": toe_sensor_v61,
                    "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_push_vel": 0.3,
                    "min_vel": 0.05,
                },
            )

            # exploit 방지 penalty
            self.rewards.per_leg_contact_min = RewTerm(
                func=custom_mdp.per_leg_contact_min_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v61,
                    "contact_threshold": 1.0,
                    "min_contact_ratio": 0.15,
                },
            )
            self.rewards.per_leg_excess_swing = RewTerm(
                func=custom_mdp.per_leg_excess_swing_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v61,
                    "contact_threshold": 1.0,
                    "max_swing_ratio": 0.70,
                },
            )
            self.rewards.pair_lock = RewTerm(
                func=custom_mdp.diagonal_pair_lock_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v61,
                    "contact_threshold": 1.0,
                    "gap_threshold": 0.45,
                },
            )

            # 최소 안정성
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -1.0
            self.rewards.action_rate_l2.weight = -0.05
            self.rewards.dof_torques_l2.weight = -0.0001

        # ══════════════════════════════════════════════════════════
        # V62: Phase-Gated Trot — drag/shuffle 해 약화 + 진짜 trot 유도
        # V61.C 기반, 3가지 변경:
        #   1) lin_vel_x=(0.08, 0.25) — 저속 정적 해 제거
        #   2) phase_gated_diagonal_propulsion — late-stance에서만 보상
        #   3) feet_air_time weight 2→4 — swing 품질 강화
        # Codex + Claude 공동 분석: V61.C의 drag exploit은 propulsion이
        # phase를 안 보기 때문. phase gate로 "올바른 위상에서 밀어야 상" 연결.
        # ══════════════════════════════════════════════════════════
        if _IS_V62:
            # ── Control (V61과 동일) ──
            self.action_warmup_steps = 5
            self.actions.joint_pos.scale = 0.25
            self.decimation = 4
            self.episode_length_s = 20.0

            # ── Commands: 저속 정적 해 제거 ──
            self.commands.base_velocity.heading_command = False
            self.commands.base_velocity.rel_standing_envs = 0.0
            self.commands.base_velocity.rel_heading_envs = 0.0
            self.commands.base_velocity.ranges.lin_vel_x = (0.08, 0.25)  # [V62] 0.0→0.08: 저속 정적 해 제거
            self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
            self.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)

            # ── Events (V61과 동일) ──
            self.events.reset_robot_joints.params["position_range"] = (0.9, 1.1)
            self.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)
            self.events.reset_base.params["pose_range"]["x"] = (-0.1, 0.1)
            self.events.reset_base.params["pose_range"]["y"] = (-0.1, 0.1)
            self.events.reset_base.params["pose_range"]["yaw"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["x"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["y"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["z"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["roll"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["pitch"] = (0.0, 0.0)
            self.events.reset_base.params["velocity_range"]["yaw"] = (0.0, 0.0)
            self.events.add_base_mass = None
            self.events.base_com = None
            self.events.base_external_force_torque = None
            self.events.push_robot = None

            # ── Terminations (V61과 동일) ──
            self.terminations.min_height.params["min_height"] = 0.14
            self.terminations.bad_orientation = DoneTerm(
                func=custom_mdp.bad_orientation_grace,
                params={
                    "limit_angle": 0.52,
                    "grace_steps": 150,
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )
            self.terminations.shoulder_splay = None
            self.terminations.posture_violation = None
            self.terminations.feet_lifted = None
            self.terminations.base_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names="base_link"),
                    "threshold": 1.0,
                },
            )
            self.terminations.non_toe_contact = DoneTerm(
                func=isaaclab_mdp.illegal_contact,
                params={
                    "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*foot_link|.*leg_link"),
                    "threshold": 1.0,
                },
            )
            toe_term_v62 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.terminations.pair_lock = DoneTerm(
                func=custom_mdp.prolonged_pair_lock_termination,
                params={
                    "sensor_cfg": toe_term_v62,
                    "contact_threshold": 1.0,
                    "gap_threshold": 0.50,
                    "grace_steps": 100,
                    "consecutive_steps": 30,
                },
            )

            # ── Curriculum: 없음 ──
            self.curriculum.reward_weights = None

            # ── Observations: phase clock ON ──
            self.observations.policy.phase_clock = ObsTerm(
                func=custom_mdp.phase_clock_obs,
                params={"frequency": 2.0},
            )

            # ── Rewards: V61 기반 + phase-gated propulsion ──
            keep_reward_names = {
                "track_lin_vel_xy_exp",
                "track_ang_vel_z_exp",
                "lin_vel_z_l2",
                "ang_vel_xy_l2",
                "action_rate_l2",
                "flat_orientation_l2",
                "dof_torques_l2",
                "flat_orientation_bonus",
            }
            for attr in list(vars(self.rewards).keys()):
                if attr.startswith("_") or attr in keep_reward_names:
                    continue
                try:
                    setattr(self.rewards, attr, None)
                except Exception:
                    pass

            # [주연] phase-conditioned contact
            toe_sensor_v62 = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            self.rewards.phase_contact = RewTerm(
                func=custom_mdp.phase_contact_reward,
                weight=10.0,
                params={
                    "sensor_cfg": toe_sensor_v62,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "contact_threshold": 1.0,
                    "standing_vel_threshold": 0.02,  # [V62] 저속 정적 해 방지
                },
            )

            # 속도 추종
            self.rewards.track_lin_vel_xy_exp.weight = 4.0
            self.rewards.track_lin_vel_xy_exp.params["std"] = 0.15
            self.rewards.track_ang_vel_z_exp.weight = 1.0
            self.rewards.track_ang_vel_z_exp.params["std"] = 0.25

            # 전진
            self.rewards.forward_velocity = RewTerm(
                func=custom_mdp.forward_velocity_reward,
                weight=3.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )

            # 수평
            self.rewards.flat_orientation_bonus = RewTerm(
                func=custom_mdp.flat_orientation_bonus,
                weight=3.0,
                params={"asset_cfg": SceneEntityCfg("robot")},
            )
            self.rewards.flat_orientation_l2.weight = -2.0

            # [V62 변경] feet_air_time weight 2→4: swing 품질 강화
            self.rewards.feet_air_time = RewTerm(
                func=velocity_mdp.feet_air_time,
                weight=4.0,  # [V62] 2.0→4.0
                params={
                    "command_name": "base_velocity",
                    "sensor_cfg": toe_sensor_v62,
                    "threshold": 0.1,
                },
            )

            # [V62 핵심] phase-gated 대각 교대 propulsion
            # late-stance에서만 push-off 보상 → drag/crawl 차단
            self.rewards.propulsion = RewTerm(
                func=custom_mdp.phase_gated_diagonal_propulsion_reward,
                weight=8.0,
                params={
                    "sensor_cfg": toe_sensor_v62,
                    "foot_cfg": SceneEntityCfg("robot", body_names=".*toe_link"),
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_push_vel": 0.3,
                    "min_vel": 0.05,
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "gate_sharpness": 5.0,
                },
            )

            # exploit 방지 penalty
            self.rewards.per_leg_contact_min = RewTerm(
                func=custom_mdp.per_leg_contact_min_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v62,
                    "contact_threshold": 1.0,
                    "min_contact_ratio": 0.15,
                },
            )
            self.rewards.per_leg_excess_swing = RewTerm(
                func=custom_mdp.per_leg_excess_swing_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v62,
                    "contact_threshold": 1.0,
                    "max_swing_ratio": 0.70,
                },
            )
            self.rewards.pair_lock = RewTerm(
                func=custom_mdp.diagonal_pair_lock_penalty,
                weight=-5.0,
                params={
                    "sensor_cfg": toe_sensor_v62,
                    "contact_threshold": 1.0,
                    "gap_threshold": 0.45,
                },
            )

            # 최소 안정성
            self.rewards.lin_vel_z_l2.weight = -2.0
            self.rewards.ang_vel_xy_l2.weight = -1.0
            self.rewards.action_rate_l2.weight = -0.05
            self.rewards.dof_torques_l2.weight = -0.0001

        # ══════════════════════════════════════════════════════════
        # V63.B: Symmetric Efficient Trot (V62 resume 보강)
        # V62 reward 구조 그대로 + 3개 항목 추가:
        #   1) pair_lr_symmetry_penalty (-0.3): pair 내 L/R 대칭, front+rear 동시
        #   2) stance_slip_penalty (-0.05): world frame foot slip 억제
        #   3) phase_foot_reach_reward (+1.0): phase별 base-frame foot x 직접 추적
        #      → stationary tapping 차단 (가장 확실한 방법)
        # observation/action 차원 동일 → V62 체크포인트 resume 가능.
        # 수치 검증: plan/V63.B_PLAN.md
        # ══════════════════════════════════════════════════════════
        if _IS_V63B:
            toe_sensor_v63b = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63b = SceneEntityCfg("robot", body_names=".*toe_link")

            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63b,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63b,
                    "foot_cfg": foot_cfg_v63b,
                    "contact_threshold": 1.0,
                },
            )
            # [V63.B 핵심] phase별 foot 위치 직접 추적 → stationary tapping 차단
            self.rewards.phase_foot_reach = RewTerm(
                func=custom_mdp.phase_foot_reach_reward,
                weight=1.0,
                params={
                    "foot_cfg": foot_cfg_v63b,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "reach_amplitude": 0.05,
                    "lift_amplitude": 0.0,  # V63.B: x만
                    "duty_factor": 0.55,
                    "std": 0.04,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.C: Full-Trajectory Trot (V63.B 재설계)
        # V63.B 실패 원인:
        #   1) phase_foot_reach가 x만 추적 → drag-with-timing 해 허용
        #   2) weight +1.0이 phase_contact(10)+propulsion(8) 대비 약함
        #   3) feet_air_time -0.11 (발 거의 안 뜸)
        # V63.C 변경:
        #   1) phase_foot_reach를 (x, z) 2D로 확장 (lift_amplitude=0.04)
        #   2) weight 재균형:
        #      phase_contact 10→6, propulsion 8→4, feet_air 4→6, foot_reach 1→5
        #   3) from-scratch (V63.B 편향 회피)
        # 수치 검증: plan/V63.C_PLAN.md
        # ══════════════════════════════════════════════════════════
        if _IS_V63C:
            toe_sensor_v63c = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63c = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.C weight 재균형 ──
            # phase_contact: 10 → 6 (foot_reach가 timing도 암묵 인코딩)
            self.rewards.phase_contact.weight = 6.0
            # propulsion: 8 → 4 (foot_reach와 경쟁 완화)
            self.rewards.propulsion.weight = 4.0
            # feet_air_time: 4 → 6 (발 들기 직접 보상 강화)
            self.rewards.feet_air_time.weight = 6.0

            # ── V63.C 2D foot_reach (dominant) ──
            self.rewards.phase_foot_reach = RewTerm(
                func=custom_mdp.phase_foot_reach_reward,
                weight=5.0,  # V63.B +1.0 → V63.C +5.0 (5배 강화)
                params={
                    "foot_cfg": foot_cfg_v63c,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "reach_amplitude": 0.05,  # x 전후 stride
                    "lift_amplitude": 0.04,   # z 높이 (V63.C 신규)
                    "duty_factor": 0.55,
                    "std": 0.035,
                },
            )

            # ── V63.B에서 이어받은 penalty 2개 (V63.C에서도 유지) ──
            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63c,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63c,
                    "foot_cfg": foot_cfg_v63c,
                    "contact_threshold": 1.0,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.D: Joint-Level Reference Motion
        # V63.B (1D foot_reach) / V63.C (2D foot_reach) 모두 실패:
        #   - foot 위치 target이 FK 경유로 학습 어려움
        #   - feet_air_time 음수 지속 (발 거의 안 듦)
        #   - PPO가 발 들기 exploration 못함 (생존 trade-off)
        # V63.D 해결:
        #   - Foot 위치 대신 **joint 각도 직접 target**
        #   - leg (hip pitch) = cos(phase) 연속 왕복
        #   - foot (knee) = swing phase에만 parabolic 접힘
        #   - gradient chain 짧음 (action → joint → reward)
        #   - dominant weight +10.0
        # 수치 검증: plan/V63.D_PLAN.md
        # ══════════════════════════════════════════════════════════
        if _IS_V63D:
            toe_sensor_v63d = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63d = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.D weight 재배치 ──
            # phase_contact: V62 10 → 4 (joint_target이 dominant)
            self.rewards.phase_contact.weight = 4.0
            # propulsion: V62 8 → 4 (경쟁 완화)
            self.rewards.propulsion.weight = 4.0
            # feet_air_time: V62 4 유지
            self.rewards.feet_air_time.weight = 4.0

            # V63.B/C의 phase_foot_reach 제거 (V63.D에서 joint_target이 대체)
            if hasattr(self.rewards, "phase_foot_reach"):
                self.rewards.phase_foot_reach = None

            # ── V63.D 핵심: joint-level reference motion ──
            self.rewards.phase_joint_target = RewTerm(
                func=custom_mdp.phase_joint_target_reward,
                weight=10.0,  # dominant
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "A_leg": 0.25,   # 14° hip pitch swing
                    "A_foot": 0.35,  # 20° knee bend during swing
                    "std": 0.3,
                },
            )

            # ── V63.B에서 이어받은 penalty 2개 (V63.D에서도 유지) ──
            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63d,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63d,
                    "foot_cfg": foot_cfg_v63d,
                    "contact_threshold": 1.0,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.E: Linear Reward + Curriculum (V63.B/C/D 세 번 실패 후 근본 전환)
        # V63.B/C/D 공통 실패 원인: Sharp exp reward → 초기 gradient 0
        # V63.E 해결:
        #   1) Linear clamp reward (모든 구간에서 non-zero, dense gradient)
        #   2) Amplitude curriculum: A_leg 3°→14°, A_foot 6°→20° (iter 0→1500)
        #   3) Balanced weight 3.0 (dominant 아님)
        #   4) phase_contact 6.0 (생존), propulsion 2.0 (drag 유인 약화)
        # 수치 검증: plan/V63.E_PLAN.md, 실험 로그: plan/V63_SERIES_LOG.md
        # ══════════════════════════════════════════════════════════
        if _IS_V63E:
            toe_sensor_v63e = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63e = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.E weight 재배치 ──
            self.rewards.phase_contact.weight = 6.0  # V62 10 → 6 (생존 안정)
            self.rewards.propulsion.weight = 2.0     # V62 8 → 2 (drag 유인 약화)
            self.rewards.feet_air_time.weight = 4.0  # V62 동일

            # V63.B/C의 phase_foot_reach 제거
            if hasattr(self.rewards, "phase_foot_reach"):
                self.rewards.phase_foot_reach = None
            # V63.D의 phase_joint_target 제거
            if hasattr(self.rewards, "phase_joint_target"):
                self.rewards.phase_joint_target = None

            # ── V63.E.1 조정: err_max 완화 + 더 느린 curriculum + 더 작은 초기 amplitude ──
            # V63.E 실패 원인: err_total이 err_max(1.5) 꽉 참 → reward 0 근접 → gradient 약함
            # V63.E.1: err_max 1.5→3.0 (관대), curriculum 1500→2500 (느림),
            #          A_start 더 작게 (초기 학습 신호 확보)
            self.rewards.phase_joint_target_linear = RewTerm(
                func=custom_mdp.phase_joint_target_linear_reward,
                weight=3.0,  # balanced
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "A_leg_start": 0.03,    # V63.E 0.05 → 0.03 (1.7°, 더 쉬움)
                    "A_leg_end": 0.25,      # 14° (최종 동일)
                    "A_foot_start": 0.05,   # V63.E 0.10 → 0.05 (2.9°, 더 쉬움)
                    "A_foot_end": 0.35,     # 20° (최종 동일)
                    "curriculum_iters": 2500,  # V63.E 1500 → 2500 (더 천천히)
                    "err_max": 3.0,         # V63.E 1.5 → 3.0 (2배 관대)
                },
            )

            # ── V63.B에서 이어받은 penalty 2개 (V63.E에서도 유지) ──
            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63e,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63e,
                    "foot_cfg": foot_cfg_v63e,
                    "contact_threshold": 1.0,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.F: Dominant Weight + 관대한 err_max + 3 Metrics
        # V63.E.1 실패 (peak 0.141 후 하락) 분석:
        #   - weight 3.0은 budget 13%로 dominant 아님
        #   - curriculum 40%에서 정체 → 남은 60% 하락 예상
        # V63.F 해결:
        #   1) weight 3→8 (dominant, 35% budget)
        #   2) phase_contact 6→3, propulsion 2→1 (경쟁 약화)
        #   3) err_max 3→4 (더 관대)
        #   4) A_end 완화 (0.25→0.20, 0.35→0.28)
        #   5) curriculum 2500→3500 (느리게)
        #   6) metric 3개 추가 (clearance, anti_phase, leg_usage_cv)
        # 수치 검증: plan/V63.F_PLAN.md
        # ══════════════════════════════════════════════════════════
        if _IS_V63F:
            toe_sensor_v63f = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63f = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.F.1 weight 재조정 (V63.F exploit 해결) ──
            # V63.F 문제: joint_target 0.74 도달 but anti_phase 0.04 (대각 교대 없음)
            # = stationary joint wiggle exploit
            # 해결: joint_target dominant 완화 + phase_contact 복원 + anti_phase reward 승격
            self.rewards.phase_contact.weight = 6.0  # V63.F 3.0 → 6.0 (구조 강제)
            self.rewards.propulsion.weight = 2.0     # V63.F 1.0 → 2.0 (약간 복원)
            self.rewards.feet_air_time.weight = 4.0  # 유지

            # V63.B/C의 phase_foot_reach 제거
            if hasattr(self.rewards, "phase_foot_reach"):
                self.rewards.phase_foot_reach = None
            # V63.D의 phase_joint_target 제거
            if hasattr(self.rewards, "phase_joint_target"):
                self.rewards.phase_joint_target = None

            # ── V63.F.1: joint_target weight 완화 (dominant 해제) ──
            self.rewards.phase_joint_target_linear = RewTerm(
                func=custom_mdp.phase_joint_target_linear_reward,
                weight=5.0,  # V63.F 8.0 → 5.0 (exploit 완화)
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "A_leg_start": 0.03,
                    "A_leg_end": 0.20,
                    "A_foot_start": 0.05,
                    "A_foot_end": 0.28,
                    "curriculum_iters": 3500,
                    "err_max": 4.0,
                },
            )

            # ── V63.B/E.1에서 이어받은 penalty 2개 ──
            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63f,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63f,
                    "foot_cfg": foot_cfg_v63f,
                    "contact_threshold": 1.0,
                },
            )

            # ── V63.F.1: anti_phase를 metric → REWARD로 승격 ──
            # V63.F exploit 해결: 대각 교대를 직접 보상
            # 정상 trot anti_phase 0.5+ × weight 3.0 = +1.5 per-step
            # 현재 exploit 0.04 × 3.0 = +0.12 per-step
            # → trot vs exploit 차이 +1.38 per-step (강한 신호)
            self.rewards.metric_anti_phase = RewTerm(
                func=custom_mdp.metric_anti_phase_contact_reward,
                weight=3.0,  # V63.F 1e-4 → V63.F.1 3.0 (REWARD 승격)
                params={
                    "sensor_cfg": toe_sensor_v63f,
                    "contact_threshold": 1.0,
                },
            )

            # ── Metric 2개는 유지 (clearance, leg_usage_cv) ──
            self.rewards.metric_clearance = RewTerm(
                func=custom_mdp.metric_clearance_mean_reward,
                weight=1e-4,
                params={
                    "sensor_cfg": toe_sensor_v63f,
                    "foot_cfg": foot_cfg_v63f,
                    "contact_threshold": 1.0,
                },
            )
            self.rewards.metric_leg_usage_cv = RewTerm(
                func=custom_mdp.metric_leg_usage_cv_reward,
                weight=1e-4,
                params={
                    "sensor_cfg": toe_sensor_v63f,
                    "contact_threshold": 1.0,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.G: Asymmetric Target + Intra-pair Sync + leg_usage Penalty
        # V63.F.1 GUI 관찰 (사용자):
        #   1. RR이 가짜로 차고 다른 3발은 발 끌기 (1발 exploit)
        #   2. 윗다리(hip pitch)가 안 올라옴 (수평 가까이 필요)
        #   3. FL-RR / FR-RL intra-pair 동기 안 됨 (가짜 trot)
        # 해결:
        #   1) asymmetric_joint_target_reward (stance/swing 분리, 큰 lift)
        #   2) intra_pair_sync_reward (+4) — 사용자 두 번째 지적
        #   3) leg_usage_cv_penalty (-3) — RR exploit 차단
        #   4) per_leg_propulsion_balance_reward (+2) — 4발 균등 추진
        #   5) phase_foot_reach, phase_joint_target_linear, V63.F metric 모두 제거
        # ══════════════════════════════════════════════════════════
        if _IS_V63G:
            toe_sensor_v63g = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63g = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.G weight 재배치 ──
            self.rewards.phase_contact.weight = 4.0
            self.rewards.propulsion.weight = 2.0
            self.rewards.feet_air_time.weight = 4.0

            # 이전 버전 reward 제거
            if hasattr(self.rewards, "phase_foot_reach"):
                self.rewards.phase_foot_reach = None
            if hasattr(self.rewards, "phase_joint_target"):
                self.rewards.phase_joint_target = None
            if hasattr(self.rewards, "phase_joint_target_linear"):
                self.rewards.phase_joint_target_linear = None
            if hasattr(self.rewards, "metric_clearance"):
                self.rewards.metric_clearance = None
            if hasattr(self.rewards, "metric_anti_phase"):
                self.rewards.metric_anti_phase = None
            if hasattr(self.rewards, "metric_leg_usage_cv"):
                self.rewards.metric_leg_usage_cv = None

            # ── V63.G.2: Asymmetric target params 복원 (V63.G의 23°) + clearance reward 도입 ──
            # V63.G.1의 31.5°는 과함, joint target만 올린다고 policy가 따라가지 않음
            # → V63.G의 23°로 복원 + clearance를 직접 reward로 보강
            self.rewards.asymmetric_joint_target = RewTerm(
                func=custom_mdp.asymmetric_joint_target_reward,
                weight=5.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "A_leg_lift_start": 0.10,
                    "A_leg_lift_end": 0.40,      # V63.G.1 0.55 → 0.40 (V63.G 23° 복원)
                    "A_foot_bend_start": 0.15,
                    "A_foot_bend_end": 0.50,     # V63.G.1 0.65 → 0.50 (V63.G 28° 복원)
                    "stance_pull_back": 0.05,
                    "curriculum_iters": 1500,    # V63.G.1 2000 → 1500
                    "err_max": 4.0,              # V63.G.1 5.0 → 4.0
                },
            )

            # ── V63.G.1: TRUE TROT PATTERN (intra × inter 곱) — V63.G.2 그대로 유지 ──
            self.rewards.true_trot_pattern = RewTerm(
                func=custom_mdp.true_trot_pattern_reward,
                weight=5.0,
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "contact_threshold": 1.0,
                },
            )

            # ── V63.G.2 신규: Clearance lift reward (literal 발 높이 직접 보상) ──
            self.rewards.clearance_lift = RewTerm(
                func=custom_mdp.clearance_lift_reward,
                weight=4.0,
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "foot_cfg": foot_cfg_v63g,
                    "contact_threshold": 1.0,
                    "target_clearance": 0.03,
                },
            )

            # ── V63.G.3 신규: Shoulder neutral penalty (11자 강제) ──
            # 사용자 GUI 두 번 지적: 다리가 八자/ㅅ자로 벌어짐
            # V63 시리즈 전체가 shoulder를 자유롭게 둠 → fix 필요
            # target_angle = 0 (완전 11자, default ±0.15도 허용 안 함)
            self.rewards.shoulder_neutral = RewTerm(
                func=custom_mdp.shoulder_neutral_penalty,
                weight=-2.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "target_angle": 0.0,  # 완전 11자
                },
            )

            # ── V63.G 핵심 3: leg_usage_cv PENALTY (RR exploit 차단) ──
            self.rewards.leg_usage_cv = RewTerm(
                func=custom_mdp.leg_usage_cv_penalty,
                weight=-3.0,  # V63.F 1e-4 metric → V63.G -3.0 강한 penalty
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "contact_threshold": 1.0,
                    "cv_threshold": 0.3,
                    "cv_max": 2.0,
                },
            )

            # ── V63.G 핵심 4: per-leg propulsion balance ──
            self.rewards.per_leg_propulsion_balance = RewTerm(
                func=custom_mdp.per_leg_propulsion_balance_reward,
                weight=2.0,
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "foot_cfg": foot_cfg_v63g,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_push_vel": 0.3,
                },
            )

            # ── V63.B에서 이어받은 penalty 2개 ──
            self.rewards.pair_lr_symmetry = RewTerm(
                func=custom_mdp.pair_lr_symmetry_penalty,
                weight=-0.3,
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "contact_threshold": 1.0,
                    "cr_weight": 0.5,
                },
            )
            self.rewards.stance_slip = RewTerm(
                func=custom_mdp.stance_slip_penalty,
                weight=-0.05,
                params={
                    "sensor_cfg": toe_sensor_v63g,
                    "foot_cfg": foot_cfg_v63g,
                    "contact_threshold": 1.0,
                },
            )

        # ══════════════════════════════════════════════════════════
        # V63.H: Dynamic Motion Exchange (근본 재설계)
        # V63.B~G.3 7번 실패의 공통 원인은 contact-based metric 한계.
        # 사용자 통찰: trot 본질 = "2발 들고 → body 관성 전진 → 새 위치 착지"
        # 해결: position/velocity/momentum 기반 reward로 재설계
        #
        # 핵심 신규:
        #   1) swing_body_forward_reward (+4) — swing 중 body 전진 (제자리 차단)
        #   2) effective_stride_reward (+5) — per-leg touchdown 거리 (per-leg dynamic)
        #
        # 유지: clearance_lift, true_trot_pattern, shoulder_neutral
        # 제거: asymmetric_joint_target, leg_usage_cv_penalty, prop_balance,
        #       phase_contact, propulsion, feet_air_time, pair_lr_symmetry,
        #       stance_slip, per_leg_excess_swing
        # 11개 reward → 9개로 정리
        # ══════════════════════════════════════════════════════════
        if _IS_V63H:
            toe_sensor_v63h = SceneEntityCfg("contact_forces", body_names=".*toe_link")
            foot_cfg_v63h = SceneEntityCfg("robot", body_names=".*toe_link")

            # ── V63.H reward 구조 정리 ──
            # 1. 제거 (V63.G.3에서 None)
            for attr_name in [
                "phase_contact",
                "propulsion",
                "feet_air_time",
                "phase_foot_reach",
                "phase_joint_target",
                "phase_joint_target_linear",
                "asymmetric_joint_target",
                "intra_pair_sync",
                "metric_clearance",
                "metric_anti_phase",
                "metric_leg_usage_cv",
                "leg_usage_cv",
                "per_leg_propulsion_balance",
                "per_leg_excess_swing",
                "pair_lr_symmetry",
                "stance_slip",
                "pair_lock",
            ]:
                if hasattr(self.rewards, attr_name):
                    setattr(self.rewards, attr_name, None)

            # 2. 핵심 신규 reward 2개
            self.rewards.swing_body_forward = RewTerm(
                func=custom_mdp.swing_body_forward_reward,
                weight=4.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_speed": 0.4,
                },
            )

            self.rewards.effective_stride = RewTerm(
                func=custom_mdp.effective_stride_reward,
                weight=5.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_stride": 0.05,
                },
            )

            # 3. 유지 reward 3개 (V63.G 시리즈에서 검증)
            self.rewards.clearance_lift = RewTerm(
                func=custom_mdp.clearance_lift_reward,
                weight=3.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "foot_cfg": foot_cfg_v63h,
                    "contact_threshold": 1.0,
                    "target_clearance": 0.03,
                },
            )

            # V63.H.1: pace gait 차단 위해 weight 강화
            # V63.H.4: 사용자 "이상한 박자" 지적 → trot 구조 우선 강화 (5.0 → 7.0)
            self.rewards.true_trot_pattern = RewTerm(
                func=custom_mdp.true_trot_pattern_reward,
                weight=7.0,  # V63.H 3.0 → H.1/H.2/H.3 5.0 → H.4 7.0 (박자 우선)
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "contact_threshold": 1.0,
                },
            )

            # V63.H.1 신규: pace gait 직접 차단
            self.rewards.anti_pace = RewTerm(
                func=custom_mdp.anti_pace_penalty,
                weight=-3.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "contact_threshold": 1.0,
                },
            )

            # V63.H.1 신규: 좌우 흔들림 (rolling) penalty
            self.rewards.lateral_balance = RewTerm(
                func=custom_mdp.lateral_balance_penalty,
                weight=-2.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                },
            )

            # V63.H.2: shoulder_neutral 강화 (-2 → -4) — FR 옆으로 벌리는 것 차단
            self.rewards.shoulder_neutral = RewTerm(
                func=custom_mdp.shoulder_neutral_penalty,
                weight=-4.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "target_angle": 0.0,
                },
            )

            # ── V63.H.2 신규: base_height_target (자세 높이 강제) ──
            # 사용자 V63.H.1 GUI 지적: "자세가 너무 낮아 윗다리 들 공간 없음"
            # target 0.18m로 정상 standing 강제 → 윗다리 들 공간 확보
            self.rewards.base_height_target = RewTerm(
                func=custom_mdp.base_height_target_reward,
                weight=4.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "target_height": 0.18,
                    "sigma": 0.05,
                },
            )

            # ── V63.H.2 복원: asymmetric_joint_target (윗다리 lift target) ──
            # 사용자 두 번 강조: "윗다리가 더 수평에 가깝게 올라와야"
            self.rewards.asymmetric_joint_target = RewTerm(
                func=custom_mdp.asymmetric_joint_target_reward,
                weight=5.0,
                params={
                    "asset_cfg": SceneEntityCfg("robot"),
                    "frequency": 2.0,
                    "duty_factor": 0.55,
                    "A_leg_lift_start": 0.15,
                    "A_leg_lift_end": 0.55,
                    "A_foot_bend_start": 0.20,
                    "A_foot_bend_end": 0.55,
                    "stance_pull_back": 0.05,
                    "curriculum_iters": 1500,
                    "err_max": 4.0,
                },
            )

            # ── V63.H.3 신규 1: Per-leg stance push MIN (좌우 비대칭 차단) ──
            # 사용자 V63.H.2 GUI: "FL 완벽, FR이 뒤로 힘차게 못 밀고 swing에서 급함"
            # → 4발 중 가장 약한 발의 stance propulsion을 보상
            # → FR이 약하면 전체 reward 낮음 → policy가 모든 발 균등 push 학습
            # V63.H.4: push_min weight 4.0 → 2.0 (trot 박자에 양보)
            self.rewards.per_leg_stance_push_min = RewTerm(
                func=custom_mdp.per_leg_stance_push_min_reward,
                weight=2.0,  # V63.H.3 4.0 → V63.H.4 2.0
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "foot_cfg": foot_cfg_v63h,
                    "asset_cfg": SceneEntityCfg("robot"),
                    "contact_threshold": 1.0,
                    "target_push_vel": 0.3,
                },
            )

            # ── V63.H.3 신규 2: 좌우 대칭 penalty ──
            self.rewards.leg_lr_symmetry = RewTerm(
                func=custom_mdp.leg_lr_symmetry_penalty,
                weight=-2.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "contact_threshold": 1.0,
                },
            )

            # 4. per_leg_contact_min만 유지 (1발 안 쓰기 차단)
            self.rewards.per_leg_contact_min = RewTerm(
                func=custom_mdp.per_leg_contact_min_penalty,
                weight=-3.0,
                params={
                    "sensor_cfg": toe_sensor_v63h,
                    "contact_threshold": 1.0,
                    "min_contact_ratio": 0.10,
                },
            )

            # ── V63.H.5: gait smoothness fix ──
            # 사용자 GUI 지적: "한 걸음 → 다음 걸음 전환 시 끊어짐"
            # P1: asymmetric_joint_target stance_pull_back 불연속 제거 (rewards.py 수정)
            # P2: action_rate_l2 -0.05 → -0.10 (2배, jerk 억제 강화)
            # 보수적 1차 수정 — 코덱스 리뷰 반영
            self.rewards.action_rate_l2.weight = -0.10

            # ══════════════════════════════════════════════════════════
            # V63.I: Frozen Diagonal Exploit 차단
            # 사용자 V63.H.5 model_2600 GUI: "FL, RR만 땅에 닿고 비대칭"
            # 데이터: contact_ratio FL 77% / FR 10% / RL 9% / RR 76%
            # → true_trot_pattern(intra×inter) 만점이지만 실제는 2발 hover exploit
            # → "매 순간 상관"만 측정하는 metric의 맹점
            #
            # 수정 (P1+P2+P4):
            # P1: per_leg_contact_min min_contact_ratio 0.10→0.40, weight -3→-8
            # P2: stance_ratio_balance_reward 신규 (+5.0, EMA 기반 장기 교대 강제)
            # P4: log_contact_ema_* 진단 logger (함수 내장)
            # ══════════════════════════════════════════════════════════
            if _IS_V63I:
                # P1: 기존 per_leg_contact_min 강화 (10% → 40% threshold)
                self.rewards.per_leg_contact_min = RewTerm(
                    func=custom_mdp.per_leg_contact_min_penalty,
                    weight=-8.0,  # V63.H -3.0 → V63.I -8.0
                    params={
                        "sensor_cfg": toe_sensor_v63h,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.40,  # V63.H 0.10 → V63.I 0.40
                    },
                )

                # P2: 신규 stance_ratio_balance (EMA 기반 장기 접지율 균등화)
                self.rewards.stance_ratio_balance = RewTerm(
                    func=custom_mdp.stance_ratio_balance_reward,
                    weight=5.0,
                    params={
                        "sensor_cfg": toe_sensor_v63h,
                        "contact_threshold": 1.0,
                        "target_ratio": 0.55,
                        "ema_decay": 0.99,
                        "sigma": 0.15,
                    },
                )

                # ══════════════════════════════════════════════════════════
                # V63.J: Alternation-Aware Trot + Role Balance
                # ══════════════════════════════════════════════════════════
                # V63.I 진단 결론:
                #   - true_trot_pattern은 편향 trot에 더 높은 점수 부여 (시간축 교대 없음)
                #   - penalty(diagonal_pair_balance, leg_lr_symmetry)만으로 못 깸
                #   - 원인: 정책 symmetry breaking (물리 대칭 검증 완료)
                #
                # 해결 철학 (코덱스):
                #   1. 주연 = "반 사이클마다 역할이 실제로 바뀌는가" (alternation)
                #   2. 보조 = per-leg propulsion/lift 분산 감소
                #   3. 기존 true_trot_pattern 약화 공존 (7→2)
                #   4. diagonal_pair_balance 제거 (alternation이 대체)
                # ══════════════════════════════════════════════════════════
                if _IS_V63J:
                    # 1. 주연: alternation_trot_reward (+5.0)
                    self.rewards.alternation_trot = RewTerm(
                        func=custom_mdp.alternation_trot_reward,
                        weight=5.0,
                        params={
                            "sensor_cfg": toe_sensor_v63h,
                            "contact_threshold": 1.0,
                            "frequency": 2.0,
                            "window": 3,
                        },
                    )

                    # 2. 기존 true_trot_pattern 약화 (7→2, 보조 역할로 유지)
                    self.rewards.true_trot_pattern.weight = 2.0

                    # 3. per-leg role variance penalty (-2.0, propulsion+lift)
                    self.rewards.per_leg_role_variance = RewTerm(
                        func=custom_mdp.per_leg_role_variance_penalty,
                        weight=-2.0,
                        params={
                            "sensor_cfg": toe_sensor_v63h,
                            "foot_cfg": foot_cfg_v63h,
                            "asset_cfg": SceneEntityCfg("robot"),
                            "contact_threshold": 1.0,
                            "ema_decay": 0.99,
                        },
                    )

                    # 4. diagonal_pair_balance 제거 (alternation이 대체)
                    if hasattr(self.rewards, "diagonal_pair_balance"):
                        self.rewards.diagonal_pair_balance = None

                    # 5. leg_lr_symmetry -2.0 유지 (약한 보조)
                    # (V63.I 원래 값 그대로, 변경 없음)

            # ══════════════════════════════════════════════════════════
            # V64: Mirror Symmetry Augmentation
            # ══════════════════════════════════════════════════════════
            # V63 시리즈 교훈:
            #   - reward penalty로는 정책 symmetry breaking 못 깸
            #   - 학습 구조 자체를 바꿔야 함
            # 해결:
            #   - Isaac Lab 내장 RslRlSymmetryCfg.data_augmentation_func
            #   - PPO 학습 시 rollout 데이터를 좌우 반전하여 augmented batch
            #   - policy가 구조적으로 좌우 대칭 표현 학습
            # Reward 정리 (코덱스 권장):
            #   - V63.J의 alternation/role_variance 제거 (mirror가 대칭 해결)
            #   - V63.I base 그대로 유지 (검증된 구조)
            #   - diagonal_pair_balance 제거
            #   - leg_lr_symmetry 제거 (mirror augmentation이 대체)
            # ══════════════════════════════════════════════════════════
            if _IS_V64:
                # V63.J 잔여물 제거 (V63.I base로 복귀)
                for attr_name in [
                    "alternation_trot",
                    "per_leg_role_variance",
                    "diagonal_pair_balance",
                ]:
                    if hasattr(self.rewards, attr_name):
                        setattr(self.rewards, attr_name, None)

                # true_trot_pattern: V63.I 원래 weight 7.0 유지
                # (mirror augmentation이 대칭 해결, reward는 trot 유도에 집중)

                # leg_lr_symmetry 유지 (-2.0) — frozen diagonal 방어 핵심!
                # V64 초기 설계에서 제거했으나, 이 penalty가 frozen diagonal에
                # -2.70/step을 부과하여 exploit 차단의 핵심이었음.
                # mirror augmentation은 PPO update-level soft constraint이지
                # per-step gradient를 제공하지 못해 이 역할을 대체 못함.
                # 따라서 leg_lr_symmetry(-2.0) + mirror loss 병행이 올바름.
                pass  # leg_lr_symmetry -2.0 유지 (V63.I 원래 값)

            # ══════════════════════════════════════════════════════════
            # V65: Curriculum Trot — true_trot → alternation 전환
            # ══════════════════════════════════════════════════════════
            # 근본 원인: true_trot_pattern이 frozen diagonal 보상 (시간축 교대 미요구)
            # V63.I~V64 모든 penalty가 이 exploit 보상을 이기지 못함 (데이터 확정)
            #
            # 해결: Curriculum으로 닭-달걀 분리
            #   Phase 1 (0~800): true_trot=4.0 → gait 부트스트랩
            #   Phase 2 (800~3000): true_trot 4→0.5 + alternation 0→5
            #   Phase 3 (3000+): alternation=5.0 주연, true_trot=0.5 보조
            #
            # per_leg_contact: 지수 penalty (threshold ramp 0.30→0.40, clamp 8.0)
            # leg_lr_symmetry: -2.0 유지 (보조 안전장치)
            # mirror_loss: 유지 (보조 regularizer)
            # ══════════════════════════════════════════════════════════
            if _IS_V65:
                # 1. V63.J/V64 잔여물 정리 (V63.I base로 복귀)
                for attr_name in [
                    "alternation_trot",
                    "per_leg_role_variance",
                    "diagonal_pair_balance",
                ]:
                    if hasattr(self.rewards, attr_name):
                        setattr(self.rewards, attr_name, None)

                # 2. true_trot_pattern: V63.I 동일 (부팅 보장)
                # V65/V65.1 실패 교훈: 4.0은 부트스트랩에 부족
                # curriculum이 gate 통과 후 7→3→0.5로 ramp-down
                self.rewards.true_trot_pattern.weight = 7.0

                # 3. alternation_trot 등록 (초기 weight 0, curriculum이 ramp-up)
                self.rewards.alternation_trot = RewTerm(
                    func=custom_mdp.alternation_trot_reward,
                    weight=0.0,  # curriculum이 800→3000에서 0→5.0으로 ramp
                    params={
                        "sensor_cfg": toe_sensor_v63h,
                        "contact_threshold": 1.0,
                        "frequency": 2.0,
                        "window": 3,
                    },
                )

                # 4. per_leg_contact: 선형(V63.I) 유지 + 지수는 초기 비활성 (curriculum이 gate 후 활성화)
                # V65 교훈: 지수 penalty가 부팅 단계에서 alive_bonus 압도 → 서기 실패
                # V65.2: Phase 1은 V63.I 동일 (per_leg_contact_min만), 지수는 weight 0으로 시작
                # per_leg_contact_min: V63.I 그대로 유지 (threshold 0.40, weight -8)
                self.rewards.per_leg_contact_exp = RewTerm(
                    func=custom_mdp.per_leg_contact_exp_penalty,
                    weight=0.0,  # Phase 1: 비활성! curriculum이 gate 후 -0.5 → -1.0 ramp
                    params={
                        "sensor_cfg": toe_sensor_v63h,
                        "contact_threshold": 1.0,
                        "min_contact_ratio": 0.20,
                        "sharpness": 8.0,
                        "max_penalty": 5.0,
                        "threshold_ramp_start": 1500,
                        "threshold_ramp_end": 3000,
                        "threshold_final": 0.35,
                    },
                )

                # 5. Curriculum term (조건부 gate + ramp)
                # V65.2: Phase 1은 V63.I 동일, gate(ep_len>900, timeout>80%) 통과 후 전환
                self.curriculum.reward_weights = CurrTerm(
                    func=custom_mdp.v65_trot_curriculum,
                    params={
                        "trot_start": 7.0,   # V63.I 동일
                        "trot_end": 0.5,
                        "alt_start": 0.0,
                        "alt_end": 5.0,
                        "update_interval": 10,
                    },
                )

                # 6. leg_lr_symmetry -2.0 유지 (V63.I 원래 값, 보조 안전장치)
                # (상속됨, 변경 없음)

            # ══════════════════════════════════════════════════════════
            # V66: Phase Randomization (최소 변경, 구조적 대칭)
            # ══════════════════════════════════════════════════════════
            # 근본 원인 재분석:
            #   모든 4096 env가 동일 phase(FL=0, FR=π)에서 시작
            #   → FL+RR이 항상 "첫 stance" → gradient 일관 편향 → frozen diagonal
            #
            # 해결: episode reset 시 env별 random phase offset (0 또는 π)
            #   → 50% env: FL first stance, 50%: FR first stance
            #   → policy gradient 평균 편향 0 → 구조적 대칭
            #
            # V64(mirror augmentation), V65(curriculum) 대비 장점:
            #   - phantom 데이터 없음 (실제 env 경험만)
            #   - phase 모순 없음 (offset이 phase_clock + joint_target 양쪽에 적용)
            #   - 부팅 지연 없음 (V63.I reward 그대로)
            #   - 20줄 수정으로 해결
            #
            # Reward: V63.I 완전 동일 (검증된 구조, 변경 없음)
            # Mirror loss/curriculum/alternation: 불필요 → 제거
            # ══════════════════════════════════════════════════════════
            if _IS_V66:
                # V65 잔여물 정리 (V63.I base 복귀)
                for attr_name in [
                    "alternation_trot",
                    "per_leg_role_variance",
                    "diagonal_pair_balance",
                    "per_leg_contact_exp",
                ]:
                    if hasattr(self.rewards, attr_name):
                        setattr(self.rewards, attr_name, None)

                # V65 curriculum 제거
                self.curriculum.reward_weights = None

                # true_trot_pattern: V63.I 원래 weight 7.0 유지
                # leg_lr_symmetry: -2.0 유지
                # per_leg_contact_min: -8.0, threshold 0.40 유지
                # stance_ratio_balance: +5.0 유지


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
