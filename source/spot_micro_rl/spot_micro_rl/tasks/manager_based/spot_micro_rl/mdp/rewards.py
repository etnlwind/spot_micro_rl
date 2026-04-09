# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Custom reward functions for SpotMicro locomotion."""

from __future__ import annotations

import math
import torch
from typing import TYPE_CHECKING

from isaaclab.assets import Articulation
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor
from isaaclab.utils.math import wrap_to_pi

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def alive_bonus(env: ManagerBasedRLEnv) -> torch.Tensor:
    """Per-step survival bonus. Returns 1.0 for every alive environment."""
    return torch.ones(env.num_envs, device=env.device)


# ═══════════════════════════════════════════
# V39: CPG / Phase Clock
# ═══════════════════════════════════════════

def phase_clock_obs(
    env: ManagerBasedRLEnv,
    frequency: float = 2.0,
) -> torch.Tensor:
    """Phase clock observation: sin/cos per leg for trot gait.

    V39: 4다리 각각의 phase를 sin/cos로 인코딩하여 8차원 observation 반환.
    Trot 패턴: FL/RR 동위상, FR/RL 반위상.

    Args:
        frequency: trot 주파수 (Hz). 1 cycle = stance + swing.
    Returns:
        (num_envs, 8) tensor: [sin_FL, sin_FR, sin_RL, sin_RR, cos_FL, cos_FR, cos_RL, cos_RR]
    """
    t = env.episode_length_buf.float() * env.step_dt  # (num_envs,)
    base_phase = 2.0 * math.pi * frequency * t  # (num_envs,)

    # Trot: FL/RR = base, FR/RL = base + π
    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase

    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)  # (num_envs, 4)
    sin_cos = torch.cat([torch.sin(phases), torch.cos(phases)], dim=1)  # (num_envs, 8)
    return sin_cos


def phase_contact_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    contact_threshold: float = 1.0,
    standing_vel_threshold: float = 0.08,
    aggregation_mode: str = "mean",
    ema_alpha: float = 0.0,
    min_target: float = 0.60,
    swing_penalty_alpha: float = 0.0,
) -> torch.Tensor:
    """Phase-conditioned contact reward with optional swing violation penalty.

    stance phase에서 접지, swing phase에서 이탈하면 보상.
    standing command (|vel| < threshold)일 때는 all-stance (4발 접지).

    V61 추가: swing_penalty_alpha > 0이면 swing phase에 접지한 다리에
    적극적 감점을 부여. 이것이 없으면 "4발 항상 접지"도 55% match로
    높은 점수를 받는 phase-matched 정적 해 exploit이 가능.

    score = stance_match + swing_match - alpha * swing_violation
    swing_violation = 접지(1) AND swing phase(expected=0) = 잘못된 접촉
    """
    contact_sensor: ContactSensor = env.scene[sensor_cfg.name]
    forces = contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids, :].norm(dim=-1)
    is_contact = (forces > contact_threshold).float()  # (num_envs, 4)

    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t

    # Trot phases: FL/RR=0, FR/RL=π
    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase
    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)

    phase_norm = phases % (2.0 * math.pi)
    stance_threshold_val = duty_factor * 2.0 * math.pi
    expected_contact = (phase_norm < stance_threshold_val).float()

    # Standing command: |vel_cmd| < threshold → all-stance
    vel_cmd = env.command_manager.get_command("base_velocity")[:, :2]
    vel_magnitude = vel_cmd.norm(dim=1)
    is_standing = (vel_magnitude < standing_vel_threshold).unsqueeze(1)  # (num_envs, 1)
    expected_contact = torch.where(is_standing.expand_as(expected_contact),
                                   torch.ones_like(expected_contact),
                                   expected_contact)

    # match = 올바른 상태 (접지 AND stance, 또는 이탈 AND swing)
    match = (is_contact == expected_contact).float()

    # swing violation = swing phase인데 접지 (잘못된 접촉)
    swing_violation = is_contact * (1.0 - expected_contact)  # (num_envs, 4)

    # score = match - alpha * violation
    score_per_leg = match - swing_penalty_alpha * swing_violation

    if ema_alpha > 0.0:
        if not hasattr(env, "_phase_contact_ema"):
            env._phase_contact_ema = score_per_leg.clone()
        else:
            reset_mask = (env.episode_length_buf <= 1).unsqueeze(1)
            env._phase_contact_ema = torch.where(
                reset_mask,
                score_per_leg,
                ema_alpha * env._phase_contact_ema + (1.0 - ema_alpha) * score_per_leg,
            )
        score_src = env._phase_contact_ema
    else:
        score_src = score_per_leg

    mean_score = score_src.mean(dim=1)
    if aggregation_mode == "mean":
        return mean_score

    min_score = score_src.min(dim=1).values
    if aggregation_mode == "min":
        return min_score
    if aggregation_mode == "mean_min":
        return 0.5 * (mean_score + min_score)
    if aggregation_mode == "floor":
        floor_gate = torch.clamp(min_score / max(min_target, 1.0e-6), 0.0, 1.0)
        return mean_score * floor_gate
    raise ValueError(f"Unsupported phase_contact aggregation_mode={aggregation_mode}")


def swing_contact_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    contact_threshold: float = 1.0,
    standing_vel_threshold: float = 0.08,
) -> torch.Tensor:
    """Swing phase에 접지한 다리 수를 penalty. phase_contact와 독립.

    phase_contact는 match 보상만 주고 violation 감점이 없어서
    "4발 항상 접지"도 55% match로 높은 점수를 받는 exploit이 가능.
    이 함수는 swing phase에 접지한 다리를 독립적으로 벌함.
    별도 weight로 조정 가능하므로 서기 학습을 막지 않으면서
    정적 해의 이점을 줄일 수 있음.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    forces = contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids, :].norm(dim=-1)
    is_contact = (forces > contact_threshold).float()

    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t

    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase
    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)

    phase_norm = phases % (2.0 * math.pi)
    stance_threshold_val = duty_factor * 2.0 * math.pi
    expected_contact = (phase_norm < stance_threshold_val).float()

    # Standing command → all-stance (violation 없음)
    vel_cmd = env.command_manager.get_command("base_velocity")[:, :2]
    vel_magnitude = vel_cmd.norm(dim=1)
    is_standing = (vel_magnitude < standing_vel_threshold).unsqueeze(1)
    expected_contact = torch.where(is_standing.expand_as(expected_contact),
                                   torch.ones_like(expected_contact),
                                   expected_contact)

    # swing violation = 접지(1) AND swing phase(expected=0)
    swing_violation = is_contact * (1.0 - expected_contact)
    return swing_violation.sum(dim=1)


def phase_foot_clearance(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot", body_names=".*toe_link"),
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    target_clearance: float = 0.04,
    standing_vel_threshold: float = 0.08,
) -> torch.Tensor:
    """V54: Phase-conditioned foot clearance — swing phase에서 발 높이 보상.

    Walk These Ways 참조: swing phase 진행도에 비례한 target height.
    swing 중반에 가장 높고, 시작/끝에 낮은 삼각파 형태.
    4발 개별 clearance를 SUM (교훈#30: magnitude가 다를 수 있으므로 mean 지양).
    standing 시에는 0 (발을 들면 안 됨).
    V54.3: boot-gate 제거 — curriculum이 weight를 0→5로 ramp.
    """
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t

    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase
    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)

    phase_norm = phases % (2.0 * math.pi)
    stance_threshold_val = duty_factor * 2.0 * math.pi

    # Swing progress: 0 at swing start, 1 at swing end
    in_swing = (phase_norm >= stance_threshold_val).float()
    swing_range = 2.0 * math.pi - stance_threshold_val
    swing_progress = torch.clamp((phase_norm - stance_threshold_val) / swing_range, 0.0, 1.0)
    # Triangle: 0→1→0 over swing phase
    swing_height_factor = 1.0 - torch.abs(2.0 * swing_progress - 1.0)  # peak at mid-swing
    target_height = target_clearance * swing_height_factor * in_swing  # (num_envs, 4)

    # Actual foot height (relative to env origin)
    foot_asset = env.scene[foot_cfg.name]
    foot_z = foot_asset.data.body_pos_w[:, foot_cfg.body_ids, 2]
    env_z = env.scene.env_origins[:, 2].unsqueeze(1)
    actual_height = foot_z - env_z  # (num_envs, 4)

    # Reward: exp(-k * (actual - target)^2) for swing legs, 0 for stance
    height_error = torch.square(actual_height - target_height)
    clearance_score = torch.exp(-1000.0 * height_error) * in_swing  # k=1000: 0mm→0.20, 20mm→0.67, 40mm→1.0

    # Standing command: 0 reward (don't lift feet)
    vel_cmd = env.command_manager.get_command("base_velocity")[:, :2]
    vel_magnitude = vel_cmd.norm(dim=1)
    moving = (vel_magnitude > standing_vel_threshold).float()

    # SUM, not mean (교훈#30: clearance magnitude varies per leg)
    return clearance_score.sum(dim=1) / 4.0 * moving  # normalize by 4 for weight scaling


# ═══════════════════════════════════════════
# V51: Gait Quality Rewards
# Standing-First + Soft Height Gate hybrid
# ═══════════════════════════════════════════


def front_rear_symmetry(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    k: float = 5.0,
) -> torch.Tensor:
    """V51: 앞뒤 다리 대칭 보상.

    앞다리 쌍과 뒷다리 쌍의 스윙 비율 차이가 작을수록 높은 보상.
    front_swing_ratio ~ rear_swing_ratio일 때 1.0, 차이 클수록 0에 수렴.
    귀뚜라미 보행(rear만 스윙) 직접 교정.
    """
    contact_sensor: ContactSensor = env.scene[sensor_cfg.name]
    contact_ratio = _contact_ratio(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    swing_ratio = 1.0 - contact_ratio  # (num_envs, 4)

    front_swing = swing_ratio[:, :2].mean(dim=1)  # FL, FR
    rear_swing = swing_ratio[:, 2:].mean(dim=1)   # RL, RR
    diff = torch.abs(front_swing - rear_swing)

    return torch.exp(-k * diff)


def height_walking_gate(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    gate_low: float = 0.17,
    gate_high: float = 0.21,
    gate_min: float = 0.2,
) -> torch.Tensor:
    """V51: soft height gate — 낮은 자세에서 walking 이득을 상쇄하는 penalty.

    boot phase(_v47_boot_gate_released_iter < 0)에서는 비활성(0 반환).
    gait_gate 해제 후 walking phase부터 적용.

    높이가 gate_high 이상이면 0 (영향 없음).
    높이가 gate_low 이하이면 -(1 - gate_min) (최대 penalty).
    """
    # boot phase에서는 gate 비활성 — 자유롭게 서기/걷기 학습
    if not hasattr(env, '_v47_boot_gate_released_iter') or env._v47_boot_gate_released_iter < 0:
        return torch.zeros(env.num_envs, device=env.device)

    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    gate = torch.clamp((height - gate_low) / (gate_high - gate_low), gate_min, 1.0)
    return gate - 1.0  # 0 when tall, -(1-gate_min) when low


# ═══════════════════════════════════════════
# V52: Min Height Termination
# ═══════════════════════════════════════════


def min_height_termination(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_height: float = 0.15,
) -> torch.Tensor:
    """V52: 최소 높이 termination. height < min_height면 에피소드 종료.

    boot phase(_v47_boot_gate_released_iter < 0)에서는 비활성.
    gait_gate 해제 후 walking phase부터 적용.
    boot_standing이 soft gradient, 이것이 hard floor.
    """
    # boot phase에서는 비활성 — 자유롭게 서기 학습
    if not hasattr(env, '_v47_boot_gate_released_iter') or env._v47_boot_gate_released_iter < 0:
        return torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)

    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    return height < min_height


# ═══════════════════════════════════════════
# V43-E: Boot Standing rewards
# ═══════════════════════════════════════════

def boot_standing_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_height: float = 0.23,
    height_k: float = 100.0,
) -> torch.Tensor:
    """V43-E: 목표 높이 근접 + 수평 자세 보상. 서있으면 ~1.0, 넘어지면 ~0.0.

    height_score = exp(-k * (height - target)^2): k=100이면 fallen(0.05m)에서 0.04
    orientation_score = exp(-7 * gravity_xy^2): 기울어지면 감소
    두 점수의 곱 → 높이 OK + 자세 OK일 때만 높은 보상.
    alive_bonus(flat +10)와 달리 방향성 있는 gradient 제공.
    """
    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2]
    height_score = torch.exp(-height_k * torch.square(height - target_height))

    gravity_xy = asset.data.projected_gravity_b[:, :2]
    orientation_score = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))

    return height_score * orientation_score


def boot_foot_contact(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V43-E: 4발 접지율 보상. 4발 모두 접지=1.0, 2발=0.5, 0발=0.0.

    Boot phase에서 "발을 땅에 대라"는 positive gradient.
    Weight +5로 약하게, iter 300~600에서 ramp down.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    is_contact = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    return is_contact.float().mean(dim=1)


# ═══════════════════════════════════════════
# V43: Connected Trot rewards
# ═══════════════════════════════════════════

def _per_leg_propulsion(env, sensor_cfg, foot_cfg, asset_cfg, contact_threshold=1.0):
    """Helper: per-leg 추진력 계산 (stance_propulsion_reward 로직 재사용).

    Returns:
        stance_mask: (num_envs, 4) — 접지 상태
        push_magnitude: (num_envs, 4) — 각 발의 추진력 (0~1 normalized)
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    stance_mask = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    foot_asset = env.scene[foot_cfg.name]
    foot_vel_w = foot_asset.data.body_vel_w[:, foot_cfg.body_ids, :3]

    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    foot_heading_vel = (
        foot_vel_w[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel_w[:, :, 1] * heading_y.unsqueeze(1)
    )
    body_vel_w = robot.data.root_lin_vel_w
    body_heading_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y

    relative_vel = foot_heading_vel - body_heading_vel.unsqueeze(1)
    push_magnitude = torch.clamp(-relative_vel, min=0.0)  # 뒤로 밀기 = 양수
    normalized_push = torch.clamp(push_magnitude / 0.3, 0.0, 1.0)

    return stance_mask, normalized_push


def forward_velocity_gated(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_vel: float = 0.3,
    propulsion_threshold: float = 0.1,
    gate_alpha: float = 1.0,
) -> torch.Tensor:
    """V43: 전진 보상 + soft propulsion gating.

    다리로 땅을 밀어서 전진할 때만 보상. 미끄러짐/기울어짐 exploit 방지.
    gate_alpha: 0.0=no gating (boot phase), 1.0=full gating.
    V43-B: boot phase에서 gate_alpha=0으로 시작, curriculum이 점진적으로 1.0까지 올림.
    """
    asset = env.scene[asset_cfg.name]
    forward_vel = asset.data.root_lin_vel_b[:, 0]
    normalized_vel = torch.clamp(forward_vel / target_vel, -1.0, 1.0)

    gravity_xy = asset.data.projected_gravity_b[:, :2]
    orientation_quality = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))

    # per-leg propulsion으로 soft gate
    stance_mask, push = _per_leg_propulsion(env, sensor_cfg, foot_cfg, asset_cfg)
    propulsion_gate = (stance_mask * push).mean(dim=1)  # 4다리 평균 추진력
    propulsion_gate = torch.clamp(propulsion_gate / propulsion_threshold, 0.0, 1.0)

    # gate_alpha blending: alpha=0 → no gating, alpha=1 → full gating
    effective_gate = (1.0 - gate_alpha) + gate_alpha * propulsion_gate

    return normalized_vel * orientation_quality * effective_gate


def gait_phase_contact_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frequency: float = 2.0,
    duty_factor: float = 0.5,
    contact_threshold: float = 1.0,
    min_push: float = 0.05,
    push_alpha: float = 1.0,
) -> torch.Tensor:
    """V43: Phase + per-leg 접지·추진 연결.

    - stance phase: 접지 + per-leg 추진력 있으면 +1, 없으면 -1
    - swing phase: 미접지 시 +1, 접지 시 -1
    push_alpha: 0.0=contact only (V42 behavior), 1.0=contact+push (V43 full).
    V43-B: boot phase에서 push_alpha=0으로 시작, curriculum이 점진적으로 1.0까지 올림.
    """
    stance_mask, push = _per_leg_propulsion(env, sensor_cfg, foot_cfg, asset_cfg, contact_threshold)

    # per-leg: 접지 중이면서 실제로 밀고 있는가
    is_pushing = (stance_mask > 0.5) & (push > min_push)

    # push_alpha blending: alpha=0 → contact only, alpha=1 → contact+push
    is_good_stance_push = is_pushing.float()     # V43: contact + push required
    is_good_stance_contact = stance_mask          # V42: contact only
    is_good_stance = push_alpha * is_good_stance_push + (1.0 - push_alpha) * is_good_stance_contact

    is_contact = stance_mask  # 접지 상태

    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t
    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase
    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)
    phase_norm = phases % (2.0 * math.pi)
    stance_threshold_val = duty_factor * 2.0 * math.pi
    in_stance = (phase_norm < stance_threshold_val).float()

    stance_score = 2.0 * is_good_stance - 1.0
    swing_score = 2.0 * (1.0 - is_contact) - 1.0

    score = in_stance * stance_score + (1.0 - in_stance) * swing_score
    return score.mean(dim=1)


def v42_boot_curriculum(
    env: ManagerBasedRLEnv,
    boot_ramp_end: int = 300,
    boot_contact_initial: float = -20.0,
    boot_contact_final: float = -100.0,
    boot_vel_low_initial: float = 0.01,
    boot_vel_high_initial: float = 0.05,
    boot_vel_low_final: float = 0.1,
    boot_vel_high_final: float = 0.5,
    gate_ramp_start: int = 500,
    gate_ramp_end: int = 1500,
    pose_ramp_start: int = 1000,
    pose_ramp_end: int = 2500,
    pose_weight_initial: float = -0.5,
    pose_weight_final: float = -0.5,
    walk_ramp_config: dict | None = None,
    boot_ramp_config: dict | None = None,
    pose_safety_threshold_dev: float = 0.45,
    pose_safety_threshold_ep: float = 200.0,
    pose_safety_fallback: float = -1.0,
    pose_safety_ema_alpha: float = 0.01,
    log_interval: int = 100,
) -> torch.Tensor:
    """V44: Boot-First Curriculum + Adaptive Pose Safety.

    Phase 1 (0~300): Boot — contacts ramp + velocity ramp, walking rewards OFF
    Phase 2 (300~800): Direction — forward_velocity + stance_propulsion ramp
    Phase 3 (500~1500): Propulsion gating — gate_alpha 0→1
    Phase 4 (800~2000): Walking — gait_phase + stride_length ramp
    Phase 5 (1000~2500): Refinement — feet_air_time + pose weight ramp

    V43-D 핵심: walking reward를 boot에서 OFF하고 순차 활성화.
    V38.3의 gait_gate 철학을 clean reward 구조에 통합.
    """
    iteration = env.common_step_counter
    if iteration % 10 != 0:
        return torch.zeros(env.num_envs, device=env.device)

    alpha = min(1.0, max(0.0, iteration / max(boot_ramp_end, 1)))

    # 1. undesired_contacts ramp: -20 → -100
    cur_contact = boot_contact_initial + (boot_contact_final - boot_contact_initial) * alpha
    try:
        cfg = env.reward_manager.get_term_cfg("undesired_contacts")
        cfg.weight = cur_contact
        env.reward_manager.set_term_cfg("undesired_contacts", cfg)
    except Exception:
        pass

    # 2. velocity command ramp: (0.01,0.05) → (0.1,0.5)
    cur_vel_low = boot_vel_low_initial + (boot_vel_low_final - boot_vel_low_initial) * alpha
    cur_vel_high = boot_vel_high_initial + (boot_vel_high_final - boot_vel_high_initial) * alpha
    try:
        env.command_manager.get_term("base_velocity").cfg.ranges.lin_vel_x = (cur_vel_low, cur_vel_high)
    except Exception:
        pass

    # 3. V43-D: Walking reward weight ramp (0 → target, 순차 활성화)
    walk_log_parts = []
    if walk_ramp_config:
        for name, cfg in walk_ramp_config.items():
            target_w = cfg["target"]
            ramp_start = cfg["start"]
            ramp_end = cfg["end"]
            if iteration < ramp_start:
                cur_w = 0.0
            elif iteration >= ramp_end:
                cur_w = target_w
            else:
                walk_alpha = (iteration - ramp_start) / (ramp_end - ramp_start)
                cur_w = target_w * walk_alpha
            try:
                term_cfg = env.reward_manager.get_term_cfg(name)
                term_cfg.weight = cur_w
                env.reward_manager.set_term_cfg(name, term_cfg)
            except Exception:
                pass
            if iteration % log_interval == 0:
                walk_log_parts.append(f"{name}={cur_w:.1f}/{target_w:.0f}")

    # 3b. V43-E: Boot reward ramp-DOWN (target → 0, standing→walking 전환)
    boot_log_parts = []
    if boot_ramp_config:
        for name, cfg in boot_ramp_config.items():
            initial_w = cfg["initial"]
            ramp_down_start = cfg["ramp_down_start"]
            ramp_down_end = cfg["ramp_down_end"]
            if iteration < ramp_down_start:
                cur_w = initial_w
            elif iteration >= ramp_down_end:
                cur_w = 0.0
            else:
                down_alpha = (iteration - ramp_down_start) / (ramp_down_end - ramp_down_start)
                cur_w = initial_w * (1.0 - down_alpha)
            try:
                term_cfg = env.reward_manager.get_term_cfg(name)
                term_cfg.weight = cur_w
                env.reward_manager.set_term_cfg(name, term_cfg)
            except Exception:
                pass
            if iteration % log_interval == 0:
                boot_log_parts.append(f"{name}={cur_w:.1f}/{initial_w:.0f}")

    # 4. Propulsion gate alpha ramp (0 → 1)
    gate_alpha_val = 0.0
    if gate_ramp_start > 0 and gate_ramp_end > gate_ramp_start:
        gate_alpha_val = min(1.0, max(0.0, (iteration - gate_ramp_start) / (gate_ramp_end - gate_ramp_start)))
        if iteration < gate_ramp_start:
            gate_alpha_val = 0.0
        try:
            fv_cfg = env.reward_manager.get_term_cfg("forward_velocity")
            fv_cfg.params["gate_alpha"] = gate_alpha_val
            env.reward_manager.set_term_cfg("forward_velocity", fv_cfg)
        except Exception:
            pass
        try:
            gp_cfg = env.reward_manager.get_term_cfg("gait_phase")
            gp_cfg.params["push_alpha"] = gate_alpha_val
            env.reward_manager.set_term_cfg("gait_phase", gp_cfg)
        except Exception:
            pass

    # 5. V44: Adaptive Pose Safety — smoothed shoulder_dev + ep_len 기반
    # EMA 초기화 (첫 호출 시)
    if not hasattr(env, '_v44_shoulder_ema'):
        env._v44_shoulder_ema = 0.30  # 낙관적 초기값
        env._v44_ep_len_ema = 250.0   # 낙관적 초기값
        env._v44_pose_in_fallback = False

    # Smoothed metrics 업데이트 (매 curriculum step)
    try:
        metrics = compute_v23_raw_metrics(env)
        if metrics:
            cur_shoulder = metrics["shoulder_mean_abs_dev_from_target_raw"].mean().item()
            env._v44_shoulder_ema = (1.0 - pose_safety_ema_alpha) * env._v44_shoulder_ema + pose_safety_ema_alpha * cur_shoulder
    except Exception:
        pass
    cur_ep_len = env.episode_length_buf.float().mean().item()
    env._v44_ep_len_ema = (1.0 - pose_safety_ema_alpha) * env._v44_ep_len_ema + pose_safety_ema_alpha * cur_ep_len

    # Adaptive 판정: smoothed shoulder_dev > threshold OR smoothed ep_len < threshold
    safety_triggered = (env._v44_shoulder_ema > pose_safety_threshold_dev) or \
                       (env._v44_ep_len_ema < pose_safety_threshold_ep and iteration > 500)
    # iter 500 이전에는 ep_len이 낮을 수 있으므로 (boot 진행 중) ep_len 조건 비활성

    if safety_triggered:
        cur_pose_weight = pose_safety_fallback  # -1.0 방어 모드
        if not env._v44_pose_in_fallback:
            env._v44_pose_in_fallback = True
            print(f"[V44-Safety] iter {iteration}: FALLBACK pose→{pose_safety_fallback:.1f} "
                  f"(shoulder_ema={env._v44_shoulder_ema:.3f}, ep_len_ema={env._v44_ep_len_ema:.1f})")
    else:
        cur_pose_weight = pose_weight_initial  # -0.5 정상 모드
        if env._v44_pose_in_fallback:
            env._v44_pose_in_fallback = False
            print(f"[V44-Safety] iter {iteration}: RESTORED pose→{pose_weight_initial:.1f} "
                  f"(shoulder_ema={env._v44_shoulder_ema:.3f}, ep_len_ema={env._v44_ep_len_ema:.1f})")

    try:
        pose_cfg = env.reward_manager.get_term_cfg("joint_default_pose")
        pose_cfg.weight = cur_pose_weight
        env.reward_manager.set_term_cfg("joint_default_pose", pose_cfg)
    except Exception:
        pass

    if iteration % log_interval == 0:
        walk_str = " | ".join(walk_log_parts) if walk_log_parts else "N/A"
        boot_str = " | ".join(boot_log_parts) if boot_log_parts else "N/A"
        safety_str = "FALLBACK" if env._v44_pose_in_fallback else "OK"
        print(f"[V44] iter {iteration}: contacts={cur_contact:.0f} vel=({cur_vel_low:.2f},{cur_vel_high:.2f}) gate={gate_alpha_val:.2f} pose={cur_pose_weight:.2f} [{safety_str}]")
        print(f"  shoulder_ema={env._v44_shoulder_ema:.3f} ep_len_ema={env._v44_ep_len_ema:.1f}")
        print(f"  boot: {boot_str}")
        print(f"  walk: {walk_str}")

    return torch.zeros(env.num_envs, device=env.device)


def _contact_force_peak(contact_sensor: ContactSensor, body_ids) -> torch.Tensor:
    """Return per-body peak contact force over the available sensor history window."""
    return contact_sensor.data.net_forces_w_history[:, :, body_ids, :].norm(dim=-1).max(dim=1)[0]


def _contact_state(contact_sensor: ContactSensor, body_ids, threshold: float) -> torch.Tensor:
    """Return boolean contact state from peak contact force over sensor history."""
    return _contact_force_peak(contact_sensor, body_ids) > threshold


def _contact_ratio(contact_sensor: ContactSensor, body_ids, threshold: float) -> torch.Tensor:
    """Return per-body contact ratio over the available sensor history window."""
    force_history = contact_sensor.data.net_forces_w_history[:, :, body_ids, :].norm(dim=-1)
    return (force_history > threshold).float().mean(dim=1)


V23_RAW_EXPORT_TERMS = [
    "stance_width_mean_raw",
    "stance_width_front_raw",
    "stance_width_rear_raw",
    "front_rear_stance_width_diff_raw",
    "shoulder_fl_raw",
    "shoulder_fr_raw",
    "shoulder_rl_raw",
    "shoulder_rr_raw",
    "shoulder_mean_abs_dev_from_target_raw",
    "shoulder_left_right_diff_raw",
    "shoulder_front_rear_diff_raw",
    "front_leg_lift_mean_raw",
    "rear_leg_lift_mean_raw",
    "front_clearance_mean_raw",
    "rear_clearance_mean_raw",
    "front_propulsion_score_raw",
    "rear_propulsion_score_raw",
    "front_rear_propulsion_diff_raw",
    "front_rear_clearance_diff_raw",
    "front_rear_swing_diff_raw",
    "contact_ratio_fl",
    "contact_ratio_fr",
    "contact_ratio_rl",
    "contact_ratio_rr",
    "stance_time_fl",
    "stance_time_fr",
    "stance_time_rl",
    "stance_time_rr",
    "swing_time_fl",
    "swing_time_fr",
    "swing_time_rl",
    "swing_time_rr",
    "propulsion_fl",
    "propulsion_fr",
    "propulsion_rl",
    "propulsion_rr",
    "leg_lift_fl",
    "leg_lift_fr",
    "leg_lift_rl",
    "leg_lift_rr",
    "clearance_fl",
    "clearance_fr",
    "clearance_rl",
    "clearance_rr",
    "diagonal_coupling_raw",
]

_V23_SHOULDER_JOINT_NAMES = [
    "front_left_shoulder",
    "front_right_shoulder",
    "rear_left_shoulder",
    "rear_right_shoulder",
]
_V23_LEG_JOINT_NAMES = [
    "front_left_leg",
    "front_right_leg",
    "rear_left_leg",
    "rear_right_leg",
]
_V23_CONTACT_BODY_NAMES = [
    "front_left_toe_link",
    "front_right_toe_link",
    "rear_left_toe_link",
    "rear_right_toe_link",
]
_V23_LEG_SUFFIXES = ("fl", "fr", "rl", "rr")

# V28.1: per-leg EMA residency state keys (contact / propulsion / usage × 4 legs = 12)
_V281_RESIDENCY_EMA_KEYS = (
    [f"contact_{s}" for s in _V23_LEG_SUFFIXES]
    + [f"prop_{s}" for s in _V23_LEG_SUFFIXES]
    + [f"usage_{s}" for s in _V23_LEG_SUFFIXES]
)


def _ensure_v281_residency_state(env: "ManagerBasedRLEnv") -> None:
    """V28.1: per-leg EMA residency tensor 초기화 (없을 때만).

    episode 단위 리셋은 reset_v23_raw_metric_extras()에서 처리.
    """
    if not hasattr(env, "_v281_residency_ema"):
        env._v281_residency_ema = {
            key: torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
            for key in _V281_RESIDENCY_EMA_KEYS
        }
    else:
        # 혹시 신규 key가 없으면 보완 (resume 대응)
        for key in _V281_RESIDENCY_EMA_KEYS:
            if key not in env._v281_residency_ema:
                env._v281_residency_ema[key] = torch.zeros(env.num_envs, dtype=torch.float, device=env.device)


