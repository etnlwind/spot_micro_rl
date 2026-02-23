# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Custom reward functions for SpotMicro locomotion."""

from __future__ import annotations

import torch
from typing import TYPE_CHECKING

from isaaclab.assets import Articulation
from isaaclab.managers import SceneEntityCfg
from isaaclab.sensors import ContactSensor
from isaaclab.utils.math import wrap_to_pi

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def joint_pos_target_l2(env: ManagerBasedRLEnv, target: float, asset_cfg: SceneEntityCfg) -> torch.Tensor:
    """Penalize joint position deviation from a target value."""
    # extract the used quantities (to enable type-hinting)
    asset: Articulation = env.scene[asset_cfg.name]
    # wrap the joint positions to (-pi, pi)
    joint_pos = wrap_to_pi(asset.data.joint_pos[:, asset_cfg.joint_ids])
    # compute the reward
    return torch.sum(torch.square(joint_pos - target), dim=1)


def standing_height_exp(
    env: ManagerBasedRLEnv,
    target_height: float,
    sigma: float = 0.05,
    start_time: float = 0.0,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    """Exponential reward that increases sharply as base approaches target height.

    COMBINED with orientation quality: reward *= orientation_factor.
    The robot must be BOTH at target height AND level to get full reward.
    This prevents the strategy of "lift front legs only + tilt".

    height_factor: exp(-(target - height)^2 / (2*sigma^2))
    orientation_factor: exp(-7.0 * sum(projected_gravity_xy^2))
      - perfectly level (gravity = [0,0,-1]): factor = 1.0
      - tilted 15deg: factor ~ 0.5
      - tilted 30deg: factor ~ 0.06

    Final reward = height_factor * orientation_factor

    If start_time > 0, the reward is zero during the first start_time seconds
    of each episode (rest phase).
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
    return result


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
) -> torch.Tensor:
    """어깨 관절이 0(중립)에서 벗어나면 페널티.

    어깨가 벌어지거나(+) 오므라지면(-) 모두 페널티.
    penalty = sum(shoulder_angle^2)
    Use with a negative weight.
    """
    asset = env.scene[shoulder_cfg.name]
    shoulder_angles = asset.data.joint_pos[:, shoulder_cfg.joint_ids]  # (num_envs, 4)
    return torch.sum(torch.square(shoulder_angles), dim=1)


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
    """높을수록 보상이 커지는 선형 높이 보상.

    min_height에서 0, max_height에서 1.0.
    orientation 보정: 수평일수록 보상 유지, 기울면 감소.
    Use with a positive weight.
    """
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
    """각 발이 개별적으로 바닥에 닿아있는 비율을 반환.

    4개 발 중 닿은 비율: 4개 다 닿으면 1.0, 3개면 0.75, 0개면 0.0.
    양수 weight와 함께 사용하면 모든 발이 바닥에 있을 때 보상.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0] > threshold
    )
    # 각 발의 접촉 비율 (0~1)
    return contacts.float().mean(dim=1)


def forward_velocity_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_vel: float = 0.3,
) -> torch.Tensor:
    """안정적 전진 보상. 수평 자세로 전진할 때만 보상.

    raw 속도를 target_vel로 정규화 (0~1 범위).
    orientation_quality를 곱해서 넘어지면서 전진해도 보상 = 0.
    → "돌진하고 넘어짐" 전략 방지.

    orientation_quality = exp(-7 * gravity_xy²)
      - 완전 수평: 1.0
      - 15도 기울임: ~0.5
      - 30도 기울임: ~0.06
    """
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
    """스윙(비접촉) 시 발이 일정 높이 이상 들려야 보상.

    전진 게이팅: 로봇이 앞으로 움직일 때만 보상 (제자리 발 들기 방지).
    vel_x < min_vel이면 보상 = 0.

    양수 weight와 함께 사용.
    """
    # 1) 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, num_feet), True = 접촉 중

    # 2) 발 높이 (지면 기준)
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, num_feet)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)  # (num_envs, 1)
    foot_height = foot_z - env_origins_z  # 지면 기준 높이

    # 3) 스윙 중인 발 (비접촉)에 대해 높이 보상
    swing_mask = ~contacts  # True = 스윙 중
    # 높이가 target_clearance 이상이면 보상 (정규화: 0~1 범위)
    clearance_reward = torch.clamp(foot_height / target_clearance, 0.0, 1.0)
    # 스윙 중인 발에만 보상 적용
    swing_reward = clearance_reward * swing_mask.float()

    # 4) 전체 발 평균 (보통 1~2개만 스윙)
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    base_reward = swing_reward.sum(dim=1) / num_swing

    # 5) 전진 게이팅: 앞으로 움직여야만 보상
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return base_reward * vel_gate


