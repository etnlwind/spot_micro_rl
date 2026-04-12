"""Record V63.I trajectory data for reference mining.

play.py 와 동일한 Hydra + OnPolicyRunner 인프라 사용.
policy rollout 중 joint/foot/root 데이터를 JSON으로 저장.

사용법 (play.cmd와 동일한 패턴):
  isaaclab.bat -p scripts/rsl_rl/record_trajectory.py ^
    --task Isaac-Velocity-Flat-SpotMicro-v0 ^
    --num_envs 16 --headless ^
    --load_run 2026-04-10_02-14-50_V63.I --checkpoint model_4999.pt
"""
import argparse
import sys
import os
import json

from isaaclab.app import AppLauncher

import cli_args  # isort: skip

parser = argparse.ArgumentParser(description="Record trajectory from trained policy.")
parser.add_argument("--num_envs", type=int, default=16)
parser.add_argument("--task", type=str, default=None)
parser.add_argument("--agent", type=str, default="rsl_rl_cfg_entry_point")
parser.add_argument("--record_steps", type=int, default=1000, help="Number of steps to record")
parser.add_argument("--output", type=str, default="logs/v63i_trajectory.json")
cli_args.add_rsl_rl_args(parser)
AppLauncher.add_app_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
sys.argv = [sys.argv[0]] + hydra_args

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import time
import torch
import numpy as np

from rsl_rl.runners import OnPolicyRunner

from isaaclab.envs import ManagerBasedRLEnvCfg, DirectRLEnvCfg, DirectMARLEnvCfg
from isaaclab_rl.rsl_rl import RslRlBaseRunnerCfg, RslRlVecEnvWrapper

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import get_checkpoint_path
from isaaclab_tasks.utils.hydra import hydra_task_config

import spot_micro_rl.tasks  # noqa: F401


@hydra_task_config(args_cli.task, args_cli.agent)
def main(env_cfg: ManagerBasedRLEnvCfg | DirectRLEnvCfg | DirectMARLEnvCfg, agent_cfg: RslRlBaseRunnerCfg):
    agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
    env_cfg.scene.num_envs = args_cli.num_envs
    env_cfg.sim.device = args_cli.device if args_cli.device else env_cfg.sim.device

    # Disable noise for clean recording
    env_cfg.observations.policy.enable_corruption = False
    env_cfg.events.base_external_force_torque = None
    env_cfg.events.push_robot = None

    log_root = os.path.join("logs", "rsl_rl", agent_cfg.experiment_name)
    log_root = os.path.abspath(log_root)
    print(f"[INFO] Log root: {log_root}")
    print(f"[INFO] load_run: {agent_cfg.load_run}")
    print(f"[INFO] load_checkpoint: {agent_cfg.load_checkpoint}")
    resume_path = get_checkpoint_path(log_root, agent_cfg.load_run, agent_cfg.load_checkpoint)
    print(f"[INFO] Resume path: {resume_path}")

    # Create env
    env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
    env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

    # Load policy
    runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
    runner.load(resume_path)
    policy = runner.get_inference_policy(device=env.unwrapped.device)

    robot = env.unwrapped.scene["robot"]
    dt = env.unwrapped.step_dt
    joint_names = robot.data.joint_names
    body_names = robot.data.body_names

    print(f"[INFO] Recording {args_cli.record_steps} steps, dt={dt}")
    print(f"[INFO] Joint names: {joint_names}")

    # Find toe body indices
    toe_ids = [i for i, name in enumerate(body_names) if 'toe' in name]
    toe_names = [body_names[i] for i in toe_ids]
    print(f"[INFO] Toe bodies: {toe_names} (ids: {toe_ids})")

    # Record
    records = []
    obs = env.get_observations()

    for step in range(args_cli.record_steps):
        with torch.inference_mode():
            actions = policy(obs)
            obs, _, dones, _ = env.step(actions)

            # Record env 0
            rec = {
                's': step,
                't': round(step * dt, 4),
                'jp': [round(x, 5) for x in robot.data.joint_pos[0].cpu().tolist()],
                'jv': [round(x, 5) for x in robot.data.joint_vel[0].cpu().tolist()],
                'act': [round(x, 5) for x in actions[0].cpu().tolist()],
                'rp': [round(x, 4) for x in robot.data.root_pos_w[0].cpu().tolist()],
                'rv': [round(x, 4) for x in robot.data.root_lin_vel_b[0].cpu().tolist()],
                'ra': [round(x, 4) for x in robot.data.root_ang_vel_b[0].cpu().tolist()],
            }

            # Toe positions (world frame)
            if toe_ids:
                rec['tp'] = [[round(x, 4) for x in robot.data.body_pos_w[0, tid].cpu().tolist()] for tid in toe_ids]

            records.append(rec)

        if step % 100 == 0:
            vx = robot.data.root_lin_vel_b[0, 0].item()
            vy = robot.data.root_lin_vel_b[0, 1].item()
            print(f"  step {step}/{args_cli.record_steps}: vx={vx:.3f} vy={vy:.3f}")

    # Save
    output_path = os.path.abspath(args_cli.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    data = {
        'meta': {
            'checkpoint': resume_path,
            'steps': args_cli.record_steps,
            'dt': dt,
            'joint_names': joint_names,
            'toe_names': toe_names,
            'toe_ids': toe_ids,
        },
        'data': records,
    }

    with open(output_path, 'w') as f:
        json.dump(data, f)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n[INFO] Saved {len(records)} steps to {output_path} ({size_kb:.1f} KB)")
    env.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