def _compute_heading_xy(quat_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    w, x, y, z = quat_w[:, 0], quat_w[:, 1], quat_w[:, 2], quat_w[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)
    return heading_x, heading_y


def _ensure_v23_raw_metric_state(env: ManagerBasedRLEnv) -> bool:
    if not hasattr(env, "_v23_raw_metric_episode_sums"):
        env._v23_raw_metric_episode_sums = {
            name: torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
            for name in V23_RAW_EXPORT_TERMS
        }
    else:
        for name in V23_RAW_EXPORT_TERMS:
            if name not in env._v23_raw_metric_episode_sums:
                env._v23_raw_metric_episode_sums[name] = torch.zeros(env.num_envs, dtype=torch.float, device=env.device)

    cache = getattr(env, "_v23_raw_metric_cache", None)
    if cache is not None:
        return bool(cache.get("enabled", False))

    robot = env.scene["robot"]
    contact_sensor = env.scene.sensors.get("contact_forces", None)
    if contact_sensor is None:
        env._v23_raw_metric_cache = {"enabled": False}
        return False

    shoulder_joint_ids, _ = robot.find_joints(_V23_SHOULDER_JOINT_NAMES, preserve_order=True)
    leg_joint_ids, _ = robot.find_joints(_V23_LEG_JOINT_NAMES, preserve_order=True)
    foot_body_ids, _ = robot.find_bodies(_V23_CONTACT_BODY_NAMES, preserve_order=True)
    contact_body_ids, _ = contact_sensor.find_bodies(_V23_CONTACT_BODY_NAMES, preserve_order=True)

    try:
        shoulder_cfg = env.reward_manager.get_term_cfg("shoulder_neutral")
        target_angles = shoulder_cfg.params.get("target_angles")
    except Exception:
        target_angles = None
    if target_angles is None or len(target_angles) != 4:
        target_angles = [-0.04, -0.04, -0.04, -0.04]

    try:
        clearance_cfg = env.reward_manager.get_term_cfg("foot_clearance")
        target_clearance = float(clearance_cfg.params.get("target_clearance", 0.03))
    except Exception:
        target_clearance = 0.03

    try:
        propulsion_cfg = env.reward_manager.get_term_cfg("stance_propulsion")
        target_push_vel = float(propulsion_cfg.params.get("target_push_vel", 0.3))
        contact_threshold = float(propulsion_cfg.params.get("contact_threshold", 1.0))
    except Exception:
        target_push_vel = 0.3
        contact_threshold = 1.0

    try:
        leg_lift_cfg = env.reward_manager.get_term_cfg("leg_lift")
        target_leg_angle = float(leg_lift_cfg.params.get("target_angle", 0.6))
    except Exception:
        target_leg_angle = 0.6

    env._v23_raw_metric_cache = {
        "enabled": True,
        "shoulder_joint_ids": shoulder_joint_ids,
        "leg_joint_ids": leg_joint_ids,
        "foot_body_ids": foot_body_ids,
        "contact_body_ids": contact_body_ids,
        "shoulder_targets": torch.tensor(target_angles, dtype=torch.float, device=env.device),
        "target_clearance": target_clearance,
        "target_push_vel": target_push_vel,
        "contact_threshold": contact_threshold,
        "target_leg_angle": target_leg_angle,
    }
    return True


def compute_v23_raw_metrics(env: ManagerBasedRLEnv) -> dict[str, torch.Tensor]:
    if not _ensure_v23_raw_metric_state(env):
        return {}

    cache = env._v23_raw_metric_cache
    robot: Articulation = env.scene["robot"]
    contact_sensor: ContactSensor = env.scene.sensors["contact_forces"]

    contact_ratio = _contact_ratio(contact_sensor, cache["contact_body_ids"], cache["contact_threshold"])
    contacts = _contact_state(contact_sensor, cache["contact_body_ids"], cache["contact_threshold"]).float()
    swing_mask = 1.0 - contacts
    front_swing_count = swing_mask[:, :2].sum(dim=1).clamp(min=1.0)
    rear_swing_count = swing_mask[:, 2:].sum(dim=1).clamp(min=1.0)
    front_stance_count = contacts[:, :2].sum(dim=1).clamp(min=1.0)
    rear_stance_count = contacts[:, 2:].sum(dim=1).clamp(min=1.0)

    shoulder_angles = robot.data.joint_pos[:, cache["shoulder_joint_ids"]]
    shoulder_targets = cache["shoulder_targets"].to(device=shoulder_angles.device, dtype=shoulder_angles.dtype)
    shoulder_dev = torch.abs(shoulder_angles - shoulder_targets)

    foot_pos_xy = robot.data.body_pos_w[:, cache["foot_body_ids"], :2]
    root_pos_xy = robot.data.root_pos_w[:, :2].unsqueeze(1)
    rel_xy = foot_pos_xy - root_pos_xy
    heading_x, heading_y = _compute_heading_xy(robot.data.root_quat_w)
    body_y = -heading_y.unsqueeze(1) * rel_xy[:, :, 0] + heading_x.unsqueeze(1) * rel_xy[:, :, 1]
    front_width = torch.abs(body_y[:, 0] - body_y[:, 1])
    rear_width = torch.abs(body_y[:, 2] - body_y[:, 3])

    leg_angles = torch.abs(robot.data.joint_pos[:, cache["leg_joint_ids"]])
    leg_lift_per_limb = leg_angles * swing_mask
    front_leg_lift = (leg_angles[:, :2] * swing_mask[:, :2]).sum(dim=1) / front_swing_count
    rear_leg_lift = (leg_angles[:, 2:] * swing_mask[:, 2:]).sum(dim=1) / rear_swing_count

    foot_height = robot.data.body_pos_w[:, cache["foot_body_ids"], 2] - env.scene.env_origins[:, 2].unsqueeze(1)
    clearance_per_limb = torch.clamp(foot_height, min=0.0) * swing_mask
    front_clearance = (foot_height[:, :2] * swing_mask[:, :2]).sum(dim=1) / front_swing_count
    rear_clearance = (foot_height[:, 2:] * swing_mask[:, 2:]).sum(dim=1) / rear_swing_count

    foot_vel_w = robot.data.body_vel_w[:, cache["foot_body_ids"], :3]
    foot_heading_vel = foot_vel_w[:, :, 0] * heading_x.unsqueeze(1) + foot_vel_w[:, :, 1] * heading_y.unsqueeze(1)
    body_vel_w = robot.data.root_lin_vel_w
    body_heading_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y
    relative_vel = foot_heading_vel - body_heading_vel.unsqueeze(1)
    push_magnitude = torch.clamp(-relative_vel, min=0.0)
    normalized_push = torch.clamp(push_magnitude / (cache["target_push_vel"] + 1e-6), 0.0, 1.0)
    propulsion_per_limb = normalized_push * contacts
    front_propulsion = (normalized_push[:, :2] * contacts[:, :2]).sum(dim=1) / front_stance_count
    rear_propulsion = (normalized_push[:, 2:] * contacts[:, 2:]).sum(dim=1) / rear_stance_count

    shoulder_fl = shoulder_angles[:, 0]
    shoulder_fr = shoulder_angles[:, 1]
    shoulder_rl = shoulder_angles[:, 2]
    shoulder_rr = shoulder_angles[:, 3]

    swing_ratio = 1.0 - contact_ratio
    front_swing_ratio = swing_ratio[:, :2].mean(dim=1)
    rear_swing_ratio = swing_ratio[:, 2:].mean(dim=1)

    return {
        "stance_width_mean_raw": (front_width + rear_width) / 2.0,
        "stance_width_front_raw": front_width,
        "stance_width_rear_raw": rear_width,
        "front_rear_stance_width_diff_raw": torch.abs(front_width - rear_width),
        "shoulder_fl_raw": shoulder_fl,
        "shoulder_fr_raw": shoulder_fr,
        "shoulder_rl_raw": shoulder_rl,
        "shoulder_rr_raw": shoulder_rr,
        "shoulder_mean_abs_dev_from_target_raw": shoulder_dev.mean(dim=1),
        "shoulder_left_right_diff_raw": (torch.abs(shoulder_fl - shoulder_fr) + torch.abs(shoulder_rl - shoulder_rr)) / 2.0,
        "shoulder_front_rear_diff_raw": (torch.abs(shoulder_fl - shoulder_rl) + torch.abs(shoulder_fr - shoulder_rr)) / 2.0,
        "front_leg_lift_mean_raw": front_leg_lift,
        "rear_leg_lift_mean_raw": rear_leg_lift,
        "front_clearance_mean_raw": front_clearance,
        "rear_clearance_mean_raw": rear_clearance,
        "front_propulsion_score_raw": front_propulsion,
        "rear_propulsion_score_raw": rear_propulsion,
        "front_rear_propulsion_diff_raw": torch.abs(front_propulsion - rear_propulsion),
        "front_rear_clearance_diff_raw": torch.abs(front_clearance - rear_clearance),
        "front_rear_swing_diff_raw": torch.abs(front_swing_ratio - rear_swing_ratio),
        "contact_ratio_fl": contact_ratio[:, 0],
        "contact_ratio_fr": contact_ratio[:, 1],
        "contact_ratio_rl": contact_ratio[:, 2],
        "contact_ratio_rr": contact_ratio[:, 3],
        "stance_time_fl": contact_ratio[:, 0],
        "stance_time_fr": contact_ratio[:, 1],
        "stance_time_rl": contact_ratio[:, 2],
        "stance_time_rr": contact_ratio[:, 3],
        "swing_time_fl": swing_ratio[:, 0],
        "swing_time_fr": swing_ratio[:, 1],
        "swing_time_rl": swing_ratio[:, 2],
        "swing_time_rr": swing_ratio[:, 3],
        "propulsion_fl": propulsion_per_limb[:, 0],
        "propulsion_fr": propulsion_per_limb[:, 1],
        "propulsion_rl": propulsion_per_limb[:, 2],
        "propulsion_rr": propulsion_per_limb[:, 3],
        "leg_lift_fl": leg_lift_per_limb[:, 0],
        "leg_lift_fr": leg_lift_per_limb[:, 1],
        "leg_lift_rl": leg_lift_per_limb[:, 2],
        "leg_lift_rr": leg_lift_per_limb[:, 3],
        "clearance_fl": clearance_per_limb[:, 0],
        "clearance_fr": clearance_per_limb[:, 1],
        "clearance_rl": clearance_per_limb[:, 2],
        "clearance_rr": clearance_per_limb[:, 3],
    }


def accumulate_v23_raw_metrics(env: ManagerBasedRLEnv) -> None:
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return
    for name, values in metrics.items():
        env._v23_raw_metric_episode_sums[name] += values * env.step_dt


def reset_v23_raw_metric_extras(env: ManagerBasedRLEnv, env_ids) -> dict[str, torch.Tensor]:
    if not hasattr(env, "_v23_raw_metric_episode_sums"):
        return {}
    if env_ids is None:
        env_ids = slice(None)
    extras = {}
    for name, buffer in env._v23_raw_metric_episode_sums.items():
        extras[f"Episode_Reward/{name}"] = torch.mean(buffer[env_ids]) / env.max_episode_length_s
        buffer[env_ids] = 0.0
    # V28.2: residency EMA 평균 로깅 (reset 전에 캡처해서 tensorboard에 기록)
    if hasattr(env, "_v281_residency_ema"):
        for key in ["contact_fl", "contact_fr", "contact_rl", "contact_rr", "prop_rl", "prop_rr"]:
            if key in env._v281_residency_ema:
                vals = env._v281_residency_ema[key][env_ids]
                if vals.numel() > 0:
                    extras[f"Episode_Reward/residency_ema_{key}"] = vals.mean()
        if "contact_rl" in env._v281_residency_ema and "contact_rr" in env._v281_residency_ema:
            rl_vals = env._v281_residency_ema["contact_rl"][env_ids]
            rr_vals = env._v281_residency_ema["contact_rr"][env_ids]
            if rl_vals.numel() > 0:
                extras["Episode_Reward/rear_pair_residency_gap"] = torch.abs(rl_vals - rr_vals).mean()
    # V28.1: per-leg EMA residency 리셋 (episode 경계에서 초기화)
    if hasattr(env, "_v281_residency_ema"):
        for buf in env._v281_residency_ema.values():
            buf[env_ids] = 0.0
    return extras


def _heading_velocity_gate(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg, min_vel: float) -> torch.Tensor:
    asset: Articulation = env.scene[asset_cfg.name]
    heading_x, heading_y = _compute_heading_xy(asset.data.root_quat_w)
    body_vel_w = asset.data.root_lin_vel_w
    forward_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y
    return torch.clamp(forward_vel / max(float(min_vel), 1.0e-6), min=0.0, max=1.0)


def _compute_limb_usage_proxy(metrics: dict[str, torch.Tensor], contact_target: float, propulsion_target: float, leg_lift_target: float, clearance_target: float) -> dict[str, torch.Tensor]:
    usage_scores: dict[str, torch.Tensor] = {}
    for suffix in _V23_LEG_SUFFIXES:
        contact = metrics[f"contact_ratio_{suffix}"]
        propulsion = metrics[f"propulsion_{suffix}"]
        leg_lift = metrics[f"leg_lift_{suffix}"]
        clearance = metrics[f"clearance_{suffix}"]
        contact_score = torch.clamp(contact / max(contact_target, 1.0e-6), min=0.0, max=1.0)
        propulsion_score = torch.clamp(propulsion / max(propulsion_target, 1.0e-6), min=0.0, max=1.0)
        leg_lift_score = torch.clamp(leg_lift / max(leg_lift_target, 1.0e-6), min=0.0, max=1.0)
        clearance_score = torch.clamp(clearance / max(clearance_target, 1.0e-6), min=0.0, max=1.0)
        swing_activity_score = 0.5 * (leg_lift_score + clearance_score)
        support_gate = torch.maximum(contact_score, propulsion_score)
        usage_scores[suffix] = (
            0.55 * contact_score
            + 0.35 * propulsion_score
            + 0.10 * swing_activity_score
        )
        usage_scores[suffix] = usage_scores[suffix] * support_gate
    return usage_scores


def limb_usage_min_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_usage: float = 0.30,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """Penalize runs where the least-used limb falls below a minimum usage proxy."""
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    usage_scores = _compute_limb_usage_proxy(metrics, contact_target, propulsion_target, leg_lift_target, clearance_target)
    usage_tensor = torch.stack([usage_scores[suffix] for suffix in _V23_LEG_SUFFIXES], dim=1)
    gap = torch.clamp(float(min_usage) - usage_tensor.min(dim=1).values, min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def rear_left_right_usage_diff_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_diff: float = 0.18,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """Penalize excessive rear-left/right limb usage asymmetry."""
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    usage_scores = _compute_limb_usage_proxy(metrics, contact_target, propulsion_target, leg_lift_target, clearance_target)
    rear_diff = torch.abs(usage_scores["rl"] - usage_scores["rr"])
    gap = torch.clamp(rear_diff - float(max_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def rear_left_contact_floor_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    floor: float = 0.30,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V25: rear-left contact_ratio가 floor 미달 시 직접 패널티.

    V24 limb_usage_min_penalty(min_usage proxy)와 달리, rear-left에만 직접 적용.
    ramp 없이 iter 0부터 full weight로 작동.
    gap = max(0, floor - contact_ratio_rl) → 접지할수록 패널티 감소.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    rl_contact = _contact_ratio(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (N, 1)
    gap = torch.clamp(float(floor) - rl_contact[:, 0], min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


# ============================================================
# V26: Symmetric Per-Leg Existence Floor Penalties
# 네 다리 모두 동일 기준으로 존재를 보장한다.
# V25의 rear_left 특화 패널티 → collapse 위치 이동 실패 교훈.
# ============================================================


def per_leg_contact_floor_penalty(
    env: ManagerBasedRLEnv,
    floor: float = 0.10,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V26: 네 다리 각각의 contact_ratio가 floor 미달 시 패널티 (symmetric).

    V25의 rear_left_contact_floor_penalty와 달리 모든 다리에 동일 기준 적용.
    각 다리의 gap을 합산 → 어느 다리가 무너져도 패널티 발생.
    floor=0.10: 완전 소멸 방지용 최소 floor (contact_quantity가 아닌 existence 보장).
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    contact_tensor = torch.stack(
        [metrics[f"contact_ratio_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    gaps = torch.clamp(float(floor) - contact_tensor, min=0.0)
    return gaps.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def per_leg_propulsion_floor_penalty(
    env: ManagerBasedRLEnv,
    floor: float = 0.05,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V26: 네 다리 각각의 propulsion이 floor 미달 시 패널티 (symmetric).

    fake contact(접지하지만 추진 없음) 차단 목적.
    contact_ratio가 살아도 propulsion이 0이면 "접지 흉내"로 처리.
    floor=0.05: 바닥을 살짝이라도 실제로 밀어야 한다는 최소 기준.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    prop_tensor = torch.stack(
        [metrics[f"propulsion_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    gaps = torch.clamp(float(floor) - prop_tensor, min=0.0)
    return gaps.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


# ============================================================
# V26: Load Sharing Penalties (symmetric left/right, front/rear)
# ============================================================


def front_left_right_usage_diff_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_diff: float = 0.40,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """V26: 앞다리 좌우(FL vs FR) usage 편중 억제.

    rear_left_right_usage_diff_penalty의 앞다리 대칭 버전.
    max_diff=0.40: 40% 이상 편중 시 penalty (부드러운 연속 함수).
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    usage_scores = _compute_limb_usage_proxy(
        metrics, contact_target, propulsion_target, leg_lift_target, clearance_target
    )
    front_diff = torch.abs(usage_scores["fl"] - usage_scores["fr"])
    gap = torch.clamp(front_diff - float(max_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def rear_left_right_propulsion_diff_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_diff: float = 0.40,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """V26: 뒷다리 좌우(RL vs RR) 추진 편중 억제.

    usage 편중과 달리 직접 propulsion 값을 비교.
    한쪽 뒷다리가 추진을 독점하는 패턴 억제.
    max_diff=0.40: 40% 이상 편중 시 penalty.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    prop_diff = torch.abs(metrics["propulsion_rl"] - metrics["propulsion_rr"])
    gap = torch.clamp(prop_diff - float(max_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def front_left_right_propulsion_diff_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_diff: float = 0.25,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """V27: 앞다리 좌우(FL vs FR) 추진 편중 억제.

    rear_left_right_propulsion_diff_penalty의 앞다리 버전.
    max_diff=0.25: 25% 이상 편중 시 penalty (V26 0.40보다 엄격).
    contact만 살아도 propulsion이 편중되면 패널티 부과.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    prop_diff = torch.abs(metrics["propulsion_fl"] - metrics["propulsion_fr"])
    gap = torch.clamp(prop_diff - float(max_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def single_limb_validity_penalty(
    env: ManagerBasedRLEnv,
    floor: float = 0.10,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V27: 가장 약한 다리의 contact+propulsion 복합 점수가 floor 미달 시 강한 패널티.

    contact와 propulsion 둘 다 봄 — contact만 살아도 fake recovery로 통과 안 됨.
    모든 4다리 중 가장 약한 다리를 기준으로 패널티 부과.
    weight는 고정 (iter 0부터 full strength, ramp 없음).

    V27 원칙: "0.000x 수준은 절대 살아 있음으로 인정하지 않는다."
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    validity_per_leg = []
    for s in _V23_LEG_SUFFIXES:
        contact = metrics[f"contact_ratio_{s}"]
        prop = metrics[f"propulsion_{s}"]
        # 두 신호 평균: 둘 다 살아야 gap이 작음 (하나만 살아도 일부 완화되지 않음)
        validity = (contact + prop) * 0.5
        validity_per_leg.append(validity)
    worst = torch.stack(validity_per_leg, dim=1).min(dim=1).values  # (N,)
    gap = torch.clamp(float(floor) - worst, min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


# ============================================================
# V28: Target-Band Incentive (Layer C)
# "floor만 넘기면 살아남는 구조" → "정상 범위에 들어와야 이득이 되는 구조"
# contact band [0.20, 0.45], propulsion band [0.15, 0.38]
# ============================================================


def per_leg_contact_target_band_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.20,
    band_high: float = 0.45,
    band_ramp_start: float = 0.05,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28: 4발 각각의 contact_ratio가 target band에 진입하면 보상.

    Trapezoid shape:
    - 0 ~ band_ramp_start: reward = 0
    - band_ramp_start ~ band_low: linear ramp 0 → 1 (gray zone incentive)
    - band_low 이상: reward = 1.0 plateau

    Layer C 핵심: floor 근처 정체가 아니라 정상 범위 진입을 유도.
    V26 iter 200 실측 기반 band: low=0.20 (최솟값 0.318의 63%), high=0.45.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    contact_tensor = torch.stack(
        [metrics[f"contact_ratio_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    ramp_width = max(float(band_low) - float(band_ramp_start), 1e-6)
    reward_per_leg = torch.clamp(
        (contact_tensor - float(band_ramp_start)) / ramp_width, 0.0, 1.0
    )
    return reward_per_leg.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def per_leg_propulsion_target_band_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.15,
    band_high: float = 0.38,
    band_ramp_start: float = 0.03,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28: 4발 각각의 propulsion이 target band에 진입하면 보상.

    contact가 살아도 propulsion이 없으면 band 보상 없음.
    V27의 per_leg_propulsion_floor_penalty(Layer B)와 함께 작용 —
    fake contact(닿기만 하고 추진 없음)를 구조적으로 불리하게 만든다.
    V26 iter 200 실측 기반 band: low=0.15 (최솟값 0.281의 53%), high=0.38.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    prop_tensor = torch.stack(
        [metrics[f"propulsion_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    ramp_width = max(float(band_low) - float(band_ramp_start), 1e-6)
    reward_per_leg = torch.clamp(
        (prop_tensor - float(band_ramp_start)) / ramp_width, 0.0, 1.0
    )
    return reward_per_leg.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def limb_usage_target_band_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.20,
    band_high: float = 0.45,
    band_ramp_start: float = 0.05,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28: 4발 각각의 usage_proxy가 target band에 있으면 보상.

    limb_usage_min_penalty(Layer B)의 "최약 다리 기준 패널티"와 달리,
    모든 다리의 usage 향상을 고르게 유도.
    band 수치는 contact band와 동일 비율 적용 (실측치 확보 시 보정).
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    usage_scores = _compute_limb_usage_proxy(
        metrics, contact_target, propulsion_target, leg_lift_target, clearance_target
    )
    usage_tensor = torch.stack(
        [usage_scores[s] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    ramp_width = max(float(band_low) - float(band_ramp_start), 1e-6)
    reward_per_leg = torch.clamp(
        (usage_tensor - float(band_ramp_start)) / ramp_width, 0.0, 1.0
    )
    return reward_per_leg.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def four_limb_cooperation_reward(
    env: ManagerBasedRLEnv,
    contact_band_low: float = 0.20,
    propulsion_band_low: float = 0.15,
    trigger_partial: int = 2,
    trigger_full: int = 3,
    min_vel: float = 0.05,
    min_leg_factor_low: float = 1.0,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28: 4발이 동시에 target band에 들어왔을 때 협동 보상.

    band_hit_count: contact AND propulsion 모두 band_low 이상인 다리 수.
    - band_hit_count < trigger_partial (2): 보상 없음
    - trigger_partial (2) ≤ band_hit_count: 0.5x 보상
    - band_hit_count ≥ trigger_full (3): 추가 0.5x (합계 1.0x)

    초기 랜덤 정책에서는 거의 0 → 학습 억제 없음.
    4발 기능 참여 형성 이후에야 의미 있는 보상이 됨 (후반 강화형).

    V28.1 min_leg_factor_low: 최약 다리의 band 참여 여부를 soft factor로 곱함.
    - 기본값 1.0이면 V28 동작과 동일 (factor 없음).
    - <1.0이면 최약 다리가 band 밖일 때 보상 감쇠: factor = min_leg_factor_low + (1 - min_leg_factor_low) * min_leg_score
    - 평균 기반 cooperation reward가 "3 good + 1 bad" 상태에 속지 않도록 방지.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    contact_tensor = torch.stack(
        [metrics[f"contact_ratio_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    prop_tensor = torch.stack(
        [metrics[f"propulsion_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    contact_in = contact_tensor >= float(contact_band_low)
    prop_in = prop_tensor >= float(propulsion_band_low)
    band_hit = (contact_in & prop_in).float()  # (N, 4): per-leg 0/1
    band_hit_count = band_hit.sum(dim=1)  # (N,)
    partial = (band_hit_count >= float(trigger_partial)).float() * 0.5
    full_bonus = (band_hit_count >= float(trigger_full)).float() * 0.5
    base_reward = partial + full_bonus
    # V28.1: min-leg soft factor (기본값 1.0이면 no-op)
    fac_low = float(min_leg_factor_low)
    if fac_low < 1.0 - 1e-6:
        min_leg_score = band_hit.min(dim=1)[0]  # (N,) — 0이면 최약 다리 band 밖
        factor = fac_low + (1.0 - fac_low) * min_leg_score
        base_reward = base_reward * factor
    return base_reward * _heading_velocity_gate(env, asset_cfg, min_vel)


# ============================================================
# V28.1: Band Residency Rewards + Rear Pair Symmetry + Late-phase Exit Penalty
# "band entry"에서 "band residency"로 — 후반 유지 강화판
# ============================================================


def _update_v281_contact_ema(
    env: "ManagerBasedRLEnv",
    metrics: dict,
    band_low: float,
    ema_alpha: float,
    band_high: float = 1.0,
) -> None:
    """contact EMA를 이 step에서 아직 업데이트하지 않은 경우에만 갱신."""
    current_step = env.common_step_counter
    if getattr(env, "_v281_contact_ema_step", -1) == current_step:
        return
    env._v281_contact_ema_step = current_step
    contact_tensor = torch.stack(
        [metrics[f"contact_ratio_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    in_band = ((contact_tensor >= band_low) & (contact_tensor <= band_high)).float()
    for i, s in enumerate(_V23_LEG_SUFFIXES):
        key = f"contact_{s}"
        env._v281_residency_ema[key].mul_(1.0 - ema_alpha).add_(in_band[:, i] * ema_alpha)


def _update_v281_prop_ema(
    env: "ManagerBasedRLEnv",
    metrics: dict,
    band_low: float,
    ema_alpha: float,
    band_high: float = 1.0,
) -> None:
    """propulsion EMA를 이 step에서 아직 업데이트하지 않은 경우에만 갱신."""
    current_step = env.common_step_counter
    if getattr(env, "_v281_prop_ema_step", -1) == current_step:
        return
    env._v281_prop_ema_step = current_step
    prop_tensor = torch.stack(
        [metrics[f"propulsion_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    in_band = ((prop_tensor >= band_low) & (prop_tensor <= band_high)).float()
    for i, s in enumerate(_V23_LEG_SUFFIXES):
        key = f"prop_{s}"
        env._v281_residency_ema[key].mul_(1.0 - ema_alpha).add_(in_band[:, i] * ema_alpha)


def _update_v281_usage_ema(
    env: "ManagerBasedRLEnv",
    metrics: dict,
    band_low: float,
    ema_alpha: float,
    contact_target: float,
    propulsion_target: float,
    leg_lift_target: float,
    clearance_target: float,
    band_high: float = 1.0,
) -> None:
    """usage EMA를 이 step에서 아직 업데이트하지 않은 경우에만 갱신."""
    current_step = env.common_step_counter
    if getattr(env, "_v281_usage_ema_step", -1) == current_step:
        return
    env._v281_usage_ema_step = current_step
    usage_scores = _compute_limb_usage_proxy(
        metrics, contact_target, propulsion_target, leg_lift_target, clearance_target
    )
    in_band = torch.stack(
        [((usage_scores[s] >= band_low) & (usage_scores[s] <= band_high)).float() for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    for i, s in enumerate(_V23_LEG_SUFFIXES):
        key = f"usage_{s}"
        env._v281_residency_ema[key].mul_(1.0 - ema_alpha).add_(in_band[:, i] * ema_alpha)


def per_leg_contact_band_residency_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.20,
    band_high: float = 1.0,
    ema_alpha: float = 0.05,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.1: 각 다리의 contact_ratio가 band 안에 지속 체류한 비율(EMA)을 보상.

    순간 진입이 아니라 episode 내 장기 체류를 유도.
    EMA는 per-env, per-episode 상태로 관리 (reset 시 초기화).
    relay: early(600→800→1000) + late(800→1000→유지) curriculum으로 제어.
    V29: band_high 추가 (default=1.0 하위 호환). 0.65 설정 시 앞발 고착 억제.
    """
    _ensure_v281_residency_state(env)
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    _update_v281_contact_ema(env, metrics, band_low, ema_alpha, band_high)
    ema_tensor = torch.stack(
        [env._v281_residency_ema[f"contact_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    return ema_tensor.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def per_leg_propulsion_band_residency_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.15,
    band_high: float = 1.0,
    ema_alpha: float = 0.05,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.1: 각 다리의 propulsion이 band 안에 지속 체류한 비율(EMA)을 보상.

    contact residency와 함께 작동하여 "접지+추진 동시 유지"를 장기 유도.
    V29: band_high 추가 (default=1.0 하위 호환).
    """
    _ensure_v281_residency_state(env)
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    _update_v281_prop_ema(env, metrics, band_low, ema_alpha, band_high)
    ema_tensor = torch.stack(
        [env._v281_residency_ema[f"prop_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    return ema_tensor.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def limb_usage_band_residency_reward(
    env: ManagerBasedRLEnv,
    band_low: float = 0.20,
    band_high: float = 1.0,
    ema_alpha: float = 0.05,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.1: 각 다리의 usage_proxy가 band 안에 지속 체류한 비율(EMA)을 보상.
    V29: band_high 추가 (default=1.0 하위 호환).
    """
    _ensure_v281_residency_state(env)
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    _update_v281_usage_ema(
        env, metrics, band_low, ema_alpha, contact_target, propulsion_target, leg_lift_target, clearance_target, band_high
    )
    ema_tensor = torch.stack(
        [env._v281_residency_ema[f"usage_{s}"] for s in _V23_LEG_SUFFIXES], dim=1
    )  # (N, 4)
    return ema_tensor.sum(dim=1) * _heading_velocity_gate(env, asset_cfg, min_vel)


def rear_pair_residency_symmetry_penalty(
    env: ManagerBasedRLEnv,
    min_diff: float = 0.05,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.1: RL과 RR의 contact residency 차이를 패널티.

    residency 자체가 EMA이므로 이중 EMA 없이 abs diff 직접 사용.
    작은 차이(min_diff 이하)는 무시하여 정상 범위 변동은 패널티 없음.
    RL이 천천히 빠지는 시간누적형 붕괴 패턴을 조기 차단.
    """
    _ensure_v281_residency_state(env)
    rl_ema = env._v281_residency_ema["contact_rl"]
    rr_ema = env._v281_residency_ema["contact_rr"]
    diff = torch.abs(rl_ema - rr_ema)
    gap = torch.clamp(diff - float(min_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def late_phase_band_exit_penalty(
    env: ManagerBasedRLEnv,
    residency_floor: float = 0.50,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.1: late phase에서 per-leg contact residency가 floor 미달 시 패널티.

    iter 800 고정 snapshot 기반이 아니라,
    late-phase에서 기대되는 최소 residency(residency_floor) 미달을 패널티로 정의.
    curriculum ramp(iter 800→1200)로 late phase에서만 점진적으로 활성화.
    """
    _ensure_v281_residency_state(env)
    penalty = torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    for s in _V23_LEG_SUFFIXES:
        ema = env._v281_residency_ema[f"contact_{s}"]
        gap = torch.clamp(float(residency_floor) - ema, min=0.0)
        penalty += gap
    return penalty * _heading_velocity_gate(env, asset_cfg, min_vel)


def rear_pair_contact_diff_penalty(
    env: ManagerBasedRLEnv,
    diff_threshold: float = 0.10,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.2: RL vs RR current-step contact_ratio 차이를 즉각 패널티.

    EMA 기반이 아닌 현재 step contact_ratio로 즉각 반응.
    run 재기동 후 EMA 워밍업 사각지대를 보완.
    threshold 미만의 소폭 변동은 무시.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    rl_contact = metrics["contact_ratio_rl"]
    rr_contact = metrics["contact_ratio_rr"]
    diff = torch.abs(rl_contact - rr_contact)
    gap = torch.clamp(diff - float(diff_threshold), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def front_pair_contact_cap_penalty(
    env: ManagerBasedRLEnv,
    contact_cap: float = 0.65,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """V28.3: FL/FR contact ratio 상한 초과 시 패널티.

    앞발 고정 local optimum 차단.
    contact_cap=0.65는 이상적 목표값이 아니라 0.84+ 고착 억제용 soft cap.
    band_high(0.45)와 다른 역할: band는 소극적 억제, cap은 적극적 패널티.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    fl_contact = metrics["contact_ratio_fl"]
    fr_contact = metrics["contact_ratio_fr"]
    gap = torch.clamp(fl_contact - float(contact_cap), min=0.0) \
        + torch.clamp(fr_contact - float(contact_cap), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


def pitch_ang_vel_l2(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_vel: float = 0.05,
) -> torch.Tensor:
    """V56.M1: body-frame pitch angular velocity 직접 억제.

    step마다 앞으로 고꾸라지는 nose-down oscillation을 직접 겨냥한다.
    ang_vel_xy_l2는 roll/pitch를 함께 벌하지만, M1에서는 pitch 축을 별도로
    더 강하게 눌러 front-heavy landing strategy를 줄이는 것이 목적이다.
    """
    asset: Articulation = env.scene[asset_cfg.name]
    ang_vel_b = getattr(asset.data, "root_ang_vel_b", None)
    if ang_vel_b is None:
        ang_vel_b = asset.data.root_ang_vel_w
    pitch_vel = ang_vel_b[:, 1]
    return torch.square(pitch_vel) * _heading_velocity_gate(env, asset_cfg, min_vel)


def front_rear_support_balance_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_diff: float = 0.50,
    contact_target: float = 0.5,
    propulsion_target: float = 0.30,
    leg_lift_target: float = 0.18,
    clearance_target: float = 0.03,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """V26: 앞/뒤 전체 지지 편중 억제.

    앞다리 usage 평균 vs 뒷다리 usage 평균의 차이를 측정.
    앞뒤는 구조적으로 다소 비대칭 허용 → max_diff=0.50으로 여유 부여.
    병적인 front-only 또는 rear-only 보행만 억제.
    """
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, dtype=torch.float, device=env.device)
    usage_scores = _compute_limb_usage_proxy(
        metrics, contact_target, propulsion_target, leg_lift_target, clearance_target
    )
    front_mean = (usage_scores["fl"] + usage_scores["fr"]) / 2.0
    rear_mean = (usage_scores["rl"] + usage_scores["rr"]) / 2.0
    support_diff = torch.abs(front_mean - rear_mean)
    gap = torch.clamp(support_diff - float(max_diff), min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)


# ============================================================
# V26: Diagonal Coupling with General Per-Limb Collapse Gate
# V25는 RL만 게이팅 → V26은 모든 다리에 대칭 soft gate 적용.
# ============================================================


def diagonal_coupling_soft_gate_reward(
    env: ManagerBasedRLEnv,
    pair_a_front_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_a_rear_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_b_front_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_b_rear_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_deadzone: float = 0.1,
    min_vel: float = 0.05,
    min_contact: float = 0.15,
    min_propulsion: float = 0.0,
) -> torch.Tensor:
    """V26/V27: diagonal coupling with general per-limb collapse soft gate.

    Pair A (FL↔RR): 두 다리 중 하나라도 collapse면 보상 attenuation.
    Pair B (FR↔RL): 두 다리 중 하나라도 collapse면 보상 attenuation.

    V25는 RL만 gate → 3-leg exploit 차단 불완전.
    V26은 FL/FR/RL/RR 모두 동일 기준으로 게이팅 → 어느 다리라도
    collapse 상태면 그 다리가 포함된 diagonal pair 보상이 감소.

    min_contact=0.15: contact_ratio 15% 이상이면 gate=1 (정상 참여).
    min_propulsion>0 (V27): propulsion도 gate에 포함 → 더 강한 차단.
      gate = (contact_gate) * (propulsion_gate)
      fake contact(접지하되 추진 0)도 gate 통과 불가.
    """
    asset: Articulation = env.scene[pair_a_front_cfg.name]

    fl_vel = asset.data.joint_vel[:, pair_a_front_cfg.joint_ids]  # (N, 2)
    rr_vel = asset.data.joint_vel[:, pair_a_rear_cfg.joint_ids]   # (N, 2)
    fr_vel = asset.data.joint_vel[:, pair_b_front_cfg.joint_ids]  # (N, 2)
    rl_vel = asset.data.joint_vel[:, pair_b_rear_cfg.joint_ids]   # (N, 2)

    dz_sq = vel_deadzone ** 2
    pair_a_corr = torch.tanh(fl_vel * rr_vel / dz_sq)
    pair_b_corr = torch.tanh(fr_vel * rl_vel / dz_sq)

    pair_a_reward = torch.clamp(pair_a_corr, 0.0, 1.0).mean(dim=1)
    pair_b_reward = torch.clamp(pair_b_corr, 0.0, 1.0).mean(dim=1)
    # Save pre-gate raw values for monitoring (diagonal_coupling_raw)
    pair_a_raw = pair_a_reward.clone()
    pair_b_raw = pair_b_reward.clone()

    # General collapse gate: attenuation이 필요한 다리가 포함된 pair의 보상을 감소
    metrics = compute_v23_raw_metrics(env)
    if metrics:
        mc = max(float(min_contact), 1.0e-6)
        fl_gate = torch.clamp(metrics["contact_ratio_fl"] / mc, 0.0, 1.0)
        rr_gate = torch.clamp(metrics["contact_ratio_rr"] / mc, 0.0, 1.0)
        fr_gate = torch.clamp(metrics["contact_ratio_fr"] / mc, 0.0, 1.0)
        rl_gate = torch.clamp(metrics["contact_ratio_rl"] / mc, 0.0, 1.0)
        # V27: propulsion gate 추가 (min_propulsion>0일 때만 활성)
        if float(min_propulsion) > 0.0:
            mp = max(float(min_propulsion), 1.0e-6)
            fl_gate = fl_gate * torch.clamp(metrics["propulsion_fl"] / mp, 0.0, 1.0)
            rr_gate = rr_gate * torch.clamp(metrics["propulsion_rr"] / mp, 0.0, 1.0)
            fr_gate = fr_gate * torch.clamp(metrics["propulsion_fr"] / mp, 0.0, 1.0)
            rl_gate = rl_gate * torch.clamp(metrics["propulsion_rl"] / mp, 0.0, 1.0)
        # pair A: FL과 RR이 모두 정상이어야 보상 (둘 다 살아야 진짜 trot)
        pair_a_reward = pair_a_reward * fl_gate * rr_gate
        # pair B: FR과 RL이 모두 정상이어야 보상
        pair_b_reward = pair_b_reward * fr_gate * rl_gate

    reward = (pair_a_reward + pair_b_reward) / 2.0

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    # Push raw (pre-gate) coupling to episode sums for gated vs raw comparison
    raw_coupling = (pair_a_raw + pair_b_raw) / 2.0 * vel_gate
    if hasattr(env, "_v23_raw_metric_episode_sums") and "diagonal_coupling_raw" in env._v23_raw_metric_episode_sums:
        env._v23_raw_metric_episode_sums["diagonal_coupling_raw"] += raw_coupling * env.step_dt

    return reward * vel_gate


def joint_pos_target_l2(env: ManagerBasedRLEnv, target: float, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Penalize joint position deviation from a target value."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    # wrap the joint positions to (-pi, pi)
    joint_pos = wrap_to_pi(asset.data.joint_pos[:, asset_cfg.joint_ids])
    # compute the reward
    return torch.sum(torch.square(joint_pos - target), dim=1)


def joint_default_pos_l2(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """모든 관절이 init pose(default_joint_pos)에서 벗어나면 penalty.

    서기 학습에서 "이상적 자세 유지"를 직접 유도.
    splay, 웅크림, 비대칭 등 모든 자세 이탈을 하나의 항으로 억제.
    """
    asset: Articulation = env.scene[asset_cfg.name]
    current = asset.data.joint_pos
    default = asset.data.default_joint_pos
    return torch.sum(torch.square(current - default), dim=1)


def standing_height_exp(
    env: ManagerBasedRLEnv,
    target_height: float,
    sigma: float = 0.05,
    start_time: float = 0.0,
    standing_vel_threshold: float | None = None,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """높이 + 수평 결합 보상. 목표 높이에 가깝고 수평일수록 높은 보상.

    높이만 맞추고 기울어지는 꼼수 방지를 위해 두 요소를 곱한다.
    start_time을 설정하면 에피소드 초반에는 보상을 주지 않는다.
    """
    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    height_factor = torch.exp(-torch.square(target_height - height) / (2.0 * sigma * sigma))
    # Orientation quality: projected gravity XY components (0 when level)
    gravity_xy = asset.data.projected_gravity_b[:, :2]  # (num_envs, 2)
    orientation_factor = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))
    result = height_factor * orientation_factor
    # Time gate: only give reward after start_time seconds
    if start_time > 0.0:
        elapsed = env.episode_length_buf * env.step_dt
        result = result * (elapsed >= start_time).float()
    # Optional command gate: only reward standing height when the commanded locomotion speed is near zero.
    # yaw 포함: sqrt(vx^2 + vy^2 + 0.5*wz^2) — yaw-only turning env에서 standing reward 방지.
    if standing_vel_threshold is not None:
        command = env.command_manager.get_command("base_velocity")
        vx = command[:, 0]
        vy = command[:, 1]
        wz = command[:, 2] if command.shape[1] > 2 else torch.zeros_like(vx)
        command_speed = torch.sqrt(vx * vx + vy * vy + 0.5 * wz * wz)
        result = result * (command_speed <= standing_vel_threshold).float()
    return result


def shoulder_torque_saturated(
    env: ManagerBasedRLEnv,
    threshold_ratio: float = 0.95,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Terminate when any shoulder joint torque reaches servo limit.
    Returns True (terminate) if any shoulder |torque| >= threshold_ratio * effort_limit."""
    asset = env.scene[asset_cfg.name]
    if not hasattr(asset.data, "applied_torque"):
        return torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    torques = asset.data.applied_torque  # (num_envs, num_joints)
    # Find shoulder joint indices
    shoulder_ids = [i for i, name in enumerate(asset.joint_names) if "shoulder" in name]
    if not shoulder_ids:
        return torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    shoulder_torques = torques[:, shoulder_ids].abs()  # (num_envs, num_shoulders)
    effort_limit = asset.actuators["legs"].effort_limit
    if isinstance(effort_limit, torch.Tensor):
        limit = float(effort_limit.max().item())
    else:
        limit = float(effort_limit)
    saturated = (shoulder_torques >= threshold_ratio * limit).any(dim=1)
    return saturated


def bad_orientation_grace(
    env: ManagerBasedRLEnv,
    limit_angle: float = 0.35,
    grace_steps: int = 150,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """bad_orientation with grace period. First grace_steps are immune."""
    asset = env.scene[asset_cfg.name]
    gravity = asset.data.projected_gravity_b  # (N, 3)
    # tilt = angle from upright: acos(-gz / |g|)
    tilt = torch.acos(torch.clamp(-gravity[:, 2] / (torch.norm(gravity, dim=1) + 1e-6), -1, 1))
    past_grace = env.episode_length_buf >= grace_steps
    return (tilt > limit_angle) & past_grace


def feet_lifted_termination(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    threshold: float = 1.0,
    grace_steps: int = 150,
    consecutive_steps: int = 5,
) -> torch.Tensor:
    """발이 하나라도 연속으로 떠있으면 termination (grace period 이후).

    순간적인 toe contact dropout으로 즉사하지 않도록, one-step glitch는 무시하고
    연속 ``consecutive_steps`` 동안 하나 이상의 toe가 비접촉일 때만 종료한다.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, threshold)
    any_lifted = ~contacts.all(dim=1)  # 하나라도 안 닿으면 True
    past_grace = env.episode_length_buf >= grace_steps

    buf_name = f"_feet_lifted_consec_{sensor_cfg.name}"
    if not hasattr(env, buf_name):
        setattr(env, buf_name, torch.zeros(env.num_envs, device=env.device, dtype=torch.long))

    consec = getattr(env, buf_name)
    reset_mask = env.episode_length_buf <= 1
    consec = torch.where(reset_mask, torch.zeros_like(consec), consec)
    consec = torch.where(any_lifted, consec + 1, torch.zeros_like(consec))
    setattr(env, buf_name, consec)

    return (consec >= consecutive_steps) & past_grace


def feet_lift_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    threshold: float = 1.0,
) -> torch.Tensor:
    """서기 중 발을 떼면 penalty. 뗀 발 수에 비례 (0~1, 1=4발 전부 뗌)."""
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, threshold)
    # contacts: True=접지, False=떠있음
    lifted = (~contacts).float()  # 떠있으면 1
    return lifted.mean(dim=1)  # 0=전부 접지, 0.25=1발, 0.5=2발, 1.0=전부 뗌


def flat_orientation_bonus(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """수평 유지 보상. 완전 수평이면 1.0, 기울어질수록 0에 가까움."""
    asset = env.scene[asset_cfg.name]
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    return torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))


def feet_below_knees(
    env: ManagerBasedRLEnv,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    knee_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize when feet are above knees. Returns penalty per foot that violates.

    Each foot's Z position should be LOWER than its corresponding knee's Z position.
    When foot_z > knee_z, the leg is inverted (unnatural).
    Returns sum of squared violations across all legs.
    """
    asset = env.scene[foot_cfg.name]
    # Get Z heights (world frame)
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, num_feet)
    knee_z = asset.data.body_pos_w[:, knee_cfg.body_ids, 2]  # (num_envs, num_knees)
    # Violation: foot is above knee (positive value = bad)
    violation = torch.clamp(foot_z - knee_z, min=0.0)  # only penalize when foot > knee
    # Sum squared violations across all legs
    return torch.sum(torch.square(violation), dim=1)


def body_height_reward(
    env: ManagerBasedRLEnv,
    target_height: float,
    penalty_below: float,
    start_time: float = 0.0,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Reward/penalize specific body links based on their height from ground.

    Returns a continuous value:
    - Negative (penalty) when body height < target_height (closer to ground = worse)
    - Positive (reward) when body height >= target_height

    The penalty scales quadratically as the body gets closer to the ground.
    The reward is a small positive value when at or above the target.

    Args:
        env: The environment.
        target_height: The desired minimum height for the body links.
        penalty_below: Height threshold below which a strong penalty applies.
        asset_cfg: The asset configuration with body_ids to check.
    """
    asset = env.scene[asset_cfg.name]
    # Get world-frame Z positions of specified bodies: (num_envs, num_bodies)
    body_heights = asset.data.body_pos_w[:, asset_cfg.body_ids, 2]  # type: ignore
    # Subtract env origins Z to get height above ground
    body_heights = body_heights - env.scene.env_origins[:, 2].unsqueeze(1)
    # Use minimum height among all specified bodies
    min_height = torch.min(body_heights, dim=1)[0]
    # Quadratic penalty below target, small reward above
    error = min_height - target_height
    # Below target: quadratic penalty (negative). Above target: small positive reward
    reward = torch.where(
        error < 0,
        -torch.square(error) * (1.0 + 10.0 * torch.clamp(-error / target_height, 0, 1)),  # stronger as closer to ground
        torch.clamp(error, max=0.05) * 2.0,  # small reward for being above target
    )
    # Time gate
    if start_time > 0.0:
        elapsed = env.episode_length_buf * env.step_dt
        reward = reward * (elapsed >= start_time).float()
    return reward


def shoulder_stance_symmetry(
    env: ManagerBasedRLEnv,
    front_shoulder_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    rear_shoulder_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize asymmetric shoulder splay between front and rear legs.

    When viewed from above, the front and rear legs should have similar
    outward splay. This function penalizes the squared difference between
    each front shoulder angle and its corresponding rear shoulder angle:
      penalty = (front_left - rear_left)^2 + (front_right - rear_right)^2

    Use with a negative weight to discourage asymmetric stance.
    """
    asset = env.scene[front_shoulder_cfg.name]
    front_angles = asset.data.joint_pos[:, front_shoulder_cfg.joint_ids]  # (num_envs, 2)
    rear_angles = asset.data.joint_pos[:, rear_shoulder_cfg.joint_ids]    # (num_envs, 2)
    # Each front shoulder should match its corresponding rear shoulder
    diff = front_angles - rear_angles
    return torch.sum(torch.square(diff), dim=1)


def shoulder_neutral_penalty(
    env: ManagerBasedRLEnv,
    shoulder_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_angles: list[float] | None = None,
) -> torch.Tensor:
    """어깨가 타깃 각도에서 벗어나면 페널티.

    V19: SpotMicro 기구학 반영 — 어깨 roll축(X)에서 음수=바깥 벌림.
    target_angles가 None이면 기존처럼 0 기준, 지정하면 해당 각도 기준.
    """
    asset = env.scene[shoulder_cfg.name]
    shoulder_angles = asset.data.joint_pos[:, shoulder_cfg.joint_ids]  # (num_envs, 4)
    if target_angles is not None:
        targets = torch.tensor(target_angles, device=shoulder_angles.device, dtype=shoulder_angles.dtype)
        return torch.sum(torch.square(shoulder_angles - targets), dim=1)
    return torch.sum(torch.square(shoulder_angles), dim=1)


def shoulder_splay_termination(
    env: ManagerBasedRLEnv,
    shoulder_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_angles: list[float] | None = None,
    threshold: float = 0.3,
    margin: float = 0.3,
    probability: float = 0.0004,
) -> torch.Tensor:
    """Soft CaT: termination probability proportional to splay deviation.

    V38.2: phase transition 제거 — dev가 threshold~threshold+margin 구간에서
    종료 확률이 0~probability로 선형 증가. dev <= threshold이면 종료 확률 0.
    """
    asset = env.scene[shoulder_cfg.name]
    shoulder_angles = asset.data.joint_pos[:, shoulder_cfg.joint_ids]
    if target_angles is not None:
        targets = torch.tensor(target_angles, device=shoulder_angles.device, dtype=shoulder_angles.dtype)
        dev = torch.abs(shoulder_angles - targets)
    else:
        dev = torch.abs(shoulder_angles)
    max_dev = dev.max(dim=1).values  # worst of 4 shoulders
    scale = torch.clamp((max_dev - threshold) / margin, 0.0, 1.0)
    effective_prob = probability * scale
    rand = torch.rand(env.num_envs, device=env.device)
    return rand < effective_prob


def stance_width_penalty(
    env: ManagerBasedRLEnv,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    front_max_width: float = 0.19,
    rear_max_width: float = 0.21,
    tolerance: float = 0.05,
) -> torch.Tensor:
    """Penalize overly wide left-right stance in the robot body frame.

    V23 phase-1 only suppresses the too-wide failure mode. The metric is computed
    in the body frame using yaw-only rotation so turning direction does not distort
    the width estimate.
    """
    asset = env.scene[foot_cfg.name]
    robot = env.scene[asset_cfg.name]

    foot_pos_xy = asset.data.body_pos_w[:, foot_cfg.body_ids, :2]
    root_pos_xy = robot.data.root_pos_w[:, :2].unsqueeze(1)
    rel_xy = foot_pos_xy - root_pos_xy

    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    yaw = torch.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    cos_yaw = torch.cos(yaw).unsqueeze(1)
    sin_yaw = torch.sin(yaw).unsqueeze(1)

    body_y = -sin_yaw * rel_xy[:, :, 0] + cos_yaw * rel_xy[:, :, 1]

    front_width = torch.abs(body_y[:, 0] - body_y[:, 1])
    rear_width = torch.abs(body_y[:, 2] - body_y[:, 3])

    front_excess = torch.clamp(front_width - front_max_width, min=0.0)
    rear_excess = torch.clamp(rear_width - rear_max_width, min=0.0)

    return torch.square(front_excess / (tolerance + 1e-6)) + torch.square(rear_excess / (tolerance + 1e-6))


def leg_pose_symmetry(
    env: ManagerBasedRLEnv,
    front_leg_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    rear_leg_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Penalize asymmetric leg/foot bending between front and rear legs.

    When viewed from the side, the front and rear legs should have similar
    bend angles. This function penalizes the squared difference between
    each front leg/foot joint and its corresponding rear joint:
      penalty = sum((front_joint_i - rear_joint_i)^2)

    Covers both 'leg' (upper) and 'foot' (lower) joints.
    Use with a negative weight to discourage asymmetric bending.
    """
    asset = env.scene[front_leg_cfg.name]
    front_angles = asset.data.joint_pos[:, front_leg_cfg.joint_ids]  # (num_envs, N)
    rear_angles = asset.data.joint_pos[:, rear_leg_cfg.joint_ids]    # (num_envs, N)
    diff = front_angles - rear_angles
    return torch.sum(torch.square(diff), dim=1)


def progressive_height_reward(
    env: ManagerBasedRLEnv,
    min_height: float,
    max_height: float,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """높을수록 보상이 커지는 선형 보상. 기울어지면 보상이 깎인다."""
    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2]
    # 높이 진행도: 0 (크라우치) ~ 1.0 (최대)
    progress = (height - min_height) / (max_height - min_height)
    progress = torch.clamp(progress, 0.0, 1.0)
    # 수평 보정: projected gravity z (완전 수평이면 -1.0)
    gravity_z = asset.data.projected_gravity_b[:, 2]  # -1.0 = 수평
    orientation_quality = torch.clamp((-gravity_z - 0.5) / 0.5, 0.0, 1.0)  # 0.5→0, 1.0→1
    return progress * orientation_quality


def all_feet_on_ground(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    threshold: float = 1.0,
) -> torch.Tensor:
    """발이 바닥에 닿아있는 비율. 4개 다 닿으면 1.0, 3개면 0.75, 0개면 0.0."""
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, threshold)
    # 각 발의 접촉 비율 (0~1)
    return contacts.float().mean(dim=1)


def contact_switch_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    threshold: float = 1.0,
) -> torch.Tensor:
    """Penalize unnecessary contact state changes between consecutive steps."""
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, threshold).float()

    if not hasattr(env, "_prev_contact_state_b1"):
        env._prev_contact_state_b1 = contacts.clone()
        return torch.zeros(env.num_envs, device=env.device)

    reset_mask = (env.episode_length_buf <= 1).unsqueeze(1)
    previous = torch.where(reset_mask, contacts, env._prev_contact_state_b1)
    switches = torch.abs(contacts - previous)
    env._prev_contact_state_b1 = contacts.clone()
    return switches.mean(dim=1)


def contact_foot_velocity_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    threshold: float = 1.0,
) -> torch.Tensor:
    """Penalize XY toe speed while the toe is in contact."""
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, threshold).float()

    asset = env.scene[foot_cfg.name]
    foot_vel_xy = asset.data.body_vel_w[:, foot_cfg.body_ids, :2]
    foot_speed_xy = torch.norm(foot_vel_xy, dim=-1)

    active_contacts = contacts.sum(dim=1)
    contact_count = active_contacts.clamp(min=1.0)
    mean_contact_speed = (foot_speed_xy * contacts).sum(dim=1) / contact_count
    return torch.where(active_contacts > 0.0, mean_contact_speed, torch.zeros_like(mean_contact_speed))


def forward_velocity_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_vel: float = 0.3,
) -> torch.Tensor:
    """수평 자세로 전진할 때만 보상. 넘어지면서 돌진하는 꼼수 방지."""
    asset = env.scene[asset_cfg.name]
    forward_vel = asset.data.root_lin_vel_b[:, 0]
    normalized_vel = torch.clamp(forward_vel / target_vel, -1.0, 1.0)
    # 수평일 때만 전진 보상 (기울어지면 보상 감소)
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    orientation_quality = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))
    return normalized_vel * orientation_quality


def foot_clearance_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_clearance: float = 0.03,
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """스윙 중인 발이 일정 높이 이상 들려야 보상. 전진 없이 발만 드는 건 방지."""
    # 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (num_envs, num_feet), True = 접촉 중

    # 발 높이 (지면 기준)
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z

    # 스윙 중인 발에 대해 높이 보상
    swing_mask = ~contacts
    clearance_reward = torch.clamp(foot_height / target_clearance, 0.0, 1.0)
    swing_reward = clearance_reward * swing_mask.float()

    # 스윙 발 평균
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    base_reward = swing_reward.sum(dim=1) / num_swing

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def rear_foot_clearance_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_clearance: float = 0.02,
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리(RL, RR)만 대상으로 한 foot clearance 보상.

    front는 이미 swing이 나오고 있으므로, rear만 직접 유도.
    body 순서: FL(0), FR(1), RL(2), RR(3).
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)

    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z

    # rear만 선택 (index 2=RL, 3=RR)
    rear_swing = ~contacts[:, 2:4]
    rear_height = foot_height[:, 2:4]
    clearance_score = torch.clamp(rear_height / target_clearance, 0.0, 1.0)
    swing_reward = clearance_score * rear_swing.float()

    num_swing = rear_swing.float().sum(dim=1).clamp(min=1.0)
    base_reward = swing_reward.sum(dim=1) / num_swing

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def rear_feet_air_time_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    threshold: float = 0.1,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리(RL, RR) touchdown 시점에 air_time 기반 보상.

    Isaac Lab feet_air_time과 동일 구조: swing→contact 전환 시점에만 보상.
    매 step dense가 아니므로 "rear를 계속 들고 있기" exploit를 방지.
    body 순서: FL(0), FR(1), RL(2), RR(3).
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)

    # rear만 (index 2=RL, 3=RR)
    rear_contacts = contacts[:, 2:4]  # (num_envs, 2)

    # air time 추적 (per-env, per-rear-leg)
    dt = env.step_dt
    if not hasattr(env, "_rear_air_time"):
        env._rear_air_time = torch.zeros(env.num_envs, 2, device=env.device)
        env._rear_last_contacts = torch.ones(env.num_envs, 2, dtype=torch.bool, device=env.device)

    # swing 중이면 시간 누적
    env._rear_air_time += dt
    env._rear_air_time *= ~rear_contacts  # contact 시 0으로 리셋

    # touchdown 감지: 이전 step swing → 현재 step contact
    first_contact = rear_contacts & ~env._rear_last_contacts

    # touchdown 시점에 보상: 리셋 전 air_time을 _rear_last_air_time에서 복원
    # air_time은 이미 리셋됐으므로, 이전 step의 값을 별도 저장
    if not hasattr(env, "_rear_last_air_time"):
        env._rear_last_air_time = torch.zeros(env.num_envs, 2, device=env.device)

    # touchdown 시 보상 = clamp(last_air_time - threshold, 0)
    # threshold 미만의 짧은 떨림은 보상 0
    air_bonus = torch.clamp(env._rear_last_air_time - threshold, min=0.0)
    reward_per_leg = air_bonus * first_contact.float()

    # 다음 step을 위해 현재 air_time 저장 (리셋 전 값 = swing 중 누적값)
    # contact 시 이미 0이므로, swing 중일 때만 갱신
    swing_mask = ~rear_contacts
    env._rear_last_air_time = torch.where(swing_mask, env._rear_air_time, env._rear_last_air_time)
    # contact된 순간 last_air_time은 유지 (touchdown 보상에 사용 후 다음 swing에서 덮어씌워짐)

    env._rear_last_contacts = rear_contacts.clone()

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward_per_leg.sum(dim=1) * vel_gate


def front_rear_swing_balance_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """Front pair vs Rear pair의 swing 비율 차이를 penalty.

    front_swing = mean(1-cr_FL, 1-cr_FR), rear_swing = mean(1-cr_RL, 1-cr_RR).
    |front_swing - rear_swing|가 크면 penalty → 한쪽만 swing하는 패턴 방지.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (num_envs, 4): FL, FR, RL, RR
    front_swing = (1.0 - cr[:, 0] + 1.0 - cr[:, 1]) / 2.0
    rear_swing = (1.0 - cr[:, 2] + 1.0 - cr[:, 3]) / 2.0
    return torch.abs(front_swing - rear_swing)


def front_rear_contact_balance_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """Front pair vs Rear pair의 contact 비율 차이를 penalty.

    한쪽 pair가 완전 접지(99%) + 다른쪽 완전 swing(1%)인 극단 해 방지.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )
    front_contact = (cr[:, 0] + cr[:, 1]) / 2.0
    rear_contact = (cr[:, 2] + cr[:, 3]) / 2.0
    return torch.abs(front_contact - rear_contact)


def adaptive_phase_diagonal_event_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    vel_scale: float = 4.0,
    min_frequency: float = 1.0,
    max_frequency: float = 4.0,
    duty_factor: float = 0.55,
    min_vel: float = 0.05,
    command_name: str = "base_velocity",
) -> torch.Tensor:
    """Command 속도 연동 phase + touchdown event 기반 diagonal 보상.

    기존 phase_contact_reward와 다른 점:
    1. frequency가 command vel_x에 비례 (느리면 느린 cadence, actual vel보다 안정적)
    2. 매 step contact match가 아닌 touchdown event 시점만 보상 (sparse)
    3. 올바른 phase에서 touchdown하면 보상, 잘못된 phase면 0

    body 순서: FL(0), FR(1), RL(2), RR(3)
    Trot: FL/RR = base phase, FR/RL = base + pi
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)

    # touchdown 감지 + episode reset 처리
    if not hasattr(env, "_adp_last_contacts"):
        env._adp_last_contacts = torch.ones(env.num_envs, 4, dtype=torch.bool, device=env.device)
    # episode reset된 env는 last_contacts를 초기화 (첫 step에서 가짜 touchdown 방지)
    reset_mask = (env.episode_length_buf <= 1).unsqueeze(1)  # (num_envs, 1)
    env._adp_last_contacts = torch.where(reset_mask, contacts, env._adp_last_contacts)
    first_contact = contacts & ~env._adp_last_contacts  # (num_envs, 4)
    env._adp_last_contacts = contacts.clone()

    # command velocity 기반 frequency (actual vel보다 안정적)
    vel_cmd = env.command_manager.get_command(command_name)[:, 0]  # cmd vel_x
    frequency = torch.clamp(vel_cmd * vel_scale, min_frequency, max_frequency)  # (num_envs,)

    # phase 계산
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t  # (num_envs,)

    # Trot phases: FL/RR = base, FR/RL = base + pi
    fl_phase = base_phase
    fr_phase = base_phase + math.pi
    rl_phase = base_phase + math.pi
    rr_phase = base_phase
    phases = torch.stack([fl_phase, fr_phase, rl_phase, rr_phase], dim=1)  # (num_envs, 4)

    # stance phase 판정: phase_norm < duty_factor * 2pi → stance expected
    phase_norm = phases % (2.0 * math.pi)
    stance_threshold_val = duty_factor * 2.0 * math.pi
    in_stance_phase = (phase_norm < stance_threshold_val)  # (num_envs, 4)

    # touchdown이 stance phase 시작 시점에 발생하면 보상
    correct_touchdown = first_contact & in_stance_phase  # (num_envs, 4)

    # per-leg reward: 올바른 touchdown마다 +1
    reward = correct_touchdown.float().sum(dim=1)

    # 전진 게이팅 (command 기반)
    vel_gate = torch.clamp(vel_cmd / min_vel, 0.0, 1.0)
    return reward * vel_gate


def non_toe_contact_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    threshold: float = 1.0,
) -> torch.Tensor:
    """toe 이외의 다리 링크(foot_link, leg_link)가 접촉하면 penalty.

    RL이 무릎/발목 관절로 바닥을 찍는 비정상 접촉을 직접 벌함.
    sensor_cfg.body_ids는 foot_link + leg_link를 포함해야 함 (toe 제외).
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    forces = contact_sensor.data.net_forces_w[:, sensor_cfg.body_ids, :].norm(dim=-1)
    contact_count = (forces > threshold).float().sum(dim=1)
    return contact_count


def contact_drag_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """접촉 중인 발의 수평 속도(끌림)를 penalty.

    RR이 뒤로 끌리거나, 발이 지면에서 미끄러지는 것을 방지.
    접촉 중 + 수평 속도가 크면 penalty.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)

    asset = env.scene[foot_cfg.name]
    foot_vel_xy = asset.data.body_vel_w[:, foot_cfg.body_ids, :2]  # (num_envs, num_feet, 2)
    foot_speed = foot_vel_xy.norm(dim=-1)  # (num_envs, num_feet)

    # 접촉 중인 발의 수평 속도만 penalty
    drag = foot_speed * contacts.float()
    return drag.sum(dim=1)


def stance_width_min_penalty(
    env: ManagerBasedRLEnv,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_width: float = 0.10,
) -> torch.Tensor:
    """앞/뒤 발 쌍의 좌우 간격이 min_width 미만이면 penalty.

    앞다리를 모아서 걷거나 crossing posture를 방지.
    body 순서: FL(0), FR(1), RL(2), RR(3).
    """
    asset = env.scene[foot_cfg.name]
    foot_y = asset.data.body_pos_w[:, foot_cfg.body_ids, 1]  # (num_envs, 4)

    # front pair 간격: |FL_y - FR_y|
    front_width = torch.abs(foot_y[:, 0] - foot_y[:, 1])
    # rear pair 간격: |RL_y - RR_y|
    rear_width = torch.abs(foot_y[:, 2] - foot_y[:, 3])

    front_gap = torch.clamp(min_width - front_width, min=0.0)
    rear_gap = torch.clamp(min_width - rear_width, min=0.0)
    return front_gap + rear_gap


def rear_trailing_penalty(
    env: ManagerBasedRLEnv,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_rear_back: float = 0.06,
) -> torch.Tensor:
    """Penalize rear toes that stay too far behind the body in the body frame.

    This directly targets the GUI-observed pathology where a rear leg trails behind
    like a tail instead of cycling under the body. Only the rear toes (RL, RR) are
    considered. The penalty is zero while both rear toes stay within the allowed
    rearward range, and grows linearly once either toe drifts farther back.
    """
    asset = env.scene[foot_cfg.name]
    robot = env.scene[asset_cfg.name]

    foot_pos_xy = asset.data.body_pos_w[:, foot_cfg.body_ids, :2]
    root_pos_xy = robot.data.root_pos_w[:, :2].unsqueeze(1)
    rel_xy = foot_pos_xy - root_pos_xy

    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    yaw = torch.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    cos_yaw = torch.cos(yaw).unsqueeze(1)
    sin_yaw = torch.sin(yaw).unsqueeze(1)

    body_x = cos_yaw * rel_xy[:, :, 0] + sin_yaw * rel_xy[:, :, 1]
    rear_x = body_x[:, 2:4]  # RL, RR

    # rear toe behind body more than max_rear_back -> penalty
    excess_back = torch.clamp((-rear_x) - max_rear_back, min=0.0)
    return excess_back.sum(dim=1)


def rear_leg_min_swing_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    min_swing_ratio: float = 0.05,
) -> torch.Tensor:
    """Penalize rear legs when either RL or RR almost never leaves stance.

    This targets the K2 pathology where RR trailing is reduced, but RL becomes
    a permanent stance anchor. The penalty is zero once both rear legs achieve
    at least ``min_swing_ratio`` over the rolling contact-ratio window.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )
    rear_swing = 1.0 - cr[:, 2:4]  # RL, RR
    swing_deficit = torch.clamp(min_swing_ratio - rear_swing, min=0.0)
    return swing_deficit.sum(dim=1)


def diagonal_pair_lock_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    gap_threshold: float = 0.45,
) -> torch.Tensor:
    """한 대각 쌍만 영구 swing하는 pair-lock exploit를 penalty.

    pairA_swing = (sw_FL + sw_RR) / 2, pairB_swing = (sw_FR + sw_RL) / 2.
    |pairA - pairB| > gap_threshold이면 초과분만큼 penalty.
    작은 차이는 무시 (정상 보행에서도 순간 비대칭 가능).
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )
    sw = 1.0 - cr  # swing ratio
    pair_a_swing = (sw[:, 0] + sw[:, 3]) / 2.0  # FL + RR
    pair_b_swing = (sw[:, 1] + sw[:, 2]) / 2.0  # FR + RL
    gap = torch.abs(pair_a_swing - pair_b_swing)
    return torch.clamp(gap - gap_threshold, min=0.0)


def prolonged_pair_lock_termination(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    gap_threshold: float = 0.50,
    grace_steps: int = 50,
    consecutive_steps: int = 20,
) -> torch.Tensor:
    """한 대각 쌍이 지속적으로 lock되면 episode 종료.

    |pairA_swing - pairB_swing| > gap_threshold가 consecutive_steps 연속이면 True.
    grace_steps 이전에는 판정 안 함.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )
    sw = 1.0 - cr
    pair_a_swing = (sw[:, 0] + sw[:, 3]) / 2.0
    pair_b_swing = (sw[:, 1] + sw[:, 2]) / 2.0
    gap = torch.abs(pair_a_swing - pair_b_swing)
    is_locked = gap > gap_threshold

    if not hasattr(env, "_pair_lock_count"):
        env._pair_lock_count = torch.zeros(env.num_envs, dtype=torch.long, device=env.device)

    # episode reset 처리
    reset_mask = env.episode_length_buf <= 1
    env._pair_lock_count = torch.where(reset_mask, torch.zeros_like(env._pair_lock_count), env._pair_lock_count)

    # 연속 카운트
    env._pair_lock_count = torch.where(is_locked, env._pair_lock_count + 1, torch.zeros_like(env._pair_lock_count))

    # grace 이후 + consecutive 초과 시 termination
    in_grace = env.episode_length_buf < grace_steps
    terminate = (~in_grace) & (env._pair_lock_count >= consecutive_steps)
    return terminate


def diagonal_pair_separation_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """대각 쌍 간 contact ratio 분리도를 직접 보상.

    |pair_A_cr - pair_B_cr|가 클수록 한 쌍이 stance, 다른 쌍이 swing.
    per_leg_contact_min/excess_swing이 극단 해를 방지하므로
    이 보상은 "적절한 범위 내에서 분리도를 높이는" 역할.
    전진 게이팅으로 정지 상태에서의 보상을 방지.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )
    pair_a = (cr[:, 0] + cr[:, 3]) / 2.0  # FL+RR
    pair_b = (cr[:, 1] + cr[:, 2]) / 2.0  # FR+RL
    separation = torch.abs(pair_a - pair_b)

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return separation * vel_gate


def forward_step_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """Swing 중인 발의 전방 속도를 보상.

    단순히 발을 드는 것이 아니라, 들린 발이 실제로 앞으로 이동하는지 보상.
    swing 중 foot의 world x 속도가 body보다 빠르면 보상 (= body 기준 전진).
    ang_vel_z=0일 때 world x ≈ body forward. "제자리 흔들기"가 아닌 "전진형 보행"을 유도.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    swing_mask = ~contacts  # (num_envs, 4)

    # 발의 world-frame velocity
    asset = env.scene[foot_cfg.name]
    foot_vel = asset.data.body_vel_w[:, foot_cfg.body_ids, 0]  # x-velocity (num_envs, 4)

    # body-frame 전방 속도 (양수 = 전진)
    robot = env.scene[asset_cfg.name]
    body_vel_x = robot.data.root_lin_vel_w[:, 0].unsqueeze(1)  # (num_envs, 1)

    # 발의 상대 전방 속도 (body 기준 전진)
    relative_fwd = foot_vel - body_vel_x  # 발이 body보다 앞으로 가면 양수

    # swing 중 + 전방 이동인 발만 보상
    fwd_reward = torch.clamp(relative_fwd, 0.0, 0.5) * swing_mask.float()

    # 전진 게이팅
    vel_gate = torch.clamp(robot.data.root_lin_vel_b[:, 0] / min_vel, 0.0, 1.0)
    return fwd_reward.sum(dim=1) * vel_gate


def simple_diagonal_coupling_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """대각선 교대(trot) 패턴을 보상.

    trot = 한 대각 쌍(FL-RR)이 swing일 때 다른 쌍(FR-RL)이 stance, 그리고 교대.
    보상 조건:
    1. 대각 쌍 내 동기화: FL-RR 비슷, FR-RL 비슷 (각 쌍이 함께 움직임)
    2. 대각 쌍 간 반대: pair_A와 pair_B가 다른 상태 (교대)
    3. 실제 움직임: 4발 모두 접지인 정적 해 배제 (최소 swing 요구)

    4발 접지 시: sync=1이지만 anti_phase=0, swing_gate=0 → 보상 0.
    """
    cr = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # FL(0), FR(1), RL(2), RR(3)

    # 대각 쌍 평균 contact ratio
    pair_a_cr = (cr[:, 0] + cr[:, 3]) / 2.0  # FL-RR
    pair_b_cr = (cr[:, 1] + cr[:, 2]) / 2.0  # FR-RL

    # 1. 쌍 내 동기화 (둘이 비슷하면 1)
    sync_a = 1.0 - torch.abs(cr[:, 0] - cr[:, 3])
    sync_b = 1.0 - torch.abs(cr[:, 1] - cr[:, 2])
    sync = (sync_a + sync_b) / 2.0

    # 2. 쌍 간 반대 (두 쌍이 다른 상태면 1)
    anti_phase = torch.abs(pair_a_cr - pair_b_cr)

    # 3. 실제 swing 존재 (4발 평균 swing > 5%면 gate=1)
    mean_swing = 1.0 - cr.mean(dim=1)
    swing_gate = torch.clamp(mean_swing / 0.05, 0.0, 1.0)

    return sync * anti_phase * swing_gate


def per_leg_contact_min_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    min_contact_ratio: float = 0.15,
) -> torch.Tensor:
    """4발 중 가장 적게 접지하는 다리의 contact_ratio가 min_contact_ratio 미만이면 penalty.

    RR만 98% 공중에 띄우는 등 한 다리 비사용 exploit를 직접 벌함.
    전체 std 대신 min값만 보므로, 정상 보행의 순간적 비대칭은 건드리지 않음.
    """
    contact_ratio = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (num_envs, num_feet)
    min_ratio = contact_ratio.min(dim=1).values  # (num_envs,)
    # min_contact_ratio 미만인 만큼 penalty (0이면 penalty 없음)
    gap = torch.clamp(min_contact_ratio - min_ratio, min=0.0)
    return gap


def per_leg_excess_swing_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    max_swing_ratio: float = 0.70,
) -> torch.Tensor:
    """한 다리의 swing 비율(=1-contact_ratio)이 max_swing_ratio를 초과하면 penalty.

    RR swing_time=0.98 같은 영구 공중부양을 직접 타격.
    정상 보행에서 swing은 보통 30-50%이므로 70% threshold는 안전한 마진.
    """
    contact_ratio = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (num_envs, num_feet)
    swing_ratio = 1.0 - contact_ratio  # (num_envs, num_feet)
    # threshold 초과분의 합 (다리별로 독립)
    excess = torch.clamp(swing_ratio - max_swing_ratio, min=0.0)
    return excess.sum(dim=1)  # 여러 다리가 동시에 초과하면 누적


def pair_lr_symmetry_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    cr_weight: float = 0.5,
) -> torch.Tensor:
    """V63.B: pair 내 L/R 대칭 penalty. front+rear 동시.

    수식:
        front_lr_diff = |sw_FL - sw_FR| + cr_weight * |cr_FL - cr_FR|
        rear_lr_diff  = |sw_RL - sw_RR| + cr_weight * |cr_RL - cr_RR|
        penalty = front_lr_diff + rear_lr_diff

    front-only가 아닌 합산 설계로 V60.D 교훈("한쪽 pair 전용 보상→반대쪽 고착") 회피.
    pair 간 대칭은 기존 pair_lock이 담당, 이 penalty는 pair 내 L/R만 본다.

    body 순서: FL(0), FR(1), RL(2), RR(3)
    """
    contact_ratio = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (num_envs, 4)
    swing_ratio = 1.0 - contact_ratio

    # front pair: FL(0) vs FR(1)
    front_sw_diff = torch.abs(swing_ratio[:, 0] - swing_ratio[:, 1])
    front_cr_diff = torch.abs(contact_ratio[:, 0] - contact_ratio[:, 1])
    front_lr = front_sw_diff + cr_weight * front_cr_diff

    # rear pair: RL(2) vs RR(3)
    rear_sw_diff = torch.abs(swing_ratio[:, 2] - swing_ratio[:, 3])
    rear_cr_diff = torch.abs(contact_ratio[:, 2] - contact_ratio[:, 3])
    rear_lr = rear_sw_diff + cr_weight * rear_cr_diff

    # KPI logging
    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_front_contact_diff"] = front_cr_diff.mean().item()
            env.extras["log_front_swing_diff"] = front_sw_diff.mean().item()
            env.extras["log_rear_contact_diff"] = rear_cr_diff.mean().item()
            env.extras["log_rear_swing_diff"] = rear_sw_diff.mean().item()

    return front_lr + rear_lr


def phase_foot_reach_reward(
    env: ManagerBasedRLEnv,
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frequency: float = 2.0,
    reach_amplitude: float = 0.05,
    lift_amplitude: float = 0.0,
    duty_factor: float = 0.55,
    std: float = 0.035,
) -> torch.Tensor:
    """V63.B/V63.C: phase별 base-frame foot (x, z) 위치 직접 추적.

    V63.B 원안은 x만 추적했으나 drag-with-timing 해에 취약했다.
    V63.C는 lift_amplitude > 0으로 z 차원을 추가해 2D 궤적으로 확장.

    X target (전후):
        target_x = reach_amplitude * cos(leg_phase)
        - phase=0 (stance 시작): +A (발이 body 앞쪽)
        - phase=π: -A (발이 body 뒤쪽)
        - phase=2π (cycle end): +A

    Z target (높이, lift_amplitude > 0일 때만):
        stance 구간 (0 ~ duty*2π): target_z = 0
        swing 구간: parabolic arc
            swing_progress = (phase - stance_end) / (swing_duration)
            target_z = lift_amplitude * sin(swing_progress * π)
        → swing 시작/끝: 0, swing 중간: lift_amplitude (최대)

    FL/RR = base_phase, FR/RL = base_phase + π → 두 쌍이 정반대 위상으로 교대.

    nominal (x, z)는 episode 시작 시점에 자동 측정 (base-frame).
    err² = (x_err)² + (z_err)²
    reward = exp(-err² / std²)

    V63.B (lift_amplitude=0): x만 추적, 기존 동작과 동일
    V63.C (lift_amplitude=0.04): x + z 2D 추적
    """
    robot = env.scene[asset_cfg.name]

    # 1. base_phase
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t  # (num_envs,)

    # 2. per-leg phase: FL(0)/RR(3) = base, FR(1)/RL(2) = base + π
    leg_phases = torch.stack([
        base_phase,
        base_phase + math.pi,
        base_phase + math.pi,
        base_phase,
    ], dim=1)  # (num_envs, 4)

    # 3. target_x = A * cos(phase)
    target_x = reach_amplitude * torch.cos(leg_phases)  # (num_envs, 4)

    # 4. target_z (swing phase에만 양수, parabolic)
    if lift_amplitude > 0.0:
        phase_norm = leg_phases % (2.0 * math.pi)
        stance_end = duty_factor * 2.0 * math.pi
        swing_duration = 2.0 * math.pi - stance_end
        in_swing = (phase_norm > stance_end).float()
        swing_progress = torch.clamp(
            (phase_norm - stance_end) / (swing_duration + 1e-6), 0.0, 1.0
        )
        target_z = in_swing * lift_amplitude * torch.sin(swing_progress * math.pi)
    else:
        target_z = torch.zeros_like(target_x)

    # 5. base-frame foot (x, z) position
    foot_pos_w = robot.data.body_pos_w[:, foot_cfg.body_ids, :3]  # (num_envs, 4, 3)
    body_pos_w = robot.data.root_pos_w  # (num_envs, 3)
    rel_xyz = foot_pos_w - body_pos_w.unsqueeze(1)  # (num_envs, 4, 3)

    heading_x, heading_y = _compute_heading_xy(robot.data.root_quat_w)
    # x in base frame (body forward direction)
    foot_x_base = (
        heading_x.unsqueeze(1) * rel_xyz[:, :, 0]
        + heading_y.unsqueeze(1) * rel_xyz[:, :, 1]
    )  # (num_envs, 4)
    # z in base frame (world z, body roll/pitch은 거의 0이라 근사)
    foot_z_base = rel_xyz[:, :, 2]  # (num_envs, 4)

    # 6. nominal (x, z) — episode reset 마다 갱신
    if not hasattr(env, "_v63_nominal_foot_x"):
        env._v63_nominal_foot_x = torch.zeros(env.num_envs, 4, device=foot_x_base.device)
        env._v63_nominal_foot_z = torch.zeros(env.num_envs, 4, device=foot_z_base.device)
    reset_mask = (env.episode_length_buf <= 1)
    if reset_mask.any():
        env._v63_nominal_foot_x[reset_mask] = foot_x_base[reset_mask].detach()
        env._v63_nominal_foot_z[reset_mask] = foot_z_base[reset_mask].detach()

    # 7. deviation from phase-target
    actual_x_offset = foot_x_base - env._v63_nominal_foot_x
    actual_z_offset = foot_z_base - env._v63_nominal_foot_z
    x_err = actual_x_offset - target_x
    z_err = actual_z_offset - target_z

    err_sq = x_err ** 2 + z_err ** 2  # (num_envs, 4)

    # 8. exponential reward per leg
    reward_per_leg = torch.exp(-err_sq / (std ** 2))

    # KPI logging
    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_foot_reach_reward"] = reward_per_leg.mean().item()
            env.extras["log_foot_x_abs_offset_fl"] = actual_x_offset[:, 0].abs().mean().item()
            env.extras["log_foot_x_abs_offset_fr"] = actual_x_offset[:, 1].abs().mean().item()
            env.extras["log_foot_z_abs_offset_fl"] = actual_z_offset[:, 0].abs().mean().item()
            env.extras["log_foot_z_abs_offset_fr"] = actual_z_offset[:, 1].abs().mean().item()
            env.extras["log_foot_x_err_mean"] = x_err.abs().mean().item()
            env.extras["log_foot_z_err_mean"] = z_err.abs().mean().item()

    return reward_per_leg.mean(dim=-1)


def phase_joint_target_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    A_leg: float = 0.25,
    A_foot: float = 0.35,
    std: float = 0.3,
) -> torch.Tensor:
    """V63.D: Joint-level reference motion tracking.

    V63.B/C의 foot 위치 target이 학습 불가능했던 것을 해결: joint 각도를
    직접 target으로 삼아 action → reward gradient를 짧게 만든다.

    Reference motion:
        leg_target  = default_leg  + A_leg × cos(leg_phase)            # hip pitch swing
        foot_target = default_foot - A_foot × in_swing × sin(s_prog × π)  # knee bend during swing

    Phase 할당:
        FL/RR = base_phase, FR/RL = base_phase + π   (trot)

    왜 foot joint는 -A_foot? URDF에서 foot angle이 positive=stretched,
    lower=bent. 발을 들려면 angle을 낮춰야 함.

    Shoulder joint는 target 없음 (V60~62 관찰: trot에서 shoulder는 거의 안 움직임).

    수치 검증:
        완벽 trot: err=0 → reward=1.0
        정지:     err≈0.18 → reward≈0.135
        차이:     +0.865/step → ep +865 (dominant 신호)
    """
    robot = env.scene[asset_cfg.name]

    # 1. Joint indices 캐싱 (첫 호출 시)
    if not hasattr(env, "_v63d_leg_ids"):
        joint_names = robot.data.joint_names
        leg_names = [
            "front_left_leg",
            "front_right_leg",
            "rear_left_leg",
            "rear_right_leg",
        ]
        foot_names = [
            "front_left_foot",
            "front_right_foot",
            "rear_left_foot",
            "rear_right_foot",
        ]
        env._v63d_leg_ids = torch.tensor(
            [joint_names.index(n) for n in leg_names],
            device=robot.data.joint_pos.device,
            dtype=torch.long,
        )
        env._v63d_foot_ids = torch.tensor(
            [joint_names.index(n) for n in foot_names],
            device=robot.data.joint_pos.device,
            dtype=torch.long,
        )
        # Default joint positions (first env, same for all)
        env._v63d_leg_defaults = robot.data.default_joint_pos[0, env._v63d_leg_ids].clone()
        env._v63d_foot_defaults = robot.data.default_joint_pos[0, env._v63d_foot_ids].clone()

    # 2. Base phase
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t  # (N,)

    # 3. Per-leg phase: FL(0)/RR(3) = base, FR(1)/RL(2) = base + π
    leg_phases = torch.stack([
        base_phase,
        base_phase + math.pi,
        base_phase + math.pi,
        base_phase,
    ], dim=1)  # (N, 4)

    # 4. Leg target (hip pitch): continuous cosine swing
    leg_target = env._v63d_leg_defaults.unsqueeze(0) + A_leg * torch.cos(leg_phases)  # (N, 4)

    # 5. Foot target (knee): parabolic bend during swing phase only
    phase_norm = leg_phases % (2.0 * math.pi)
    stance_end = duty_factor * 2.0 * math.pi
    swing_dur = 2.0 * math.pi - stance_end
    in_swing = (phase_norm > stance_end).float()
    swing_progress = torch.clamp(
        (phase_norm - stance_end) / (swing_dur + 1e-6), 0.0, 1.0
    )
    foot_bend = A_foot * in_swing * torch.sin(swing_progress * math.pi)
    foot_target = env._v63d_foot_defaults.unsqueeze(0) - foot_bend  # (N, 4)

    # 6. Actual joint positions
    leg_actual = robot.data.joint_pos[:, env._v63d_leg_ids]   # (N, 4)
    foot_actual = robot.data.joint_pos[:, env._v63d_foot_ids]  # (N, 4)

    # 7. Per-joint squared error, sum over 8 joints
    leg_err = (leg_actual - leg_target) ** 2  # (N, 4)
    foot_err = (foot_actual - foot_target) ** 2  # (N, 4)
    err_sum = leg_err.sum(dim=-1) + foot_err.sum(dim=-1)  # (N,)

    # 8. Exponential reward
    reward = torch.exp(-err_sum / (std ** 2))

    # KPI logging
    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_joint_target_reward"] = reward.mean().item()
            env.extras["log_joint_err_leg_mean"] = leg_err.mean().item()
            env.extras["log_joint_err_foot_mean"] = foot_err.mean().item()
            env.extras["log_joint_err_total"] = err_sum.mean().item()
            # Per-leg error (to detect asymmetry)
            env.extras["log_joint_err_fl"] = (leg_err[:, 0] + foot_err[:, 0]).mean().item()
            env.extras["log_joint_err_fr"] = (leg_err[:, 1] + foot_err[:, 1]).mean().item()
            env.extras["log_joint_err_rl"] = (leg_err[:, 2] + foot_err[:, 2]).mean().item()
            env.extras["log_joint_err_rr"] = (leg_err[:, 3] + foot_err[:, 3]).mean().item()

    return reward


def phase_joint_target_linear_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    A_leg_start: float = 0.05,
    A_leg_end: float = 0.25,
    A_foot_start: float = 0.10,
    A_foot_end: float = 0.35,
    curriculum_iters: int = 1500,
    err_max: float = 1.5,
) -> torch.Tensor:
    """V63.E: Linear clamp + curriculum joint target tracking.

    V63.D의 sharp exp(-err/std²)는 초기 err가 커서 reward ≈ 0 → gradient ≈ 0.
    V63.E는 linear clamp로 초기 stationary 상태에서도 non-zero reward 제공.

    Reward:
        err_total = Σ_8_joints |actual - target|
        reward = clamp(1.0 - err_total / err_max, 0, 1)

    Curriculum (amplitude 점진 확대):
        iter 0:    A_leg=A_leg_start, A_foot=A_foot_start   (쉬운 target)
        iter 1500: A_leg=A_leg_end,   A_foot=A_foot_end     (최종 target)

    Target:
        leg_target  = default + A_leg × cos(leg_phase)
        foot_target = default - A_foot × in_swing × sin(swing_progress × π)

    수치 검증:
    - 초기 stationary (A_leg=0.05): err ~0.24 → reward 0.84 (non-zero!)
    - 후기 stationary (A_leg=0.25): err ~1.04 → reward 0.31
    - 완벽 trot: err=0 → reward 1.0
    """
    robot = env.scene[asset_cfg.name]

    # 1. Joint indices 캐싱
    if not hasattr(env, "_v63e_leg_ids"):
        joint_names = robot.data.joint_names
        leg_names = [
            "front_left_leg", "front_right_leg",
            "rear_left_leg", "rear_right_leg",
        ]
        foot_names = [
            "front_left_foot", "front_right_foot",
            "rear_left_foot", "rear_right_foot",
        ]
        env._v63e_leg_ids = torch.tensor(
            [joint_names.index(n) for n in leg_names],
            device=robot.data.joint_pos.device,
            dtype=torch.long,
        )
        env._v63e_foot_ids = torch.tensor(
            [joint_names.index(n) for n in foot_names],
            device=robot.data.joint_pos.device,
            dtype=torch.long,
        )
        env._v63e_leg_defaults = robot.data.default_joint_pos[0, env._v63e_leg_ids].clone()
        env._v63e_foot_defaults = robot.data.default_joint_pos[0, env._v63e_foot_ids].clone()

    # 2. Curriculum: iter-based amplitude scaling
    #    env.common_step_counter가 있으면 사용, 없으면 자체 카운터
    step_count = getattr(env, "common_step_counter", None)
    if step_count is None:
        if not hasattr(env, "_v63e_step_counter"):
            env._v63e_step_counter = 0
        env._v63e_step_counter += 1
        step_count = env._v63e_step_counter

    # num_steps_per_env=24 (Isaac Lab 표준 rollout size)
    iter_approx = float(step_count) / 24.0
    frac = min(iter_approx / float(curriculum_iters), 1.0)
    A_leg = A_leg_start + (A_leg_end - A_leg_start) * frac
    A_foot = A_foot_start + (A_foot_end - A_foot_start) * frac

    # 3. Base phase
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t  # (N,)

    # 4. Per-leg phase: FL/RR = base, FR/RL = base + π
    leg_phases = torch.stack([
        base_phase,
        base_phase + math.pi,
        base_phase + math.pi,
        base_phase,
    ], dim=1)  # (N, 4)

    # 5. Leg target (hip pitch)
    leg_target = env._v63e_leg_defaults.unsqueeze(0) + A_leg * torch.cos(leg_phases)

    # 6. Foot target (knee, swing phase에만 접힘)
    phase_norm = leg_phases % (2.0 * math.pi)
    stance_end = duty_factor * 2.0 * math.pi
    swing_dur = 2.0 * math.pi - stance_end
    in_swing = (phase_norm > stance_end).float()
    swing_progress = torch.clamp(
        (phase_norm - stance_end) / (swing_dur + 1e-6), 0.0, 1.0
    )
    foot_bend = A_foot * in_swing * torch.sin(swing_progress * math.pi)
    foot_target = env._v63e_foot_defaults.unsqueeze(0) - foot_bend

    # 7. Actual joint positions
    leg_actual = robot.data.joint_pos[:, env._v63e_leg_ids]
    foot_actual = robot.data.joint_pos[:, env._v63e_foot_ids]

    # 8. L1 error total (sum of absolute errors)
    leg_err_abs = (leg_actual - leg_target).abs()   # (N, 4)
    foot_err_abs = (foot_actual - foot_target).abs()  # (N, 4)
    err_total = leg_err_abs.sum(dim=-1) + foot_err_abs.sum(dim=-1)  # (N,)

    # 9. Linear clamp reward
    reward = torch.clamp(1.0 - err_total / err_max, 0.0, 1.0)

    # KPI logging
    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_joint_target_reward"] = reward.mean().item()
            env.extras["log_joint_err_total"] = err_total.mean().item()
            env.extras["log_joint_err_leg_mean"] = leg_err_abs.mean().item()
            env.extras["log_joint_err_foot_mean"] = foot_err_abs.mean().item()
            env.extras["log_curriculum_A_leg"] = float(A_leg)
            env.extras["log_curriculum_A_foot"] = float(A_foot)
            env.extras["log_curriculum_frac"] = float(frac)
            # per-leg err (비대칭 감지)
            env.extras["log_joint_err_fl"] = (leg_err_abs[:, 0] + foot_err_abs[:, 0]).mean().item()
            env.extras["log_joint_err_fr"] = (leg_err_abs[:, 1] + foot_err_abs[:, 1]).mean().item()
            env.extras["log_joint_err_rl"] = (leg_err_abs[:, 2] + foot_err_abs[:, 2]).mean().item()
            env.extras["log_joint_err_rr"] = (leg_err_abs[:, 3] + foot_err_abs[:, 3]).mean().item()

    return reward


def metric_clearance_mean_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V63.F Metric: 4발 평균 foot clearance (world frame z).

    feet_air_time은 reward proxy라 literal 체공시간 모름. 이 metric은
    실제로 발이 지면에서 얼마나 떠있는지 직접 측정.

    Tier: Metric only (weight 1e-4로 주입, 학습 영향 무시 수준)

    Log:
        - log_clearance_mean         : 4발 평균 (모든 순간)
        - log_clearance_swing_only   : swing 중인 발만 평균
        - log_clearance_fl/fr/rl/rr  : per-leg
    """
    robot = env.scene[foot_cfg.name]
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]

    # World frame foot z
    foot_z_w = robot.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (N, 4)
    ground_z = env.scene.env_origins[:, 2].unsqueeze(1)  # (N, 1)
    clearance = (foot_z_w - ground_z).clamp(min=0.0)  # (N, 4)

    # Swing mask (contact 중이 아닌 발만)
    contact_mask = _contact_state(
        contact_sensor, sensor_cfg.body_ids, contact_threshold
    ).float()  # (N, 4)
    swing_mask = 1.0 - contact_mask

    clearance_all_mean = clearance.mean(dim=-1)  # (N,) 4발 평균
    swing_count = swing_mask.sum(dim=-1).clamp(min=1.0)
    clearance_swing_only = (clearance * swing_mask).sum(dim=-1) / swing_count

    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_clearance_mean"] = clearance_all_mean.mean().item()
            env.extras["log_clearance_swing_only"] = clearance_swing_only.mean().item()
            env.extras["log_clearance_fl"] = clearance[:, 0].mean().item()
            env.extras["log_clearance_fr"] = clearance[:, 1].mean().item()
            env.extras["log_clearance_rl"] = clearance[:, 2].mean().item()
            env.extras["log_clearance_rr"] = clearance[:, 3].mean().item()

    # Return clearance_mean (weight 1e-4 곱해져 Episode_Reward에 기록)
    return clearance_all_mean


def metric_anti_phase_contact_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V63.F Metric: 대각 쌍의 anti-phase 정도 측정.

    phase_contact는 timing match만 측정하므로 4발 동시 접지 crawl과 구분 못함.
    이 metric은 **대각 쌍이 얼마나 반대 위상으로 움직이는지** 직접 측정.

    pair_a = (FL + RR) / 2  # 0, 0.5, 1
    pair_b = (FR + RL) / 2
    anti_phase_score = |pair_a - pair_b|

    - 0: 4발 동시 상태 (drag/bound)
    - 0.5~1.0: 정상 trot (pair_a 접지 시 pair_b swing)
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contact = _contact_state(
        contact_sensor, sensor_cfg.body_ids, contact_threshold
    ).float()  # (N, 4) FL, FR, RL, RR

    pair_a = (contact[:, 0] + contact[:, 3]) * 0.5
    pair_b = (contact[:, 1] + contact[:, 2]) * 0.5
    anti_phase = torch.abs(pair_a - pair_b)  # (N,)

    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_anti_phase_contact"] = anti_phase.mean().item()
            env.extras["log_pair_a_contact"] = pair_a.mean().item()
            env.extras["log_pair_b_contact"] = pair_b.mean().item()

    return anti_phase


def metric_leg_usage_cv_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V63.F Metric: 4발 사용 균형의 변동계수 (coefficient of variation).

    CV = std(swing_ratio) / mean(swing_ratio)

    한 발만 과/과소 사용하는 병변을 한 숫자로 감지:
    - CV < 0.1: 4발 균형 (정상)
    - CV 0.1~0.3: 약간 편향
    - CV > 0.3: 명백한 병변 (V60.A RR exploit 등)

    구현: contact_ratio (에피소드 내 평균) 기반.
    """
    contact_ratio = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (N, 4)
    swing_ratio = 1.0 - contact_ratio

    mean_sw = swing_ratio.mean(dim=-1)  # (N,)
    # 분산 기반 std (unbiased=False로 N으로 나눔)
    std_sw = swing_ratio.std(dim=-1, unbiased=False)  # (N,)
    cv = std_sw / (mean_sw + 1e-6)  # (N,)

    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_leg_usage_cv"] = cv.mean().item()
            env.extras["log_swing_ratio_min"] = swing_ratio.min(dim=-1).values.mean().item()
            env.extras["log_swing_ratio_max"] = swing_ratio.max(dim=-1).values.mean().item()
            env.extras["log_swing_ratio_mean"] = mean_sw.mean().item()

    return cv


def stance_slip_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V63.B: stance 중 발의 world-frame 수평 속도 = slip. drag/skate 추진 직접 억제.

    수식:
        slip_per_leg = contact_mask * ||foot_vel_xy_world||
        penalty = mean(slip_per_leg)

    핵심: foot velocity는 **world frame**. body velocity를 빼지 않음.
    이상적 stance는 발이 world에서 정지해야 하므로 0이 목표.
    drag 상태에서는 body 전진 속도가 발에 일부 전달되어 양수.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contact_mask = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    foot_asset = env.scene[foot_cfg.name]
    # WORLD FRAME foot velocity (body_vel_w returns linear+angular world velocity)
    foot_vel_w = foot_asset.data.body_vel_w[:, foot_cfg.body_ids, :3]  # (num_envs, 4, 3)
    foot_speed_xy = torch.norm(foot_vel_w[:, :, :2], dim=-1)  # (num_envs, 4)

    slip_per_leg = contact_mask * foot_speed_xy  # (num_envs, 4)

    # KPI logging
    if hasattr(env, "extras"):
        with torch.no_grad():
            env.extras["log_stance_slip_mean"] = slip_per_leg.mean().item()
            env.extras["log_stance_slip_front"] = slip_per_leg[:, :2].mean().item()
            env.extras["log_stance_slip_rear"] = slip_per_leg[:, 2:].mean().item()
            # per-leg
            env.extras["log_stance_slip_fl"] = slip_per_leg[:, 0].mean().item()
            env.extras["log_stance_slip_fr"] = slip_per_leg[:, 1].mean().item()
            env.extras["log_stance_slip_rl"] = slip_per_leg[:, 2].mean().item()
            env.extras["log_stance_slip_rr"] = slip_per_leg[:, 3].mean().item()

    return slip_per_leg.mean(dim=-1)


def rear_left_right_balance_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """Rear pair(RL, RR)의 contact ratio 차이를 penalty.

    현재 병변이 RR에 집중돼 있으므로 전체 4발 std보다 rear pair만 표적.
    정상 보행에서도 순간 차이는 있으나, RL=0.975 vs RR=0.033 같은
    극단적 비대칭은 이 penalty로 직접 벌함.
    """
    contact_ratio = _contact_ratio(
        env.scene.sensors[sensor_cfg.name], sensor_cfg.body_ids, contact_threshold
    )  # (num_envs, num_feet) — 순서: FL, FR, RL, RR
    # rear pair: index 2=RL, 3=RR
    rl_ratio = contact_ratio[:, 2]
    rr_ratio = contact_ratio[:, 3]
    return torch.abs(rl_ratio - rr_ratio)


def excessive_contact_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    command_name: str = "base_velocity",
    max_contact_time: float = 0.4,
    cap: float = 0.6,
    yaw_scale: float = 0.5,
    command_threshold: float = 0.1,
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """Moving env에서 발이 과도하게 오래 접촉 시 penalty. Drag propulsion을 dense하게 억제.

    feet_air_time(sparse, touchdown 시점에만 발생)과 달리,
    이 penalty는 매 step contact_time 초과분에 비례하여 발생한다.
    정상 보행(주기적 발 들기)에서는 contact_time이 reset되어 penalty=0.
    Drag 상태에서는 contact_time이 누적되어 penalty가 지속 증가.

    집계: mean + 0.5*max — 전체 drag와 단일 leg drag 모두 포착.
    Gate: sqrt(vx^2 + vy^2 + yaw_scale*wz^2) > threshold — standing env 제외, yaw 포함.
    Cap: excess를 cap에서 제한하여 무한 누적 방지.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # per-foot continuous contact time
    net_forces = contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1)
    in_contact = net_forces.max(dim=1)[0] > contact_threshold  # (num_envs, num_feet)
    contact_time = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids]

    # saturating excess: clamp(contact_time - max, 0, cap)
    excess = torch.clamp(contact_time - max_contact_time, min=0.0, max=cap)

    # aggregate: mean + 0.5*max (전체 drag + single leg drag 모두 포착)
    penalty = excess.mean(dim=1) + 0.5 * excess.max(dim=1).values

    # command gate: yaw 포함 locomotion command 기준
    command = env.command_manager.get_command(command_name)
    vx = command[:, 0]
    vy = command[:, 1]
    wz = command[:, 2] if command.shape[1] > 2 else torch.zeros_like(vx)
    cmd_magnitude = torch.sqrt(vx * vx + vy * vy + yaw_scale * wz * wz)
    penalty = penalty * (cmd_magnitude > command_threshold).float()

    # safety clamp: cap=0.6이면 max possible = 0.6 + 0.3 = 0.9
    return torch.clamp(penalty, max=2.0)


def moving_height_l2(
    env: ManagerBasedRLEnv,
    target_height: float = 0.18,
    command_name: str = "base_velocity",
    yaw_scale: float = 0.5,
    command_threshold: float = 0.1,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Moving env 전용 높이 L2 penalty. Standing env는 standing_height가 담당.

    (height - target)²를 반환하되, command 속도가 threshold 이하(standing)이면 0.
    Walking env에서 웅크리는 해를 억제.
    """
    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    height_error_sq = torch.square(height - target_height)

    # moving env에서만 적용
    command = env.command_manager.get_command(command_name)
    vx = command[:, 0]
    vy = command[:, 1]
    wz = command[:, 2] if command.shape[1] > 2 else torch.zeros_like(vx)
    cmd_magnitude = torch.sqrt(vx * vx + vy * vy + yaw_scale * wz * wz)
    moving_mask = (cmd_magnitude > command_threshold).float()

    return height_error_sq * moving_mask


def prolonged_contact_termination(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    command_name: str = "base_velocity",
    max_contact_time: float = 0.25,
    yaw_scale: float = 0.5,
    command_threshold: float = 0.1,
    start_time: float = 0.15,
) -> torch.Tensor:
    """Terminate when disallowed bodies remain in sustained contact during locomotion.

    This is intended for the ``L L`` sit pathology: lower foot-body links lie on the ground
    and remain there stably. Unlike immediate illegal-contact termination, this gives the
    policy a short window to recover before ending the episode.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contact_time = contact_sensor.data.current_contact_time[:, sensor_cfg.body_ids]
    prolonged_contact = contact_time.max(dim=1).values > max_contact_time

    command = env.command_manager.get_command(command_name)
    vx = command[:, 0]
    vy = command[:, 1]
    wz = command[:, 2] if command.shape[1] > 2 else torch.zeros_like(vx)
    cmd_magnitude = torch.sqrt(vx * vx + vy * vy + yaw_scale * wz * wz)
    moving = cmd_magnitude > command_threshold

    elapsed = env.episode_length_buf * env.step_dt
    time_gate = elapsed >= start_time

    return prolonged_contact & moving & time_gate


def b4_phase_curriculum(
    env: ManagerBasedRLEnv,
    phase2_iter: int = 500,
    phase3_iter: int = 1500,
) -> None:
    """V58.B4 3-Phase 자동 커리큘럼.

    Phase 1 (iter 0~500):    standing only, 균형 학습
    Phase 2 (iter 500~1500): standing 50% + 느린 전진 0~0.2
    Phase 3 (iter 1500~):    standing 20% + 전진 0~0.4
    """
    iteration = env.common_step_counter // env.max_episode_length if hasattr(env, 'max_episode_length') else 0

    cmd_mgr = env.command_manager
    command_term = cmd_mgr._terms.get("base_velocity", None)
    if command_term is None:
        return

    cfg = command_term.cfg

    if iteration < phase2_iter:
        # Phase 1: standing only
        cfg.rel_standing_envs = 1.0
        cfg.ranges.lin_vel_x = (0.0, 0.0)
        cfg.ranges.ang_vel_z = (0.0, 0.0)
    elif iteration < phase3_iter:
        # Phase 2: 50% standing + slow walking
        cfg.rel_standing_envs = 0.5
        cfg.ranges.lin_vel_x = (0.0, 0.2)
        cfg.ranges.ang_vel_z = (-0.1, 0.1)
    else:
        # Phase 3: 20% standing + normal walking
        cfg.rel_standing_envs = 0.2
        cfg.ranges.lin_vel_x = (0.0, 0.4)
        cfg.ranges.ang_vel_z = (-0.2, 0.2)


def delayed_posture_termination(
    env: ManagerBasedRLEnv,
    min_height: float = 0.14,
    max_tilt: float = 0.5,
    violation_duration: float = 1.0,
    grace_period: float = 1.5,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """높이 또는 수평 위반이 연속 violation_duration 이상 지속 시 terminate.

    즉시 사망이 아닌 복원 기회를 준다. grace_period 이전에는 체크하지 않음 (settling 보호).
    violation_duration 초가 연속으로 기준 미달이면 terminate.

    내부 상태: env._posture_violation_steps로 연속 위반 step 수 추적.
    """
    asset = env.scene[asset_cfg.name]
    height = asset.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    tilt = torch.norm(gravity_xy, dim=1)

    # 위반 조건: 높이 미달 OR 기울어짐 초과
    violated = (height < min_height) | (tilt > max_tilt)

    # grace period 체크
    elapsed = env.episode_length_buf * env.step_dt
    in_grace = elapsed < grace_period

    # 연속 위반 카운터 (env에 저장)
    if not hasattr(env, "_posture_violation_steps"):
        env._posture_violation_steps = torch.zeros(env.num_envs, device=env.device)

    # grace period 또는 위반 아닌 경우 카운터 리셋
    reset_mask = in_grace | (~violated)
    env._posture_violation_steps[reset_mask] = 0.0
    env._posture_violation_steps[~reset_mask] += 1.0

    # episode reset 시 카운터 리셋 (episode_length_buf=0이면 방금 reset된 env)
    just_reset = env.episode_length_buf == 0
    env._posture_violation_steps[just_reset] = 0.0

    # violation_duration 초과 시 terminate
    violation_steps = violation_duration / env.step_dt
    return env._posture_violation_steps >= violation_steps


def stationary_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    threshold: float = 0.05,
) -> torch.Tensor:
    """로봇이 제자리에 머물 때 보상. XY 속도가 threshold 미만이면 1.0 반환."""
    asset = env.scene[asset_cfg.name]
    vel_xy = asset.data.root_lin_vel_b[:, :2]
    vel_magnitude = torch.norm(vel_xy, dim=1)
    return torch.where(
        vel_magnitude < threshold,
        torch.ones_like(vel_magnitude),
        torch.zeros_like(vel_magnitude),
    )


def stationary_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    threshold: float = 0.05,
) -> torch.Tensor:
    """Backward-compatible alias for historical configs."""
    return stationary_reward(env, asset_cfg=asset_cfg, threshold=threshold)


def trot_gait_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """트로트 걸음걸이 보상.

    4가지 성분을 0.4*mean + 0.6*min으로 결합해서,
    하나라도 못하면 전체 점수가 낮아지게 함.

    성분:
      1) 대각선 페어A 동기화 (FL+RR)
      2) 대각선 페어B 동기화 (FR+RL)
      3) 페어 간 반위상
      4) 같은쪽 비동기 (벌레걸음 방지)

    전진 게이팅 적용됨.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # 각 발의 접촉 여부: FL(0), FR(1), RL(2), RR(3)
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    # 대각선 페어 A: FL(0) + RR(3)
    diag_a_sync = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 3])
    # 대각선 페어 B: FR(1) + RL(2)
    diag_b_sync = 1.0 - torch.abs(contacts[:, 1] - contacts[:, 2])

    # 페어 간 반위상
    pair_a_state = (contacts[:, 0] + contacts[:, 3]) / 2.0
    pair_b_state = (contacts[:, 1] + contacts[:, 2]) / 2.0
    anti_phase = torch.abs(pair_a_state - pair_b_state)

    # 같은쪽 비동기 (벌레걸음 방지)
    front_desync = torch.abs(contacts[:, 0] - contacts[:, 1])
    rear_desync = torch.abs(contacts[:, 2] - contacts[:, 3])
    side_desync = (front_desync + rear_desync) / 2.0

    # min-heavy 결합
    components = torch.stack([diag_a_sync, diag_b_sync, anti_phase, side_desync], dim=1)
    mean_val = components.mean(dim=1)
    min_val = components.min(dim=1)[0]
    base_reward = 0.4 * mean_val + 0.6 * min_val

    # 전진 게이팅: 앞으로 움직여야만 보상
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def same_side_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """비트로트 보행 패턴 페널티.

    바운딩(앞뒤 동기화)과 페이싱(좌우 동기화)를 모두 감지.
    각각 max로 잡아서 한 쌍이라도 동기화되면 전체 페널티.
    서있을 때는 4발 접지가 정상이므로 전진 중에만 적용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4) - FL(0), FR(1), RL(2), RR(3)

    # --- 바운딩 감지: 앞다리끼리 / 뒷다리끼리 동기화 ---
    front_same = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 1])
    rear_same = 1.0 - torch.abs(contacts[:, 2] - contacts[:, 3])
    bounding = torch.max(front_same, rear_same)  # 한 쌍이라도 동기화면 전체 페널티

    # --- 페이싱 감지: 왼쪽끼리 / 오른쪽끼리 동기화 ---
    left_same = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 2])
    right_same = 1.0 - torch.abs(contacts[:, 1] - contacts[:, 3])
    pacing = torch.max(left_same, right_same)

    # 바운딩과 페이싱 중 더 큰 위반을 페널티
    penalty = torch.max(bounding, pacing)

    # 전진 게이팅: 보행 중에만 페널티 (서있을 때는 4발 접지 OK)
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return penalty * vel_gate


def gait_contact_count_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """동시 접촉 발 수 보상: 트로트는 항상 2개발이 바닥에 있어야 한다.

    2개 = 1.0점, 3또는 1개 = 0.5점, 0또는 4개 = 0점.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    num_contacts = contacts.sum(dim=1)  # 0~4
    # 2개일 때 최대, 0이나 4일 때 0
    base_reward = 1.0 - torch.abs(num_contacts - 2.0) / 2.0
    base_reward = torch.clamp(base_reward, 0.0, 1.0)

    # 전진 게이팅: 앞으로 움직여야만 보상
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def swing_stride_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """스윙 보폭 보상: 발이 공중에서 앞으로 이동한 거리에 비례하여 보상.

    강아지처럼 걸으려면 발을 들어서 앞으로 내디떠야 함.
    스윙 중인 발의 전방 속도를 측정해서 보상한다.
    """
    # 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (num_envs, num_feet), True = 접촉

    # 발의 월드 속도
    asset = env.scene[foot_cfg.name]
    foot_vel = asset.data.body_vel_w[:, foot_cfg.body_ids, :3]  # (num_envs, num_feet, 3)

    # 로봇 전방 방향 (heading)
    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w  # (num_envs, 4)
    # heading vector (2D)
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    # 발의 heading 방향 속도
    foot_forward_vel = (
        foot_vel[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel[:, :, 1] * heading_y.unsqueeze(1)
    )

    # 스윙 중인 발의 전방 이동량 보상
    swing_mask = ~contacts
    forward_component = torch.clamp(foot_forward_vel, min=0.0)
    normalized = torch.clamp(forward_component / 0.5, 0.0, 1.0)
    swing_reward = normalized * swing_mask.float()

    # 평균
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    base_reward = swing_reward.sum(dim=1) / num_swing

    # 전진 게이팅
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def rear_swing_bonus(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_clearance: float = 0.08,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷발 스윙 보너스: 뒷발이 공중에 들리면 직접 보상.

    앞발만 움직이고 뒷발은 바닥에 고정하는 local minimum 방지용.
    뒷발(RL, RR)이 스윙 중이고 높이 들렸을 때 보상한다.
    """
    # 접촉 감지 (4발 모두)
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (num_envs, 4)

    # 뒷발 높이
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, 4)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z

    # 뒷발(2,3)의 스윙 여부와 높이
    rear_swing = ~contacts[:, 2:]  # (num_envs, 2)
    rear_height = foot_height[:, 2:]
    
    # target_clearance 이상이면 만점
    height_reward = torch.clamp(rear_height / target_clearance, 0.0, 1.0)
    rear_reward = (height_reward * rear_swing.float()).sum(dim=1)
    rear_reward = rear_reward / 2.0

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return rear_reward * vel_gate


def uphill_bonus(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    min_vel: float = 0.05,
    max_climb_rate: float = 0.1,
) -> torch.Tensor:
    """오르막 등반 보너스: 전진하면서 높이가 올라가면 보상.

    Z 속도로 등반 여부를 감지하고, 전진 + 수평 조건을 게이팅해서
    넘어지거나 제자리에서 점프하는 걸 방지한다.
    3. 전진 게이팅: 앞으로 움직여야만 보상 (제자리 점프 방지)
    4. 수평 보정: 넘어지면서 높이 증가하는 경우 방지

    Args:
        env: The environment.
        asset_cfg: Robot asset configuration.
        min_vel: 전진 속도 문턴값.
        max_climb_rate: 최대 등반 속도 (m/s). 이 속도에서 보상 1.0.
    """
    asset = env.scene[asset_cfg.name]

    # 1) Z 속도로 등반 감지
    vel_z = asset.data.root_lin_vel_w[:, 2]
    climb_rate = torch.clamp(vel_z, min=0.0)
    normalized_climb = torch.clamp(climb_rate / max_climb_rate, 0.0, 1.0)

    # 2) 전진 게이팅
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    # 3) 수평 보정: 넘어지면 보상 안 됨
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    orientation_quality = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))

    return normalized_climb * vel_gate * orientation_quality


def leg_lift_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    leg_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_angle: float = 0.6,
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """스윙 중 leg(힙) 관절 각도 보상: 다리를 높이 들어올리도록 유도.

    leg 관절이 중립에서 벗어나 회전하면 발이 높이 들림.
    스윙 중인 다리에 대해서만 target_angle까지 정규화해서 보상.
    속도 게이팅 없음 — 제자리 트로트에서도 작동.
    """
    # 접촉 감지 → 스윙 마스크
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    swing_mask = ~contacts

    # leg 관절 각도
    asset: Articulation = env.scene[leg_joint_cfg.name]
    leg_angles = asset.data.joint_pos[:, leg_joint_cfg.joint_ids]

    # 중립 대비 변위가 클수록 보상
    displacement = torch.abs(leg_angles)
    normalized = torch.clamp(displacement / target_angle, 0.0, 1.0)

    # 스윙 중인 다리만
    swing_reward = normalized * swing_mask.float()

    # 스윙 다리 평균
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    return swing_reward.sum(dim=1) / num_swing


def front_leg_lift_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    leg_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_angle: float = 0.6,
    contact_threshold: float = 1.0,
) -> torch.Tensor:
    """V52.2: 앞다리 전용 leg lift 보상.

    leg_lift_reward와 동일 로직이지만 앞다리 2개(FL, FR)만 대상.
    기존 leg_lift(4발 평균)은 뒷다리가 점수를 지배하므로,
    앞다리 전용 보상으로 front lift를 직접 유도.

    sensor_cfg.body_ids[:2] = FL, FR toe
    leg_joint_cfg.joint_ids[:2] = FL, FR leg joint
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # sensor_cfg가 앞다리 2개만 지정 (body_ids = FL, FR toe)
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    swing_mask = ~contacts

    asset: Articulation = env.scene[leg_joint_cfg.name]
    # leg_joint_cfg가 앞다리 2개만 지정 (joint_ids = FL, FR leg)
    leg_angles = asset.data.joint_pos[:, leg_joint_cfg.joint_ids]

    displacement = torch.abs(leg_angles)
    normalized = torch.clamp(displacement / target_angle, 0.0, 1.0)

    swing_reward = normalized * swing_mask.float()
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    return swing_reward.sum(dim=1) / num_swing


def terrain_progress_reward(
    env: ManagerBasedRLEnv,
) -> torch.Tensor:
    """지형 난이도 비례 보상. 어려운 지형에 있을수록 큰 보상.

    커리큐럼에 의해 승급된 레벨이 높을수록 보상이 커져서
    어려운 지형에서 살아남으려는 동기를 강화한다.
    """
    terrain = env.scene.terrain
    levels = terrain.terrain_levels
    max_level = terrain.max_terrain_level
    return levels.float() / max_level


def distance_walked_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_distance: float = 2.0,
) -> torch.Tensor:
    """원점에서 멀리 걸을수록 보상. 커리큐럼 승급 유도용."""
    asset = env.scene[asset_cfg.name]
    # 현재 위치에서 환경 원점까지 XY 거리
    distance = torch.norm(
        asset.data.root_pos_w[:, :2] - env.scene.env_origins[:, :2], dim=1
    )
    return torch.clamp(distance / target_distance, 0.0, 1.0)


def rear_alternation_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리 교대 보상: RL과 RR이 번갈아 움직이도록 유도.

    뒷다리가 둘 다 달라붙어서 안정적 지지대 역할만 하는 걸 방지.
    하나는 접지, 하나는 스윙 상태일 때 보상한다.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4)

    # 뒷다리 접촉 상태 차이: 다르면 1.0 (교대 중)
    rear_diff = torch.abs(contacts[:, 2] - contacts[:, 3])

    # 전진 게이팅
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return rear_diff * vel_gate


def rear_both_ground_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리 동시 접지 페널티: 두 뒷다리가 동시에 땅에 있으면 페널티.

    rear_alternation의 보완재. 교대 보상만으로는 local minimum 탈출이
    안 돼서 동시 접지 자체에 직접 페널티를 줌.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4)

    # 뒷다리 둘 다 접지일 때만 1.0
    rear_both = contacts[:, 2] * contacts[:, 3]

    # 전진 게이팅
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return rear_both * vel_gate


# ============================================================
# V31: Front leg swing rewards (rear 보상의 앞다리 대칭 버전)
# rear 계열 5개 중 3개를 앞다리에 적용 + min_swing_ratio 공통 패널티
# ============================================================


def front_swing_bonus(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_clearance: float = 0.05,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """앞발 스윙 보너스: 앞발이 공중에 들리면 직접 보상.

    V31: rear_swing_bonus의 앞다리 미러.
    앞발(FL, FR)이 스윙 중이고 높이 들렸을 때 보상한다.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (num_envs, 4)

    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, 4)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z

    # 앞발(0,1)의 스윙 여부와 높이
    front_swing = ~contacts[:, :2]  # (num_envs, 2)
    front_height = foot_height[:, :2]

    height_reward = torch.clamp(front_height / target_clearance, 0.0, 1.0)
    front_reward = (height_reward * front_swing.float()).sum(dim=1)
    front_reward = front_reward / 2.0

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return front_reward * vel_gate


def front_alternation_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """앞다리 교대 보상: FL과 FR이 번갈아 움직이도록 유도.

    V31: rear_alternation_reward의 앞다리 미러.
    하나는 접지, 하나는 스윙 상태일 때 보상한다.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4)

    # 앞다리 접촉 상태 차이: 다르면 1.0 (교대 중)
    front_diff = torch.abs(contacts[:, 0] - contacts[:, 1])

    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return front_diff * vel_gate


def front_both_ground_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """앞다리 동시 접지 페널티: 두 앞다리가 동시에 땅에 있으면 페널티.

    V31: rear_both_ground_penalty의 앞다리 미러.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4)

    # 앞다리 둘 다 접지일 때만 1.0
    front_both = contacts[:, 0] * contacts[:, 1]

    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return front_both * vel_gate


def min_swing_ratio_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_swing: float = 0.20,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """최소 스윙 비율 패널티: 어떤 다리든 swing ratio < min_swing이면 패널티.

    V31: 4발 공통 적용. 특정 다리가 과도하게 접지 유지하는 것을 방지.
    현재 step의 contact state 기반 (episode-level이 아닌 step-level).
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4)

    # swing = 1 - contact (step-level)
    # 접지 중인 다리에 대해서 min_swing만큼의 deficit 계산
    # contact=1이면 swing=0, deficit=min_swing
    # contact=0이면 swing=1, deficit=0 (no penalty)
    deficit = torch.clamp(min_swing - (1.0 - contacts), min=0.0)  # (num_envs, 4)
    penalty = deficit.sum(dim=1)  # 전체 다리 deficit 합산

    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return penalty * vel_gate


def front_joint_velocity_reward(
    env: ManagerBasedRLEnv,
    front_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_threshold: float = 0.5,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """앞다리 관절 속도 보상: 앞다리 관절이 실제로 움직여야 보상.

    V31.2: rear_joint_velocity_reward의 앞다리 미러.
    앞다리 6개 관절(2 shoulder + 2 leg + 2 foot)의 절대 속도 합 기반.
    joint-level이므로 contact 기반 역할 분리를 방지한다.
    """
    asset: Articulation = env.scene[front_joint_cfg.name]
    joint_vel = torch.abs(asset.data.joint_vel[:, front_joint_cfg.joint_ids])
    vel_sum = torch.sum(joint_vel, dim=1)
    reward = torch.clamp(vel_sum / vel_threshold, 0.0, 1.0)

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return reward * vel_gate


def front_joint_frozen_penalty(
    env: ManagerBasedRLEnv,
    front_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frozen_threshold: float = 0.3,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """앞다리 관절 동결 페널티: 앞다리가 움직이지 않으면 페널티.

    V31.2: rear_joint_frozen_penalty의 앞다리 미러.
    앞다리 관절 속도 합 < frozen_threshold이면 페널티 1.0.
    joint-level이므로 contact 기반 역할 분리를 방지한다.
    """
    asset: Articulation = env.scene[front_joint_cfg.name]
    joint_vel = torch.abs(asset.data.joint_vel[:, front_joint_cfg.joint_ids])
    vel_sum = torch.sum(joint_vel, dim=1)
    is_frozen = (vel_sum < frozen_threshold).float()

    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return is_frozen * vel_gate


def rear_forward_stride_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_clearance: float = 0.06,
    target_fwd_vel: float = 0.3,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷발 전방 보폭 보상: 뒷발이 들려서 앞으로 실제로 이동해야 보상.

    뒷발이 접촉 센서상 교대는 하지만 살짝 들었다 내려놓는
    토큰 교대 문제를 해결하기 위해 [높이 × 전방속도] 곱으로 보상.
    둘 다 있어야 보상이 나오므로 제자리 들기나 바닥 끌기는 0점.
    """
    # 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (num_envs, 4)

    # 뒷발 스윙 마스크 (인덱스 2, 3)
    rear_swing = ~contacts[:, 2:]  # (num_envs, 2)

    # 뒷발 높이
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, 4)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z
    rear_height = foot_height[:, 2:]
    # 높이 점수
    height_score = torch.clamp(rear_height / target_clearance, 0.0, 1.0)

    # 뒷발의 전방 속도 (로봇 heading 방향)
    foot_vel = asset.data.body_vel_w[:, foot_cfg.body_ids, :3]
    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)
    # 뒷발의 heading 방향 속도
    rear_fwd_vel = (
        foot_vel[:, 2:, 0] * heading_x.unsqueeze(1) +
        foot_vel[:, 2:, 1] * heading_y.unsqueeze(1)
    )
    # 전방 속도 점수 (target_fwd_vel 기준)
    fwd_score = torch.clamp(rear_fwd_vel / target_fwd_vel, 0.0, 1.0)

    # 높이 × 전방속도: 둘 다 있어야 보상
    stride_quality = height_score * fwd_score
    rear_reward = (stride_quality * rear_swing.float()).sum(dim=1) / 2.0

    # 전진 게이팅
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return rear_reward * vel_gate


def foot_extension_penalty(
    env: ManagerBasedRLEnv,
    foot_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_angle: float = 1.5,
) -> torch.Tensor:
    """foot 관절 과신전 페널티.

    foot joint가 max_angle(기본 1.5rad)을 넘으면 발바닥이 앞을 향하는
    비자연스러운 자세가 됨. 초과분에 2차 페널티.
    """
    asset: Articulation = env.scene[foot_joint_cfg.name]
    foot_angles = asset.data.joint_pos[:, foot_joint_cfg.joint_ids]
    # max_angle 초과분만 2차 페널티
    excess = torch.clamp(foot_angles - max_angle, min=0.0)
    return torch.sum(torch.square(excess), dim=1)


def action_rate_l2_clamped(env: ManagerBasedRLEnv, max_value: float = 50.0) -> torch.Tensor:
    """액션 변화율 L2 페널티 (클램핑 적용).

    연속 스텝 간 액션 차이의 L2 노름을 계산하되, max_value로 클램핑하여
    극단적 액션 변화에 의한 보상 폭발을 방지.

    12 관절 기준 정상 범위: 0.1~10, 비정상: 10^15+
    max_value=50은 충분한 페널티를 허용하면서 발산을 방지.
    """
    raw = torch.sum(
        torch.square(env.action_manager.action - env.action_manager.prev_action), dim=-1
    )
    return torch.clamp(raw, max=max_value)


# ============================================================
# V14: 접촉 독립 뒷다리 보상 (Contact-independent rear leg rewards)
# ============================================================

def rear_joint_velocity_reward(
    env: ManagerBasedRLEnv,
    rear_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_threshold: float = 0.5,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리 관절 속도 보상: 뒷다리 관절이 실제로 움직여야 보상.

    접촉 센서에 의존하지 않고, 뒷다리 관절(어깨, 레그, 풋)의 절대 속도를
    직접 측정. 관절이 움직이지 않는 '고정' 상태를 방지.

    vel_threshold는 6개 뒷다리 관절의 절대 속도 합이 이 값 이상이면
    보상 1.0. 정상 보행 시 관절 속도 합 = 3~12 rad/s.

    Args:
        rear_joint_cfg: 뒷다리 관절 설정 (6개: 2 shoulder + 2 leg + 2 foot)
        vel_threshold: 관절 속도 합 정규화 기준값 (rad/s)
        min_vel: 전진 속도 게이팅 문턱값
    """
    asset: Articulation = env.scene[rear_joint_cfg.name]
    # 뒷다리 관절 속도 절대값 합
    joint_vel = torch.abs(asset.data.joint_vel[:, rear_joint_cfg.joint_ids])
    vel_sum = torch.sum(joint_vel, dim=1)
    # 정규화: vel_threshold에서 보상 1.0
    reward = torch.clamp(vel_sum / vel_threshold, 0.0, 1.0)

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return reward * vel_gate


def rear_joint_frozen_penalty(
    env: ManagerBasedRLEnv,
    rear_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frozen_threshold: float = 0.3,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷다리 관절 동결 페널티: 뒷다리가 움직이지 않으면 페널티.

    전진 보행 중 뒷다리 관절의 속도 합이 frozen_threshold 미만이면
    페널티 1.0. 이 위이면 0.0.

    rear_joint_velocity_reward의 보완재: 보상으로 유도 + 페널티로 직접 처벌.

    Args:
        rear_joint_cfg: 뒷다리 관절 설정
        frozen_threshold: 이 속도 합 이하면 '동결'로 판정 (rad/s)
        min_vel: 전진 속도 게이팅 문턱값
    """
    asset: Articulation = env.scene[rear_joint_cfg.name]
    joint_vel = torch.abs(asset.data.joint_vel[:, rear_joint_cfg.joint_ids])
    vel_sum = torch.sum(joint_vel, dim=1)
    # frozen_threshold 미만 = 동결 = 페널티 1.0
    is_frozen = (vel_sum < frozen_threshold).float()

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return is_frozen * vel_gate


def forward_velocity_rear_gated(
    env: ManagerBasedRLEnv,
    rear_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_vel: float = 0.5,
    rear_gate_threshold: float = 0.5,
) -> torch.Tensor:
    """뒷다리 활동 게이팅 전진 보상: 뒷다리가 움직여야 전진 보상을 받을 수 있음.

    forward_velocity_reward와 동일하지만, 뒷다리 관절 속도에 비례하는
    게이트를 곱한다. 뒷다리 고정 상태에서는 전진해도 보상이 0.

    이것이 V14의 핵심: '뒷다리 없이 전진 불가' 원칙.

    Args:
        rear_joint_cfg: 뒷다리 관절 설정
        asset_cfg: 로봇 설정
        target_vel: 목표 전진 속도
        rear_gate_threshold: 뒷다리 관절 속도 합이 이 값 이상이면 게이트=1.0
    """
    asset = env.scene[asset_cfg.name]
    forward_vel = asset.data.root_lin_vel_b[:, 0]
    normalized_vel = torch.clamp(forward_vel / target_vel, -1.0, 1.0)

    # 수평 게이팅 (기존과 동일)
    gravity_xy = asset.data.projected_gravity_b[:, :2]
    orientation_quality = torch.exp(-7.0 * torch.sum(torch.square(gravity_xy), dim=1))

    # 뒷다리 활동 게이팅 (V14 핵심)
    rear_asset: Articulation = env.scene[rear_joint_cfg.name]
    rear_vel = torch.abs(rear_asset.data.joint_vel[:, rear_joint_cfg.joint_ids])
    rear_vel_sum = torch.sum(rear_vel, dim=1)
    rear_gate = torch.clamp(rear_vel_sum / rear_gate_threshold, 0.0, 1.0)

    return normalized_vel * orientation_quality * rear_gate


def diagonal_joint_coupling_reward(
    env: ManagerBasedRLEnv,
    pair_a_front_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_a_rear_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_b_front_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    pair_b_rear_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    vel_deadzone: float = 0.1,
    min_vel: float = 0.05,
    rl_participation_sensor_cfg: SceneEntityCfg | None = None,
    rl_contact_threshold: float = 1.0,
    rl_min_contact: float = 0.15,
) -> torch.Tensor:
    """대각선 쌍 관절 커플링 보상: trot의 핵심 구조를 직접 강제.

    대각선 다리 쌍(FL↔RR, FR↔RL)의 leg+foot 관절 속도가
    같은 방향이면 보상. 접촉 센서에 의존하지 않고 직접 관절 운동학을
    비교하므로 뒷다리가 끌리는 local minimum을 방지.

    tanh(v1*v2/deadzone^2) 방식으로 부드러운 상관 측정.
    양의 상관(같은 방향)만 보상하고, 음의 상관(반대 방향)이나
    한쪽이 정지(0 상관)일 때는 보상 0.

    Args:
        pair_a_front_cfg: FL leg+foot 관절 (front_left_leg, front_left_foot)
        pair_a_rear_cfg: RR leg+foot 관절 (rear_right_leg, rear_right_foot)
        pair_b_front_cfg: FR leg+foot 관절 (front_right_leg, front_right_foot)
        pair_b_rear_cfg: RL leg+foot 관절 (rear_left_leg, rear_left_foot)
        vel_deadzone: 이 속도 이하의 관절은 상관 기여가 작음 (rad/s)
        min_vel: 전진 속도 게이팅 문턱값
    """
    asset: Articulation = env.scene[pair_a_front_cfg.name]

    # 대각선 페어 A: FL vs RR (leg+foot 속도)
    fl_vel = asset.data.joint_vel[:, pair_a_front_cfg.joint_ids]  # (N, 2)
    rr_vel = asset.data.joint_vel[:, pair_a_rear_cfg.joint_ids]   # (N, 2)

    # 대각선 페어 B: FR vs RL (leg+foot 속도)
    fr_vel = asset.data.joint_vel[:, pair_b_front_cfg.joint_ids]  # (N, 2)
    rl_vel = asset.data.joint_vel[:, pair_b_rear_cfg.joint_ids]   # (N, 2)

    # 속도 상관: tanh(v1*v2 / deadzone^2) → [-1, 1]
    dz_sq = vel_deadzone ** 2
    pair_a_corr = torch.tanh(fl_vel * rr_vel / dz_sq)  # (N, 2)
    pair_b_corr = torch.tanh(fr_vel * rl_vel / dz_sq)  # (N, 2)

    # 양의 상관만 보상 (같은 방향), 음의 상관이나 0은 보상 없음
    pair_a_reward = torch.clamp(pair_a_corr, 0.0, 1.0).mean(dim=1)
    pair_b_reward = torch.clamp(pair_b_corr, 0.0, 1.0).mean(dim=1)

    # V25: RL 참여 soft gate — RL이 접지하지 않으면 pair_b(FR↔RL) 보상 차감
    # 3다리 보행으로 diagonal_coupling 보상을 얻는 경로를 차단
    if rl_participation_sensor_cfg is not None:
        contact_sensor: ContactSensor = env.scene.sensors[rl_participation_sensor_cfg.name]
        rl_contact = _contact_ratio(contact_sensor, rl_participation_sensor_cfg.body_ids, rl_contact_threshold)[:, 0]
        rl_gate = torch.clamp(rl_contact / max(float(rl_min_contact), 1.0e-6), 0.0, 1.0)
        pair_b_reward = pair_b_reward * rl_gate

    reward = (pair_a_reward + pair_b_reward) / 2.0

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate


# ============================================================
# V18.3: 스탠스 추진 보상 (Stance Propulsion Reward)
# 발이 바닥에 닿아서 뒤로 밀어야 동체가 앞으로 나가는 메커니즘 보상
# ============================================================

def diagonal_pair_propulsion_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_push_vel: float = 0.3,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """대각 쌍이 동시에 밀어야 보상. trot 보행의 핵심 직접 유도.

    pair_A: FL(왼앞) + RR(오른뒤) → 동시에 push-off하면 보상
    pair_B: FR(오른앞) + RL(왼뒤) → 동시에 push-off하면 보상

    min(FL_push, RR_push)로 계산하므로:
    - 한쪽만 밀면 → min = 0 → 보상 없음
    - 앞다리 안 밀면 → pair 보상 0 → 앞다리 참여 강제
    - 대각 쌍이 함께 밀면 → 보상 최대

    body 순서: FL(0), FR(1), RL(2), RR(3)
    """
    # per-leg propulsion 계산 (stance_propulsion_reward와 동일 로직)
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    stance_mask = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    foot_asset = env.scene[foot_cfg.name]
    foot_vel_w = foot_asset.data.body_vel_w[:, foot_cfg.body_ids, :3]

    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    foot_heading_vel = (
        foot_vel_w[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel_w[:, :, 1] * heading_y.unsqueeze(1)
    )
    body_vel_w = robot.data.root_lin_vel_w
    body_heading_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y

    relative_vel = foot_heading_vel - body_heading_vel.unsqueeze(1)
    push_magnitude = torch.clamp(-relative_vel, min=0.0)
    normalized_push = torch.clamp(push_magnitude / target_push_vel, 0.0, 1.0)
    per_leg_push = normalized_push * stance_mask  # (num_envs, 4): FL, FR, RL, RR

    # 대각 쌍 propulsion: 교대 보너스 — 한 쌍이 밀고 다른 쌍이 swing이어야 보상
    pair_a = torch.min(per_leg_push[:, 0], per_leg_push[:, 3])  # min(FL, RR)
    pair_b = torch.min(per_leg_push[:, 1], per_leg_push[:, 2])  # min(FR, RL)

    # 교대 보너스: push_pair(더 강한 쪽) × swing_pair(약한 쪽이 안 미는 정도)
    # crawl(동시 밀기): push=1, swing=1-1=0 → bonus=0
    # trot(교대 밀기): push=1, swing=1-0=1 → bonus=1
    push_pair = torch.max(pair_a, pair_b)
    swing_pair = 1.0 - torch.min(pair_a, pair_b)
    reward = push_pair * swing_pair

    # 전진 게이팅
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate


def phase_gated_diagonal_propulsion_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_push_vel: float = 0.3,
    min_vel: float = 0.05,
    frequency: float = 2.0,
    duty_factor: float = 0.55,
    gate_sharpness: float = 5.0,
) -> torch.Tensor:
    """Phase-gated 대각 교대 propulsion. late-stance(마지막 ~25%)에서 push-off할 때만 보상.

    V62: diagonal_pair_propulsion_reward에 phase gate를 추가.
    - stance 0~75%: gate≈0 → 접지만으로는 보상 없음
    - stance 75~100% (late-stance): gate가 0.5→1.0으로 상승 → push-off 보상
    - swing phase: stance_mask=0이므로 자동 0

    이것이 drag/crawl exploit을 막는 핵심 메커니즘:
    - drag: 항상 접지(contact_ratio 90%+) → stance 대부분에서 gate≈0으로 보상 차단
    - trot: late stance에서 강하게 밀고 바로 swing → gate≈1에서 보상 최대

    gate_sharpness로 전환 폭 조절 (높을수록 날카로운 on/off, 낮을수록 부드러운 전환).

    body 순서: FL(0), FR(1), RL(2), RR(3)
    """
    # ── per-leg propulsion 계산 (기존과 동일) ──
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    stance_mask = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    foot_asset = env.scene[foot_cfg.name]
    foot_vel_w = foot_asset.data.body_vel_w[:, foot_cfg.body_ids, :3]

    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    foot_heading_vel = (
        foot_vel_w[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel_w[:, :, 1] * heading_y.unsqueeze(1)
    )
    body_vel_w = robot.data.root_lin_vel_w
    body_heading_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y

    relative_vel = foot_heading_vel - body_heading_vel.unsqueeze(1)
    push_magnitude = torch.clamp(-relative_vel, min=0.0)
    normalized_push = torch.clamp(push_magnitude / target_push_vel, 0.0, 1.0)
    per_leg_push = normalized_push * stance_mask  # (num_envs, 4)

    # ��─ phase gate: late-stance에서만 보상 ──
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = 2.0 * math.pi * frequency * t

    # Trot phases: FL/RR=0, FR/RL=π
    leg_phases = torch.stack([
        base_phase,                # FL
        base_phase + math.pi,     # FR
        base_phase + math.pi,     # RL
        base_phase,                # RR
    ], dim=1)  # (num_envs, 4)

    # phase_norm: 0~2π, stance=0~duty*2π, swing=duty*2π~2π
    phase_norm = leg_phases % (2.0 * math.pi)
    stance_end = duty_factor * 2.0 * math.pi  # stance phase 끝 (≈3.46 rad)
    late_onset = stance_end * 0.75  # late-stance 시작점 (stance의 75%)

    # late_stance_gate: stance 마지막 ~25%에서 gate≈1, 그 전에는 gate≈0
    # sigmoid(5 * (phase - late_onset)):
    #   phase=0 (stance 시작): sigmoid(-12.96) ≈ 0    → gate≈0
    #   phase=2.0 (stance 58%): sigmoid(-2.96) ≈ 0.05 → gate≈0
    #   phase=2.59 (75%): sigmoid(0) = 0.5             → gate=0.5
    #   phase=3.0 (87%): sigmoid(2.04) ≈ 0.88          → gate≈0.9
    #   phase=3.46 (stance 끝): sigmoid(4.32) ≈ 0.99   → gate≈1
    # swing phase (phase_norm > stance_end)에서는 stance_mask=0이 이미 차단
    late_gate = torch.sigmoid(gate_sharpness * (phase_norm - late_onset))

    per_leg_push_gated = per_leg_push * late_gate  # (num_envs, 4)

    # ── 대각 쌍 교대 보너스 (V61.C와 동일) ──
    pair_a = torch.min(per_leg_push_gated[:, 0], per_leg_push_gated[:, 3])  # min(FL, RR)
    pair_b = torch.min(per_leg_push_gated[:, 1], per_leg_push_gated[:, 2])  # min(FR, RL)

    push_pair = torch.max(pair_a, pair_b)
    swing_pair = 1.0 - torch.min(pair_a, pair_b)
    reward = push_pair * swing_pair

    # ── 전진 게이팅 ──
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    # ── KPI logging: 에피소드별 누적 통계 ──
    if hasattr(env, "extras"):
        with torch.no_grad():
            num_envs = stance_mask.shape[0]

            # 누적 버퍼 초기화 (최초 호출 또는 에피소드 리셋 시)
            if not hasattr(env, "_v62_contact_sum"):
                env._v62_contact_sum = torch.zeros(num_envs, 4, device=stance_mask.device)
                env._v62_both_pairs_sum = torch.zeros(num_envs, device=stance_mask.device)
                env._v62_step_count = torch.zeros(num_envs, device=stance_mask.device)

            # 에피소드 리셋 감지 (episode_length_buf <= 1)
            reset_mask = (env.episode_length_buf <= 1)
            if reset_mask.any():
                env._v62_contact_sum[reset_mask] = 0.0
                env._v62_both_pairs_sum[reset_mask] = 0.0
                env._v62_step_count[reset_mask] = 0.0

            # 현재 step 누적
            env._v62_contact_sum += stance_mask  # (num_envs, 4)
            pair_a_contact = torch.min(stance_mask[:, 0], stance_mask[:, 3])
            pair_b_contact = torch.min(stance_mask[:, 1], stance_mask[:, 2])
            env._v62_both_pairs_sum += pair_a_contact * pair_b_contact
            env._v62_step_count += 1.0

            # 에피소드 내 시간 평균 비율 계산
            safe_count = env._v62_step_count.clamp(min=1.0)
            ep_contact_ratio = env._v62_contact_sum / safe_count.unsqueeze(1)  # (num_envs, 4)
            ep_swing_ratio = 1.0 - ep_contact_ratio
            ep_both_pairs = env._v62_both_pairs_sum / safe_count

            # 환경 전체 평균 → 텐서보드 로깅
            cr_mean = ep_contact_ratio.mean(dim=0)  # (4,)
            env.extras["log_contact_ratio_fl"] = cr_mean[0].item()
            env.extras["log_contact_ratio_fr"] = cr_mean[1].item()
            env.extras["log_contact_ratio_rl"] = cr_mean[2].item()
            env.extras["log_contact_ratio_rr"] = cr_mean[3].item()
            env.extras["log_mean_swing_ratio"] = ep_swing_ratio.mean().item()
            env.extras["log_pair_both_stance"] = ep_both_pairs.mean().item()

            sw_mean = ep_swing_ratio.mean(dim=0)
            env.extras["log_swing_time_fl"] = sw_mean[0].item()
            env.extras["log_swing_time_fr"] = sw_mean[1].item()
            env.extras["log_swing_time_rl"] = sw_mean[2].item()
            env.extras["log_swing_time_rr"] = sw_mean[3].item()

            # 이 두 값은 순간 측정이 적절 (에피소드 누적 불필요)
            env.extras["log_phase_gated_propulsion"] = (per_leg_push_gated.sum(dim=1) * vel_gate).mean().item()
            front_prop = (per_leg_push_gated[:, 0] + per_leg_push_gated[:, 1]).mean()
            rear_prop = (per_leg_push_gated[:, 2] + per_leg_push_gated[:, 3]).mean()
            env.extras["log_front_rear_prop_diff"] = (front_prop - rear_prop).item()

    return reward * vel_gate


def stance_propulsion_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_push_vel: float = 0.3,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """스탠스 추진 보상: 발이 바닥에 닿은 상태에서 동체 대비 뒤로 밀리면 보상.

    보행의 물리적 원리: 스탠스 페이즈에서 발이 지면에 고정되고,
    다리가 뒤로 밀면서 동체가 앞으로 나간다. 이때 발의 월드 속도는
    거의 0이고, 동체는 앞으로 이동하므로 발의 동체-상대 속도는
    heading 방향으로 음수(뒤쪽)가 된다.

    측정: stance 중인 발의 heading 방향 속도 - 동체의 heading 방향 속도
    이 값이 음수(발이 동체 대비 뒤쪽으로 이동) → 추진력 발생 → 보상

    Args:
        sensor_cfg: 발 접촉 센서 설정
        foot_cfg: 발 바디 설정 (속도 추적용)
        asset_cfg: 로봇 설정
        contact_threshold: 접촉 판정 힘 문턱값 (N)
        target_push_vel: 정규화 기준 추진 속도 (m/s)
        min_vel: 전진 속도 게이팅 문턱값
    """
    # 1) 접촉 감지 → 스탠스 마스크
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    stance_mask = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()  # (num_envs, 4), 1.0 = 접촉 중 (스탠스)

    # 2) 발의 월드 속도
    foot_asset = env.scene[foot_cfg.name]
    foot_vel_w = foot_asset.data.body_vel_w[:, foot_cfg.body_ids, :3]  # (num_envs, 4, 3)

    # 3) 로봇 heading 방향 계산
    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    # 4) 발의 heading 방향 속도 (월드 프레임)
    foot_heading_vel = (
        foot_vel_w[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel_w[:, :, 1] * heading_y.unsqueeze(1)
    )  # (num_envs, 4)

    # 5) 동체의 heading 방향 속도 (월드 프레임)
    body_vel_w = robot.data.root_lin_vel_w  # (num_envs, 3)
    body_heading_vel = body_vel_w[:, 0] * heading_x + body_vel_w[:, 1] * heading_y  # (num_envs,)

    # 6) 발의 동체-상대 heading 속도
    # 음수 = 발이 동체 대비 뒤로 이동 = 바닥을 밀고 있음
    relative_vel = foot_heading_vel - body_heading_vel.unsqueeze(1)  # (num_envs, 4)

    # 7) 추진력: 음의 상대속도를 양의 보상으로 변환
    push_magnitude = torch.clamp(-relative_vel, min=0.0)  # (num_envs, 4)
    normalized_push = torch.clamp(push_magnitude / target_push_vel, 0.0, 1.0)

    # 8) 스탠스 중인 발만 보상
    stance_push = normalized_push * stance_mask
    num_stance = stance_mask.sum(dim=1).clamp(min=1.0)
    reward = stance_push.sum(dim=1) / num_stance

    # 9) 전진 게이팅
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate


# ============================================================
# V18.2: 관절 과속 진동 페널티
# ============================================================

def excessive_joint_oscillation_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_vel_per_joint: float = 5.0,
) -> torch.Tensor:
    """개별 관절 속도가 max_vel_per_joint를 초과하면 페널티.

    '벌레 걸음' 데드락의 근본 원인인 고속 미세진동(~20 rad/s)을
    직접 억제한다. 정상 보행 시 관절속도는 3~5 rad/s 수준.

    Args:
        asset_cfg: 로봇 에셋 설정
        max_vel_per_joint: 페널티 없는 최대 관절 속도 (rad/s)
    """
    asset: Articulation = env.scene[asset_cfg.name]
    joint_vel = torch.abs(asset.data.joint_vel[:, asset_cfg.joint_ids])
    excess = torch.clamp(joint_vel - max_vel_per_joint, min=0.0)
    return excess.mean(dim=1)


# ============================================================
# V17: 걸음걸이 주기 보상 & 보폭 길이 보상
# ============================================================

def gait_cycle_period_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_period_min: float = 0.3,
    target_period_max: float = 0.5,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """걸음걸이 주기(cycle period) 보상: 각 발의 접지→접지 간격이 목표 범위 내이면 보상.

    벌레 걷기의 핵심 문제는 접지 간격이 10ms 수준으로 매우 짧다는 것.
    이 보상은 같은 발이 접지한 뒤 다음 접지까지의 시간을 추적하고,
    그 간격이 target_period_min ~ target_period_max 사이이면 보상을 준다.

    env._gait_cycle_last_contact에 각 발의 마지막 접지 시각을 저장하고,
    접지 전환 시점에 측정한 주기로 보상을 계산한다.

    Args:
        sensor_cfg: 발 접촉 센서 설정
        asset_cfg: 로봇 설정
        target_period_min: 최소 목표 주기 (초)
        target_period_max: 최대 목표 주기 (초)
        min_vel: 전진 속도 게이팅 문턱값
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    is_contact = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    num_envs = is_contact.shape[0]
    num_feet = is_contact.shape[1]
    current_time = env.episode_length_buf.float() * env.step_dt  # (num_envs,)

    # 상태 초기화 (에피소드 시작 시)
    if not hasattr(env, "_gait_cycle_last_contact"):
        env._gait_cycle_last_contact = torch.zeros(num_envs, num_feet, device=is_contact.device)
        env._gait_cycle_prev_contact = torch.zeros(num_envs, num_feet, device=is_contact.device)
        env._gait_cycle_measured_period = torch.zeros(num_envs, num_feet, device=is_contact.device)

    # 디바이스 체크 및 크기 맞춤
    if env._gait_cycle_last_contact.shape[0] != num_envs:
        env._gait_cycle_last_contact = torch.zeros(num_envs, num_feet, device=is_contact.device)
        env._gait_cycle_prev_contact = torch.zeros(num_envs, num_feet, device=is_contact.device)
        env._gait_cycle_measured_period = torch.zeros(num_envs, num_feet, device=is_contact.device)

    # 에피소드 리셋 처리
    reset_mask = (env.episode_length_buf <= 1).unsqueeze(1).expand_as(is_contact).float()
    env._gait_cycle_last_contact = env._gait_cycle_last_contact * (1.0 - reset_mask)
    env._gait_cycle_prev_contact = env._gait_cycle_prev_contact * (1.0 - reset_mask)
    env._gait_cycle_measured_period = env._gait_cycle_measured_period * (1.0 - reset_mask)

    # 접촉 전환 감지: 이전에 비접촉 → 현재 접촉 (touchdown)
    touchdown = (is_contact > 0.5) & (env._gait_cycle_prev_contact < 0.5)

    # touchdown 시점에 주기 측정
    time_expanded = current_time.unsqueeze(1).expand_as(is_contact)
    time_since_last = time_expanded - env._gait_cycle_last_contact
    # touchdown인 발만 주기 업데이트 (last_contact > 0인 경우만)
    valid_touchdown = touchdown & (env._gait_cycle_last_contact > 0.0)
    env._gait_cycle_measured_period = torch.where(
        valid_touchdown,
        time_since_last,
        env._gait_cycle_measured_period,
    )
    # touchdown 시점의 시각 저장
    env._gait_cycle_last_contact = torch.where(
        touchdown,
        time_expanded,
        env._gait_cycle_last_contact,
    )

    # 이전 접촉 상태 업데이트
    env._gait_cycle_prev_contact = is_contact.clone()

    # 보상 계산: 측정된 주기가 목표 범위 내이면 보상
    period = env._gait_cycle_measured_period
    # 범위 내: 1.0, 범위 밖: exp(-distance^2)
    in_range = (period >= target_period_min) & (period <= target_period_max)
    target_mid = (target_period_min + target_period_max) / 2.0
    target_sigma = (target_period_max - target_period_min) / 2.0
    distance = (period - target_mid) / (target_sigma + 1e-6)
    period_reward = torch.where(
        in_range,
        torch.ones_like(period),
        torch.exp(-torch.square(distance)),
    )
    # 아직 측정되지 않은 발(period=0)은 보상 0
    period_reward = period_reward * (period > 0.0).float()

    # 4발 평균
    reward = period_reward.mean(dim=1)

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate


def stride_length_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_stride: float = 0.06,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """보폭 길이 보상: 스윙 시작~착지까지 발의 XY 평면 이동 거리를 측정.

    벌레 걷기의 문제 중 하나는 발이 거의 이동하지 않고 제자리에서
    빠르게 올렸다 내린다는 것. 이 보상은 실제 발의 이동 거리를
    추적하여 target_stride 이상이면 보상을 준다.

    발이 지면을 떠날 때(liftoff) XY 위치를 기록하고,
    착지(touchdown) 시 이동 거리를 계산한다.

    Args:
        sensor_cfg: 발 접촉 센서 설정
        foot_cfg: 발 바디 설정 (위치 추적용)
        asset_cfg: 로봇 설정 (게이팅용)
        target_stride: 목표 보폭 길이 (m)
        min_vel: 전진 속도 게이팅 문턱값
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    is_contact = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    asset: Articulation = env.scene[foot_cfg.name]
    foot_pos_xy = asset.data.body_pos_w[:, foot_cfg.body_ids, :2]  # (num_envs, 4, 2)

    num_envs = is_contact.shape[0]
    num_feet = is_contact.shape[1]

    # 상태 초기화
    if not hasattr(env, "_stride_liftoff_pos"):
        env._stride_liftoff_pos = torch.zeros(num_envs, num_feet, 2, device=is_contact.device)
        env._stride_prev_contact = torch.ones(num_envs, num_feet, device=is_contact.device)
        env._stride_measured = torch.zeros(num_envs, num_feet, device=is_contact.device)

    if env._stride_liftoff_pos.shape[0] != num_envs:
        env._stride_liftoff_pos = torch.zeros(num_envs, num_feet, 2, device=is_contact.device)
        env._stride_prev_contact = torch.ones(num_envs, num_feet, device=is_contact.device)
        env._stride_measured = torch.zeros(num_envs, num_feet, device=is_contact.device)

    # 에피소드 리셋 처리
    reset_mask = (env.episode_length_buf <= 1)
    if reset_mask.any():
        env._stride_liftoff_pos[reset_mask] = 0.0
        env._stride_prev_contact[reset_mask] = 1.0
        env._stride_measured[reset_mask] = 0.0

    # 이벤트 감지
    liftoff = (is_contact < 0.5) & (env._stride_prev_contact > 0.5)  # 접지→비접지
    touchdown = (is_contact > 0.5) & (env._stride_prev_contact < 0.5)  # 비접지→접지

    # liftoff 시 XY 위치 기록
    for f in range(num_feet):
        mask = liftoff[:, f]
        if mask.any():
            env._stride_liftoff_pos[mask, f, :] = foot_pos_xy[mask, f, :]

    # touchdown 시 보폭 측정
    for f in range(num_feet):
        mask = touchdown[:, f]
        if mask.any():
            displacement = foot_pos_xy[mask, f, :] - env._stride_liftoff_pos[mask, f, :]
            distance = torch.norm(displacement, dim=-1)  # (count,)
            env._stride_measured[mask, f] = distance

    # 이전 접촉 상태 업데이트
    env._stride_prev_contact = is_contact.clone()

    # 보상 계산: 보폭이 target_stride에 가까울수록 보상
    stride = env._stride_measured
    # target 이상이면 보상 1.0, 미만이면 비례
    normalized = torch.clamp(stride / (target_stride + 1e-6), 0.0, 2.0)
    # 1.0에서 최대, 0이면 최소, 2.0 이상이면 약간 감소
    stride_reward = torch.where(
        normalized <= 1.0,
        normalized,  # 0~target: 선형 증가
        2.0 - normalized,  # target~2*target: 감소 (너무 큰 보폭 억제)
    )
    stride_reward = torch.clamp(stride_reward, 0.0, 1.0)
    # 아직 측정 안 된 발(stride=0)은 보상 0
    stride_reward = stride_reward * (stride > 0.001).float()

    # 4발 평균
    reward = stride_reward.mean(dim=1)

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate


def swing_quality_gated_velocity(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_swing_ratio: float = 0.15,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """스윙 품질 게이티드 속도 보상 (V29 신규).

    4발 모두 최소 swing ratio 이상 들어올릴 때만 속도를 보상한다.
    앞발만 땅에 붙이고 뒷발만 스윙하는 벌레걸음을 원천 차단.

    보상값 = min(4발 swing_ratio) × heading_velocity
      - min() 은 가장 덜 스윙하는 발이 bottleneck이 됨
      - 4발 모두 min_swing_ratio 이상이어야 의미 있는 보상

    Args:
        sensor_cfg: 발 접촉 센서 설정
        asset_cfg: 로봇 설정
        contact_threshold: 접촉 판정 임계값
        min_swing_ratio: 모든 발에 요구되는 최소 swing ratio
        min_vel: 전진 속도 최소 게이팅 문턱값
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    is_contact = _contact_state(contact_sensor, sensor_cfg.body_ids, contact_threshold).float()

    num_envs = is_contact.shape[0]

    # swing ratio EMA 상태 초기화
    if not hasattr(env, "_swing_gate_ema"):
        env._swing_gate_ema = torch.full((num_envs, 4), 0.5, device=is_contact.device)

    if env._swing_gate_ema.shape[0] != num_envs:
        env._swing_gate_ema = torch.full((num_envs, 4), 0.5, device=is_contact.device)

    # 에피소드 리셋
    reset_mask = (env.episode_length_buf <= 1)
    if reset_mask.any():
        env._swing_gate_ema[reset_mask] = 0.5

    # swing = 1 - contact, EMA로 부드럽게
    swing = 1.0 - is_contact  # (num_envs, 4)
    env._swing_gate_ema = 0.95 * env._swing_gate_ema + 0.05 * swing

    # 4발 중 최솟값 — 가장 적게 스윙하는 발이 bottleneck
    min_swing = env._swing_gate_ema.min(dim=1).values  # (num_envs,)

    # heading velocity (x 방향)
    robot: Articulation = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_x_clamped = torch.clamp(vel_x, 0.0, None)

    # min_swing_ratio 이하이면 0 (hard gate)
    swing_gate = torch.clamp((min_swing - min_swing_ratio) / (0.5 - min_swing_ratio + 1e-6), 0.0, 1.0)

    # 전진 속도 최소 게이팅 (정지/후진 시 보상 차단)
    vel_gate = _heading_velocity_gate(env, asset_cfg, min_vel)

    return swing_gate * vel_x_clamped * vel_gate


# ============================================================
# V20: Soft-Ramp Reward Weight Curriculum (STAND → WALK → TROT)
# Hard phase switch를 선형 보간 ramp로 대체하여 critic shock 방지.
# Metric gating: 보행 구조 유지 확인 후에만 ramp 진행.
# ============================================================

# Phase별 가중치 정의 (모듈 레벨 상수)
_CURRICULUM_PHASE_WEIGHTS: dict[int, dict[str, float]] = {
    1: {  # STAND — 서기 안정화, 페널티 최소, bootstrap 활성
        "standing_height": 40.0,
        "height_bonus": 25.0,
        "forward_velocity_bootstrap": 8.0,
        "forward_velocity": 2.0,
        "same_side_penalty": 0.0,
        "rear_both_ground": 0.0,
        "undesired_contacts": -20.0,
        "feet_below_knees": -30.0,
        "trot_gait": 5.0,
        "rear_joint_frozen": -10.0,
        "diagonal_coupling": 5.0,
        "gait_cycle_period": 0.0,
        "stride_length": 0.0,
        "foot_clearance": 2.0,
        "joint_vel_l2": -0.05,
        "action_rate_l2": -0.3,
        "flat_orientation_l2": -1.0,
        "shoulder_neutral": -1.0,
        "stance_width_penalty": 0.0,
        "dof_acc_l2": -5.0e-07,
        "joint_oscillation": -5.0,
        "stance_propulsion": 8.0,
    },
    2: {  # WALK — 전진 보행, 점진적 gait 도입
        "standing_height": 8.0,
        "height_bonus": 15.0,
        "forward_velocity_bootstrap": 4.0,
        "forward_velocity": 12.0,
        "same_side_penalty": -10.0,
        "rear_both_ground": -30.0,
        "undesired_contacts": -50.0,
        "feet_below_knees": -80.0,
        "trot_gait": 20.0,
        "rear_joint_frozen": -30.0,
        "diagonal_coupling": 15.0,
        "gait_cycle_period": 8.0,
        "stride_length": 6.0,
        "foot_clearance": 5.0,
        "joint_vel_l2": -0.5,
        "action_rate_l2": -1.0,
        "flat_orientation_l2": -3.0,
        "shoulder_neutral": -3.0,
        "stance_width_penalty": -1.0,
        "dof_acc_l2": -2.0e-06,
        "joint_oscillation": -15.0,
        "stance_propulsion": 15.0,
    },
    3: {  # TROT — 전체 가중치 복원
        "standing_height": 3.0,
        "height_bonus": 7.0,
        "forward_velocity_bootstrap": 0.0,
        "forward_velocity": 12.0,
        "same_side_penalty": -30.0,
        "rear_both_ground": -80.0,
        "undesired_contacts": -100.0,
        "feet_below_knees": -150.0,
        "trot_gait": 40.0,
        "rear_joint_frozen": -60.0,
        "diagonal_coupling": 25.0,
        "gait_cycle_period": 15.0,
        "stride_length": 12.0,
        "foot_clearance": 8.0,
        "joint_vel_l2": -1.0,
        "action_rate_l2": -3.0,
        "flat_orientation_l2": -7.0,
        "shoulder_neutral": -6.0,
        "stance_width_penalty": -2.5,
        "dof_acc_l2": -5.0e-06,
        "joint_oscillation": -20.0,
        "stance_propulsion": 20.0,
    },
}


def _curriculum_target_alpha(iteration: int, ramp_start: int, ramp_end: int) -> float:
    """Iteration 기반 목표 alpha (0.0~1.0) 계산."""
    if iteration <= ramp_start:
        return 0.0
    if iteration >= ramp_end:
        return 1.0
    return (iteration - ramp_start) / (ramp_end - ramp_start)


def _curriculum_alpha_relay_early(
    iteration: int,
    up_start: int,
    up_end: int,
    down_end: int,
) -> float:
    """V28.1 relay early alpha: up_start→up_end ramp up, up_end→down_end ramp down.

    triangle 형태 (up_end에서 1.0, down_end 이후 0.0).
    예: early residency, iter 600→800→1000
    """
    if iteration <= up_start:
        return 0.0
    if iteration < up_end:
        return (iteration - up_start) / max(up_end - up_start, 1)
    if iteration < down_end:
        return 1.0 - (iteration - up_end) / max(down_end - up_end, 1)
    return 0.0


def _curriculum_apply_v281_weights(
    env: ManagerBasedRLEnv,
    # relay early alpha (triangle 600→800→1000)
    residency_early_alpha: float,
    # relay late alpha (ramp up 800→1000, hold 1000+)
    residency_late_alpha: float,
    # per-metric early/late max weight
    contact_residency_early_max: float,
    contact_residency_late_max: float,
    prop_residency_early_max: float,
    prop_residency_late_max: float,
    usage_residency_early_max: float,
    usage_residency_late_max: float,
    # rear pair symmetry alpha + max
    rear_symmetry_alpha: float,
    rear_symmetry_max: float,
    # late-phase exit penalty alpha + max
    exit_penalty_alpha: float,
    exit_penalty_max: float,
    # cooperation min-leg factor (ramp 0→target)
    coop_min_leg_alpha: float,
    coop_min_leg_factor_target: float,
    # V28.2: rear pair contact diff penalty alpha + max
    rear_contact_diff_alpha: float = 0.0,
    rear_contact_diff_max: float = 0.0,
    # V29: stride length reward alpha + max
    stride_length_alpha: float = 0.0,
    stride_length_max: float = 0.0,
    # V29: swing quality gated velocity reward alpha + max
    swing_gate_alpha: float = 0.0,
    swing_gate_max: float = 0.0,
    # V31: front swing ramp
    front_swing_alpha: float = 0.0,
    front_swing_bonus_max: float = 0.0,
    front_alternation_max: float = 0.0,
    front_both_ground_max: float = 0.0,
    min_swing_ratio_max: float = 0.0,
    # V31.2: front joint-level rewards (same ramp as front_swing)
    front_joint_velocity_max: float = 0.0,
    front_joint_frozen_max: float = 0.0,
) -> None:
    """V28.1 신규 term들의 가중치를 relay/ramp alpha 기반으로 적용."""
    # 1. Residency rewards (relay: early + late 합산 → 단일 term weight)
    residency_terms: dict[str, tuple[float, float]] = {
        "contact_residency": (contact_residency_early_max, contact_residency_late_max),
        "prop_residency": (prop_residency_early_max, prop_residency_late_max),
        "usage_residency": (usage_residency_early_max, usage_residency_late_max),
    }
    for term_name, (early_max, late_max) in residency_terms.items():
        if abs(early_max) < 1e-9 and abs(late_max) < 1e-9:
            continue
        total_w = residency_early_alpha * early_max + residency_late_alpha * late_max
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = total_w
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    # 2. Rear pair symmetry penalty (simple ramp)
    if abs(rear_symmetry_max) > 1e-9:
        rear_sym_w = rear_symmetry_alpha * rear_symmetry_max
        try:
            cfg = env.reward_manager.get_term_cfg("rear_pair_residency_symmetry")
            cfg.weight = rear_sym_w
            env.reward_manager.set_term_cfg("rear_pair_residency_symmetry", cfg)
        except Exception:
            pass

    # 3. Late-phase band exit penalty (simple ramp)
    if abs(exit_penalty_max) > 1e-9:
        exit_w = exit_penalty_alpha * exit_penalty_max
        try:
            cfg = env.reward_manager.get_term_cfg("late_phase_band_exit")
            cfg.weight = exit_w
            env.reward_manager.set_term_cfg("late_phase_band_exit", cfg)
        except Exception:
            pass

    # 4. Cooperation min-leg factor: four_limb_cooperation term의 params 업데이트
    if abs(coop_min_leg_factor_target - 1.0) > 1e-6 and abs(coop_min_leg_alpha) > 1e-9:
        # factor_low: 1.0 (V28 기본) → coop_min_leg_factor_target (V28.1 목표)
        # alpha 0→1 ramp으로 부드럽게 전환
        current_factor = 1.0 - coop_min_leg_alpha * (1.0 - coop_min_leg_factor_target)
        try:
            cfg = env.reward_manager.get_term_cfg("four_limb_cooperation")
            cfg.params["min_leg_factor_low"] = current_factor
            env.reward_manager.set_term_cfg("four_limb_cooperation", cfg)
        except Exception:
            pass

    # 5. V28.2: Rear pair contact diff penalty (current-step, simple ramp)
    if abs(rear_contact_diff_max) > 1e-9:
        rear_cd_w = rear_contact_diff_alpha * rear_contact_diff_max
        try:
            cfg = env.reward_manager.get_term_cfg("rear_pair_contact_diff")
            cfg.weight = rear_cd_w
            env.reward_manager.set_term_cfg("rear_pair_contact_diff", cfg)
        except Exception:
            pass

    # 6. V29: Stride length reward (simple ramp)
    if abs(stride_length_max) > 1e-9:
        stride_w = stride_length_alpha * stride_length_max
        try:
            cfg = env.reward_manager.get_term_cfg("stride_length")
            cfg.weight = stride_w
            env.reward_manager.set_term_cfg("stride_length", cfg)
        except Exception:
            pass

    # 7. V29: Swing quality gated velocity reward (simple ramp)
    if abs(swing_gate_max) > 1e-9:
        swing_gate_w = swing_gate_alpha * swing_gate_max
        try:
            cfg = env.reward_manager.get_term_cfg("swing_gate_velocity")
            cfg.weight = swing_gate_w
            env.reward_manager.set_term_cfg("swing_gate_velocity", cfg)
        except Exception:
            pass

    # 8. V31: Front swing rewards (simple ramp, 6 terms)
    _v31_terms: dict[str, float] = {
        "front_swing": front_swing_alpha * front_swing_bonus_max,
        "front_alternation": front_swing_alpha * front_alternation_max,
        "front_both_ground": front_swing_alpha * front_both_ground_max,
        "min_swing_ratio": front_swing_alpha * min_swing_ratio_max,
        "front_joint_velocity": front_swing_alpha * front_joint_velocity_max,
        "front_joint_frozen": front_swing_alpha * front_joint_frozen_max,
    }
    for term_name, w in _v31_terms.items():
        if abs(w) < 1e-9 and abs(front_swing_alpha) < 1e-9:
            continue
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = w
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass


def _curriculum_apply_layer_c_weights(
    env: ManagerBasedRLEnv,
    band_alpha: float,
    band_contact_initial: float,
    band_contact_final: float,
    band_propulsion_initial: float,
    band_propulsion_final: float,
    coop_alpha: float,
    coop_usage_initial: float,
    coop_usage_final: float,
    coop_reward_initial: float,
    coop_reward_final: float,
) -> None:
    """V28 Layer C target-band + cooperation 가중치 ramp 적용 (복잡도 분리)."""
    band_terms: dict[str, tuple[float, float]] = {
        "per_leg_contact_target_band": (band_contact_initial, band_contact_final),
        "per_leg_propulsion_target_band": (band_propulsion_initial, band_propulsion_final),
    }
    for term_name, (w_init, w_final) in band_terms.items():
        if abs(w_init) < 1e-9 and abs(w_final) < 1e-9:
            continue
        current = w_init + band_alpha * (w_final - w_init)
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    coop_terms: dict[str, tuple[float, float]] = {
        "limb_usage_target_band": (coop_usage_initial, coop_usage_final),
        "four_limb_cooperation": (coop_reward_initial, coop_reward_final),
    }
    for term_name, (w_init, w_final) in coop_terms.items():
        if abs(w_init) < 1e-9 and abs(w_final) < 1e-9:
            continue
        current = w_init + coop_alpha * (w_final - w_init)
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass


def _curriculum_apply_weights(
    env: ManagerBasedRLEnv,
    alpha12: float,
    alpha23: float,
    validity_alpha: float,
    validity_limb_usage_initial: float,
    validity_limb_usage_final: float,
    validity_rear_diff_initial: float,
    validity_rear_diff_final: float,
    floor_alpha: float = 0.0,
    load_alpha: float = 0.0,
    floor_limb_usage_initial: float = 0.0,
    floor_limb_usage_final: float = 0.0,
    floor_per_leg_contact_initial: float = 0.0,
    floor_per_leg_contact_final: float = 0.0,
    floor_per_leg_propulsion_initial: float = 0.0,
    floor_per_leg_propulsion_final: float = 0.0,
    load_rear_usage_diff_final: float = 0.0,
    load_front_usage_diff_final: float = 0.0,
    load_rear_prop_diff_final: float = 0.0,
    load_front_rear_balance_final: float = 0.0,
    load_front_prop_diff_final: float = 0.0,
    # V27.1a: single_limb_validity_penalty soft ramp
    validity_gate_alpha: float = 1.0,
    validity_gate_initial: float = -60.0,
    validity_gate_final: float = -60.0,
    # V27.1b: per_leg_propulsion_floor 전용 alpha (contact floor와 분리)
    propulsion_floor_alpha: float = -1.0,
    # V28: Layer C target-band reward ramp
    band_alpha: float = 0.0,
    band_contact_initial: float = 0.0,
    band_contact_final: float = 0.0,
    band_propulsion_initial: float = 0.0,
    band_propulsion_final: float = 0.0,
    # V28: usage band + cooperation ramp (별도 alpha)
    coop_alpha: float = 0.0,
    coop_usage_initial: float = 0.0,
    coop_usage_final: float = 0.0,
    coop_reward_initial: float = 0.0,
    coop_reward_final: float = 0.0,
) -> None:
    """alpha 기반으로 Phase 가중치를 보간하여 적용."""
    w = _CURRICULUM_PHASE_WEIGHTS
    for term_name in w[1]:
        w1 = w[1][term_name]
        w2 = w[2][term_name]
        w3 = w[3][term_name]
        # 2단계 보간: P1→P2 (alpha12), 이후 P2→P3 (alpha23)
        if alpha23 > 0.0:
            current = w2 + alpha23 * (w3 - w2)
        else:
            current = w1 + alpha12 * (w2 - w1)
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    # Legacy validity terms (V24 path, no-op if weights are 0)
    validity_terms = {
        "limb_usage_min_penalty": (float(validity_limb_usage_initial), float(validity_limb_usage_final)),
        "rear_left_right_usage_diff_penalty": (float(validity_rear_diff_initial), float(validity_rear_diff_final)),
    }
    for term_name, (w_init, w_final) in validity_terms.items():
        if abs(w_init) < 1e-9 and abs(w_final) < 1e-9:
            continue
        current = w_init + validity_alpha * (w_final - w_init)
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    # V26: Existence floor ramp (iter 0 ~ floor_ramp_end)
    # V27.1b: per_leg_propulsion_floor는 propulsion_floor_alpha로 별도 처리
    floor_terms: dict[str, tuple[float, float]] = {
        "limb_usage_min_penalty": (float(floor_limb_usage_initial), float(floor_limb_usage_final)),
        "per_leg_contact_floor": (float(floor_per_leg_contact_initial), float(floor_per_leg_contact_final)),
    }
    for term_name, (w_init, w_final) in floor_terms.items():
        if abs(w_init) < 1e-9 and abs(w_final) < 1e-9:
            continue
        current = w_init + floor_alpha * (w_final - w_init)
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    # V27.1b: per_leg_propulsion_floor 전용 ramp (propulsion_floor_alpha)
    # propulsion_floor_alpha < 0 이면 contact와 동일한 floor_alpha 사용 (하위호환)
    _prop_alpha = floor_alpha if propulsion_floor_alpha < 0.0 else propulsion_floor_alpha
    _prop_w_init = float(floor_per_leg_propulsion_initial)
    _prop_w_final = float(floor_per_leg_propulsion_final)
    if abs(_prop_w_init) > 1e-9 or abs(_prop_w_final) > 1e-9:
        _prop_current = _prop_w_init + _prop_alpha * (_prop_w_final - _prop_w_init)
        try:
            cfg = env.reward_manager.get_term_cfg("per_leg_propulsion_floor")
            cfg.weight = _prop_current
            env.reward_manager.set_term_cfg("per_leg_propulsion_floor", cfg)
        except Exception:
            pass

    # V26/V27: Load sharing ramp (load_ramp_start ~ load_ramp_end), starts from 0
    load_terms: dict[str, float] = {
        "rear_left_right_usage_diff_penalty": float(load_rear_usage_diff_final),
        "front_left_right_usage_diff_penalty": float(load_front_usage_diff_final),
        "rear_left_right_propulsion_diff_penalty": float(load_rear_prop_diff_final),
        "front_rear_support_balance_penalty": float(load_front_rear_balance_final),
        "front_left_right_propulsion_diff_penalty": float(load_front_prop_diff_final),
    }
    for term_name, w_final in load_terms.items():
        if abs(w_final) < 1e-9:
            continue
        current = 0.0 + load_alpha * w_final
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = current
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass

    # V27.1a: single_limb_validity_penalty soft ramp (iter 0 ~ validity_gate_ramp_end)
    # initial에서 final까지 선형 보간 — iter 0부터 너무 강하게 왜곡하지 않도록
    vg_initial = float(validity_gate_initial)
    vg_final = float(validity_gate_final)
    if abs(vg_initial - vg_final) > 1e-6 or abs(vg_initial) > 1e-6:
        vg_current = vg_initial + float(validity_gate_alpha) * (vg_final - vg_initial)
        try:
            cfg = env.reward_manager.get_term_cfg("single_limb_validity_penalty")
            cfg.weight = vg_current
            env.reward_manager.set_term_cfg("single_limb_validity_penalty", cfg)
        except Exception:
            pass

    # V28: Layer C target-band + cooperation ramp (별도 헬퍼 — 복잡도 분리)
    _curriculum_apply_layer_c_weights(
        env,
        band_alpha=float(band_alpha),
        band_contact_initial=float(band_contact_initial),
        band_contact_final=float(band_contact_final),
        band_propulsion_initial=float(band_propulsion_initial),
        band_propulsion_final=float(band_propulsion_final),
        coop_alpha=float(coop_alpha),
        coop_usage_initial=float(coop_usage_initial),
        coop_usage_final=float(coop_usage_final),
        coop_reward_initial=float(coop_reward_initial),
        coop_reward_final=float(coop_reward_final),
    )


# ── 로깅 대상 핵심 term 정의 ──
_LOG_WEIGHT_TERMS = [
    "forward_velocity",
    "forward_velocity_bootstrap",
    "trot_gait",
    "standing_height",
    "height_bonus",
    "shoulder_neutral",
    "stance_width_penalty",
    "joint_vel_l2",
    "dof_acc_l2",
    # V26 existence floor (없으면 skip)
    "limb_usage_min_penalty",
    "per_leg_contact_floor",
    "per_leg_propulsion_floor",
    # V26 load sharing (없으면 skip)
    "rear_left_right_usage_diff_penalty",
    "front_left_right_usage_diff_penalty",
    "rear_left_right_propulsion_diff_penalty",
    "front_rear_support_balance_penalty",
    # V27 신규
    "front_left_right_propulsion_diff_penalty",
    "single_limb_validity_penalty",
    # V28 Layer C (없으면 skip)
    "per_leg_contact_target_band",
    "per_leg_propulsion_target_band",
    "limb_usage_target_band",
    "four_limb_cooperation",
    # V28.1 residency / symmetry / exit (없으면 skip)
    "contact_residency",
    "prop_residency",
    "usage_residency",
    "rear_pair_residency_symmetry",
    "late_phase_band_exit",
    # V31 front swing (없으면 skip)
    "front_swing",
    "front_alternation",
    "front_both_ground",
    "min_swing_ratio",
    # V31.2 front joint-level (없으면 skip)
    "front_joint_velocity",
    "front_joint_frozen",
]
_LOG_RAW_GAIT_TERMS = ["forward_velocity", "trot_gait", "diagonal_coupling", "leg_lift", "foot_clearance"]
_LOG_RAW_QUALITY_TERMS = ["joint_vel_l2", "dof_acc_l2", "action_rate_l2"]


def _safe_policy_obs_dim(env: ManagerBasedRLEnv) -> int | None:
    obs_buf = getattr(env, "obs_buf", None)
    if isinstance(obs_buf, torch.Tensor) and obs_buf.ndim >= 2:
        return int(obs_buf.shape[1])
    return None


def _safe_policy_obs_term_names(env: ManagerBasedRLEnv) -> list[str]:
    om = getattr(env, "observation_manager", None)
    if om is None:
        return []
    candidates = [
        getattr(om, "_group_obs_term_names", None),
        getattr(om, "group_obs_term_names", None),
        getattr(om, "_group_term_names", None),
    ]
    for candidate in candidates:
        try:
            names = candidate.get("policy")
            if names:
                return list(names)
        except Exception:
            pass
    return []


def _log_v55_audit_snapshot(env: ManagerBasedRLEnv, iteration: int, v55_track: str) -> None:
    logged = getattr(env, "_v55_logged_audits", set())
    if iteration in logged:
        return

    term_names = list(getattr(env.reward_manager, "_term_names", []))
    policy_obs_terms = _safe_policy_obs_term_names(env)
    obs_dim = _safe_policy_obs_dim(env)

    def _weight_of(term_name: str) -> str:
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            return f"{cfg.weight:.4f}"
        except Exception:
            return "n/a"

    active_terms = []
    for name in term_names:
        try:
            cfg = env.reward_manager.get_term_cfg(name)
            if abs(float(cfg.weight)) > 1.0e-8:
                active_terms.append(name)
        except Exception:
            pass

    print(f"\n{'=' * 60}")
    print(f"[V55 Audit] iter {iteration} | track={v55_track}")
    print(
        "  phase_obs="
        f"{'ON' if 'phase_clock' in policy_obs_terms else 'OFF'}"
        f"  phase_contact={_weight_of('phase_contact')}"
        f"  phase_clearance={_weight_of('phase_clearance')}"
        f"  obs_dim={obs_dim if obs_dim is not None else 'unknown'}"
        f"  active_reward_terms={len(active_terms)}"
    )

    focus_terms = [
        "boot_standing",
        "standing_height",
        "height_bonus",
        "feet_air_time",
        "forward_velocity",
        "forward_velocity_bootstrap",
        "trot_gait",
        "diagonal_coupling",
        "shoulder_neutral",
        "stance_width_penalty",
        "phase_contact",
        "phase_clearance",
        "joint_vel_l2",
        "dof_acc_l2",
        "action_rate_l2",
    ]
    parts = []
    for name in focus_terms:
        if name in term_names:
            parts.append(f"{name}={_weight_of(name)}")
    if parts:
        print(f"  focus_weights: {', '.join(parts)}")

    logged.add(iteration)
    env._v55_logged_audits = logged
    print(f"{'=' * 60}")


def _apply_v55_runtime_overrides(
    env: ManagerBasedRLEnv,
    action_rate_weight: float | None,
    joint_vel_weight: float | None,
    dof_acc_weight: float | None,
    forward_velocity_weight: float | None,
    forward_velocity_bootstrap_weight: float | None,
    standing_height_weight: float | None = None,
    height_bonus_weight: float | None = None,
    trot_gait_weight: float | None = None,
    diagonal_coupling_weight: float | None = None,
    stance_propulsion_weight: float | None = None,
) -> None:
    overrides = {
        "action_rate_l2": action_rate_weight,
        "joint_vel_l2": joint_vel_weight,
        "dof_acc_l2": dof_acc_weight,
        "forward_velocity": forward_velocity_weight,
        "forward_velocity_bootstrap": forward_velocity_bootstrap_weight,
        "standing_height": standing_height_weight,
        "height_bonus": height_bonus_weight,
        "trot_gait": trot_gait_weight,
        "diagonal_coupling": diagonal_coupling_weight,
        "stance_propulsion": stance_propulsion_weight,
    }
    for term_name, weight in overrides.items():
        if weight is None:
            continue
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = float(weight)
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass


def _apply_v55_release_soft_ramp(
    env: ManagerBasedRLEnv,
    iteration: int,
    ramp_iters: int,
    shoulder_pre: float | None,
    shoulder_post: float | None,
    stance_pre: float | None,
    stance_post: float | None,
    rear_prop_diff_pre: float | None = None,
    rear_prop_diff_post: float | None = None,
    front_prop_diff_pre: float | None = None,
    front_prop_diff_post: float | None = None,
    rear_usage_diff_pre: float | None = None,
    rear_usage_diff_post: float | None = None,
    front_usage_diff_pre: float | None = None,
    front_usage_diff_post: float | None = None,
    per_leg_contact_floor_pre: float | None = None,
    per_leg_contact_floor_post: float | None = None,
) -> None:
    if ramp_iters <= 0:
        ramp_iters = 1
    release_iter = getattr(env, "_v47_boot_gate_released_iter", -1)
    if release_iter is None or release_iter < 0:
        alpha = 0.0
    else:
        alpha = min(1.0, max(0.0, (iteration - release_iter) / float(ramp_iters)))

    def _blend(pre: float | None, post: float | None) -> float | None:
        if pre is None or post is None:
            return None
        return float(pre + (post - pre) * alpha)

    overrides = {
        "shoulder_neutral": _blend(shoulder_pre, shoulder_post),
        "stance_width_penalty": _blend(stance_pre, stance_post),
        "rear_left_right_propulsion_diff_penalty": _blend(rear_prop_diff_pre, rear_prop_diff_post),
        "front_left_right_propulsion_diff_penalty": _blend(front_prop_diff_pre, front_prop_diff_post),
        "rear_left_right_usage_diff_penalty": _blend(rear_usage_diff_pre, rear_usage_diff_post),
        "front_left_right_usage_diff_penalty": _blend(front_usage_diff_pre, front_usage_diff_post),
        "per_leg_contact_floor": _blend(per_leg_contact_floor_pre, per_leg_contact_floor_post),
    }
    for term_name, weight in overrides.items():
        if weight is None:
            continue
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = float(weight)
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass


def _apply_v55_release_forward_ramp(
    env: ManagerBasedRLEnv,
    iteration: int,
    ramp_iters: int,
    forward_pre: float | None,
    forward_post: float | None,
    forward_bootstrap_pre: float | None,
    forward_bootstrap_post: float | None,
) -> None:
    if ramp_iters <= 0:
        ramp_iters = 1
    release_iter = getattr(env, "_v47_boot_gate_released_iter", -1)
    if release_iter is None or release_iter < 0:
        alpha = 0.0
    else:
        alpha = min(1.0, max(0.0, (iteration - release_iter) / float(ramp_iters)))

    def _blend(pre: float | None, post: float | None) -> float | None:
        if pre is None or post is None:
            return None
        return float(pre + (post - pre) * alpha)

    overrides = {
        "forward_velocity": _blend(forward_pre, forward_post),
        "forward_velocity_bootstrap": _blend(forward_bootstrap_pre, forward_bootstrap_post),
    }
    for term_name, weight in overrides.items():
        if weight is None:
            continue
        try:
            cfg = env.reward_manager.get_term_cfg(term_name)
            cfg.weight = float(weight)
            env.reward_manager.set_term_cfg(term_name, cfg)
        except Exception:
            pass


def _log_v55_release_debug(env: ManagerBasedRLEnv, iteration: int) -> None:
    if iteration not in (499, 500, 501):
        return
    names = [
        "forward_velocity",
        "forward_velocity_bootstrap",
        "shoulder_neutral",
        "stance_width_penalty",
        "rear_left_right_propulsion_diff_penalty",
        "front_left_right_propulsion_diff_penalty",
        "rear_left_right_usage_diff_penalty",
        "front_left_right_usage_diff_penalty",
        "per_leg_contact_floor",
    ]
    parts: list[str] = []
    for name in names:
        try:
            cfg = env.reward_manager.get_term_cfg(name)
            parts.append(f"{name}={cfg.weight:.4f}")
        except Exception:
            parts.append(f"{name}=<missing>")
    print(f"[ReleaseDebug] iter {iteration}: " + ", ".join(parts))


def _curriculum_log_snapshot(env: ManagerBasedRLEnv, iteration: int,
                             alpha12: float, alpha23: float, validity_alpha: float, gate_paused: bool) -> None:
    """Ramp 상태 + key weight + raw metric snapshot 로깅.

    리뷰어 요청 A, B:
      A) phase, alpha, gate 상태, 주요 weight 값
      B) raw gait + quality metric snapshot
    """
    phase_str = _curriculum_phase_str(alpha12, alpha23)
    mean_ep_len = env.episode_length_buf.float().mean().item()
    gate_str = "PAUSED" if gate_paused else "active"

    print(f"\n{'─' * 60}")
    print(f"[Curriculum Snapshot] iter {iteration} | {phase_str}")
    print(f"  alpha12={alpha12:.4f}  alpha23={alpha23:.4f}  validity_alpha={validity_alpha:.4f}  gate={gate_str}  ep_len={mean_ep_len:.1f}")

    # A: 현재 적용된 주요 weight 값
    weight_parts = []
    for name in _LOG_WEIGHT_TERMS:
        try:
            cfg = env.reward_manager.get_term_cfg(name)
            weight_parts.append(f"{name}={cfg.weight:.4f}")
        except Exception:
            pass
    if weight_parts:
        print(f"  weights: {', '.join(weight_parts)}")

    # B: raw metric snapshot (from _step_reward)
    rm = env.reward_manager
    term_names = rm._term_names
    step_reward = rm._step_reward  # (num_envs, num_terms), weighted per-step

    # Gait raw metrics
    gait_parts = []
    for name in _LOG_RAW_GAIT_TERMS:
        if name in term_names:
            idx = term_names.index(name)
            try:
                cfg = rm.get_term_cfg(name)
                w = cfg.weight
                weighted_mean = step_reward[:, idx].mean().item()
                raw = weighted_mean / w if abs(w) > 1e-8 else 0.0
                gait_parts.append(f"{name}={raw:.4f}")
            except Exception:
                pass
    if gait_parts:
        print(f"  raw gait: {', '.join(gait_parts)}")

    # Quality raw metrics (penalties — raw 값은 양수, weight가 음수)
    quality_parts = []
    for name in _LOG_RAW_QUALITY_TERMS:
        if name in term_names:
            idx = term_names.index(name)
            try:
                cfg = rm.get_term_cfg(name)
                w = cfg.weight
                weighted_mean = step_reward[:, idx].mean().item()
                raw = weighted_mean / w if abs(w) > 1e-8 else 0.0
                quality_parts.append(f"{name}={raw:.4f}")
            except Exception:
                pass
    if quality_parts:
        print(f"  raw quality: {', '.join(quality_parts)}")
    print(f"{'─' * 60}")


def reward_weight_curriculum(
    env: ManagerBasedRLEnv,
    env_ids: torch.Tensor,
    num_steps_per_env: int = 48,
    # Ramp 구간 정의
    ramp1_start: int = 1500,    # Phase 1→2 ramp 시작
    ramp1_end: int = 3000,      # Phase 1→2 ramp 완료
    ramp2_start: int = 5500,    # Phase 2→3 ramp 시작
    ramp2_end: int = 8000,      # Phase 2→3 ramp 완료
    validity_ramp_start: int = 200,
    validity_ramp_end: int = 600,
    validity_limb_usage_initial: float = -3.0,
    validity_limb_usage_final: float = -12.0,
    validity_rear_diff_initial: float = -2.0,
    validity_rear_diff_final: float = -8.0,
    # V26: Existence floor ramp (iter 0 ~ floor_ramp_end)
    floor_ramp_start: int = 0,
    floor_ramp_end: int = 1,
    floor_limb_usage_initial: float = 0.0,
    floor_limb_usage_final: float = 0.0,
    floor_per_leg_contact_initial: float = 0.0,
    floor_per_leg_contact_final: float = 0.0,
    floor_per_leg_propulsion_initial: float = 0.0,
    floor_per_leg_propulsion_final: float = 0.0,
    # V26: Load sharing ramp (load_ramp_start ~ load_ramp_end)
    load_ramp_start: int = 0,
    load_ramp_end: int = 1,
    load_rear_usage_diff_final: float = 0.0,
    load_front_usage_diff_final: float = 0.0,
    load_rear_prop_diff_final: float = 0.0,
    load_front_rear_balance_final: float = 0.0,
    load_front_prop_diff_final: float = 0.0,
    # V27.1a: single_limb_validity_penalty soft ramp
    validity_gate_ramp_start: int = 0,
    validity_gate_ramp_end: int = 1,
    validity_gate_initial: float = -60.0,
    validity_gate_final: float = -60.0,
    # V27.1b: per_leg_propulsion_floor 전용 ramp (contact와 분리)
    propulsion_floor_ramp_start: int = -1,
    propulsion_floor_ramp_end: int = -1,
    # V28: Layer C target-band reward ramp (iter 100~300)
    band_ramp_start: int = 100,
    band_ramp_end: int = 300,
    band_contact_initial: float = 0.0,
    band_contact_final: float = 0.0,
    band_propulsion_initial: float = 0.0,
    band_propulsion_final: float = 0.0,
    # V28: usage band + cooperation ramp (iter 200~450)
    coop_ramp_start: int = 200,
    coop_ramp_end: int = 450,
    coop_usage_initial: float = 0.0,
    coop_usage_final: float = 0.0,
    coop_reward_initial: float = 0.0,
    coop_reward_final: float = 0.0,
    # V28.1: residency relay ramp (early triangle: up_start→up_end→down_end)
    residency_relay_up_start: int = 600,   # early ramp up 시작
    residency_relay_up_end: int = 800,     # early ramp up 완료 / late ramp up 시작
    residency_relay_down_end: int = 1000,  # early ramp down 완료 / late ramp up 완료
    contact_residency_early_max: float = 0.0,
    contact_residency_late_max: float = 0.0,
    prop_residency_early_max: float = 0.0,
    prop_residency_late_max: float = 0.0,
    usage_residency_early_max: float = 0.0,
    usage_residency_late_max: float = 0.0,
    # V28.1: rear pair symmetry penalty ramp
    rear_symmetry_ramp_start: int = 600,
    rear_symmetry_ramp_end: int = 1000,
    rear_symmetry_max: float = 0.0,
    # V28.1: late-phase band exit penalty ramp
    exit_penalty_ramp_start: int = 800,
    exit_penalty_ramp_end: int = 1200,
    exit_penalty_max: float = 0.0,
    # V28.1: cooperation min-leg factor ramp (1.0 → target)
    coop_min_leg_ramp_start: int = 800,
    coop_min_leg_ramp_end: int = 1000,
    coop_min_leg_factor_target: float = 1.0,  # 1.0이면 V28 동작 유지
    # V28.2: rear pair contact diff penalty ramp (current-step)
    rear_contact_diff_ramp_start: int = 300,
    rear_contact_diff_ramp_end: int = 600,
    rear_contact_diff_max: float = 0.0,
    # V29: stride length reward ramp
    stride_length_ramp_start: int = 400,
    stride_length_ramp_end: int = 700,
    stride_length_max: float = 0.0,
    # V29: swing quality gated velocity reward ramp
    swing_gate_ramp_start: int = 600,
    swing_gate_ramp_end: int = 900,
    swing_gate_max: float = 0.0,
    # V31: front swing ramp (앞다리 swing 강제)
    front_swing_ramp_start: int = 100,
    front_swing_ramp_end: int = 400,
    front_swing_bonus_max: float = 0.0,
    front_alternation_max: float = 0.0,
    front_both_ground_max: float = 0.0,
    min_swing_ratio_max: float = 0.0,
    # V31.2: front joint-level rewards (same ramp as front_swing)
    front_joint_velocity_max: float = 0.0,
    front_joint_frozen_max: float = 0.0,
    # V35.5: boot stability ramp
    boot_ramp_end: int = 0,                    # 0이면 비활성화
    boot_undesired_contacts_floor: float = -100.0,  # 초기 undesired_contacts weight
    boot_vel_x_min: float = 0.1,               # 초기 속도 범위
    boot_vel_x_max: float = 0.5,
    boot_vel_restore_iter: int = 500,           # 속도 복원 iter
    # V37: anti-splay curriculum ramp
    splay_ramp_start: int = 0,                   # 0이면 비활성화
    splay_ramp_end: int = 0,
    splay_shoulder_initial: float = -4.0,
    splay_shoulder_final: float = -4.0,
    splay_stance_initial: float = -2.5,
    splay_stance_final: float = -2.5,
    splay_height_initial: float = 0.24,
    splay_height_final: float = 0.24,
    # V38.2: Soft CaT ramp (threshold/margin 고정, probability만 ramp)
    cat_ramp_start: int = 0,
    cat_ramp_end: int = 0,
    cat_threshold: float = 0.3,
    cat_margin: float = 0.3,
    cat_probability_final: float = 0.002,
    # 업데이트 주기
    update_interval: int = 10,  # ramp 중 N iteration마다 가중치 갱신
    # Metric gating (보행 구조 보호)
    gait_gate_enabled: bool = True,
    gait_gate_min_ep_len: float = 200.0,  # ep_len < 이 값이면 ramp 일시정지
    # V47: boot reward ramp-down (gait_gate 연동)
    boot_standing_initial: float = 0.0,   # 0이면 비활성
    boot_standing_floor: float = 0.0,     # V50.2: ramp-down 최소값 (0이면 완전 소멸)
    boot_contact_initial: float = 0.0,    # 0이면 비활성
    boot_ramp_down_iters: int = 300,      # gait_gate 해제 후 몇 iter에 걸쳐 floor까지 감소
    # V54.2: boot-only bridge (gait_gate 해제 후 0으로 감소)
    boot_leg_lift_initial: float = 0.0,     # 0이면 비활성
    boot_rear_vel_initial: float = 0.0,     # 0이면 비활성
    boot_bridge_ramp_down_iters: int = 500, # gait_gate 해제 후 몇 iter에 걸쳐 0으로
    # V54.3: phase ramp-in (gait_gate 해제 후 0→target으로 점진 증가)
    phase_contact_target: float = 0.0,      # 0이면 비활성
    phase_clearance_target: float = 0.0,    # 0이면 비활성
    phase_ramp_in_iters: int = 500,         # gait_gate 해제 후 몇 iter에 걸쳐 target까지
    phase_table_enabled: bool = True,       # False면 legacy STAND/WALK/TROT phase table 비활성
    v55_track: str | None = None,
    v55_action_rate_weight: float | None = None,
    v55_joint_vel_weight: float | None = None,
    v55_dof_acc_weight: float | None = None,
    v55_forward_velocity_weight: float | None = None,
    v55_forward_velocity_bootstrap_weight: float | None = None,
    v55_standing_height_weight: float | None = None,
    v55_height_bonus_weight: float | None = None,
    v55_trot_gait_weight: float | None = None,
    v55_diagonal_coupling_weight: float | None = None,
    v55_stance_propulsion_weight: float | None = None,
    v55_release_forward_ramp_iters: int = 0,
    v55_release_forward_velocity_pre: float | None = None,
    v55_release_forward_velocity_post: float | None = None,
    v55_release_forward_velocity_bootstrap_pre: float | None = None,
    v55_release_forward_velocity_bootstrap_post: float | None = None,
    v55_release_soft_ramp_iters: int = 0,
    v55_release_shoulder_neutral_pre: float | None = None,
    v55_release_shoulder_neutral_post: float | None = None,
    v55_release_stance_width_pre: float | None = None,
    v55_release_stance_width_post: float | None = None,
    v55_release_rear_prop_diff_pre: float | None = None,
    v55_release_rear_prop_diff_post: float | None = None,
    v55_release_front_prop_diff_pre: float | None = None,
    v55_release_front_prop_diff_post: float | None = None,
    v55_release_rear_usage_diff_pre: float | None = None,
    v55_release_rear_usage_diff_post: float | None = None,
    v55_release_front_usage_diff_pre: float | None = None,
    v55_release_front_usage_diff_post: float | None = None,
    v55_release_per_leg_contact_floor_pre: float | None = None,
    v55_release_per_leg_contact_floor_post: float | None = None,
    # 로깅
    log_interval: int = 100,    # N iteration마다 상태 출력
) -> None:
    """Soft-ramp 리워드 가중치 커리큘럼 (V20, V26 확장).

    기존 hard phase switch를 선형 보간 ramp로 대체.
    Phase 1 (STAND) → Phase 2 (WALK) → Phase 3 (TROT) 가중치를
    ramp 구간에서 점진적으로 보간하여 critic shock를 방지한다.

    V26 확장: existence floor ramp + load sharing ramp.
      - floor_ramp: iter 0~200 동안 존재 floor 패널티 ramp-up
      - load_ramp: iter 200~350 동안 하중 분산 패널티 ramp-up

    Metric gating: 평균 episode length가 gait_gate_min_ep_len 미만이면
    ramp를 일시정지하여 보행 구조 붕괴를 방지한다.

    주의: common_step_counter는 체크포인트에 저장되지 않으므로
          resume 시 train.py에서 runner.current_learning_iteration 기반으로
          common_step_counter를 동기화해야 한다. (V18.3 fix)
    """
    step = env.common_step_counter
    iteration = step // num_steps_per_env

    # ── 상태 초기화 (최초 호출 또는 resume 후) ──
    if not hasattr(env, "_crr_alpha12"):
        # resume 시 iteration 기반으로 alpha를 복원 (과거 ramp는 완료된 것으로 간주)
        env._crr_alpha12 = _curriculum_target_alpha(iteration, ramp1_start, ramp1_end)
        env._crr_alpha23 = _curriculum_target_alpha(iteration, ramp2_start, ramp2_end)
        env._crr_validity_alpha = _curriculum_target_alpha(iteration, validity_ramp_start, validity_ramp_end)
        env._crr_floor_alpha = _curriculum_target_alpha(iteration, floor_ramp_start, floor_ramp_end)
        env._crr_load_alpha = _curriculum_target_alpha(iteration, load_ramp_start, load_ramp_end)
        env._crr_validity_gate_alpha = _curriculum_target_alpha(iteration, validity_gate_ramp_start, validity_gate_ramp_end)
        # V27.1b: propulsion floor 전용 alpha (-1이면 contact와 동일한 floor_alpha 사용)
        _prop_ramp_start = propulsion_floor_ramp_start if propulsion_floor_ramp_start >= 0 else floor_ramp_start
        _prop_ramp_end = propulsion_floor_ramp_end if propulsion_floor_ramp_end >= 0 else floor_ramp_end
        env._crr_propulsion_floor_alpha = _curriculum_target_alpha(iteration, _prop_ramp_start, _prop_ramp_end)
        # V28: Layer C alphas
        env._crr_band_alpha = _curriculum_target_alpha(iteration, band_ramp_start, band_ramp_end)
        env._crr_coop_alpha = _curriculum_target_alpha(iteration, coop_ramp_start, coop_ramp_end)
        # V28.1: residency relay alphas
        env._crr_residency_early_alpha = _curriculum_alpha_relay_early(
            iteration, residency_relay_up_start, residency_relay_up_end, residency_relay_down_end
        )
        env._crr_residency_late_alpha = _curriculum_target_alpha(
            iteration, residency_relay_up_end, residency_relay_down_end
        )
        env._crr_rear_symmetry_alpha = _curriculum_target_alpha(
            iteration, rear_symmetry_ramp_start, rear_symmetry_ramp_end
        )
        env._crr_exit_penalty_alpha = _curriculum_target_alpha(
            iteration, exit_penalty_ramp_start, exit_penalty_ramp_end
        )
        env._crr_coop_min_leg_alpha = _curriculum_target_alpha(
            iteration, coop_min_leg_ramp_start, coop_min_leg_ramp_end
        )
        env._crr_rear_contact_diff_alpha = _curriculum_target_alpha(
            iteration, rear_contact_diff_ramp_start, rear_contact_diff_ramp_end
        )
        env._crr_stride_length_alpha = _curriculum_target_alpha(
            iteration, stride_length_ramp_start, stride_length_ramp_end
        )
        env._crr_swing_gate_alpha = _curriculum_target_alpha(
            iteration, swing_gate_ramp_start, swing_gate_ramp_end
        )
        env._crr_front_swing_alpha = _curriculum_target_alpha(
            iteration, front_swing_ramp_start, front_swing_ramp_end
        )
        env._crr_last_update = iteration
        env._crr_gate_paused = False
        if phase_table_enabled:
            _curriculum_apply_weights(
                env,
                env._crr_alpha12,
                env._crr_alpha23,
                env._crr_validity_alpha,
                validity_limb_usage_initial,
                validity_limb_usage_final,
                validity_rear_diff_initial,
                validity_rear_diff_final,
                floor_alpha=env._crr_floor_alpha,
                load_alpha=env._crr_load_alpha,
                floor_limb_usage_initial=floor_limb_usage_initial,
                floor_limb_usage_final=floor_limb_usage_final,
                floor_per_leg_contact_initial=floor_per_leg_contact_initial,
                floor_per_leg_contact_final=floor_per_leg_contact_final,
                floor_per_leg_propulsion_initial=floor_per_leg_propulsion_initial,
                floor_per_leg_propulsion_final=floor_per_leg_propulsion_final,
                load_rear_usage_diff_final=load_rear_usage_diff_final,
                load_front_usage_diff_final=load_front_usage_diff_final,
                load_rear_prop_diff_final=load_rear_prop_diff_final,
                load_front_rear_balance_final=load_front_rear_balance_final,
                load_front_prop_diff_final=load_front_prop_diff_final,
                validity_gate_alpha=env._crr_validity_gate_alpha,
                validity_gate_initial=validity_gate_initial,
                validity_gate_final=validity_gate_final,
                propulsion_floor_alpha=env._crr_propulsion_floor_alpha,
                band_alpha=env._crr_band_alpha,
                band_contact_initial=band_contact_initial,
                band_contact_final=band_contact_final,
                band_propulsion_initial=band_propulsion_initial,
                band_propulsion_final=band_propulsion_final,
                coop_alpha=env._crr_coop_alpha,
                coop_usage_initial=coop_usage_initial,
                coop_usage_final=coop_usage_final,
                coop_reward_initial=coop_reward_initial,
                coop_reward_final=coop_reward_final,
            )
        # V28.1: residency relay + symmetry + exit + min-leg factor 초기 적용
        _curriculum_apply_v281_weights(
            env,
            residency_early_alpha=env._crr_residency_early_alpha,
            residency_late_alpha=env._crr_residency_late_alpha,
            contact_residency_early_max=contact_residency_early_max,
            contact_residency_late_max=contact_residency_late_max,
            prop_residency_early_max=prop_residency_early_max,
            prop_residency_late_max=prop_residency_late_max,
            usage_residency_early_max=usage_residency_early_max,
            usage_residency_late_max=usage_residency_late_max,
            rear_symmetry_alpha=env._crr_rear_symmetry_alpha,
            rear_symmetry_max=rear_symmetry_max,
            exit_penalty_alpha=env._crr_exit_penalty_alpha,
            exit_penalty_max=exit_penalty_max,
            coop_min_leg_alpha=env._crr_coop_min_leg_alpha,
            coop_min_leg_factor_target=coop_min_leg_factor_target,
            rear_contact_diff_alpha=env._crr_rear_contact_diff_alpha,
            rear_contact_diff_max=rear_contact_diff_max,
            stride_length_alpha=env._crr_stride_length_alpha,
            stride_length_max=stride_length_max,
            swing_gate_alpha=env._crr_swing_gate_alpha,
            swing_gate_max=swing_gate_max,
            front_swing_alpha=env._crr_front_swing_alpha,
            front_swing_bonus_max=front_swing_bonus_max,
            front_alternation_max=front_alternation_max,
            front_both_ground_max=front_both_ground_max,
            min_swing_ratio_max=min_swing_ratio_max,
            front_joint_velocity_max=front_joint_velocity_max,
            front_joint_frozen_max=front_joint_frozen_max,
        )
        phase_str = _curriculum_phase_str(env._crr_alpha12, env._crr_alpha23)
        print(f"\n{'=' * 60}")
        print(f"[Curriculum] INIT @ iter {iteration} | {phase_str}")
        print(f"  alpha12={env._crr_alpha12:.3f}, alpha23={env._crr_alpha23:.3f}, validity_alpha={env._crr_validity_alpha:.3f}")
        print(f"  floor_alpha={env._crr_floor_alpha:.3f}, prop_floor_alpha={env._crr_propulsion_floor_alpha:.3f}, load_alpha={env._crr_load_alpha:.3f}")
        print(f"  validity_gate_alpha={env._crr_validity_gate_alpha:.3f} (weight {validity_gate_initial:.1f}→{validity_gate_final:.1f})")
        print(f"  band_alpha={env._crr_band_alpha:.3f}, coop_alpha={env._crr_coop_alpha:.3f} (V28 Layer C)")
        print(f"  ramp1=[{ramp1_start}~{ramp1_end}], ramp2=[{ramp2_start}~{ramp2_end}]")
        print(f"  floor_ramp=[{floor_ramp_start}~{floor_ramp_end}], prop_floor_ramp=[{_prop_ramp_start}~{_prop_ramp_end}], load_ramp=[{load_ramp_start}~{load_ramp_end}]")
        print(f"  validity_gate_ramp=[{validity_gate_ramp_start}~{validity_gate_ramp_end}]")
        print(f"  band_ramp=[{band_ramp_start}~{band_ramp_end}], coop_ramp=[{coop_ramp_start}~{coop_ramp_end}] (V28)")
        print(f"  residency_relay=[{residency_relay_up_start}→{residency_relay_up_end}→{residency_relay_down_end}] (V28.1)")
        print(f"  rear_sym_ramp=[{rear_symmetry_ramp_start}~{rear_symmetry_ramp_end}], exit_ramp=[{exit_penalty_ramp_start}~{exit_penalty_ramp_end}] (V28.1)")
        print(f"  coop_min_leg_ramp=[{coop_min_leg_ramp_start}~{coop_min_leg_ramp_end}] target={coop_min_leg_factor_target:.2f} (V28.1)")
        print(f"  rear_contact_diff_ramp=[{rear_contact_diff_ramp_start}~{rear_contact_diff_ramp_end}] max={rear_contact_diff_max:.1f} (V28.2)")
        print(f"  stride_length_ramp=[{stride_length_ramp_start}~{stride_length_ramp_end}] max={stride_length_max:.1f} (V29)")
        print(f"  swing_gate_ramp=[{swing_gate_ramp_start}~{swing_gate_ramp_end}] max={swing_gate_max:.1f} (V29)")
        print(f"  front_swing_ramp=[{front_swing_ramp_start}~{front_swing_ramp_end}] bonus={front_swing_bonus_max:.1f} alt={front_alternation_max:.1f} both={front_both_ground_max:.1f} min_swing={min_swing_ratio_max:.1f} jv={front_joint_velocity_max:.1f} jf={front_joint_frozen_max:.1f} (V31.2)")
        print(f"  gait_gate={'ON' if gait_gate_enabled else 'OFF'} (min_ep_len={gait_gate_min_ep_len})")
        print(f"{'=' * 60}")
        # INIT 시점 key weight 로깅
        weight_parts = []
        for name in _LOG_WEIGHT_TERMS:
            try:
                cfg = env.reward_manager.get_term_cfg(name)
                weight_parts.append(f"{name}={cfg.weight:.4f}")
            except Exception:
                pass
        if weight_parts:
            print(f"  init weights: {', '.join(weight_parts)}")
        if v55_track:
            _apply_v55_runtime_overrides(
                env,
                action_rate_weight=v55_action_rate_weight,
                joint_vel_weight=v55_joint_vel_weight,
                dof_acc_weight=v55_dof_acc_weight,
                forward_velocity_weight=v55_forward_velocity_weight,
                forward_velocity_bootstrap_weight=v55_forward_velocity_bootstrap_weight,
                standing_height_weight=v55_standing_height_weight,
                height_bonus_weight=v55_height_bonus_weight,
                trot_gait_weight=v55_trot_gait_weight,
                diagonal_coupling_weight=v55_diagonal_coupling_weight,
                stance_propulsion_weight=v55_stance_propulsion_weight,
            )
            if v55_release_soft_ramp_iters > 0:
                _apply_v55_release_soft_ramp(
                    env,
                    iteration=iteration,
                    ramp_iters=v55_release_soft_ramp_iters,
                    shoulder_pre=v55_release_shoulder_neutral_pre,
                    shoulder_post=v55_release_shoulder_neutral_post,
                    stance_pre=v55_release_stance_width_pre,
                    stance_post=v55_release_stance_width_post,
                    rear_prop_diff_pre=v55_release_rear_prop_diff_pre,
                    rear_prop_diff_post=v55_release_rear_prop_diff_post,
                    front_prop_diff_pre=v55_release_front_prop_diff_pre,
                    front_prop_diff_post=v55_release_front_prop_diff_post,
                    rear_usage_diff_pre=v55_release_rear_usage_diff_pre,
                    rear_usage_diff_post=v55_release_rear_usage_diff_post,
                    front_usage_diff_pre=v55_release_front_usage_diff_pre,
                    front_usage_diff_post=v55_release_front_usage_diff_post,
                    per_leg_contact_floor_pre=v55_release_per_leg_contact_floor_pre,
                    per_leg_contact_floor_post=v55_release_per_leg_contact_floor_post,
                )
            if v55_release_forward_ramp_iters > 0:
                _apply_v55_release_forward_ramp(
                    env,
                    iteration=iteration,
                    ramp_iters=v55_release_forward_ramp_iters,
                    forward_pre=v55_release_forward_velocity_pre,
                    forward_post=v55_release_forward_velocity_post,
                    forward_bootstrap_pre=v55_release_forward_velocity_bootstrap_pre,
                    forward_bootstrap_post=v55_release_forward_velocity_bootstrap_post,
                )
            _log_v55_release_debug(env, iteration)
        if v55_track:
            _log_v55_audit_snapshot(env, iteration, v55_track)
        return None

    # ── V35.5: Boot stability ramp ──
    if boot_ramp_end > 0:
        # undesired_contacts weight: boot_floor → -100.0 over iter 0~boot_ramp_end
        boot_alpha = min(1.0, max(0.0, iteration / boot_ramp_end))
        boot_uc_weight = boot_undesired_contacts_floor + (-100.0 - boot_undesired_contacts_floor) * boot_alpha
        try:
            uc_cfg = env.reward_manager.get_term_cfg("undesired_contacts")
            uc_cfg.weight = boot_uc_weight
        except Exception:
            pass

        # velocity command ramp: boot_vel → original over iter 0~boot_vel_restore_iter
        vel_alpha = min(1.0, max(0.0, iteration / boot_vel_restore_iter)) if boot_vel_restore_iter > 0 else 1.0
        orig_vel_min, orig_vel_max = 0.1, 0.5
        cur_vel_min = boot_vel_x_min + (orig_vel_min - boot_vel_x_min) * vel_alpha
        cur_vel_max = boot_vel_x_max + (orig_vel_max - boot_vel_x_max) * vel_alpha
        try:
            env.command_manager.get_term("base_velocity").cfg.ranges.lin_vel_x = (cur_vel_min, cur_vel_max)
        except Exception:
            pass

    if v55_track and iteration in (100, 500):
        _log_v55_audit_snapshot(env, iteration, v55_track)

        # Log boot ramp state periodically
        if iteration % log_interval == 0:
            print(f"[Boot] iter {iteration}: uc_weight={boot_uc_weight:.1f}, vel_x=({cur_vel_min:.3f}, {cur_vel_max:.3f})")

    # ── V37: Anti-splay curriculum ramp ──
    if splay_ramp_start > 0 and splay_ramp_end > splay_ramp_start:
        if iteration >= splay_ramp_start:
            splay_alpha = min(1.0, max(0.0, (iteration - splay_ramp_start) / (splay_ramp_end - splay_ramp_start)))
            # shoulder_neutral weight ramp
            cur_shoulder = splay_shoulder_initial + (splay_shoulder_final - splay_shoulder_initial) * splay_alpha
            try:
                sn_cfg = env.reward_manager.get_term_cfg("shoulder_neutral")
                sn_cfg.weight = cur_shoulder
            except Exception:
                pass
            # stance_width_penalty weight ramp
            cur_stance = splay_stance_initial + (splay_stance_final - splay_stance_initial) * splay_alpha
            try:
                sw_cfg = env.reward_manager.get_term_cfg("stance_width_penalty")
                sw_cfg.weight = cur_stance
            except Exception:
                pass
            # height target ramp
            cur_height = splay_height_initial + (splay_height_final - splay_height_initial) * splay_alpha
            try:
                bh_cfg = env.reward_manager.get_term_cfg("base_height_l2")
                bh_cfg.params["target_height"] = cur_height
                sh_cfg = env.reward_manager.get_term_cfg("standing_height")
                sh_cfg.params["target_height"] = cur_height
            except Exception:
                pass
            # Log
            if iteration % log_interval == 0:
                print(f"[Splay] iter {iteration}: shoulder={cur_shoulder:.1f}, stance={cur_stance:.1f}, height={cur_height:.3f} (alpha={splay_alpha:.2f})")

    # ── V38.2: Soft CaT ramp (threshold/margin 고정, probability만 ramp) ──
    if cat_ramp_start > 0 and cat_ramp_end > cat_ramp_start:
        if iteration < cat_ramp_start:
            # Boot phase: Soft CaT disabled (probability=0)
            try:
                cat_cfg = env.termination_manager.get_term_cfg("shoulder_splay")
                cat_cfg.params["threshold"] = cat_threshold
                cat_cfg.params["margin"] = cat_margin
                cat_cfg.params["probability"] = 0.0
                env.termination_manager.set_term_cfg("shoulder_splay", cat_cfg)
            except Exception:
                pass
        elif iteration <= cat_ramp_end:
            cat_alpha = min(1.0, max(0.0, (iteration - cat_ramp_start) / (cat_ramp_end - cat_ramp_start)))
            cur_prob = cat_probability_final * cat_alpha
            try:
                cat_cfg = env.termination_manager.get_term_cfg("shoulder_splay")
                cat_cfg.params["threshold"] = cat_threshold
                cat_cfg.params["margin"] = cat_margin
                cat_cfg.params["probability"] = cur_prob
                env.termination_manager.set_term_cfg("shoulder_splay", cat_cfg)
            except Exception:
                pass
            if iteration % log_interval == 0:
                print(f"[CaT] iter {iteration}: th={cat_threshold:.2f} m={cat_margin:.2f} prob={cur_prob:.4f} (a={cat_alpha:.2f})")

    # ── 업데이트 주기 확인 ──
    if iteration - env._crr_last_update < update_interval:
        return None
    env._crr_last_update = iteration

    # ── Target alpha (iteration 기반 목표) ──
    target_12 = _curriculum_target_alpha(iteration, ramp1_start, ramp1_end)
    target_23 = _curriculum_target_alpha(iteration, ramp2_start, ramp2_end)
    target_validity = _curriculum_target_alpha(iteration, validity_ramp_start, validity_ramp_end)
    target_floor = _curriculum_target_alpha(iteration, floor_ramp_start, floor_ramp_end)
    target_load = _curriculum_target_alpha(iteration, load_ramp_start, load_ramp_end)
    target_validity_gate = _curriculum_target_alpha(iteration, validity_gate_ramp_start, validity_gate_ramp_end)
    # V27.1b: propulsion floor 전용 target
    _prop_ramp_start_u = propulsion_floor_ramp_start if propulsion_floor_ramp_start >= 0 else floor_ramp_start
    _prop_ramp_end_u = propulsion_floor_ramp_end if propulsion_floor_ramp_end >= 0 else floor_ramp_end
    target_prop_floor = _curriculum_target_alpha(iteration, _prop_ramp_start_u, _prop_ramp_end_u)
    # V28: Layer C targets
    target_band = _curriculum_target_alpha(iteration, band_ramp_start, band_ramp_end)
    target_coop = _curriculum_target_alpha(iteration, coop_ramp_start, coop_ramp_end)
    # V28.1: residency relay + symmetry + exit + min-leg targets
    target_residency_early = _curriculum_alpha_relay_early(
        iteration, residency_relay_up_start, residency_relay_up_end, residency_relay_down_end
    )
    target_residency_late = _curriculum_target_alpha(
        iteration, residency_relay_up_end, residency_relay_down_end
    )
    target_rear_symmetry = _curriculum_target_alpha(iteration, rear_symmetry_ramp_start, rear_symmetry_ramp_end)
    target_exit_penalty = _curriculum_target_alpha(iteration, exit_penalty_ramp_start, exit_penalty_ramp_end)
    target_coop_min_leg = _curriculum_target_alpha(iteration, coop_min_leg_ramp_start, coop_min_leg_ramp_end)
    target_rear_contact_diff = _curriculum_target_alpha(iteration, rear_contact_diff_ramp_start, rear_contact_diff_ramp_end)
    target_stride_length = _curriculum_target_alpha(iteration, stride_length_ramp_start, stride_length_ramp_end)
    target_swing_gate = _curriculum_target_alpha(iteration, swing_gate_ramp_start, swing_gate_ramp_end)
    target_front_swing = _curriculum_target_alpha(iteration, front_swing_ramp_start, front_swing_ramp_end)

    # 이미 target에 도달 → alpha ramp 스킵 (boot/bridge ramp-down은 계속 실행)
    _all_alphas_done = (
        abs(env._crr_alpha12 - target_12) < 1e-6
        and abs(env._crr_alpha23 - target_23) < 1e-6
        and abs(env._crr_validity_alpha - target_validity) < 1e-6
        and abs(env._crr_floor_alpha - target_floor) < 1e-6
        and abs(env._crr_load_alpha - target_load) < 1e-6
        and abs(env._crr_validity_gate_alpha - target_validity_gate) < 1e-6
        and abs(env._crr_propulsion_floor_alpha - target_prop_floor) < 1e-6
        and abs(env._crr_band_alpha - target_band) < 1e-6
        and abs(env._crr_coop_alpha - target_coop) < 1e-6
        and abs(env._crr_residency_early_alpha - target_residency_early) < 1e-6
        and abs(env._crr_residency_late_alpha - target_residency_late) < 1e-6
        and abs(env._crr_rear_symmetry_alpha - target_rear_symmetry) < 1e-6
        and abs(env._crr_exit_penalty_alpha - target_exit_penalty) < 1e-6
        and abs(env._crr_coop_min_leg_alpha - target_coop_min_leg) < 1e-6
        and abs(env._crr_rear_contact_diff_alpha - target_rear_contact_diff) < 1e-6
        and abs(env._crr_stride_length_alpha - target_stride_length) < 1e-6
        and abs(env._crr_swing_gate_alpha - target_swing_gate) < 1e-6
        and abs(env._crr_front_swing_alpha - target_front_swing) < 1e-6
    )
    # Note: return None 제거 — gait_gate/boot ramp-down은 alpha 완료 후에도 실행 필요

    # ── Metric gating: 보행 구조 보호 ──
    gait_paused = False
    if gait_gate_enabled:
        mean_ep_len = env.episode_length_buf.float().mean().item()
        if mean_ep_len < gait_gate_min_ep_len:
            gait_paused = True
            if not env._crr_gate_paused:
                env._crr_gate_paused = True
                print(f"[Curriculum] [PAUSED] Ramp PAUSED @ iter {iteration} "
                      f"(ep_len={mean_ep_len:.1f} < {gait_gate_min_ep_len})")
        elif env._crr_gate_paused:
            env._crr_gate_paused = False
            print(f"[Curriculum] ▶ Ramp RESUMED @ iter {iteration} "
                  f"(ep_len={mean_ep_len:.1f})")

    # ── V47: Boot reward ramp-down (gait_gate 연동) ──
    if boot_standing_initial > 0 or boot_contact_initial > 0:
        if not hasattr(env, '_v47_boot_gate_released_iter'):
            env._v47_boot_gate_released_iter = -1  # gait_gate 해제 시점 기록

        # V54.2: ep_len 기반 해제 OR iteration 500 fallback
        # episode_length_buf.mean은 mid-episode 평균이라 200에 못 미칠 수 있음
        iter_fallback = (iteration >= 500)
        if (gait_gate_enabled and not gait_paused and env._v47_boot_gate_released_iter < 0) or \
           (iter_fallback and env._v47_boot_gate_released_iter < 0):
            env._v47_boot_gate_released_iter = iteration
            reason = "iter_fallback" if (gait_paused and iter_fallback) else "ep_len_gate"
            print(f"[V47-Boot] iter {iteration}: gait_gate released ({reason}), boot ramp-down starts")

        if env._v47_boot_gate_released_iter > 0:
            elapsed = iteration - env._v47_boot_gate_released_iter
            down_alpha = min(1.0, elapsed / max(boot_ramp_down_iters, 1))
            # V50.2: initial → floor (floor=0이면 기존과 동일)
            boot_st_w = boot_standing_initial + (boot_standing_floor - boot_standing_initial) * down_alpha
            boot_ct_w = boot_contact_initial * (1.0 - down_alpha)
        else:
            boot_st_w = boot_standing_initial
            boot_ct_w = boot_contact_initial

        try:
            if boot_standing_initial > 0:
                bst_cfg = env.reward_manager.get_term_cfg("boot_standing")
                bst_cfg.weight = boot_st_w
                env.reward_manager.set_term_cfg("boot_standing", bst_cfg)
        except Exception:
            pass
        try:
            if boot_contact_initial > 0:
                bct_cfg = env.reward_manager.get_term_cfg("boot_contact")
                bct_cfg.weight = boot_ct_w
                env.reward_manager.set_term_cfg("boot_contact", bct_cfg)
        except Exception:
            pass

        # V54.2: boot-only bridge ramp-down (leg_lift, rear_joint_velocity)
        if boot_leg_lift_initial > 0 or boot_rear_vel_initial > 0:
            if env._v47_boot_gate_released_iter > 0:
                bridge_elapsed = iteration - env._v47_boot_gate_released_iter
                bridge_alpha = min(1.0, bridge_elapsed / max(boot_bridge_ramp_down_iters, 1))
                bridge_ll_w = boot_leg_lift_initial * (1.0 - bridge_alpha)
                bridge_rv_w = boot_rear_vel_initial * (1.0 - bridge_alpha)
            else:
                bridge_ll_w = boot_leg_lift_initial
                bridge_rv_w = boot_rear_vel_initial
            try:
                if boot_leg_lift_initial > 0:
                    ll_cfg = env.reward_manager.get_term_cfg("leg_lift")
                    ll_cfg.weight = bridge_ll_w
                    env.reward_manager.set_term_cfg("leg_lift", ll_cfg)
            except Exception:
                pass
            try:
                if boot_rear_vel_initial > 0:
                    rv_cfg = env.reward_manager.get_term_cfg("rear_joint_velocity")
                    rv_cfg.weight = bridge_rv_w
                    env.reward_manager.set_term_cfg("rear_joint_velocity", rv_cfg)
            except Exception:
                pass

        # V54.3: phase ramp-in (bridge와 동일 구간, 반대 방향)
        if phase_contact_target > 0 or phase_clearance_target > 0:
            if env._v47_boot_gate_released_iter > 0:
                phase_elapsed = iteration - env._v47_boot_gate_released_iter
                phase_alpha = min(1.0, phase_elapsed / max(phase_ramp_in_iters, 1))
                phase_c_w = phase_contact_target * phase_alpha
                phase_cl_w = phase_clearance_target * phase_alpha
            else:
                phase_c_w = 0.0
                phase_cl_w = 0.0
            try:
                pc_cfg = env.reward_manager.get_term_cfg("phase_contact")
                pc_cfg.weight = phase_c_w
                env.reward_manager.set_term_cfg("phase_contact", pc_cfg)
            except Exception:
                pass
            try:
                pcl_cfg = env.reward_manager.get_term_cfg("phase_clearance")
                pcl_cfg.weight = phase_cl_w
                env.reward_manager.set_term_cfg("phase_clearance", pcl_cfg)
            except Exception:
                pass

        if iteration % log_interval == 0:
            bridge_info = ""
            if boot_leg_lift_initial > 0:
                bridge_info = f" leg_lift={bridge_ll_w:.1f} rear_vel={bridge_rv_w:.1f}"
            phase_info = ""
            if phase_contact_target > 0:
                phase_info = f" phase_c={phase_c_w:.1f} phase_cl={phase_cl_w:.1f}"
            print(f"  [V47-Boot] boot_standing={boot_st_w:.1f} boot_contact={boot_ct_w:.1f}{bridge_info}{phase_info}")

    def _apply_v55_post_curriculum_overrides() -> None:
        if not v55_track:
            return
        _apply_v55_runtime_overrides(
            env,
            action_rate_weight=v55_action_rate_weight,
            joint_vel_weight=v55_joint_vel_weight,
            dof_acc_weight=v55_dof_acc_weight,
            forward_velocity_weight=v55_forward_velocity_weight,
            forward_velocity_bootstrap_weight=v55_forward_velocity_bootstrap_weight,
            standing_height_weight=v55_standing_height_weight,
            height_bonus_weight=v55_height_bonus_weight,
            trot_gait_weight=v55_trot_gait_weight,
            diagonal_coupling_weight=v55_diagonal_coupling_weight,
            stance_propulsion_weight=v55_stance_propulsion_weight,
        )
        if v55_release_soft_ramp_iters > 0:
            _apply_v55_release_soft_ramp(
                env,
                iteration=iteration,
                ramp_iters=v55_release_soft_ramp_iters,
                shoulder_pre=v55_release_shoulder_neutral_pre,
                shoulder_post=v55_release_shoulder_neutral_post,
                stance_pre=v55_release_stance_width_pre,
                stance_post=v55_release_stance_width_post,
                rear_prop_diff_pre=v55_release_rear_prop_diff_pre,
                rear_prop_diff_post=v55_release_rear_prop_diff_post,
                front_prop_diff_pre=v55_release_front_prop_diff_pre,
                front_prop_diff_post=v55_release_front_prop_diff_post,
                rear_usage_diff_pre=v55_release_rear_usage_diff_pre,
                rear_usage_diff_post=v55_release_rear_usage_diff_post,
                front_usage_diff_pre=v55_release_front_usage_diff_pre,
                front_usage_diff_post=v55_release_front_usage_diff_post,
                per_leg_contact_floor_pre=v55_release_per_leg_contact_floor_pre,
                per_leg_contact_floor_post=v55_release_per_leg_contact_floor_post,
            )
        if v55_release_forward_ramp_iters > 0:
            _apply_v55_release_forward_ramp(
                env,
                iteration=iteration,
                ramp_iters=v55_release_forward_ramp_iters,
                forward_pre=v55_release_forward_velocity_pre,
                forward_post=v55_release_forward_velocity_post,
                forward_bootstrap_pre=v55_release_forward_velocity_bootstrap_pre,
                forward_bootstrap_post=v55_release_forward_velocity_bootstrap_post,
            )
        _log_v55_release_debug(env, iteration)

    # ── Alpha 진행 (한 주기당 최대 증가량 제한) ──
    if _all_alphas_done:
        _apply_v55_post_curriculum_overrides()
        return None  # alpha ramp 완료 — boot/bridge ramp-down은 위에서 처리됨

    max_step_12 = update_interval / max(1, ramp1_end - ramp1_start)
    max_step_23 = update_interval / max(1, ramp2_end - ramp2_start)
    max_step_validity = update_interval / max(1, validity_ramp_end - validity_ramp_start)
    max_step_floor = update_interval / max(1, floor_ramp_end - floor_ramp_start)
    max_step_load = update_interval / max(1, load_ramp_end - load_ramp_start)
    max_step_vgate = update_interval / max(1, validity_gate_ramp_end - validity_gate_ramp_start)
    max_step_prop_floor = update_interval / max(1, _prop_ramp_end_u - _prop_ramp_start_u)
    max_step_band = update_interval / max(1, band_ramp_end - band_ramp_start)
    max_step_coop = update_interval / max(1, coop_ramp_end - coop_ramp_start)
    # V28.1: relay 는 triangle 이므로 증가/감소 모두 허용 — target으로 직접 설정
    max_step_rear_sym = update_interval / max(1, rear_symmetry_ramp_end - rear_symmetry_ramp_start)
    max_step_exit = update_interval / max(1, exit_penalty_ramp_end - exit_penalty_ramp_start)
    max_step_coop_min_leg = update_interval / max(1, coop_min_leg_ramp_end - coop_min_leg_ramp_start)
    max_step_rear_contact_diff = update_interval / max(1, rear_contact_diff_ramp_end - rear_contact_diff_ramp_start)
    max_step_stride_length = update_interval / max(1, stride_length_ramp_end - stride_length_ramp_start)
    max_step_swing_gate = update_interval / max(1, swing_gate_ramp_end - swing_gate_ramp_start)
    max_step_front_swing = update_interval / max(1, front_swing_ramp_end - front_swing_ramp_start)

    new_12 = env._crr_alpha12 if gait_paused else min(target_12, env._crr_alpha12 + max_step_12)
    new_23 = env._crr_alpha23 if gait_paused else min(target_23, env._crr_alpha23 + max_step_23)
    new_validity = min(target_validity, env._crr_validity_alpha + max_step_validity)
    # floor/load/validity_gate ramps are NOT paused by gait gate (existence floor must always progress)
    new_floor = min(target_floor, env._crr_floor_alpha + max_step_floor)
    new_load = min(target_load, env._crr_load_alpha + max_step_load)
    new_validity_gate = min(target_validity_gate, env._crr_validity_gate_alpha + max_step_vgate)
    new_prop_floor = min(target_prop_floor, env._crr_propulsion_floor_alpha + max_step_prop_floor)
    # V28: Layer C ramps (NOT paused by gait gate)
    new_band = min(target_band, env._crr_band_alpha + max_step_band)
    new_coop = min(target_coop, env._crr_coop_alpha + max_step_coop)
    # V28.1: residency relay — triangle이므로 target으로 직접 수렴 (단순 할당)
    new_residency_early = target_residency_early
    new_residency_late = target_residency_late
    new_rear_symmetry = min(target_rear_symmetry, env._crr_rear_symmetry_alpha + max_step_rear_sym)
    new_exit_penalty = min(target_exit_penalty, env._crr_exit_penalty_alpha + max_step_exit)
    new_coop_min_leg = min(target_coop_min_leg, env._crr_coop_min_leg_alpha + max_step_coop_min_leg)
    new_rear_contact_diff = min(target_rear_contact_diff, env._crr_rear_contact_diff_alpha + max_step_rear_contact_diff)
    new_stride_length = min(target_stride_length, env._crr_stride_length_alpha + max_step_stride_length)
    new_swing_gate = min(target_swing_gate, env._crr_swing_gate_alpha + max_step_swing_gate)
    new_front_swing = min(target_front_swing, env._crr_front_swing_alpha + max_step_front_swing)

    # 실제 변화 없으면 스킵
    if (
        abs(new_12 - env._crr_alpha12) < 1e-6
        and abs(new_23 - env._crr_alpha23) < 1e-6
        and abs(new_validity - env._crr_validity_alpha) < 1e-6
        and abs(new_floor - env._crr_floor_alpha) < 1e-6
        and abs(new_load - env._crr_load_alpha) < 1e-6
        and abs(new_validity_gate - env._crr_validity_gate_alpha) < 1e-6
        and abs(new_prop_floor - env._crr_propulsion_floor_alpha) < 1e-6
        and abs(new_band - env._crr_band_alpha) < 1e-6
        and abs(new_coop - env._crr_coop_alpha) < 1e-6
        and abs(new_residency_early - env._crr_residency_early_alpha) < 1e-6
        and abs(new_residency_late - env._crr_residency_late_alpha) < 1e-6
        and abs(new_rear_symmetry - env._crr_rear_symmetry_alpha) < 1e-6
        and abs(new_exit_penalty - env._crr_exit_penalty_alpha) < 1e-6
        and abs(new_coop_min_leg - env._crr_coop_min_leg_alpha) < 1e-6
        and abs(new_rear_contact_diff - env._crr_rear_contact_diff_alpha) < 1e-6
        and abs(new_stride_length - env._crr_stride_length_alpha) < 1e-6
        and abs(new_swing_gate - env._crr_swing_gate_alpha) < 1e-6
        and abs(new_front_swing - env._crr_front_swing_alpha) < 1e-6
    ):
        _apply_v55_post_curriculum_overrides()
        return None

    old_12 = env._crr_alpha12
    old_23 = env._crr_alpha23
    old_validity = env._crr_validity_alpha
    env._crr_alpha12 = new_12
    env._crr_alpha23 = new_23
    env._crr_validity_alpha = new_validity
    env._crr_floor_alpha = new_floor
    env._crr_load_alpha = new_load
    env._crr_validity_gate_alpha = new_validity_gate
    env._crr_propulsion_floor_alpha = new_prop_floor
    env._crr_band_alpha = new_band
    env._crr_coop_alpha = new_coop
    env._crr_residency_early_alpha = new_residency_early
    env._crr_residency_late_alpha = new_residency_late
    env._crr_rear_symmetry_alpha = new_rear_symmetry
    env._crr_exit_penalty_alpha = new_exit_penalty
    env._crr_coop_min_leg_alpha = new_coop_min_leg
    env._crr_rear_contact_diff_alpha = new_rear_contact_diff
    env._crr_stride_length_alpha = new_stride_length
    env._crr_swing_gate_alpha = new_swing_gate
    env._crr_front_swing_alpha = new_front_swing

    # ── 가중치 적용 ──
    if phase_table_enabled:
        _curriculum_apply_weights(
            env,
            new_12,
            new_23,
            new_validity,
            validity_limb_usage_initial,
            validity_limb_usage_final,
            validity_rear_diff_initial,
            validity_rear_diff_final,
            floor_alpha=new_floor,
            load_alpha=new_load,
            floor_limb_usage_initial=floor_limb_usage_initial,
            floor_limb_usage_final=floor_limb_usage_final,
            floor_per_leg_contact_initial=floor_per_leg_contact_initial,
            floor_per_leg_contact_final=floor_per_leg_contact_final,
            floor_per_leg_propulsion_initial=floor_per_leg_propulsion_initial,
            floor_per_leg_propulsion_final=floor_per_leg_propulsion_final,
            load_rear_usage_diff_final=load_rear_usage_diff_final,
            load_front_usage_diff_final=load_front_usage_diff_final,
            load_rear_prop_diff_final=load_rear_prop_diff_final,
            load_front_rear_balance_final=load_front_rear_balance_final,
            load_front_prop_diff_final=load_front_prop_diff_final,
            validity_gate_alpha=new_validity_gate,
            validity_gate_initial=validity_gate_initial,
            validity_gate_final=validity_gate_final,
            propulsion_floor_alpha=new_prop_floor,
            band_alpha=new_band,
            band_contact_initial=band_contact_initial,
            band_contact_final=band_contact_final,
            band_propulsion_initial=band_propulsion_initial,
            band_propulsion_final=band_propulsion_final,
            coop_alpha=new_coop,
            coop_usage_initial=coop_usage_initial,
            coop_usage_final=coop_usage_final,
            coop_reward_initial=coop_reward_initial,
            coop_reward_final=coop_reward_final,
        )
    # V28.1: residency relay + symmetry + exit + min-leg factor 적용
    _curriculum_apply_v281_weights(
        env,
        residency_early_alpha=new_residency_early,
        residency_late_alpha=new_residency_late,
        contact_residency_early_max=contact_residency_early_max,
        contact_residency_late_max=contact_residency_late_max,
        prop_residency_early_max=prop_residency_early_max,
        prop_residency_late_max=prop_residency_late_max,
        usage_residency_early_max=usage_residency_early_max,
        usage_residency_late_max=usage_residency_late_max,
        rear_symmetry_alpha=new_rear_symmetry,
        rear_symmetry_max=rear_symmetry_max,
        exit_penalty_alpha=new_exit_penalty,
        exit_penalty_max=exit_penalty_max,
        coop_min_leg_alpha=new_coop_min_leg,
        coop_min_leg_factor_target=coop_min_leg_factor_target,
        rear_contact_diff_alpha=new_rear_contact_diff,
        rear_contact_diff_max=rear_contact_diff_max,
        stride_length_alpha=new_stride_length,
        stride_length_max=stride_length_max,
        swing_gate_alpha=new_swing_gate,
        swing_gate_max=swing_gate_max,
        front_swing_alpha=new_front_swing,
        front_swing_bonus_max=front_swing_bonus_max,
        front_alternation_max=front_alternation_max,
        front_both_ground_max=front_both_ground_max,
        min_swing_ratio_max=min_swing_ratio_max,
        front_joint_velocity_max=front_joint_velocity_max,
        front_joint_frozen_max=front_joint_frozen_max,
    )

    _apply_v55_post_curriculum_overrides()

    # ── 주기적 로깅 (key weight + raw metric snapshot) ──
    if iteration % log_interval == 0:
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)

    # ── 마일스톤 로깅 (ramp 시작/완료 + snapshot) ──
    if abs(old_12) < 1e-6 and new_12 > 1e-6:
        print(f"\n[Curriculum] [>>] Ramp 1→2 START @ iter {iteration} (STAND→WALK)")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)
    if abs(new_12 - 1.0) < 1e-6 and abs(old_12 - 1.0) >= 1e-6:
        print(f"\n[Curriculum] [OK] Ramp 1→2 COMPLETE @ iter {iteration} (STAND→WALK)")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)
    if abs(old_23) < 1e-6 and new_23 > 1e-6:
        print(f"\n[Curriculum] [>>] Ramp 2→3 START @ iter {iteration} (WALK→TROT)")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)
    if abs(new_23 - 1.0) < 1e-6 and abs(old_23 - 1.0) >= 1e-6:
        print(f"\n[Curriculum] [OK] Ramp 2→3 COMPLETE @ iter {iteration} (WALK→TROT)")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)
    if abs(old_validity) < 1e-6 and new_validity > 1e-6:
        print(f"\n[Curriculum] [>>] Validity Ramp START @ iter {iteration}")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)
    if abs(new_validity - 1.0) < 1e-6 and abs(old_validity - 1.0) >= 1e-6:
        print(f"\n[Curriculum] [OK] Validity Ramp COMPLETE @ iter {iteration}")
        _curriculum_log_snapshot(env, iteration, new_12, new_23, new_validity, env._crr_gate_paused)

    return None


def _curriculum_phase_str(alpha12: float, alpha23: float) -> str:
    """현재 커리큘럼 상태를 문자열로 반환."""
    if alpha12 < 1e-6:
        return "Phase 1 (STAND)"
    if alpha12 < 1.0 - 1e-6:
        return f"Ramp 1→2 ({alpha12:.0%})"
    if alpha23 < 1e-6:
        return "Phase 2 (WALK)"
    if alpha23 < 1.0 - 1e-6:
        return f"Ramp 2→3 ({alpha23:.0%})"
    return "Phase 3 (TROT)"


# ═══════════════════════════════════════════════════════════════════
# Curriculum State Save / Restore
# ═══════════════════════════════════════════════════════════════════
# "state가 있으면 state 복원, 없으면 deterministic recompute"
#
# 저장: 체크포인트마다 curriculum alpha + reward weight snapshot
# 복원: snapshot 우선, 없으면 iteration 기반 재계산 (기존 로직)
# 검증: 첫 rollout 전 weight trace 로그 출력
# ═══════════════════════════════════════════════════════════════════

# reward_weight_curriculum의 env 속성 목록
_CRR_ALPHA_KEYS = [
    "_crr_alpha12", "_crr_alpha23", "_crr_validity_alpha",
    "_crr_floor_alpha", "_crr_load_alpha", "_crr_validity_gate_alpha",
    "_crr_propulsion_floor_alpha", "_crr_band_alpha", "_crr_coop_alpha",
    "_crr_residency_early_alpha", "_crr_residency_late_alpha",
    "_crr_rear_symmetry_alpha", "_crr_exit_penalty_alpha",
    "_crr_coop_min_leg_alpha", "_crr_rear_contact_diff_alpha",
    "_crr_stride_length_alpha", "_crr_swing_gate_alpha",
    "_crr_front_swing_alpha",
]

_CRR_META_KEYS = [
    "_crr_last_update", "_crr_gate_paused",
]

# v42_boot_curriculum의 env 속성 (V44 adaptive safety)
_V44_STATE_KEYS = [
    "_v44_shoulder_ema", "_v44_ep_len_ema", "_v44_pose_in_fallback",
]

# V47 boot ramp-down
_V47_STATE_KEYS = [
    "_v47_boot_gate_released_iter",
]

_PHASE_CONTACT_STATE_KEYS = [
    "_phase_contact_ema",
]

_ALL_CURRICULUM_KEYS = _CRR_ALPHA_KEYS + _CRR_META_KEYS + _V44_STATE_KEYS + _V47_STATE_KEYS + _PHASE_CONTACT_STATE_KEYS


def get_curriculum_snapshot(env) -> dict:
    """Collect all curriculum state from env for checkpoint saving.

    Returns dict with:
      - alphas: all _crr_* alpha values
      - meta: _crr_last_update, _crr_gate_paused
      - v44/v47: boot curriculum state (if exists)
      - reward_weights: {term_name: weight} for all active reward terms
      - iteration: current learning iteration (from common_step_counter)
    """
    state = {"_version": 1}

    # Curriculum alphas and meta
    for key in _ALL_CURRICULUM_KEYS:
        if hasattr(env, key):
            state[key] = getattr(env, key)

    # Current reward weights (the ground truth of what's applied)
    weights = {}
    try:
        for name in env.reward_manager._term_names:
            cfg = env.reward_manager.get_term_cfg(name)
            weights[name] = cfg.weight
    except Exception:
        pass
    state["_reward_weights"] = weights

    # Termination params (CaT etc.) — only scalar types to avoid stale SceneEntityCfg
    term_params = {}
    _SAFE_TYPES = (int, float, bool, str)
    try:
        for name in env.termination_manager._term_names:
            cfg = env.termination_manager.get_term_cfg(name)
            if cfg.params:
                scalars = {k: v for k, v in cfg.params.items() if isinstance(v, _SAFE_TYPES)}
                if scalars:
                    term_params[name] = scalars
    except Exception:
        pass
    state["_termination_params"] = term_params

    return state


def restore_curriculum_snapshot(env, state: dict) -> bool:
    """Restore curriculum state to env from saved snapshot.

    Returns True if snapshot was applied, False if empty/invalid.
    """
    if not state or "_version" not in state:
        return False

    restored_keys = []

    # Restore curriculum alphas and meta
    for key in _ALL_CURRICULUM_KEYS:
        if key in state:
            value = state[key]
            if key == "_phase_contact_ema":
                try:
                    if tuple(value.shape) != (env.num_envs, 4):
                        continue
                    value = value.to(device=env.device)
                except Exception:
                    continue
            setattr(env, key, value)
            restored_keys.append(key)

    # Restore reward weights / termination params
    # 버전이 변경된 resume에서는 env_cfg 설정이 우선해야 하므로 skip
    from spot_micro_rl.tasks.manager_based.spot_micro_rl.spot_micro_rl_env_cfg import TRAIN_VERSION
    saved_iteration = state.get("_iteration", -1)
    weights = state.get("_reward_weights", {})
    term_params = state.get("_termination_params", {})

    # 현재 env_cfg의 reward weight를 먼저 수집
    current_weights = {}
    try:
        for name in env.reward_manager._term_names:
            cfg = env.reward_manager.get_term_cfg(name)
            current_weights[name] = cfg.weight
    except Exception:
        pass

    # 저장된 weight와 현재 weight가 다르면 = 버전 변경 resume
    version_changed = False
    for name, w in weights.items():
        if name in current_weights and abs(current_weights[name] - w) > 1e-6:
            version_changed = True
            break
    # 현재 env_cfg에만 있는 새 reward가 있으면 = 버전 변경
    new_rewards = set(current_weights.keys()) - set(weights.keys())
    if new_rewards:
        version_changed = True

    if version_changed:
        weight_count = 0
        term_count = 0
        print(f"[Curriculum] Version change detected (new rewards: {new_rewards})")
        print(f"[Curriculum] Reward weight/termination restore SKIPPED (env_cfg {TRAIN_VERSION} priority)")
    else:
        weight_count = 0
        for name, w in weights.items():
            try:
                cfg = env.reward_manager.get_term_cfg(name)
                cfg.weight = w
                env.reward_manager.set_term_cfg(name, cfg)
                weight_count += 1
            except Exception:
                pass

        term_count = 0
        for name, params in term_params.items():
            try:
                cfg = env.termination_manager.get_term_cfg(name)
                for k, v in params.items():
                    cfg.params[k] = v
                env.termination_manager.set_term_cfg(name, cfg)
                term_count += 1
            except Exception:
                pass

    alpha_count = sum(1 for k in _CRR_ALPHA_KEYS if k in state)
    print(f"[Curriculum] Snapshot restored: {alpha_count} alphas, "
          f"{weight_count} reward weights, {term_count} termination terms")

    return True


def log_reward_weight_trace(env, label: str = "RESUME") -> dict:
    """Log current reward weights for verification.

    Returns the weight dict for comparison.
    """
    weights = {}
    try:
        for name in env.reward_manager._term_names:
            cfg = env.reward_manager.get_term_cfg(name)
            weights[name] = cfg.weight
    except Exception:
        pass

    # Alpha summary
    alpha_summary = {}
    for key in _CRR_ALPHA_KEYS:
        if hasattr(env, key):
            alpha_summary[key.replace("_crr_", "")] = getattr(env, key)

    print(f"\n{'='*60}")
    print(f"[Curriculum] Weight Trace @ {label}")
    print(f"{'='*60}")

    if alpha_summary:
        print(f"  Alphas:")
        for k, v in sorted(alpha_summary.items()):
            print(f"    {k}: {v:.4f}")

    if hasattr(env, "_crr_gate_paused"):
        print(f"  gate_paused: {env._crr_gate_paused}")

    nonzero = {k: v for k, v in sorted(weights.items()) if abs(v) > 1e-6}
    print(f"  Active reward weights ({len(nonzero)}/{len(weights)} nonzero):")
    for name, w in nonzero.items():
        print(f"    {name}: {w:.4f}")
    print(f"{'='*60}\n")

    return weights
