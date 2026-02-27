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
    """어깨가 중립(0)에서 벗어나면 페널티. 다리가 벌어지거나 오므라드는 걸 억제한다."""
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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, num_feet), True = 접촉 중

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


def stationary_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    threshold: float = 0.05,
) -> torch.Tensor:
    """로봇이 멈춰있을 때 페널티. XY 속도가 threshold 미만이면 1.0 반환."""
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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()

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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4) - FL(0), FR(1), RL(2), RR(3)

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

    강아지처럼 걸으려면 발을 들어서 앞으로 내디떠야 함.
    스윙 중인 발의 전방 속도를 측정해서 보상한다.
    """
    # 접촉 감지
    contact_sensor: ContactSensor = env.scene.sensors[sensor_cfg.name]
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, num_feet), True = 접촉

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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, 4)

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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )
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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4)

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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    ).float()  # (num_envs, 4)

    # 뒷다리 둘 다 접지일 때만 1.0
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
    contacts = (
        contact_sensor.data.net_forces_w_history[:, :, sensor_cfg.body_ids, :].norm(dim=-1).max(dim=1)[0]
        > contact_threshold
    )  # (num_envs, 4)

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
    reward = (pair_a_reward + pair_b_reward) / 2.0

    # 전진 게이팅
    robot = env.scene[asset_cfg.name]
    vel_x = robot.data.root_lin_vel_b[:, 0]
    vel_gate = torch.clamp(vel_x / min_vel, 0.0, 1.0)

    return reward * vel_gate