def stationary_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    threshold: float = 0.05,
) -> torch.Tensor:
    """로봇이 멈춰있을 때 페널티. 속도 < threshold이면 -1.0 반환.

    서있기 local minimum을 깨기 위한 직접적 페널티.
    XY 평면 속도 크기가 threshold 미만이면 -1.0, 이상이면 0.0.
    음수 weight와 함께 사용.
    """
    asset = env.scene[asset_cfg.name]
    vel_xy = asset.data.root_lin_vel_b[:, :2]
    vel_magnitude = torch.norm(vel_xy, dim=1)
    return torch.where(
        vel_magnitude < threshold,
        torch.ones_like(vel_magnitude),
        torch.zeros_like(vel_magnitude),
    )


def trot_gait_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """min-heavy 트로트 걸음걸이 보상 (V7).

    V6: 4개 구성요소를 균등하게(0.25씩) 덧셈 → 일부만 충족해도 0.5+ 가능 → 불완전 트롯 허용.
    V7: 0.4*mean + 0.6*min → 가장 약한 성분이 전체를 끌어내림.
      - 4개 모두 1.0 → 1.0
      - 3개 1.0, 1개 0.0 → 0.4*0.75 + 0.6*0.0 = 0.30 (V6: 0.75)
      - 2개 1.0, 2개 0.0 → 0.4*0.50 + 0.6*0.0 = 0.20 (V6: 0.50)
    → 모든 성분이 높아야 높은 보상 (부분 진행도는 여전히 보상하면서도 엄격)

    전진 게이팅: 로봇이 앞으로 움직일 때만 보상 (제자리 트롯 방지).

    구성요소 (각 0~1):
      1) 대각선 페어A 동기화: FL(0)과 RR(3)이 같은 상태 → 1
      2) 대각선 페어B 동기화: FR(1)과 RL(2)이 같은 상태 → 1
      3) 페어 간 반위상: 페어A ≠ 페어B → 1
      4) 같은쪽 비동기: FL≠FR, RL≠RR → 1 (벌레걸음 방지)

    body_names 순서: front_left, front_right, rear_left, rear_right
    반환: 0~1 (완벽한 트로트=1)
    양수 weight와 함께 사용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    # 각 발의 접촉 여부: (num_envs, 4) - FL(0), FR(1), RL(2), RR(3)
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()

    # 1) 대각선 페어 A 동기화: FL(0)과 RR(3)이 같은 상태면 1
    diag_a_sync = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 3])
    # 2) 대각선 페어 B 동기화: FR(1)과 RL(2)이 같은 상태면 1
    diag_b_sync = 1.0 - torch.abs(contacts[:, 1] - contacts[:, 2])

    # 3) 페어 간 반위상: A와 B가 반대 상태면 1
    pair_a_state = (contacts[:, 0] + contacts[:, 3]) / 2.0
    pair_b_state = (contacts[:, 1] + contacts[:, 2]) / 2.0
    anti_phase = torch.abs(pair_a_state - pair_b_state)

    # 4) 같은쪽 비동기: FL≠FR이고 RL≠RR이면 1 (벌레걸음 직접 방지)
    front_desync = torch.abs(contacts[:, 0] - contacts[:, 1])  # 다르면 1
    rear_desync = torch.abs(contacts[:, 2] - contacts[:, 3])   # 다르면 1
    side_desync = (front_desync + rear_desync) / 2.0

    # V7: min-heavy 결합 — 가장 약한 성분이 전체를 끌어내림
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
    """비-트로트 보행 패턴 페널티 (V9: max 기반, 개별 쌍 감지).

    V8: bounding = avg(front_same, rear_same) → 뒷다리만 동시 움직여도 0.5로 희석.
    V9: bounding = max(front_same, rear_same) → 한 쌍이라도 동기화되면 전체 페널티.
         pacing  = max(left_same, right_same)  → 마찬가지.

    트로트: FL+RR / FR+RL 대각선 쌍이 교대.
    바운딩: FL+FR 동시 (앞뒤 동기화) → front_same, rear_same 검사
    페이싱: FL+RL 동시 (좌우 동기화) → left_same, right_same 검사

    penalty = max(bounding, pacing)

    - 완벽한 트로트: 0.0 (페널티 없음)
    - 뒷다리만 동시: ~1.0 (V8: 0.5, V9: 1.0)
    - 페이싱 또는 바운딩: ~1.0 (최대 페널티)

    전진 게이팅: 서있을 때(4발 접지)는 페널티 없음, 보행 중에만.
    음수 weight와 함께 사용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4) - FL(0), FR(1), RL(2), RR(3)

    # --- 바운딩 감지: 앞다리끼리 / 뒷다리끼리 동기화 ---
    front_same = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 1])  # FL==FR → 1
    rear_same = 1.0 - torch.abs(contacts[:, 2] - contacts[:, 3])   # RL==RR → 1
    bounding = torch.max(front_same, rear_same)  # V9: avg→max (한 쌍이라도 동기화면 전체 페널티)

    # --- 페이싱 감지: 왼쪽끼리 / 오른쪽끼리 동기화 ---
    left_same = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 2])   # FL==RL → 1
    right_same = 1.0 - torch.abs(contacts[:, 1] - contacts[:, 3])  # FR==RR → 1
    pacing = torch.max(left_same, right_same)  # V9: avg→max

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
    """동시 접촉 발 수 보상: 항상 2개 발이 바닥에 있어야 보상.

    전진 게이팅: 로봇이 앞으로 움직일 때만 보상.

    4개 접촉(서있음) → 0점
    3개 접촉 → 0.5점
    2개 접촉(트로트) → 1.0점 (최대 보상)
    1개 접촉 → 0.5점
    0개 접촉(점프) → 0점

    양수 weight와 함께 사용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()

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

    강아지처럼 걸으려면 발을 들어서 앞으로 "뻗어" 내딛어야 함.
    벌레처럼 기는 걸음은 발이 거의 앞으로 이동하지 않음.

    원리:
    1. 스윙 중인 발(비접촉)의 로봇 기준 전방 속도를 측정
    2. 발이 앞으로 빠르게 이동할수록 높은 보상 (reach forward)
    3. 전진 게이팅: 로봇이 앞으로 움직여야만 보상

    양수 weight와 함께 사용.
    """
    # 1) 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, num_feet), True = 접촉

    # 2) 발의 월드 속도
    asset = env.scene[foot_cfg.name]
    foot_vel = asset.data.body_vel_w[:, foot_cfg.body_ids, :3]  # (num_envs, num_feet, 3)

    # 3) 로봇 전방 방향 (heading)
    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w  # (num_envs, 4)
    # heading vector (2D)
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)

    # 4) 발의 전방 속도 (heading 방향 성분)
    foot_forward_vel = (
        foot_vel[:, :, 0] * heading_x.unsqueeze(1) +
        foot_vel[:, :, 1] * heading_y.unsqueeze(1)
    )  # (num_envs, num_feet)

    # 5) 스윙 중인 발만, 전방으로 빠르게 이동하면 보상
    swing_mask = ~contacts  # True = 스윙
    forward_component = torch.clamp(foot_forward_vel, min=0.0)
    # 정규화: 0.5 m/s 이상이면 최대 보상
    normalized = torch.clamp(forward_component / 0.5, 0.0, 1.0)
    swing_reward = normalized * swing_mask.float()

    # 6) 평균
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    base_reward = swing_reward.sum(dim=1) / num_swing

    # 7) 전진 게이팅
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
    """뒷발 스윙 보너스: 뒷발이 들려야 직접 보상.

    문제: 로봇이 뒷발을 바닥에 고정하고 앞발만 움직이는 local minimum.
    해결: 뒷발(rear_left=2, rear_right=3)이 공중에 있고 높이 들렸을 때 직접 보상.

    body_names 순서: front_left(0), front_right(1), rear_left(2), rear_right(3)
    양수 weight와 함께 사용.
    """
    # 1) 접촉 감지 (4발 모두)
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, 4)

    # 2) 뒷발 높이
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, 4)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z

    # 3) 뒷발(인덱스 2,3)에 대해서만 스윙 보상
    rear_swing = ~contacts[:, 2:]  # (num_envs, 2), True = 뒷발 스윙 중
    rear_height = foot_height[:, 2:]  # (num_envs, 2)
    
    # 높이 보상: target_clearance 이상이면 1.0
    height_reward = torch.clamp(rear_height / target_clearance, 0.0, 1.0)
    # 스윙 중인 뒷발만
    rear_reward = (height_reward * rear_swing.float()).sum(dim=1)
    # 최소 1개 뒷발이 들려야 의미있는 보상 (0~1 정규화)
    rear_reward = rear_reward / 2.0  # 최대 2개 뒷발

    # 4) 전진 게이팅
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

    원리:
    1. 월드 프레임 Z 속도 (root_lin_vel_w[:, 2])로 높이 변화 감지
    2. Z 속도 > 0 = 오르막 등반 중
    3. 전진 게이팅: 앞으로 움직여야만 보상 (제자리 점프 방지)
    4. 수평 보정: 넘어지면서 높이 증가하는 경우 방지

    Args:
        env: The environment.
        asset_cfg: Robot asset configuration.
        min_vel: 최소 전진 속도 (이하면 보상 0).
        max_climb_rate: 최대 등반 속도 (m/s). 이 속도에서 보상 = 1.0.
            SpotMicro 크기 고려: 0.1 m/s 정도면 상당한 등반.

    반환: 0~1 (완벽한 오르막 등반 = 1)
    양수 weight와 함께 사용.
    """
    asset = env.scene[asset_cfg.name]

    # 1) 월드 프레임 Z 속도 (양수 = 위로 이동 = 오르막)
    vel_z = asset.data.root_lin_vel_w[:, 2]
    climb_rate = torch.clamp(vel_z, min=0.0)
    # 정규화: max_climb_rate에서 1.0
    normalized_climb = torch.clamp(climb_rate / max_climb_rate, 0.0, 1.0)

    # 2) 전진 게이팅: 앞으로 움직여야만 보상 (제자리 점프 방지)
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    # 3) 수평 보정: 넘어지면서 높이 올라가는 것 방지
    #    orientation_quality: 수평이면 1.0, 기울면 급감
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
    """스윙 중 leg 관절(hip) 각도 보상: 다리를 높이 들어올리도록 유도.

    SpotMicro의 leg 관절은 hip flexion/extension을 제어.
    중립(0도)에서는 다리가 수직으로 늘어져 있음.
    관절이 회전하면 leg_link가 수평에 가까워지며 발이 높이 들림.

    스윙 중(발이 지면에서 떨어진 상태)인 다리에 대해서만 보상.
    속도 게이팅 없음 — 제자리 트롯에서도 작동.

    sensor_cfg body_ids → foot contact (FL=0, FR=1, RL=2, RR=3)
    leg_joint_cfg joint_ids → leg joints (FL=0, FR=1, RL=2, RR=3)
    순서가 대응되어야 함.

    Args:
        env: The environment.
        sensor_cfg: Contact sensor config for foot links.
        leg_joint_cfg: Robot config with joint_ids for leg (hip) joints.
        target_angle: Target joint angle (radians) for full reward. ~0.6 rad ≈ 34°.
        contact_threshold: Force threshold for contact detection.

    반환: 0~1 (모든 스윙 다리가 target_angle만큼 회전 = 1)
    양수 weight와 함께 사용.
    """
    # 1) 접촉 감지 → 스윙 마스크
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, 4)
    swing_mask = ~contacts  # True = 스윙 중

    # 2) leg 관절 각도
    asset: Articulation = env.scene[leg_joint_cfg.name]
    leg_angles = asset.data.joint_pos[:, leg_joint_cfg.joint_ids]  # (num_envs, 4)

    # 3) 중립 대비 절대 각도가 클수록 보상 (전방/후방 모두)
    displacement = torch.abs(leg_angles)
    normalized = torch.clamp(displacement / target_angle, 0.0, 1.0)

    # 4) 스윙 중인 다리만 보상
    swing_reward = normalized * swing_mask.float()

    # 5) 스윙 다리 평균
    num_swing = swing_mask.float().sum(dim=1).clamp(min=1.0)
    return swing_reward.sum(dim=1) / num_swing


def terrain_progress_reward(
    env: ManagerBasedRLEnv,
) -> torch.Tensor:
    """지형 난이도 비례 보상: 어려운 지형에 있을수록 큰 보상.

    커리큘럼에 의해 로봇이 쉬운 지형(level 0)에서 어려운 지형(level N)으로
    진행할 때, 높은 레벨에 있다는 것 자체를 보상한다.
    이를 통해 에이전트가 어려운 지형에서 살아남으려는 동기를 강화한다.

    terrain_level / max_terrain_level → 0~1 정규화.
    level 0 = 0 보상, 최고 레벨 = 1.0 보상.

    반환: (num_envs,) 텐서, 0~1 범위.
    양수 weight와 함께 사용.
    """
    terrain = env.scene.terrain
    levels = terrain.terrain_levels  # (num_envs,), int
    max_level = terrain.max_terrain_level  # = num_rows
    return levels.float() / max_level  # 선형: 0~1


def distance_walked_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    target_distance: float = 2.0,
) -> torch.Tensor:
    """원점에서 멀리 걸을수록 보상. 커리큘럼 승급 유도.

    terrain_levels_vel 커리큘럼은 terrain_size/2 이상 걸으면 승급시킨다.
    이 보상은 로봇이 원점에서 멀리 걸어가도록 직접적으로 유도하여
    커리큘럼 승급을 촉진한다.

    distance / target_distance로 정규화, 1.0에서 saturate.

    Args:
        asset_cfg: 로봇 엔티티
        target_distance: 포화 거리 (m). terrain_size/2와 같거나 약간 크게.

    Returns:
        (num_envs,) 0~1 범위
    """
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
    """뒷다리 교대 보상 (V10): 뒷다리가 번갈아 움직이도록 직접 유도.

    문제: 뒷다리가 둘 다 땅에 붙어서 안정적 지지대 역할만 함 (local minimum).
    해결: RL과 RR이 서로 '다른' 접촉 상태에 있을 때 직접 보상.
      - RL=접지, RR=스윙 (또는 반대) → reward = 1.0 (교대 중)
      - RL=접지, RR=접지 → reward = 0.0 (둘 다 땅에 → 트롯 아님)
      - RL=스윙, RR=스윙 → reward = 0.0 (둘 다 공중 → 점프)

    전진 게이팅: 서있을 때는 보상 없음, 보행 중에만.

    body_names 순서: FL(0), FR(1), RL(2), RR(3)
    양수 weight와 함께 사용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4)

    # 뒷다리 접촉 상태 차이: RL(2) vs RR(3)
    # 다르면 1.0 (하나는 접지, 하나는 스윙 = 교대 중)
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
    """뒷다리 동시 접지 페널티 (V11): 두 뒷다리가 동시에 땅에 있으면 직접 페널티.

    rear_alternation_reward의 보완 (채찍 역할).
    교대에 보상만 주는 것으로 local minimum 탈출이 안 되어,
    동시 접지 자체에 직접 페널티를 가해 탈출을 강제.

    penalty = RL접지 * RR접지 (둘 다 접지일 때만 1.0, 아니면 0.0)

    전진 게이팅: 서있을 때는 페널티 없음, 보행 중에만.

    body_names 순서: FL(0), FR(1), RL(2), RR(3)
    음수 weight와 함께 사용.
    """
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4)

    # 뒷다리 둘 다 접지: RL(2) * RR(3) → 둘 다 1이면 1.0, 아니면 0.0
    rear_both = contacts[:, 2] * contacts[:, 3]

    # 전진 게이팅
    asset = env.scene[asset_cfg.name]
    vel_x = asset.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return rear_both * vel_gate


