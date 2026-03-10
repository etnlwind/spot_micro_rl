import argparse
import csv
import datetime
import json
import os
import sys
import urllib.request
import zipfile

import numpy as np
from PIL import Image
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Collect checkpoint diagnostics with foot/toe/aggregate comparison")
parser.add_argument("--task", type=str, default="Isaac-Velocity-Flat-SpotMicro-v0")
parser.add_argument("--checkpoint", type=str, default="")
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--steps", type=int, default=120)
parser.add_argument("--contact_threshold", type=float, default=1.0)
parser.add_argument("--camera_zoom", type=float, default=0.85)
parser.add_argument("--video_resolution", type=str, default="1920x1080")
parser.add_argument(
    "--contact_primary_mode",
    type=str,
    default="toe",
    choices=["foot", "toe", "aggregate"],
)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
args_cli.enable_cameras = True

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RSL_RL_SCRIPT_DIR = os.path.join(SCRIPT_DIR, "rsl_rl")
if RSL_RL_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, RSL_RL_SCRIPT_DIR)

sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

from isaaclab.envs import DirectMARLEnv, DirectRLEnvCfg, DirectMARLEnvCfg, ManagerBasedRLEnvCfg, multi_agent_to_single_agent
from isaaclab.utils.assets import retrieve_file_path
from isaaclab_rl.rsl_rl import RslRlBaseRunnerCfg, RslRlVecEnvWrapper
from rsl_rl.runners import DistillationRunner, OnPolicyRunner

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

import spot_micro_rl.tasks  # noqa: F401


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIMB_ORDER = ("LF", "RF", "LR", "RR")
CONTACT_MODES = ("foot", "toe", "aggregate")
LIMB_PATTERNS = {
    "LF": ("front_left_",),
    "RF": ("front_right_",),
    "LR": ("rear_left_",),
    "RR": ("rear_right_",),
}
VIEWS = ("side", "front", "rear", "top_oblique")


def load_env(path):
    env = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
    return env


def send_document(token, chat_id, file_path, caption):
    boundary = "----diagzipboundary"
    with open(file_path, "rb") as file:
        payload = file.read()

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
    body += f"{chat_id}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
    body += f"{caption}\r\n".encode("utf-8")
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="document"; filename="' + os.path.basename(file_path).encode() + b'"\r\n'
    body += b"Content-Type: application/zip\r\n\r\n"
    body += payload
    body += f"\r\n--{boundary}--\r\n".encode()

    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=body)
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    urllib.request.urlopen(request, timeout=180)


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def camera_offsets(view, zoom):
    offsets = {
        "side": ((2.6, -0.45, 0.62), (0.0, 0.0, 0.26)),
        "front": ((0.0, 2.0, 0.50), (0.0, 0.0, 0.28)),
        "rear": ((0.0, -2.0, 0.50), (0.0, 0.0, 0.28)),
        "top_oblique": ((1.25, 1.25, 1.35), (0.0, 0.0, 0.22)),
    }
    eye, look = offsets.get(view, offsets["side"])
    zoom = max(0.2, float(zoom))
    return (eye[0] * zoom, eye[1] * zoom, eye[2] * zoom), look


def resolve_body_groups(body_names):
    lower_names = [name.lower() for name in body_names]
    mappings = {mode: {} for mode in CONTACT_MODES}
    for limb, fragments in LIMB_PATTERNS.items():
        foot_indices = [
            index for index, name in enumerate(lower_names)
            if "foot" in name and any(fragment in name for fragment in fragments)
        ]
        toe_indices = [
            index for index, name in enumerate(lower_names)
            if "toe" in name and any(fragment in name for fragment in fragments)
        ]
        mappings["foot"][limb] = {
            "indices": foot_indices[:1],
            "names": [body_names[index] for index in foot_indices[:1]],
        }
        mappings["toe"][limb] = {
            "indices": toe_indices[:1],
            "names": [body_names[index] for index in toe_indices[:1]],
        }
        aggregate_indices = sorted(set(foot_indices[:1] + toe_indices[:1]))
        mappings["aggregate"][limb] = {
            "indices": aggregate_indices,
            "names": [body_names[index] for index in aggregate_indices],
        }
    return mappings


def scalar_from_indices(values, indices, mode):
    if not indices:
        return 0.0
    selected = values[indices]
    if mode == "aggregate":
        return float(selected.sum())
    return float(selected.max())


