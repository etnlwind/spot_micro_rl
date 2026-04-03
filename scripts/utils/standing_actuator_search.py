# Copyright (c) 2022-2025, The Isaac Lab Project Developers
# SPDX-License-Identifier: BSD-3-Clause

"""Search zero-action standing actuator gains with step-halving coordinate search.

Focus:
    Reduce the initial rebound after contact while keeping long zero-action stability.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser(description="Search zero-action standing actuator gains for SpotMicro.")
parser.add_argument("--task", type=str, required=True, help="Task name.")
parser.add_argument("--num_envs", type=int, default=16, help="Number of environments.")
parser.add_argument("--steps", type=int, default=120, help="Zero-action steps per evaluation.")
parser.add_argument("--contact_threshold", type=float, default=1.0)
parser.add_argument("--stiffness", type=float, default=8.0)
parser.add_argument("--damping", type=float, default=3.0)
parser.add_argument("--stiffness_step", type=float, default=2.0)
parser.add_argument("--damping_step", type=float, default=1.0)
parser.add_argument("--stiffness_min_step", type=float, default=0.5)
parser.add_argument("--damping_min_step", type=float, default=0.25)
parser.add_argument("--stiffness_min", type=float, default=2.0)
parser.add_argument("--stiffness_max", type=float, default=18.0)
parser.add_argument("--damping_min", type=float, default=0.5)
parser.add_argument("--damping_max", type=float, default=8.0)
parser.add_argument("--max_passes", type=int, default=6)
parser.add_argument(
    "--log_file",
    type=str,
    default="logs/diagnostics/standing_actuator_search_latest.log",
    help="Log file path.",
)
parser.add_argument(
    "--checkpoint_file",
    type=str,
    default="logs/diagnostics/standing_actuator_search_latest.json",
    help="Checkpoint JSON path.",
)
parser.add_argument("--disable_fabric", action="store_true", default=False)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg

import spot_micro_rl.tasks  # noqa: F401
from spot_micro_rl.robots import SPOT_MICRO_CFG


def _make_logger(path_str: str):
    log_path = Path(path_str)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")

    def log(line: str):
        print(line)
        handle.write(line + "\n")
        handle.flush()

    return log, handle, log_path


def _write_checkpoint(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _set_actuator_gains(stiffness: float, damping: float):
    SPOT_MICRO_CFG.actuators["legs"].stiffness = {".*": float(stiffness)}
    SPOT_MICRO_CFG.actuators["legs"].damping = {".*": float(damping)}


def _clamp(name: str, value: float) -> float:
    if name == "stiffness":
        return min(max(value, args_cli.stiffness_min), args_cli.stiffness_max)
    return min(max(value, args_cli.damping_min), args_cli.damping_max)


def _toe_contact(env, threshold: float) -> torch.Tensor:
    robot = env.scene["robot"]
    toe_ids = env._actuator_search_toe_body_ids
    contact_sensor = env.scene.sensors["contact_forces"]
    forces = contact_sensor.data.net_forces_w_history[:, 0, toe_ids]
    return (torch.norm(forces, dim=-1) > threshold).float()


def _evaluate(stiffness: float, damping: float) -> dict[str, float]:
    _set_actuator_gains(stiffness, damping)
    env_cfg = parse_env_cfg(
        args_cli.task,
        device=args_cli.device,
        num_envs=args_cli.num_envs,
        use_fabric=not args_cli.disable_fabric,
    )
    env = gym.make(args_cli.task, cfg=env_cfg)
    env.reset()
    env = env.unwrapped
    robot = env.scene["robot"]
    env._actuator_search_toe_body_ids = torch.tensor(
        [
            robot.find_bodies(name)[0][0]
            for name in ["front_left_toe_link", "front_right_toe_link", "rear_left_toe_link", "rear_right_toe_link"]
        ],
        device=env.device,
        dtype=torch.long,
    )
    root_pos0 = robot.data.root_pos_w.clone()

    height_series = []
    ang_series = []
    drift_series = []
    toe_series = []
    terminated = torch.zeros(env.num_envs, dtype=torch.bool, device=env.device)
    time_outs = torch.zeros_like(terminated)

    with torch.inference_mode():
        for _ in range(args_cli.steps):
            actions = torch.zeros((env.num_envs, env.action_manager.total_action_dim), device=env.device)
            _, _, terminated, time_outs, _ = env.step(actions)
            height = robot.data.root_pos_w[:, 2] - env.scene.env_origins[:, 2]
            roots_xy = robot.data.root_pos_w[:, :2] - root_pos0[:, :2]
            drift_xy = torch.norm(roots_xy, dim=1)
            ang_xy = torch.norm(robot.data.root_ang_vel_b[:, :2], dim=1)
            toe_contact = _toe_contact(env, args_cli.contact_threshold).mean(dim=1)
            height_series.append(height.mean().item())
            drift_series.append(drift_xy.mean().item())
            ang_series.append(ang_xy.mean().item())
            toe_series.append(toe_contact.mean().item())
            if not simulation_app.is_running():
                break

    env.close()

    init_height = height_series[0]
    peak_height = max(height_series)
    overshoot = max(0.0, peak_height - init_height)
    metrics = {
        "stiffness": float(stiffness),
        "damping": float(damping),
        "init_height": float(init_height),
        "peak_height": float(peak_height),
        "height_20": float(height_series[min(19, len(height_series) - 1)]),
        "overshoot": float(overshoot),
        "toe_contact_mean": float(sum(toe_series) / len(toe_series)),
        "toe_contact_20": float(toe_series[min(19, len(toe_series) - 1)]),
        "drift_20": float(drift_series[min(19, len(drift_series) - 1)]),
        "ang_20": float(ang_series[min(19, len(ang_series) - 1)]),
        "drift_final": float(drift_series[-1]),
        "ang_final": float(ang_series[-1]),
        "terminated_frac": float(terminated.float().mean().item()),
        "time_out_frac": float(time_outs.float().mean().item()),
        "mean_ep_len": float(env.episode_length_buf.float().mean().item()),
    }
    metrics["score"] = _score(metrics)
    return metrics


def _score(m: dict[str, float]) -> float:
    return (
        2.0 * m["toe_contact_mean"]
        + 1.5 * m["toe_contact_20"]
        + 0.8 * m["mean_ep_len"] / max(args_cli.steps, 1)
        - 8.0 * m["overshoot"]
        - 2.0 * m["terminated_frac"]
        - 1.2 * m["drift_20"]
        - 0.8 * m["ang_20"]
        - 0.4 * m["drift_final"]
        - 0.2 * m["ang_final"]
    )


def _format(prefix: str, m: dict[str, float]) -> str:
    return (
        f"{prefix}"
        f" | score={m['score']:.4f}"
        f" | stiffness={m['stiffness']:.3f}"
        f" damping={m['damping']:.3f}"
        f" | init_h={m['init_height']:.4f}"
        f" peak_h={m['peak_height']:.4f}"
        f" over={m['overshoot']:.4f}"
        f" | toe20={m['toe_contact_20']:.4f}"
        f" toe_mean={m['toe_contact_mean']:.4f}"
        f" | drift20={m['drift_20']:.4f}"
        f" ang20={m['ang_20']:.4f}"
        f" | driftF={m['drift_final']:.4f}"
        f" angF={m['ang_final']:.4f}"
        f" | term={m['terminated_frac']:.4f}"
        f" ep={m['mean_ep_len']:.2f}"
    )


def _adaptive_line_search(current: dict[str, float], best: dict[str, float], key: str, step_size: float, log):
    probes = []
    for direction in (-1.0, 1.0):
        candidate = dict(current)
        candidate[key] = _clamp(key, candidate[key] + direction * step_size)
        metrics = _evaluate(candidate["stiffness"], candidate["damping"])
        probes.append((direction, metrics))
        log(_format(f"[TRY] key={key} step={direction * step_size:+.4f}", metrics))

    direction, trial_best = max(probes, key=lambda item: item[1]["score"])
    if trial_best["score"] <= best["score"]:
        return current, best, False

    current = {"stiffness": trial_best["stiffness"], "damping": trial_best["damping"]}
    best = trial_best
    log(_format(f"[ACCEPT] key={key} step={direction * step_size:+.4f}", best))

    while simulation_app.is_running():
        candidate = dict(current)
        candidate[key] = _clamp(key, candidate[key] + direction * step_size)
        if candidate[key] == current[key]:
            break
        metrics = _evaluate(candidate["stiffness"], candidate["damping"])
        log(_format(f"[EXTEND] key={key} step={direction * step_size:+.4f}", metrics))
        if metrics["score"] <= best["score"]:
            break
        current = {"stiffness": metrics["stiffness"], "damping": metrics["damping"]}
        best = metrics
        log(_format("[ACCEPT] extend", best))

    return current, best, True


def main():
    log, handle, log_path = _make_logger(args_cli.log_file)
    checkpoint_path = Path(args_cli.checkpoint_file)
    current = {"stiffness": args_cli.stiffness, "damping": args_cli.damping}
    best = None
    step_sizes = {"stiffness": args_cli.stiffness_step, "damping": args_cli.damping_step}
    min_steps = {"stiffness": args_cli.stiffness_min_step, "damping": args_cli.damping_min_step}

    try:
        log(f"[INFO] log_file={log_path}")
        log(f"[INFO] checkpoint_file={checkpoint_path}")
        best = _evaluate(current["stiffness"], current["damping"])
        log(_format("[INIT]", best))
        _write_checkpoint(checkpoint_path, {"status": "running", "phase": "init", "best": best, "current": current})

        coordinate_order = ["stiffness", "damping"]
        for pass_idx in range(1, args_cli.max_passes + 1):
            log(f"[PASS] index={pass_idx}")
            improved_in_pass = False
            active = False
            for key in coordinate_order:
                if step_sizes[key] < min_steps[key]:
                    continue
                active = True
                current, best, improved = _adaptive_line_search(current, best, key, step_sizes[key], log)
                _write_checkpoint(
                    checkpoint_path,
                    {
                        "status": "running",
                        "phase": "search",
                        "pass_idx": pass_idx,
                        "active_key": key,
                        "best": best,
                        "current": current,
                        "step_sizes": step_sizes,
                    },
                )
                if improved:
                    improved_in_pass = True
                else:
                    step_sizes[key] *= 0.5
                    log(f"[SHRINK] key={key} new_step={step_sizes[key]:.4f}")
            if not active:
                log("[PASS] all_steps_below_min")
                break
            if not improved_in_pass:
                log("[PASS] no_improvement")

        log(_format("[BEST]", best))
        _write_checkpoint(
            checkpoint_path,
            {"status": "completed", "phase": "done", "best": best, "current": current, "step_sizes": step_sizes},
        )
    except Exception:
        log("[ERROR] standing_actuator_search crashed")
        for line in traceback.format_exc().splitlines():
            log(line)
        if best is not None:
            log(_format("[BEST_SO_FAR]", best))
            _write_checkpoint(
                checkpoint_path,
                {"status": "error", "phase": "exception", "best": best, "current": current, "step_sizes": step_sizes},
            )
        raise
    finally:
        if best is not None:
            log(_format("[FINAL_BEST_SO_FAR]", best))
        handle.close()


if __name__ == "__main__":
    main()
    simulation_app.close()