def rear_forward_stride_reward(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    foot_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    contact_threshold: float = 1.0,
    target_clearance: float = 0.06,
    min_vel: float = 0.05,
) -> torch.Tensor:
    """뒷발 전방 보폭 보상 (V12): 뒷발이 들려서 앞으로 이동해야 보상.

    V10/V11 문제: 뒷발이 접촉 센서상 교대는 하지만 실제 보폭이 없음.
    살짝 들어올렸다가 제자리에 내려놓는 "토큰 교대" — 전진에 기여하지 않음.

    해결: 뒷발이 스윙 중일 때 [높이 × 전방 속도] 곱으로 보상.
      - 높이만 있고 전방 속도 없음 → 보상 = 0 (제자리 들기)
      - 전방 속도만 있고 높이 없음 → 보상 = 0 (바닥 끌기)
      - 높이 + 전방 속도 → 보상 = 1.0 (실제 보폭!)

    body_names 순서: FL(0), FR(1), RL(2), RR(3)
    양수 weight와 함께 사용.
    """
    # 1) 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, 4)

    # 2) 뒷발 스윙 마스크 (인덱스 2, 3)
    rear_swing = ~contacts[:, 2:]  # (num_envs, 2), True = 스윙 중

    # 3) 뒷발 높이
    asset = env.scene[foot_cfg.name]
    foot_z = asset.data.body_pos_w[:, foot_cfg.body_ids, 2]  # (num_envs, 4)
    env_origins_z = env.scene.env_origins[:, 2].unsqueeze(1)
    foot_height = foot_z - env_origins_z
    rear_height = foot_height[:, 2:]  # (num_envs, 2)
    # 높이 점수: target_clearance 이상이면 1.0
    height_score = torch.clamp(rear_height / target_clearance, 0.0, 1.0)

    # 4) 뒷발의 전방 속도 (로봇 heading 방향)
    foot_vel = asset.data.body_vel_w[:, foot_cfg.body_ids, :3]  # (num_envs, 4, 3)
    robot = env.scene[asset_cfg.name]
    quat = robot.data.root_quat_w
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    heading_x = 1.0 - 2.0 * (y * y + z * z)
    heading_y = 2.0 * (x * y + w * z)
    # 뒷발(인덱스 2, 3)의 heading 방향 속도
    rear_fwd_vel = (
        foot_vel[:, 2:, 0] * heading_x.unsqueeze(1) +
        foot_vel[:, 2:, 1] * heading_y.unsqueeze(1)
    )  # (num_envs, 2)
    # 전방 속도 점수: 0.3 m/s 이상이면 1.0 (뒤로 가면 0)
    fwd_score = torch.clamp(rear_fwd_vel / 0.3, 0.0, 1.0)

    # 5) 높이 × 전방속도 (곱): 둘 다 있어야 높은 보상
    stride_quality = height_score * fwd_score  # (num_envs, 2)
    # 스윙 중인 뒷발만
    rear_reward = (stride_quality * rear_swing.float()).sum(dim=1) / 2.0  # 0~1 정규화

    # 6) 전진 게이팅
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)
    return rear_reward * vel_gate


def foot_extension_penalty(
    env: ManagerBasedRLEnv,
    foot_joint_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    max_angle: float = 1.5,
) -> torch.Tensor:
    """foot 관절 과신전 페널티: 발바닥이 앞을 향하지 않도록.

    SpotMicro foot joint 범위: -0.1 ~ 2.59 rad.
    자연스러운 서기/걷기에서 foot joint 각도는 보통 0.3 ~ 1.2 rad.
    max_angle(기본 1.5 rad ≈ 86°)을 초과하면 발바닥이 앞을 향하는
    비자연스러운 자세 → 2차 페널티.

    penalty = sum(max(0, angle - max_angle)^2)

    음수 weight와 함께 사용.
    """
    asset: Articulation = env.scene[foot_joint_cfg.name]
    foot_angles = asset.data.joint_pos[:, foot_joint_cfg.joint_ids]  # (num_envs, 4)
    # max_angle 초과분만 페널티 (2차, 초과할수록 비례 증가)
    excess = torch.clamp(foot_angles - max_angle, min=0.0)
    return torch.sum(torch.square(excess), dim=1)
