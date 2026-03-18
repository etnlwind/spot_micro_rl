# Copyright (c) 2022-2025, The Isaac Lab Project Developers (https://github.com/isaac-sim/IsaacLab/blob/main/CONTRIBUTORS.md).
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""Script to play a checkpoint if an RL agent from RSL-RL."""

"""Launch Isaac Sim Simulator first."""

import argparse
import csv
import json
import sys

from isaaclab.app import AppLauncher

# local imports
import cli_args  # isort: skip

# add argparse arguments
parser = argparse.ArgumentParser(description="Train an RL agent with RSL-RL.")
parser.add_argument("--video", action="store_true", default=False, help="Record videos during training.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video (in steps).")
parser.add_argument(
    "--camera_view",
    type=str,
    default="side",
    choices=["overview", "side", "front", "rear", "top", "top_oblique"],
    help="Camera view preset for video recording.",
)
parser.add_argument(
    "--camera_zoom",
    type=float,
    default=1.0,
    help="Camera distance scale (<1.0 = closer, >1.0 = farther).",
)
parser.add_argument(
    "--save_contact_csv",
    action="store_true",
    default=False,
    help="Save per-step foot contact states (LF/RF/LR/RR) to CSV during video recording.",
)
parser.add_argument(
    "--contact_threshold",
    type=float,
    default=1.0,
    help="Contact force threshold used to binarize contact state.",
)
parser.add_argument(
    "--contact_primary_mode",
    type=str,
    default="toe",
    choices=["foot", "toe", "aggregate"],
    help="Primary contact mode used for compatibility CSV columns LF/RF/LR/RR.",
)
parser.add_argument(
    "--disable_fabric", action="store_true", default=False, help="Disable fabric and use USD I/O operations."
)
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default=None, help="Name of the task.")
parser.add_argument(
    "--agent", type=str, default="rsl_rl_cfg_entry_point", help="Name of the RL agent configuration entry point."
)
parser.add_argument("--seed", type=int, default=None, help="Seed used for the environment")
parser.add_argument(
    "--use_pretrained_checkpoint",
    action="store_true",
    help="Use the pre-trained checkpoint from Nucleus.",
)
parser.add_argument("--real-time", action="store_true", default=False, help="Run in real-time, if possible.")
# append RSL-RL cli arguments
cli_args.add_rsl_rl_args(parser)
# append AppLauncher cli args
AppLauncher.add_app_launcher_args(parser)
# parse the arguments
args_cli, hydra_args = parser.parse_known_args()
# always enable cameras to record video
if args_cli.video:
    args_cli.enable_cameras = True

# clear out sys.argv for Hydra
sys.argv = [sys.argv[0]] + hydra_args

# launch omniverse app
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

"""Rest everything follows."""

import gymnasium as gym
import os
import time
import torch

from rsl_rl.runners import DistillationRunner, OnPolicyRunner

from isaaclab.envs import (
    DirectMARLEnv,
    DirectMARLEnvCfg,
    DirectRLEnvCfg,
    ManagerBasedRLEnvCfg,
    multi_agent_to_single_agent,
)
from isaaclab.utils.assets import retrieve_file_path
from isaaclab.utils.dict import print_dict
from isaaclab.utils.pretrained_checkpoint import get_published_pretrained_checkpoint

from isaaclab_rl.rsl_rl import RslRlBaseRunnerCfg, RslRlVecEnvWrapper, export_policy_as_jit, export_policy_as_onnx

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

import spot_micro_rl.tasks  # noqa: F401


CONTACT_LIMB_ORDER = ("LF", "RF", "LR", "RR")
CONTACT_MODE_ORDER = ("foot", "toe", "aggregate")
CONTACT_LIMB_PATTERNS = {
    "LF": ("front_left_",),
    "RF": ("front_right_",),
    "LR": ("rear_left_",),
    "RR": ("rear_right_",),
}


def _camera_offsets(view_name: str, zoom: float = 1.0):
    """Return (eye_offset, lookat_offset) relative to robot base position."""
    offsets = {
        "overview": ((3.0, -3.0, 2.2), (0.0, 0.0, 0.35)),
        "side": ((2.6, -0.45, 0.62), (0.0, 0.0, 0.26)),
        "front": ((0.0, 2.0, 0.50), (0.0, 0.0, 0.28)),
        "rear": ((0.0, -2.0, 0.50), (0.0, 0.0, 0.28)),
        "top": ((0.0, 0.0, 2.1), (0.0, 0.0, 0.22)),
        "top_oblique": ((1.25, 1.25, 1.35), (0.0, 0.0, 0.22)),
    }
    eye_off, look_off = offsets.get(view_name, offsets["side"])
    zoom = max(0.2, float(zoom))
    eye_scaled = (eye_off[0] * zoom, eye_off[1] * zoom, eye_off[2] * zoom)
    return eye_scaled, look_off


def _apply_camera_view_preset(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, view_name: str):
    """Apply camera pose preset for consistent gait evaluation videos."""
    if view_name == "overview":
        print("[INFO] Camera view preset: overview | using default viewer pose")
        return

    # Initial pose before stepping. Runtime follow logic keeps robot centered.
    eye, lookat = _camera_offsets(view_name, args_cli.camera_zoom)
    if hasattr(env_cfg, "viewer") and env_cfg.viewer is not None:
        env_cfg.viewer.eye = eye
        env_cfg.viewer.lookat = lookat
    print(f"[INFO] Camera view preset: {view_name} | eye={eye} lookat={lookat}")


def _configure_view_specific_visuals(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, view_name: str):
    """Adjust per-view debug visuals without affecting training configs."""
    if view_name != "top":
        return

    commands = getattr(env_cfg, "commands", None)
    base_velocity = getattr(commands, "base_velocity", None) if commands is not None else None
    if base_velocity is not None and hasattr(base_velocity, "debug_vis"):
        base_velocity.debug_vis = False
        print("[INFO] Top view: disabled base_velocity debug visualization")


def _get_contact_body_names(contact_sensor):
    """Return sensor body names or deterministic placeholders."""
    body_names = list(getattr(contact_sensor, "body_names", []) or [])
    if not body_names:
        body_count = int(contact_sensor.data.net_forces_w_history.shape[2])
        body_names = [f"body_{i}" for i in range(body_count)]
    return body_names


def _resolve_contact_body_map(contact_sensor):
    """Resolve LF/RF/LR/RR mappings for foot, toe, and aggregate modes."""
    body_names = _get_contact_body_names(contact_sensor)
    lower_names = [n.lower() for n in body_names]
    mappings = {mode: {} for mode in CONTACT_MODE_ORDER}

    for limb, fragments in CONTACT_LIMB_PATTERNS.items():
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

    return mappings, body_names


def _collapse_contact_force(body_forces: torch.Tensor, indices: list[int], mode: str) -> float:
    """Collapse per-body forces into one limb force."""
    if not indices:
        return 0.0
    selected = body_forces[indices]
    if mode == "aggregate":
        return float(selected.sum().item())
    return float(selected.max().item())


def _build_contact_csv_header():
    header = ["step", "LF", "RF", "LR", "RR", "LF_force", "RF_force", "LR_force", "RR_force"]
    for mode in CONTACT_MODE_ORDER:
        for limb in CONTACT_LIMB_ORDER:
            header.append(f"{limb}_{mode}")
        for limb in CONTACT_LIMB_ORDER:
            header.append(f"{limb}_{mode}_force")
    return header


def _build_contact_csv_row(step: int, body_forces: torch.Tensor, contact_map: dict, threshold: float, primary_mode: str):
    row = [step]
    mode_contacts = {}
    mode_forces = {}

    for mode in CONTACT_MODE_ORDER:
        mode_contacts[mode] = {}
        mode_forces[mode] = {}
        for limb in CONTACT_LIMB_ORDER:
            indices = contact_map[mode][limb]["indices"]
            force_value = _collapse_contact_force(body_forces, indices, mode)
            mode_forces[mode][limb] = force_value
            mode_contacts[mode][limb] = int(force_value > threshold)

    for limb in CONTACT_LIMB_ORDER:
        row.append(mode_contacts[primary_mode][limb])
    for limb in CONTACT_LIMB_ORDER:
        row.append(f"{mode_forces[primary_mode][limb]:.4f}")
    for mode in CONTACT_MODE_ORDER:
        for limb in CONTACT_LIMB_ORDER:
            row.append(mode_contacts[mode][limb])
        for limb in CONTACT_LIMB_ORDER:
            row.append(f"{mode_forces[mode][limb]:.4f}")
    return row


def _print_contact_mapping(contact_map: dict):
    for mode in CONTACT_MODE_ORDER:
        print(f"[INFO] Contact mapping mode={mode}")
        for limb in CONTACT_LIMB_ORDER:
            mapping = contact_map[mode][limb]
            print(f"  {limb}: indices={mapping['indices']} names={mapping['names']}")


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlBaseRunnerCfg):
    """Play with RSL-RL agent."""
    # grab task name for checkpoint path
    task_name = args_cli.task.split(":")[-1]
    train_task_name = task_name.replace("-Play", "")

    # override configurations with non-hydra CLI arguments
    agent_cfg: RslRlBaseRunnerCfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs

    # set the environment seed
    # note: certain randomizations occur in the environment initialization so we set the seed here
    env_cfg.seed = agent_cfg.seed
    env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device

    # specify directory for logging experiments
    log_root_path = os.path.join("logs", "rsl_rl", agent_cfg.experiment_name)
    log_root_path = os.path.abspath(log_root_path)
    print(f"[INFO] Loading experiment from directory: {log_root_path}")
    if args_cli.use_pretrained_checkpoint:
        resume_path = get_published_pretrained_checkpoint("rsl_rl", train_task_name)
        if not resume_path:
            print("[INFO] Unfortunately a pre-trained checkpoint is currently unavailable for this task.")
            return
    elif args_cli.checkpoint:
        resume_path = retrieve_file_path(args_cli.checkpoint)
    else:
        resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)

    log_dir = os.path.dirname(resume_path)

    # set the log directory for the environment (works for all environment types)
    env_cfg.log_dir = log_dir

    # set viewer resolution for video recording (from .env or default 1080p)
    if args_cli.video:
        _res_str = os.environ.get("VIDEO_RESOLUTION", "1920x1080")
        _w, _h = (int(x) for x in _res_str.split("x"))
        env_cfg.viewer.resolution = (_w, _h)
        print(f"[INFO] Video resolution: {_w}x{_h}")
        _configure_view_specific_visuals(env_cfg, args_cli.camera_view)
        _apply_camera_view_preset(env_cfg, args_cli.camera_view)

    # create isaac environment
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)

    # convert to single-agent instance if required by the RL algorithm
    if isinstance(env.unwrapped, DirectMARLEnv):
        env = multi_agent_to_single_agent(env)

    # wrap for video recording
    if args_cli.video:
        video_kwargs = {
            "video_folder": os.path.join(log_dir, "videos", "play"),
            "step_trigger": lambda step: step == 0,
            "video_length": args_cli.video_length,
            "disable_logger": True,
        }
        print("[INFO] Recording videos during training.")
        print_dict(video_kwargs, nesting=4)
        env = gym.wrappers.RecordVideo(env, **video_kwargs)

    # wrap around environment for rsl-rl
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    print(f"[INFO]: Loading model checkpoint from: {resume_path}")
    # load previously trained model
    if agent_cfg.class_name == "OnPolicyRunner":
        runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    elif agent_cfg.class_name == "DistillationRunner":
        runner = DistillationRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    else:
        raise ValueError(f"Unsupported runner class: {agent_cfg.class_name}")
    runner.load(resume_path)

    # obtain the trained policy for inference
    policy = runner.get_inference_policy(device=env.unwrapped.device)

    # extract the neural network module
    # we do this in a try-except to maintain backwards compatibility.
    try:
        # version 2.3 onwards
        policy_nn = runner.alg.policy
    except AttributeError:
        # version 2.2 and below
        policy_nn = runner.alg.actor_critic

    # extract the normalizer
    if hasattr(policy_nn, "actor_obs_normalizer"):
        normalizer = policy_nn.actor_obs_normalizer
    elif hasattr(policy_nn, "student_obs_normalizer"):
        normalizer = policy_nn.student_obs_normalizer
    else:
        normalizer = None

    # export policy to onnx/jit
    export_model_dir = os.path.join(os.path.dirname(resume_path), "exported")
    export_policy_as_jit(policy_nn, normalizer=normalizer, path=export_model_dir, filename="policy.pt")
    export_policy_as_onnx(policy_nn, normalizer=normalizer, path=export_model_dir, filename="policy.onnx")

    dt = env.unwrapped.step_dt

    # reset environment
    obs = env.get_observations()
    timestep = 0
    camera_follow_error_logged = False
    follow_camera = args_cli.video and (args_cli.num_envs == 1) and (args_cli.camera_view != "overview")
    contact_csv_fp = None
    contact_csv_writer = None
    contact_sensor = None
    contact_map = None
    contact_meta_path = None

    if args_cli.video and args_cli.save_contact_csv:
        try:
            contact_sensor = env.unwrapped.scene.sensors.get("contact_forces", None)
            if contact_sensor is not None:
                contact_map, body_names = _resolve_contact_body_map(contact_sensor)
                csv_dir = os.path.join(log_dir, "videos", "play")
                os.makedirs(csv_dir, exist_ok=True)
                csv_path = os.path.join(csv_dir, f"contact_states_{args_cli.camera_view}.csv")
                contact_csv_fp = open(csv_path, "w", newline="", encoding="utf-8")
                contact_csv_writer = csv.writer(contact_csv_fp)
                contact_csv_writer.writerow(_build_contact_csv_header())
                print(f"[INFO] Contact CSV: {csv_path}")
                _print_contact_mapping(contact_map)

                contact_meta_path = os.path.join(csv_dir, f"contact_meta_{args_cli.camera_view}.json")
                contact_meta = {
                    "camera_view": args_cli.camera_view,
                    "contact_threshold": float(args_cli.contact_threshold),
                    "primary_contact_mode": args_cli.contact_primary_mode,
                    "sensor_name": "contact_forces",
                    "contact_modes": contact_map,
                    "sensor_body_names": body_names,
                    "raw_force_definition": {
                        "foot": "max over selected foot_link bodies of max-history ||net_forces_w||",
                        "toe": "max over selected toe_link bodies of max-history ||net_forces_w||",
                        "aggregate": "sum of selected foot_link+toe_link body forces after max-history reduction",
                    },
                }
                with open(contact_meta_path, "w", encoding="utf-8") as mf:
                    json.dump(contact_meta, mf, indent=2, ensure_ascii=False)
                print(f"[INFO] Contact meta: {contact_meta_path}")
            else:
                print("[WARN] contact_forces sensor not found. CSV export disabled.")
        except Exception as err:
            print(f"[WARN] Contact CSV init failed: {err}")
            contact_csv_writer = None
    # simulate environment
    while simulation_app.is_running():
        start_time = time.time()
        # run everything in inference mode
        with torch.inference_mode():
            # agent stepping
            actions = policy(obs)
            # env stepping
            obs, _, dones, _ = env.step(actions)
            # reset recurrent states for episodes that have terminated
            policy_nn.reset(dones)

        # Keep single-robot recordings centered by following base position.
        if follow_camera:
            try:
                robot = env.unwrapped.scene["robot"]
                base_pos = robot.data.root_pos_w[0]
                eye_off, look_off = _camera_offsets(args_cli.camera_view, args_cli.camera_zoom)
                eye = (
                    float(base_pos[0]) + eye_off[0],
                    float(base_pos[1]) + eye_off[1],
                    float(base_pos[2]) + eye_off[2],
                )
                lookat = (
                    float(base_pos[0]) + look_off[0],
                    float(base_pos[1]) + look_off[1],
                    float(base_pos[2]) + look_off[2],
                )
                env.unwrapped.sim.set_camera_view(eye, lookat)
            except Exception as err:
                if not camera_follow_error_logged:
                    print(f"[WARN] Camera follow disabled due to runtime error: {err}")
                    camera_follow_error_logged = True
                follow_camera = False
        if args_cli.video:
            timestep += 1

            # Write contact state aligned to recorded timestep.
            if contact_csv_writer is not None and contact_sensor is not None and contact_map is not None:
                try:
                    forces = contact_sensor.data.net_forces_w_history[0, :, :, :].norm(dim=-1).max(dim=0)[0]
                    contact_csv_writer.writerow(
                        _build_contact_csv_row(
                            timestep,
                            forces,
                            contact_map,
                            float(args_cli.contact_threshold),
                            args_cli.contact_primary_mode,
                        )
                    )
                except Exception as err:
                    print(f"[WARN] Contact CSV write failed at step {timestep}: {err}")

            # Exit the play loop after recording one video
            if timestep == args_cli.video_length:
                break

        # time delay for real-time evaluation
        sleep_time = dt - (time.time() - start_time)
        if args_cli.real_time and sleep_time > 0:
            time.sleep(sleep_time)

    # close file handle before simulator shutdown
    if contact_csv_fp is not None:
        try:
            contact_csv_fp.close()
        except Exception:
            pass

    # close the simulator
    env.close()


if __name__ == "__main__":
    # run the main function
    main()
    # close sim app
    simulation_app.close()