def vector_from_indices(values, indices):
    if not indices:
        return np.zeros(values.shape[-1], dtype=np.float32)
    return values[indices].mean(axis=0).astype(np.float32)


def build_contact_row(step, force_peaks, sensor_map, threshold, primary_mode):
    row = [step]
    contacts = {mode: {} for mode in CONTACT_MODES}
    forces = {mode: {} for mode in CONTACT_MODES}
    for mode in CONTACT_MODES:
        for limb in LIMB_ORDER:
            indices = sensor_map[mode][limb]["indices"]
            force_value = scalar_from_indices(force_peaks, indices, mode)
            forces[mode][limb] = force_value
            contacts[mode][limb] = int(force_value > threshold)

    for limb in LIMB_ORDER:
        row.append(contacts[primary_mode][limb])
    for limb in LIMB_ORDER:
        row.append(f"{forces[primary_mode][limb]:.4f}")
    for mode in CONTACT_MODES:
        for limb in LIMB_ORDER:
            row.append(contacts[mode][limb])
        for limb in LIMB_ORDER:
            row.append(f"{forces[mode][limb]:.4f}")
    return row


def build_contact_header():
    header = ["step", "LF", "RF", "LR", "RR", "LF_force", "RF_force", "LR_force", "RR_force"]
    for mode in CONTACT_MODES:
        for limb in LIMB_ORDER:
            header.append(f"{limb}_{mode}")
        for limb in LIMB_ORDER:
            header.append(f"{limb}_{mode}_force")
    return header


def compute_transition_arrays(contacts):
    previous = np.zeros(4, dtype=bool)
    touchdowns = []
    liftoffs = []
    for current in contacts.astype(bool):
        touchdown = current & (~previous)
        liftoff = (~current) & previous
        touchdowns.append(touchdown.astype(np.int32))
        liftoffs.append(liftoff.astype(np.int32))
        previous = current
    return np.asarray(touchdowns, dtype=np.int32), np.asarray(liftoffs, dtype=np.int32)


def compute_gait_cycle_proxy(contacts, vel_gate, step_dt, target_min=0.3, target_max=0.5):
    previous = np.zeros(4, dtype=bool)
    last_contact = np.zeros(4, dtype=np.float32)
    measured = np.zeros(4, dtype=np.float32)
    rewards = []
    valid_event_count = 0
    target_mid = (target_min + target_max) / 2.0
    target_sigma = (target_max - target_min) / 2.0

    for step, current in enumerate(contacts.astype(bool)):
        time_now = step * step_dt
        touchdown = current & (~previous)
        valid_touchdown = touchdown & (last_contact > 0.0)
        if valid_touchdown.any():
            measured[valid_touchdown] = time_now - last_contact[valid_touchdown]
            valid_event_count += int(valid_touchdown.sum())
        last_contact[touchdown] = time_now

        in_range = (measured >= target_min) & (measured <= target_max)
        distance = (measured - target_mid) / (target_sigma + 1e-6)
        period_reward = np.where(in_range, 1.0, np.exp(-(distance ** 2)))
        period_reward = period_reward * (measured > 0.0)
        rewards.append(float(period_reward.mean() * vel_gate[step]))
        previous = current

    return np.asarray(rewards, dtype=np.float32), valid_event_count


def compute_stride_proxy(contacts, positions_xy, vel_gate, target_stride=0.06):
    previous = np.ones(4, dtype=bool)
    liftoff_pos = np.zeros((4, 2), dtype=np.float32)
    measured = np.zeros(4, dtype=np.float32)
    touchdown_measurements = 0
    rewards = []

    for step, current in enumerate(contacts.astype(bool)):
        liftoff = (~current) & previous
        touchdown = current & (~previous)
        if liftoff.any():
            liftoff_pos[liftoff] = positions_xy[step, liftoff]
        if touchdown.any():
            displacement = positions_xy[step, touchdown] - liftoff_pos[touchdown]
            measured[touchdown] = np.linalg.norm(displacement, axis=1)
            touchdown_measurements += int(touchdown.sum())

        normalized = np.clip(measured / (target_stride + 1e-6), 0.0, 2.0)
        stride_reward = np.where(normalized <= 1.0, normalized, 2.0 - normalized)
        stride_reward = np.clip(stride_reward, 0.0, 1.0)
        stride_reward = stride_reward * (measured > 0.001)
        rewards.append(float(stride_reward.mean() * vel_gate[step]))
        previous = current

    return np.asarray(rewards, dtype=np.float32), touchdown_measurements, measured.copy()


