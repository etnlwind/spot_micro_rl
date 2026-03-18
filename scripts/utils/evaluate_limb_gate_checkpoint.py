import argparse
import json
import os
import sys

from isaaclab.app import AppLauncher

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
RSL_RL_SCRIPT_DIR = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
for path in (RSL_RL_SCRIPT_DIR, SCRIPTS_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import cli_args  # isort: skip

parser = argparse.ArgumentParser(description="Replay checkpoint and evaluate limb-validity KPI")
parser.add_argument("--task", type=str, default="Isaac-Velocity-Flat-SpotMicro-v0")
parser.add_argument("--num_envs", type=int, default=1)
parser.add_argument("--steps", type=int, default=650)
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
args_cli.enable_cameras = False

sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

from rsl_rl.runners import DistillationRunner, OnPolicyRunner

from isaaclab.envs import DirectMARLEnv, DirectMARLEnvCfg, DirectRLEnvCfg, ManagerBasedRLEnvCfg, multi_agent_to_single_agent
from isaaclab.utils.assets import retrieve_file_path
from isaaclab_tasks.utils.hydra import hydra_task_config
from isaaclab_rl.rsl_rl import RslRlBaseRunnerCfg, RslRlVecEnvWrapper

import isaaclab_tasks  # noqa: F401
import spot_micro_rl.tasks  # noqa: F401

import common


def _to_float(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return float(value.item())
        except Exception:
            pass
    try:
        return float(value)
    except Exception:
        return None


def _extract_iteration(checkpoint_path: str) -> int:
    name = os.path.basename(checkpoint_path)
    if name.startswith("model_") and name.endswith(".pt"):
        try:
            return int(name[len("model_"):-len(".pt")])
        except ValueError:
            return 0
    return 0


@hydra_task_config(args_cli.task, "rsl_rl_cfg_entry_point")
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlBaseRunnerCfg):
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.seed = agent_cfg.seed
    resume_path = retrieve_file_path(args_cli.checkpoint)
    log_dir = os.path.dirname(resume_path)
    env_cfg.log_dir = log_dir
    if args_cli.device:
        agent_cfg.device = args_cli.device

    sim_env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
    if isinstance(sim_env.unwrapped, DirectMARLEnv):
        sim_env = multi_agent_to_single_agent(sim_env)
    rl_env = RslRlVecEnvWrapper(sim_env, clip_actions=agent_cfg.clip_actions)

    runner_cls = OnPolicyRunner if agent_cfg.class_name == "OnPolicyRunner" else DistillationRunner
    runner = runner_cls(rl_env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path)
    policy = runner.get_inference_policy(device=rl_env.unwrapped.device)

    obs = rl_env.get_observations()
    captured_log = None
    last_log_keys = []
    for _ in range(int(args_cli.steps)):
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, _, _ = rl_env.step(actions)
        log_payload = dict((rl_env.unwrapped.extras or {}).get("log", {}))
        if log_payload:
            last_log_keys = sorted(log_payload.keys())
            if "Episode_Reward/contact_ratio_fl" in log_payload:
                captured_log = log_payload
                break

    if captured_log is None:
        raise RuntimeError(
            f"No limb raw KPI extras captured within {args_cli.steps} steps. Last log keys: {last_log_keys[:20]}"
        )

    rewards = {}
    for key, value in captured_log.items():
        if key.startswith("Episode_Reward/"):
            rewards[key.replace("Episode_Reward/", "")] = _to_float(value)

    limb_metrics = common.compute_limb_validity_metrics(rewards)
    iteration = _extract_iteration(resume_path)
    kpi = common.build_supervisor_kpi_snapshot_for_iteration(log_dir, iteration)
    tb_data = common.read_tfevents(log_dir) or {}
    vf_loss = common._scalar_value_at_or_before(tb_data, "Loss/value_function", iteration) or 0.0
    hard_gate = bool(
        (kpi.get("survival_pct") or 0.0) >= 70.0
        and (kpi.get("fall_pct") is None or (kpi.get("fall_pct") or 0.0) <= 10.0)
        and vf_loss <= 5.0
        and (kpi.get("gait_score") or 0) >= 5
    )

    result = {
        "checkpoint": resume_path,
        "run_dir": log_dir,
        "iter": iteration,
        "hard_safety_gate_pass": hard_gate,
        "limb_validity_gate_pass": limb_metrics["limb_validity_gate_pass"],
        "limb_validity_reason": limb_metrics["limb_validity_reason"],
        "limb_usage_min": limb_metrics["limb_usage_min"],
        "limb_usage_variance": limb_metrics["limb_usage_variance"],
        "rear_left_right_usage_diff": limb_metrics["rear_left_right_usage_diff"],
        "front_left_right_usage_diff": limb_metrics["front_left_right_usage_diff"],
        "rear_left_right_propulsion_diff": limb_metrics["rear_left_right_propulsion_diff"],
        "contact_ratio_fl": rewards.get("contact_ratio_fl"),
        "contact_ratio_fr": rewards.get("contact_ratio_fr"),
        "contact_ratio_rl": rewards.get("contact_ratio_rl"),
        "contact_ratio_rr": rewards.get("contact_ratio_rr"),
        "stance_time_fl": rewards.get("stance_time_fl"),
        "stance_time_fr": rewards.get("stance_time_fr"),
        "stance_time_rl": rewards.get("stance_time_rl"),
        "stance_time_rr": rewards.get("stance_time_rr"),
        "swing_time_fl": rewards.get("swing_time_fl"),
        "swing_time_fr": rewards.get("swing_time_fr"),
        "swing_time_rl": rewards.get("swing_time_rl"),
        "swing_time_rr": rewards.get("swing_time_rr"),
        "propulsion_fl": rewards.get("propulsion_fl"),
        "propulsion_fr": rewards.get("propulsion_fr"),
        "propulsion_rl": rewards.get("propulsion_rl"),
        "propulsion_rr": rewards.get("propulsion_rr"),
        "leg_lift_fl": rewards.get("leg_lift_fl"),
        "leg_lift_fr": rewards.get("leg_lift_fr"),
        "leg_lift_rl": rewards.get("leg_lift_rl"),
        "leg_lift_rr": rewards.get("leg_lift_rr"),
        "clearance_fl": rewards.get("clearance_fl"),
        "clearance_fr": rewards.get("clearance_fr"),
        "clearance_rl": rewards.get("clearance_rl"),
        "clearance_rr": rewards.get("clearance_rr"),
        "limb_usage_fl": limb_metrics["limb_usage_scores"].get("fl"),
        "limb_usage_fr": limb_metrics["limb_usage_scores"].get("fr"),
        "limb_usage_rl": limb_metrics["limb_usage_scores"].get("rl"),
        "limb_usage_rr": limb_metrics["limb_usage_scores"].get("rr"),
        "survival_pct": kpi.get("survival_pct"),
        "fall_pct": kpi.get("fall_pct"),
        "gait_score": kpi.get("gait_score"),
        "posture_score": kpi.get("posture_score"),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    rl_env.close()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
