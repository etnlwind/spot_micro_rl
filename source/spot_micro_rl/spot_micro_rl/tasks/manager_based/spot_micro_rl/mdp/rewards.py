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
    """덧셈 방식 트로트 걸음걸이 보상 (V6).

    V4의 곱셈(AND)은 그래디언트가 0인 영역이 넓어 학습 실패.
    V6: 4개 구성요소를 독립적으로 덧셈 → 부분 진행도 보상.

    전진 게이팅: 로봇이 앞으로 움직일 때만 보상 (제자리 트롯 방지).

    구성요소 (각 0~1, 균등 가중):
      1) 대각선 페어A 동기화: FL(0)과 RR(3)이 같은 상태 → 1
      2) 대각선 페어B 동기화: FR(1)과 RL(2)이 같은 상태 → 1
      3) 페어 간 반위상: 페어A ≠ 페어B → 1
      4) 같은쪽 비동기: FL≠FR, RL≠RR → 1 (벌레걸음 방지)

    덧셈 결합 → 부분 달성도 보상, 4개 모두 만족 = 1.0.

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

    # 덧셈 결합: 각 성분 독립적으로 보상 (부분 진행도 가능)
    base_reward = 0.25 * diag_a_sync + 0.25 * diag_b_sync + 0.25 * anti_phase + 0.25 * side_desync

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
    """비-트로트 보행 패턴 페널티 (V8: 바운딩 + 페이싱 모두 감지).

    트로트: FL+RR / FR+RL 대각선 쌍이 교대.
    바운딩: FL+FR 동시 (앞뒤 동기화) → front_same, rear_same 검사
    페이싱: FL+RL 동시 (좌우 동기화) → left_same, right_same 검사

    V6~V7.1: 바운딩만 감지 → 페이싱을 놓침 (보상까지 받음!)
    V8: 바운딩과 페이싱 중 더 큰 위반을 페널티.

    바운딩 = max(front_same, rear_same)  → 0~1
    페이싱 = max(left_same, right_same)  → 0~1
    penalty = max(bounding, pacing)      → 0~1

    - 완벽한 트로트: 0.0 (페널티 없음)
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
    bounding = (front_same + rear_same) / 2.0

    # --- 페이싱 감지: 왼쪽끼리 / 오른쪽끼리 동기화 ---
    left_same = 1.0 - torch.abs(contacts[:, 0] - contacts[:, 2])   # FL==RL → 1
    right_same = 1.0 - torch.abs(contacts[:, 1] - contacts[:, 3])  # FR==RR → 1
    pacing = (left_same + right_same) / 2.0

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