def compute_stance_propulsion_proxy(contacts, foot_vel_w, heading_xy, body_heading_vel, vel_gate, target_push_vel=0.3):
    foot_heading_vel = (
        foot_vel_w[:, :, 0] * heading_xy[:, 0][:, None]
        + foot_vel_w[:, :, 1] * heading_xy[:, 1][:, None]
    )
    relative_vel = foot_heading_vel - body_heading_vel[:, None]
    push_magnitude = np.clip(-relative_vel, 0.0, None)
    normalized = np.clip(push_magnitude / target_push_vel, 0.0, 1.0)
    stance_mask = contacts.astype(np.float32)
    rewards = []
    for step in range(len(contacts)):
        count = max(float(stance_mask[step].sum()), 1.0)
        rewards.append(float((normalized[step] * stance_mask[step]).sum() / count * vel_gate[step]))
    return np.asarray(rewards, dtype=np.float32)


def compute_trot_proxy(contacts, vel_gate):
    diag_a = 1.0 - np.abs(contacts[:, 0] - contacts[:, 3])
    diag_b = 1.0 - np.abs(contacts[:, 1] - contacts[:, 2])
    pair_a = (contacts[:, 0] + contacts[:, 3]) / 2.0
    pair_b = (contacts[:, 1] + contacts[:, 2]) / 2.0
    anti_phase = np.abs(pair_a - pair_b)
    front_desync = np.abs(contacts[:, 0] - contacts[:, 1])
    rear_desync = np.abs(contacts[:, 2] - contacts[:, 3])
    side_desync = (front_desync + rear_desync) / 2.0
    components = np.stack([diag_a, diag_b, anti_phase, side_desync], axis=1)
    return (0.4 * components.mean(axis=1) + 0.6 * components.min(axis=1)) * vel_gate


def compute_rear_alternation_proxy(contacts, vel_gate):
    return np.abs(contacts[:, 2] - contacts[:, 3]) * vel_gate


def compute_rear_forward_stride_proxy(contacts, foot_pos_z, foot_vel_w, heading_xy, vel_gate, target_clearance=0.06, target_fwd_vel=0.3):
    rear_swing = 1.0 - contacts[:, 2:]
    rear_height = foot_pos_z[:, 2:]
    height_score = np.clip(rear_height / target_clearance, 0.0, 1.0)
    rear_fwd_vel = (
        foot_vel_w[:, 2:, 0] * heading_xy[:, 0][:, None]
        + foot_vel_w[:, 2:, 1] * heading_xy[:, 1][:, None]
    )
    fwd_score = np.clip(rear_fwd_vel / target_fwd_vel, 0.0, 1.0)
    return ((height_score * fwd_score * rear_swing).sum(axis=1) / 2.0) * vel_gate


def quaternion_pitch_deg(quat_wxyz):
    w = quat_wxyz[:, 0]
    x = quat_wxyz[:, 1]
    y = quat_wxyz[:, 2]
    z = quat_wxyz[:, 3]
    sin_pitch = 2.0 * (w * y - z * x)
    sin_pitch = np.clip(sin_pitch, -1.0, 1.0)
    return np.degrees(np.arcsin(sin_pitch)).astype(np.float32)


def summarize_mode(contacts, forces_peak, positions, velocities, env_origins_z, heading_xy, body_heading_vel, vel_gate, step_dt):
    touchdowns, liftoffs = compute_transition_arrays(contacts)
    gait_cycle_reward, gait_cycle_events = compute_gait_cycle_proxy(contacts, vel_gate, step_dt)
    stride_reward, stride_events, last_stride = compute_stride_proxy(contacts, positions[:, :, :2], vel_gate)
    stance_reward = compute_stance_propulsion_proxy(contacts, velocities, heading_xy, body_heading_vel, vel_gate)
    trot_reward = compute_trot_proxy(contacts, vel_gate)
    rear_alt_reward = compute_rear_alternation_proxy(contacts, vel_gate)
    foot_height = positions[:, :, 2] - env_origins_z[:, None]
    rear_forward_reward = compute_rear_forward_stride_proxy(contacts, foot_height, velocities, heading_xy, vel_gate)

    diag_sync = 1.0 - float(np.mean(np.abs(contacts[:, 0] - contacts[:, 3]) + np.abs(contacts[:, 1] - contacts[:, 2])) / 2.0)
    lateral_sync = 1.0 - float(np.mean(np.abs(contacts[:, 0] - contacts[:, 1]) + np.abs(contacts[:, 2] - contacts[:, 3])) / 2.0)
    diag_touchdowns = int(((touchdowns[:, 0] & touchdowns[:, 3]) | (touchdowns[:, 1] & touchdowns[:, 2])).sum())
    lateral_touchdowns = int(((touchdowns[:, 0] & touchdowns[:, 1]) | (touchdowns[:, 2] & touchdowns[:, 3])).sum())

    summary = {
        "touchdown_count": int(touchdowns.sum()),
        "liftoff_count": int(liftoffs.sum()),
        "touchdown_pair_diagonal": diag_touchdowns,
        "touchdown_pair_lateral": lateral_touchdowns,
        "mean_peak_force": float(forces_peak.mean()),
        "max_peak_force": float(forces_peak.max()),
        "mean_contacts_per_step": float(contacts.sum(axis=1).mean()),
        "diag_sync": diag_sync,
        "lateral_sync": lateral_sync,
        "trot_gait_mean": float(trot_reward.mean()),
        "rear_alternation_mean": float(rear_alt_reward.mean()),
        "gait_cycle_period_mean": float(gait_cycle_reward.mean()),
        "gait_cycle_period_nonzero_steps": int((gait_cycle_reward > 0.0).sum()),
        "gait_cycle_period_valid_events": int(gait_cycle_events),
        "stride_length_mean": float(stride_reward.mean()),
        "stride_length_nonzero_steps": int((stride_reward > 0.0).sum()),
        "stride_length_valid_events": int(stride_events),
        "stride_length_last_mean": float(last_stride.mean()),
        "stance_propulsion_mean": float(stance_reward.mean()),
        "rear_forward_stride_mean": float(rear_forward_reward.mean()),
    }
    timeseries = {
        "touchdowns": touchdowns,
        "liftoffs": liftoffs,
        "trot_gait": trot_reward,
        "rear_alternation": rear_alt_reward,
        "gait_cycle_period": gait_cycle_reward,
        "stride_length": stride_reward,
        "stance_propulsion": stance_reward,
        "rear_forward_stride": rear_forward_reward,
    }
    return summary, timeseries


def summarize_body_stability(root_pos_w, env_origin_z, root_quat_w):
    base_height = root_pos_w[:, 2] - env_origin_z
    pitch_deg = quaternion_pitch_deg(root_quat_w)
    abs_pitch_deg = np.abs(pitch_deg)
    return {
        "base_height_mean": float(base_height.mean()),
        "base_height_std": float(base_height.std()),
        "base_height_min": float(base_height.min()),
        "pitch_abs_mean_deg": float(abs_pitch_deg.mean()),
        "pitch_abs_max_deg": float(abs_pitch_deg.max()),
    }


def collect_tb_snapshot(run_dir):
    snapshot = {}
    try:
        accumulator = EventAccumulator(run_dir)
        accumulator.Reload()
    except Exception:
        return snapshot

    tags = accumulator.Tags().get("scalars", [])
    for tag in [
        "Episode_Reward/trot_gait",
        "Episode_Reward/rear_alternation",
        "Episode_Reward/gait_cycle_period",
        "Episode_Reward/stride_length",
        "Episode_Reward/stance_propulsion",
        "Episode_Reward/rear_forward_stride",
        "Episode_Reward/rear_joint_velocity",
        "Episode_Reward/rear_swing",
        "Episode_Reward/diagonal_coupling",
    ]:
        if tag in tags:
            values = accumulator.Scalars(tag)
            if values:
                snapshot[tag] = {"step": int(values[-1].step), "value": float(values[-1].value)}
    return snapshot


def save_frames(sim_env, positions_w, frame_root):
    for view in VIEWS:
        os.makedirs(os.path.join(frame_root, view), exist_ok=True)

    for step, position in enumerate(positions_w):
        for view in VIEWS:
            eye_off, look_off = camera_offsets(view, args_cli.camera_zoom)
            eye = (float(position[0]) + eye_off[0], float(position[1]) + eye_off[1], float(position[2]) + eye_off[2])
            look = (float(position[0]) + look_off[0], float(position[1]) + look_off[1], float(position[2]) + look_off[2])
            sim_env.unwrapped.sim.set_camera_view(eye, look)
            rgb = sim_env.render()
            if isinstance(rgb, tuple):
                rgb = rgb[0]
            array = np.asarray(rgb)
            if array.ndim == 4:
                array = array[0]
            Image.fromarray(array.astype(np.uint8)).save(
                os.path.join(frame_root, view, f"{view}_{step:04d}.jpg"),
                format="JPEG",
                quality=92,
            )


@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlBaseRunnerCfg):
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.seed = agent_cfg.seed
    width, height = (int(value) for value in args_cli.video_resolution.split("x"))
    env_cfg.viewer.resolution = (width, height)

    log_root = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
    if args_cli.checkpoint:
        resume_path = retrieve_file_path(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(log_root, agent_cfg.load_run, agent_cfg.load_checkpoint)
    log_dir = os.path.dirname(resume_path)
    env_cfg.log_dir = log_dir

    sim_env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    if isinstance(sim_env.unwrapped, DirectMARLEnv):
        sim_env = multi_agent_to_single_agent(sim_env)
    rl_env = RslRlVecEnvWrapper(sim_env, clip_actions=agent_cfg.clip_actions)

    if agent_cfg.class_name == "OnPolicyRunner":
        runner = OnPolicyRunner(rl_env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    else:
        runner = DistillationRunner(rl_env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path)
    policy = runner.get_inference_policy(device=rl_env.unwrapped.device)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = os.path.join(PROJECT_ROOT, "logs", "diagnostics", f"diag_{timestamp}")
    csv_root = os.path.join(out_root, "csv")
    meta_root = os.path.join(out_root, "meta")
    frame_root = os.path.join(out_root, "frames")
    os.makedirs(csv_root, exist_ok=True)
    os.makedirs(meta_root, exist_ok=True)
    os.makedirs(frame_root, exist_ok=True)

    robot = sim_env.unwrapped.scene["robot"]
    contact_sensor = sim_env.unwrapped.scene.sensors.get("contact_forces", None)
    if contact_sensor is None:
        raise RuntimeError("contact_forces sensor is required for diagnostics")

    sensor_body_names = list(getattr(contact_sensor, "body_names", []) or [])
    robot_body_names = list(getattr(robot, "body_names", []) or [])
    sensor_map = resolve_body_groups(sensor_body_names)
    robot_map = resolve_body_groups(robot_body_names)

    config_snapshot = {
        "checkpoint": resume_path,
        "task": args_cli.task,
        "steps": int(args_cli.steps),
        "contact_threshold": float(args_cli.contact_threshold),
        "primary_contact_mode": args_cli.contact_primary_mode,
        "sensor_body_names": sensor_body_names,
        "robot_body_names": robot_body_names,
        "sensor_contact_modes": sensor_map,
        "robot_contact_modes": robot_map,
        "force_reduction": {
            "foot": "max over selected foot_link bodies after max-history norm reduction",
            "toe": "max over selected toe_link bodies after max-history norm reduction",
            "aggregate": "sum of selected foot_link and toe_link forces after max-history norm reduction",
        },
    }
    with open(os.path.join(meta_root, "config_snapshot.json"), "w", encoding="utf-8") as file:
        json.dump(config_snapshot, file, indent=2, ensure_ascii=False)

    obs = rl_env.get_observations()
    step_rows = []
    rollout = {
        mode: {"force_peak": [], "contact_peak": [], "pos": [], "vel": []}
        for mode in CONTACT_MODES
    }
    root_pos_w = []
    root_lin_vel_b = []
    root_lin_vel_w = []
    root_quat_w = []
    env_origin_z = []

    for step in range(args_cli.steps):
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, _, _ = rl_env.step(actions)

        force_history = contact_sensor.data.net_forces_w_history[0].detach().cpu()
        force_peaks = force_history.norm(dim=-1).max(dim=0)[0].numpy()
        body_pos_w = robot.data.body_pos_w[0].detach().cpu().numpy()
        body_vel_w = robot.data.body_vel_w[0].detach().cpu().numpy()[:, :3]
        current_root_pos_w = robot.data.root_pos_w[0].detach().cpu().numpy()
        current_root_lin_vel_b = robot.data.root_lin_vel_b[0].detach().cpu().numpy()
        current_root_lin_vel_w = robot.data.root_lin_vel_w[0].detach().cpu().numpy()
        current_root_quat_w = robot.data.root_quat_w[0].detach().cpu().numpy()
        current_origin_z = float(sim_env.unwrapped.scene.env_origins[0, 2].item())

        step_rows.append(build_contact_row(step, force_peaks, sensor_map, float(args_cli.contact_threshold), args_cli.contact_primary_mode))

        for mode in CONTACT_MODES:
            peak_forces = []
            contacts = []
            positions = []
            velocities = []
            for limb in LIMB_ORDER:
                sensor_indices = sensor_map[mode][limb]["indices"]
                robot_indices = robot_map[mode][limb]["indices"]
                peak_force = scalar_from_indices(force_peaks, sensor_indices, mode)
                peak_forces.append(peak_force)
                contacts.append(float(peak_force > float(args_cli.contact_threshold)))
                positions.append(vector_from_indices(body_pos_w, robot_indices))
                velocities.append(vector_from_indices(body_vel_w, robot_indices))
            rollout[mode]["force_peak"].append(peak_forces)
            rollout[mode]["contact_peak"].append(contacts)
            rollout[mode]["pos"].append(positions)
            rollout[mode]["vel"].append(velocities)

        root_pos_w.append(current_root_pos_w)
        root_lin_vel_b.append(current_root_lin_vel_b)
        root_lin_vel_w.append(current_root_lin_vel_w)
        root_quat_w.append(current_root_quat_w)
        env_origin_z.append(current_origin_z)

    root_pos_w = np.asarray(root_pos_w, dtype=np.float32)
    root_lin_vel_b = np.asarray(root_lin_vel_b, dtype=np.float32)
    root_lin_vel_w = np.asarray(root_lin_vel_w, dtype=np.float32)
    root_quat_w = np.asarray(root_quat_w, dtype=np.float32)
    env_origin_z = np.asarray(env_origin_z, dtype=np.float32)

    heading_xy = np.column_stack((
        1.0 - 2.0 * (root_quat_w[:, 2] ** 2 + root_quat_w[:, 3] ** 2),
        2.0 * (root_quat_w[:, 1] * root_quat_w[:, 2] + root_quat_w[:, 0] * root_quat_w[:, 3]),
    )).astype(np.float32)
    body_heading_vel = (root_lin_vel_w[:, 0] * heading_xy[:, 0] + root_lin_vel_w[:, 1] * heading_xy[:, 1]).astype(np.float32)
    vel_gate = np.clip(root_lin_vel_b[:, 0] / 0.05, 0.0, 1.0).astype(np.float32)

    write_csv(os.path.join(csv_root, "contact_force_modes.csv"), build_contact_header(), step_rows)

    summary_rows = []
    event_rows = []
    proxy_rows = []
    all_summaries = {}
    summary_fields = [
        "touchdown_count",
        "liftoff_count",
        "touchdown_pair_diagonal",
        "touchdown_pair_lateral",
        "mean_peak_force",
        "max_peak_force",
        "mean_contacts_per_step",
        "diag_sync",
        "lateral_sync",
        "trot_gait_mean",
        "rear_alternation_mean",
        "gait_cycle_period_mean",
        "gait_cycle_period_nonzero_steps",
        "gait_cycle_period_valid_events",
        "stride_length_mean",
        "stride_length_nonzero_steps",
        "stride_length_valid_events",
        "stride_length_last_mean",
        "stance_propulsion_mean",
        "rear_forward_stride_mean",
    ]

    for mode in CONTACT_MODES:
        mode_contacts = np.asarray(rollout[mode]["contact_peak"], dtype=np.float32)
        mode_force_peak = np.asarray(rollout[mode]["force_peak"], dtype=np.float32)
        mode_positions = np.asarray(rollout[mode]["pos"], dtype=np.float32)
        mode_velocities = np.asarray(rollout[mode]["vel"], dtype=np.float32)

        summary, timeseries = summarize_mode(
            mode_contacts,
            mode_force_peak,
            mode_positions,
            mode_velocities,
            env_origin_z,
            heading_xy,
            body_heading_vel,
            vel_gate,
            float(sim_env.unwrapped.step_dt),
        )
        all_summaries[mode] = summary
        summary_rows.append([mode] + [summary[field] for field in summary_fields])

        for step in range(args_cli.steps):
            for limb_index, limb in enumerate(LIMB_ORDER):
                event_rows.append([
                    step,
                    mode,
                    limb,
                    int(timeseries["touchdowns"][step, limb_index]),
                    int(timeseries["liftoffs"][step, limb_index]),
                    float(mode_force_peak[step, limb_index]),
                    int(mode_contacts[step, limb_index]),
                ])
            proxy_rows.append([
                step,
                mode,
                float(timeseries["trot_gait"][step]),
                float(timeseries["rear_alternation"][step]),
                float(timeseries["gait_cycle_period"][step]),
                float(timeseries["stride_length"][step]),
                float(timeseries["stance_propulsion"][step]),
                float(timeseries["rear_forward_stride"][step]),
            ])

    write_csv(
        os.path.join(csv_root, "contact_event_summary.csv"),
        ["mode"] + summary_fields,
        summary_rows,
    )
    write_csv(
        os.path.join(csv_root, "contact_event_timeseries.csv"),
        ["step", "mode", "limb", "touchdown", "liftoff", "peak_force", "contact_state"],
        event_rows,
    )
    write_csv(
        os.path.join(csv_root, "reward_proxy_timeseries.csv"),
        ["step", "mode", "trot_gait", "rear_alternation", "gait_cycle_period", "stride_length", "stance_propulsion", "rear_forward_stride"],
        proxy_rows,
    )

    before_after = {
        "before_mode": "foot",
        "after_mode": "toe",
        "aggregate_mode": "aggregate",
        "body_stability": summarize_body_stability(root_pos_w, env_origin_z, root_quat_w),
        "summary": all_summaries,
        "delta_after_minus_before": {},
        "delta_aggregate_minus_before": {},
        "tensorboard_last": collect_tb_snapshot(log_dir),
    }
    for field in [
        "touchdown_count",
        "liftoff_count",
        "touchdown_pair_diagonal",
        "touchdown_pair_lateral",
        "trot_gait_mean",
        "rear_alternation_mean",
        "gait_cycle_period_mean",
        "gait_cycle_period_valid_events",
        "stride_length_mean",
        "stride_length_valid_events",
        "stance_propulsion_mean",
        "rear_forward_stride_mean",
        "diag_sync",
        "lateral_sync",
    ]:
        before_after["delta_after_minus_before"][field] = float(all_summaries["toe"][field] - all_summaries["foot"][field])
        before_after["delta_aggregate_minus_before"][field] = float(all_summaries["aggregate"][field] - all_summaries["foot"][field])

    with open(os.path.join(meta_root, "before_after_summary.json"), "w", encoding="utf-8") as file:
        json.dump(before_after, file, indent=2, ensure_ascii=False)

    notes = ["Checkpoint contact-mode comparison"]
    for mode in CONTACT_MODES:
        summary = all_summaries[mode]
        notes.append(
            f"{mode}: touchdown={summary['touchdown_count']} liftoff={summary['liftoff_count']} "
            f"diag_touch={summary['touchdown_pair_diagonal']} lateral_touch={summary['touchdown_pair_lateral']} "
            f"gait_cycle={summary['gait_cycle_period_mean']:.4f} stride={summary['stride_length_mean']:.4f} "
            f"stance={summary['stance_propulsion_mean']:.4f} trot={summary['trot_gait_mean']:.4f}"
        )
    with open(os.path.join(out_root, "analysis_notes.txt"), "w", encoding="utf-8") as file:
        file.write("\n".join(notes) + "\n")

    save_frames(sim_env, root_pos_w, frame_root)

    zip_path = os.path.join(PROJECT_ROOT, "logs", "diagnostics", f"checkpoint_diagnostics_{timestamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(out_root):
            for name in files:
                file_path = os.path.join(root, name)
                archive.write(file_path, os.path.relpath(file_path, out_root))

    print(f"diagnostics_dir: {out_root}")
    print(f"zip: {zip_path}")
    print(json.dumps(before_after, indent=2, ensure_ascii=False))

    env_file = load_env(os.path.join(PROJECT_ROOT, ".env"))
    token = env_file.get("TELEGRAM_TOKEN", "")
    chat_id = env_file.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        send_document(token, chat_id, zip_path, "Checkpoint diagnostics package (foot/toe/aggregate comparison)")
        print("telegram: sent")

    rl_env.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()