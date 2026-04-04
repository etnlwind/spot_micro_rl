"""Search for ideal standing pose via loaded equilibrium measurement.

Methodology:
  1. Generate candidate poses: grid over (shoulder, leg, foot)
  2. ALL randomization OFF (events individually disabled)
  3. Root state explicitly fixed (identity rotation, zero velocity)
  4. Drop under gravity with zero action, measure steady-state
  5. Score: height + low drop + symmetry + low splay + low torque

Usage:
  isaaclab.bat -p scripts/utils/find_ideal_stance.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless
  isaaclab.bat -p scripts/utils/find_ideal_stance.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless --mode=single
  isaaclab.bat -p scripts/utils/find_ideal_stance.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless --mode=fine --leg_center=-0.52 --shoulder_center=0.04
  isaaclab.bat -p scripts/utils/find_ideal_stance.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --headless --mode=foot_sweep --leg_center=-0.52
"""

import argparse
import math
import os
import sys
from datetime import datetime

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", type=str, required=True)
parser.add_argument("--steps", type=int, default=500)
parser.add_argument(
    "--mode",
    type=str,
    default="grid",
    choices=["grid", "single", "fine", "foot_sweep", "binary"],
    help="grid: 4x4 shoulder x leg, single: current init only, "
         "fine: narrow search around center, foot_sweep: leg fixed + foot independent, "
         "binary: iterative binary search (3 rounds, front/rear asymmetry)",
)
parser.add_argument("--leg_center", type=float, default=-0.52)
parser.add_argument("--shoulder_center", type=float, default=0.04)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym
import torch

import isaaclab_tasks  # noqa: F401
import spot_micro_rl.tasks  # noqa: F401
from isaaclab_tasks.utils import parse_env_cfg


class TeeLogger:
    """Write to both stdout and a log file. Line-buffered to survive crashes."""
    def __init__(self, log_path: str):
        self.terminal = sys.stdout
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        # buffering=1 = line-buffered (flush on every newline)
        self.log = open(log_path, "w", encoding="utf-8", buffering=1)

    def write(self, msg):
        try:
            self.terminal.write(msg)
        except Exception:
            pass
        try:
            self.log.write(msg)
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
        except Exception:
            pass
        try:
            self.log.flush()
        except Exception:
            pass

    def close(self):
        try:
            self.log.flush()
            self.log.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_matching_foot(leg_angle: float) -> float:
    """Choose foot angle so toe x-offset is near zero in FK."""
    target_sin = (0.01 * math.cos(leg_angle) - 0.12 * math.sin(leg_angle)) / 0.115
    target_sin = max(-1.0, min(1.0, target_sin))
    total_angle = math.asin(target_sin)
    foot = total_angle - leg_angle
    return max(-0.07, min(1.81, foot))


def compute_fk(leg: float, foot: float) -> tuple[float, float]:
    """Return (toe_x_mm, toe_height_m) relative to shoulder."""
    total = leg + foot
    toe_x = -0.01 * math.cos(leg) + (-0.12) * math.sin(leg) + (-0.115) * math.sin(total)
    toe_z = 0.01 * math.sin(leg) + (-0.12) * math.cos(leg) + (-0.115) * math.cos(total)
    height = -toe_z + 0.02
    return toe_x * 1000.0, height


def quat_to_euler(quat: torch.Tensor) -> torch.Tensor:
    """Convert wxyz quaternions to roll, pitch, yaw."""
    w, x, y, z = quat[:, 0], quat[:, 1], quat[:, 2], quat[:, 3]
    roll = torch.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = torch.asin(torch.clamp(2 * (w * y - z * x), -1, 1))
    yaw = torch.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return torch.stack([roll, pitch, yaw], dim=1)


def disable_events(env_cfg) -> None:
    """Make the probe deterministic: no reset/startup randomization."""
    if not hasattr(env_cfg, "events") or env_cfg.events is None:
        return
    for name in [
        "physics_material",
        "add_base_mass",
        "base_com",
        "base_external_force_torque",
        "reset_base",
        "push_robot",
        "reset_robot_joints",
    ]:
        if hasattr(env_cfg.events, name):
            setattr(env_cfg.events, name, None)


def build_candidates(mode: str, shoulder_center: float, leg_center: float) -> list[dict]:
    """Build candidate list based on mode."""
    if mode == "single":
        return [{"shoulder": 0.04, "leg": -0.52, "foot": 0.87, "label": "current_init"}]

    if mode == "foot_sweep":
        sh, lg = shoulder_center, leg_center
        foot_vals = [0.60, 0.70, 0.75, 0.80, 0.85, 0.87, 0.90, 0.95,
                     1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50]
        return [{"shoulder": sh, "leg": lg, "foot": f, "label": f"foot={f:.2f}"} for f in foot_vals]

    if mode == "fine":
        sh_vals = [shoulder_center - 0.02, shoulder_center - 0.01, shoulder_center, shoulder_center + 0.01]
        leg_vals = [leg_center - 0.10, leg_center - 0.05, leg_center, leg_center + 0.05]
    else:  # grid
        sh_vals = [0.00, 0.02, 0.04, 0.06]
        leg_vals = [-0.70, -0.52, -0.40, -0.25]

    candidates = []
    for sh in sh_vals:
        for lg in leg_vals:
            ft = compute_matching_foot(lg)
            candidates.append({"shoulder": max(0.0, sh), "leg": lg, "foot": ft,
                               "label": f"sh={sh:.3f}_lg={lg:.3f}"})
    return candidates


def linspace(low: float, high: float, n: int) -> list[float]:
    if n == 1:
        return [(low + high) / 2]
    return [low + i * (high - low) / (n - 1) for i in range(n)]


def symmetry_penalty(
    avg_jp: torch.Tensor,
    joint_pos_init: torch.Tensor,
    short_names: list[str],
    env_idx: int,
) -> dict[str, float]:
    """Compute LR asymmetry, FR asymmetry, and splay separately."""
    lr_penalty = 0.0
    fr_penalty = 0.0
    splay_penalty = 0.0

    for pair in [("FL", "FR"), ("RL", "RR")]:
        for jtype in ["sho", "leg", "foo"]:
            li = short_names.index(f"{pair[0]}_{jtype}")
            ri = short_names.index(f"{pair[1]}_{jtype}")
            lv = avg_jp[env_idx, li].item()
            rv = avg_jp[env_idx, ri].item()
            asym = lv + rv if jtype == "sho" else lv - rv
            lr_penalty += abs(math.degrees(asym))

    for jtype in ["leg", "foo"]:
        fi = short_names.index(f"FL_{jtype}")
        ri = short_names.index(f"RL_{jtype}")
        fr_penalty += abs(math.degrees(avg_jp[env_idx, fi].item() - avg_jp[env_idx, ri].item()))

    for j_idx, sn in enumerate(short_names):
        if "sho" in sn:
            spread = abs(avg_jp[env_idx, j_idx].item()) - abs(joint_pos_init[env_idx, j_idx].item())
            splay_penalty += max(0.0, math.degrees(spread))

    return {"lr_deg": lr_penalty, "fr_deg": fr_penalty, "splay_deg": splay_penalty}


# ---------------------------------------------------------------------------
# Simulation runner (shared by all modes)
# ---------------------------------------------------------------------------

def run_sim(candidates: list[dict], steps: int, verbose: bool = True) -> list[dict]:
    """Run zero-action simulation for candidates. Returns list of result dicts with ttf, height, etc."""
    n = len(candidates)

    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=n, use_fabric=True)
    env_cfg.terminations = None
    env_cfg.rewards = None
    env_cfg.commands.base_velocity.rel_standing_envs = 1.0
    env_cfg.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
    disable_events(env_cfg)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env.reset()

    robot = env.unwrapped.scene["robot"]
    joint_names = robot.joint_names
    device = env.unwrapped.device
    nj = len(joint_names)

    # Set init poses
    joint_pos_init = torch.zeros(n, nj, device=device)
    for j_idx, name in enumerate(joint_names):
        for env_idx, c in enumerate(candidates):
            if "shoulder" in name:
                sign = -1.0 if "left" in name else 1.0
                joint_pos_init[env_idx, j_idx] = sign * c["shoulder"]
            elif "leg" in name:
                if "front" in name:
                    joint_pos_init[env_idx, j_idx] = c.get("front_leg", c["leg"])
                else:
                    joint_pos_init[env_idx, j_idx] = c.get("rear_leg", c["leg"])
            elif "foot" in name:
                if "front" in name:
                    joint_pos_init[env_idx, j_idx] = c.get("front_foot", c["foot"])
                else:
                    joint_pos_init[env_idx, j_idx] = c.get("rear_foot", c["foot"])

    root_state = robot.data.default_root_state.clone()
    root_state[:, :] = 0.0
    root_state[:, 3] = 1.0
    for env_idx, c in enumerate(candidates):
        fl = c.get("front_leg", c["leg"])
        ff = c.get("front_foot", c["foot"])
        _, fk_h = compute_fk(fl, ff)
        root_state[env_idx, 0] = env.unwrapped.scene.env_origins[env_idx, 0]
        root_state[env_idx, 1] = env.unwrapped.scene.env_origins[env_idx, 1]
        root_state[env_idx, 2] = env.unwrapped.scene.env_origins[env_idx, 2] + fk_h - 0.004

    robot.write_root_state_to_sim(root_state)
    robot.write_joint_state_to_sim(joint_pos_init, torch.zeros_like(joint_pos_init))

    # Time-to-fall tracking
    fall_threshold_rad = math.radians(30.0)
    time_to_fall = torch.full((n,), float(steps), device=device)

    # Detailed per-step log: height, pitch, roll for every candidate at key steps
    detail_steps = list(range(1, min(101, steps + 1))) + list(range(110, steps + 1, 10))
    detail_log = []  # list of (step, heights[], pitches[], rolls[])

    # Accumulate pitch in first 50% (before fall) for quality assessment
    pitch_sum_early = torch.zeros(n, device=device)
    pitch_count_early = torch.zeros(n, device=device)

    try:
        with torch.inference_mode():
            for step in range(1, steps + 1):
                actions = torch.zeros(env.action_space.shape, device=device)
                env.step(actions)
                heights = robot.data.root_pos_w[:, 2] - env.unwrapped.scene.env_origins[:, 2]
                rpy = quat_to_euler(robot.data.root_quat_w)

                pitch_abs = rpy[:, 1].abs()
                roll_abs = rpy[:, 0].abs()
                roll_from_upright = torch.min(roll_abs, math.pi - roll_abs)
                falling = (pitch_abs > fall_threshold_rad) | (roll_from_upright > fall_threshold_rad)
                newly_fallen = falling & (time_to_fall == float(steps))
                time_to_fall[newly_fallen] = float(step)

                # Accumulate pitch before fall (per-env)
                still_standing = time_to_fall == float(steps)
                pitch_sum_early[still_standing] += pitch_abs[still_standing]
                pitch_count_early[still_standing] += 1

                # Detailed log at key steps
                if step in detail_steps:
                    detail_log.append((
                        step,
                        heights.cpu().tolist(),
                        [math.degrees(rpy[i, 1].item()) for i in range(n)],
                        [math.degrees(rpy[i, 0].item()) for i in range(n)],
                    ))

                if verbose and step % 10 == 0:
                    survived = (time_to_fall == float(steps)).sum().item()
                    if step <= 100 or step % 50 == 0:
                        print(f"  step {step}: survived={survived}/{n}", flush=True)
    finally:
        env.close()

    # Average pitch while standing (lower = more horizontal)
    avg_pitch_standing = torch.where(
        pitch_count_early > 0,
        pitch_sum_early / pitch_count_early,
        torch.full_like(pitch_sum_early, math.pi / 2),  # default = 90deg if never stood
    )

    # Print detailed step-by-step log
    if verbose:
        print(f"\n--- Detailed Step Log (height mm / pitch deg) ---", flush=True)
        header = f"{'step':>5}"
        for i in range(n):
            header += f" {'h'+str(i):>7} {'p'+str(i):>6}"
        print(header)
        for step, hs, ps, rs in detail_log:
            line = f"{step:5d}"
            for i in range(n):
                line += f" {hs[i]*1000:7.1f} {ps[i]:+6.1f}"
            print(line, flush=True)

    # Build results
    results = []
    for i in range(n):
        results.append({
            "idx": i,
            "candidate": candidates[i],
            "ttf": time_to_fall[i].item(),
            "avg_pitch_deg": math.degrees(avg_pitch_standing[i].item()),
            "joint_pos_loaded": {joint_names[j]: joint_pos_init[i, j].item() for j in range(nj)},
        })
    return results


# ---------------------------------------------------------------------------
# Binary search mode
# ---------------------------------------------------------------------------

def compute_foot_for_toe_shift(leg_angle: float, toe_shift_mm: float) -> float:
    """Compute foot angle that places toe at (shoulder_x + toe_shift) in FK.
    toe_shift_mm > 0 = toes forward, < 0 = toes backward.
    """
    # Target: toe_x = toe_shift_mm / 1000
    # toe_x = -0.01*cos(leg) + (-0.12)*sin(leg) + (-0.115)*sin(leg+foot)
    # => sin(leg+foot) = (toe_shift/1000 + 0.01*cos(leg) + 0.12*sin(leg)) / (-0.115)
    target_x = toe_shift_mm / 1000.0
    val = -(target_x + 0.01 * math.cos(leg_angle) + 0.12 * math.sin(leg_angle)) / 0.115
    # Note: the original equation has -0.01*cos + (-0.12)*sin + (-0.115)*sin(total) = target_x
    # => (-0.115)*sin(total) = target_x + 0.01*cos - (-0.12*sin)
    # Let me redo carefully:
    # toe_x = -0.01*cos(L) - 0.12*sin(L) - 0.115*sin(L+F) = target_x
    # => -0.115*sin(L+F) = target_x + 0.01*cos(L) + 0.12*sin(L)
    # => sin(L+F) = -(target_x + 0.01*cos(L) + 0.12*sin(L)) / 0.115
    val = -(target_x + 0.01 * math.cos(leg_angle) + 0.12 * math.sin(leg_angle)) / 0.115
    val = max(-1.0, min(1.0, val))
    total = math.asin(val)
    foot = total - leg_angle
    return max(-0.07, min(1.81, foot))


def run_binary_search() -> None:
    """Binary search for optimal horizontal stance via CoM balancing.

    Key insight: body must stay HORIZONTAL (same leg angles front/rear).
    Search variables:
      - leg angle (same for all 4 legs = horizontal body)
      - toe_shift (moves all toes forward/backward = shifts support polygon)
      - shoulder (splay)
    The toe_shift that gives longest ttf = CoM directly over support polygon center.
    """
    rounds = 3
    steps = args_cli.steps
    n_per_round = 16

    # Search ranges
    leg_lo, leg_hi = -0.80, -0.20
    shift_lo, shift_hi = -30.0, 30.0  # toe shift in mm
    sh_lo, sh_hi = 0.00, 0.06

    print(f"=== Binary Search: Horizontal Stance + CoM Balance ===")
    print(f"Rounds: {rounds}, Candidates/round: {n_per_round}, Steps: {steps}")
    print(f"Search: leg=[{leg_lo:.2f},{leg_hi:.2f}] toe_shift=[{shift_lo:.0f},{shift_hi:.0f}]mm sh=[{sh_lo:.2f},{sh_hi:.2f}]")
    print(f"\nConstraint: front_leg = rear_leg (horizontal body)")
    print(f"toe_shift > 0 = toes forward, < 0 = toes backward")

    best_overall = None

    for rnd in range(1, rounds + 1):
        print(f"\n{'='*70}")
        print(f"=== Round {rnd}/{rounds} ===")
        print(f"Ranges: leg=[{leg_lo:.3f},{leg_hi:.3f}] shift=[{shift_lo:.1f},{shift_hi:.1f}]mm sh=[{sh_lo:.3f},{sh_hi:.3f}]")

        # 2 shoulder x 2 leg x 4 toe_shift = 16 candidates
        sh_vals = linspace(sh_lo, sh_hi, 2)
        leg_vals = linspace(leg_lo, leg_hi, 2)
        shift_vals = linspace(shift_lo, shift_hi, 4)

        candidates = []
        for sh in sh_vals:
            for lg in leg_vals:
                for ts in shift_vals:
                    ft = compute_foot_for_toe_shift(lg, ts)
                    toe_x_mm, fk_h = compute_fk(lg, ft)
                    candidates.append({
                        "shoulder": max(0.0, sh),
                        "leg": lg,
                        "foot": ft,
                        "toe_shift": ts,
                        "toe_x_actual": toe_x_mm,
                        "fk_h": fk_h,
                        "label": f"sh={sh:.3f}_lg={lg:.3f}_ts={ts:+.0f}",
                    })

        candidates = candidates[:n_per_round]

        print(f"\n{'idx':>4} {'sh':>6} {'leg':>7} {'foot':>7} {'shift':>6} {'toe_x':>7} {'fk_h':>7}")
        print("-" * 55)
        for i, c in enumerate(candidates):
            print(f"{i:4d} {c['shoulder']:6.3f} {c['leg']:7.3f} {c['foot']:7.3f} "
                  f"{c['toe_shift']:+6.0f} {c['toe_x_actual']:+7.1f} {c['fk_h']*1000:7.1f}")

        # Run simulation
        results = run_sim(candidates, steps, verbose=True)

        # Score: ttf dominates (body is horizontal by construction)
        for r in results:
            r["score"] = r["ttf"] - r["avg_pitch_deg"] * 0.5

        results.sort(key=lambda r: r["score"], reverse=True)

        print(f"\n--- Round {rnd} Results ---")
        print(f"{'rank':>5} {'idx':>4} {'sh':>6} {'leg':>7} {'shift':>6} "
              f"{'ttf':>5} {'pitch':>6} {'fk_h':>7} {'SCORE':>7}")
        print("-" * 65)
        for rank, r in enumerate(results):
            c = r["candidate"]
            marker = " <--" if rank == 0 else ""
            print(f"{rank+1:5d} {r['idx']:4d} {c['shoulder']:6.3f} {c['leg']:7.3f} "
                  f"{c['toe_shift']:+6.0f} {r['ttf']:5.0f} {r['avg_pitch_deg']:+6.1f} "
                  f"{c['fk_h']*1000:7.1f} {r['score']:7.1f}{marker}")

        # Narrow to top half
        top_half = results[:max(1, len(results) // 2)]
        sh_top = [r["candidate"]["shoulder"] for r in top_half]
        leg_top = [r["candidate"]["leg"] for r in top_half]
        shift_top = [r["candidate"]["toe_shift"] for r in top_half]

        margin_lg = (leg_hi - leg_lo) * 0.15
        margin_ts = (shift_hi - shift_lo) * 0.15
        margin_sh = (sh_hi - sh_lo) * 0.15

        leg_lo = min(leg_top) - margin_lg
        leg_hi = max(leg_top) + margin_lg
        shift_lo = min(shift_top) - margin_ts
        shift_hi = max(shift_top) + margin_ts
        sh_lo = max(0.0, min(sh_top) - margin_sh)
        sh_hi = max(sh_top) + margin_sh

        best_overall = results[0]

    # Final result
    c = best_overall["candidate"]
    print(f"\n{'='*70}")
    print(f"=== BINARY SEARCH RESULT ===")
    print(f"{'='*70}")
    print(f"Score: {best_overall['score']:.1f} (ttf={best_overall['ttf']:.0f}, avg_pitch={best_overall['avg_pitch_deg']:+.1f}d)")
    print(f"  shoulder:  {c['shoulder']:.4f}")
    print(f"  leg:       {c['leg']:.4f} (all 4 legs, horizontal body)")
    print(f"  foot:      {c['foot']:.4f}")
    print(f"  toe_shift: {c['toe_shift']:+.1f}mm (from shoulder-vertical)")
    print(f"  FK height: {c['fk_h']*1000:.1f}mm")
    print(f"  toe_x:     {c['toe_x_actual']:+.1f}mm (actual)")
    if c["toe_shift"] > 0:
        print(f"\n  -> CoM is FORWARD of body center: toes shifted {c['toe_shift']:+.0f}mm forward to compensate")
    elif c["toe_shift"] < 0:
        print(f"\n  -> CoM is REARWARD of body center: toes shifted {c['toe_shift']:+.0f}mm backward to compensate")
    else:
        print(f"\n  -> CoM is at body center")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Log all output to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "logs", "stance_search")
    log_path = os.path.join(log_dir, f"stance_{args_cli.mode}_{timestamp}.log")
    tee = TeeLogger(log_path)
    original_stdout = sys.stdout
    sys.stdout = tee
    try:
        _main_inner(tee, log_path)
    except Exception as e:
        print(f"\n!!! ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise
    finally:
        sys.stdout = original_stdout
        tee.close()
        print(f"\nLog saved: {log_path}")


def _main_inner(tee: TeeLogger, log_path: str) -> None:
    print(f"Log file: {log_path}")

    if args_cli.mode == "binary":
        run_binary_search()
        return

    steps = args_cli.steps
    candidates = build_candidates(args_cli.mode, args_cli.shoulder_center, args_cli.leg_center)
    n = len(candidates)

    print(f"=== Ideal Stance Search ({args_cli.mode}) ===")
    print(f"Candidates: {n}, Steps: {steps}")
    print(f"\n{'idx':>4} {'shoulder':>9} {'leg':>8} {'foot':>8} {'fk_h_mm':>8} {'toe_x_mm':>9} label")
    print("-" * 72)
    for i, c in enumerate(candidates):
        toe_x_mm, fk_h = compute_fk(c["leg"], c["foot"])
        print(f"{i:4d} {c['shoulder']:9.3f} {c['leg']:8.3f} {c['foot']:8.3f} "
              f"{fk_h * 1000:8.1f} {toe_x_mm:+9.1f} {c['label']}")

    # --- Create env: disable randomization, keep commands (observation needs base_velocity) ---
    env_cfg = parse_env_cfg(args_cli.task, device=args_cli.device, num_envs=n, use_fabric=True)
    env_cfg.terminations = None
    env_cfg.rewards = None
    env_cfg.commands.base_velocity.rel_standing_envs = 1.0
    env_cfg.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
    env_cfg.commands.base_velocity.ranges.ang_vel_z = (0.0, 0.0)
    disable_events(env_cfg)

    env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
    env.reset()

    robot = env.unwrapped.scene["robot"]
    joint_names = robot.joint_names
    device = env.unwrapped.device
    nj = len(joint_names)

    short_names = []
    for name in joint_names:
        parts = name.split("_")
        short_names.append(f"{parts[0][0].upper()}{parts[1][0].upper()}_{parts[2][:3]}")

    # --- Set init poses with explicit root state ---
    joint_pos_init = torch.zeros(n, nj, device=device)
    for j_idx, name in enumerate(joint_names):
        for env_idx, c in enumerate(candidates):
            if "shoulder" in name:
                sign = -1.0 if "left" in name else 1.0
                joint_pos_init[env_idx, j_idx] = sign * c["shoulder"]
            elif "leg" in name:
                joint_pos_init[env_idx, j_idx] = c["leg"]
            elif "foot" in name:
                joint_pos_init[env_idx, j_idx] = c["foot"]

    root_state = robot.data.default_root_state.clone()
    root_state[:, :] = 0.0
    root_state[:, 3] = 1.0  # identity quaternion wxyz
    for env_idx, c in enumerate(candidates):
        _, fk_h = compute_fk(c["leg"], c["foot"])
        root_state[env_idx, 0] = env.unwrapped.scene.env_origins[env_idx, 0]
        root_state[env_idx, 1] = env.unwrapped.scene.env_origins[env_idx, 1]
        root_state[env_idx, 2] = env.unwrapped.scene.env_origins[env_idx, 2] + fk_h - 0.004

    robot.write_root_state_to_sim(root_state)
    robot.write_joint_state_to_sim(joint_pos_init, torch.zeros_like(joint_pos_init))

    # --- Simulate ---
    print(f"\nSettling {steps} steps (zero action, deterministic)...", flush=True)

    settle_start = steps * 3 // 4
    jp_sum = torch.zeros(n, nj, device=device)
    jv_sum = torch.zeros(n, nj, device=device)
    jt_sum = torch.zeros(n, nj, device=device)
    h_sum = torch.zeros(n, device=device)
    roll_sum = torch.zeros(n, device=device)
    pitch_sum = torch.zeros(n, device=device)
    count = 0
    fell_flags = torch.zeros(n, dtype=torch.bool, device=device)
    # Time-to-fall: first step where |pitch| > 30 deg
    fall_threshold_rad = math.radians(30.0)
    time_to_fall = torch.full((n,), float(steps), device=device)  # default = survived all steps

    snap_steps = [1, 5, 10, 25, 50, 75, 100, 150, 200, steps]
    snapshots = {}

    with torch.inference_mode():
        for step in range(1, steps + 1):
            actions = torch.zeros(env.action_space.shape, device=device)
            env.step(actions)
            heights = robot.data.root_pos_w[:, 2] - env.unwrapped.scene.env_origins[:, 2]
            rpy = quat_to_euler(robot.data.root_quat_w)
            fell_flags |= heights < 0.10

            # Track time-to-fall (first crossing)
            pitch_abs = rpy[:, 1].abs()
            roll_abs = rpy[:, 0].abs()
            # Fall = pitch > 30deg OR roll > 30deg (but roll ~180 = flipped, so use min(roll, 180-roll))
            roll_from_upright = torch.min(roll_abs, math.pi - roll_abs)
            falling = (pitch_abs > fall_threshold_rad) | (roll_from_upright > fall_threshold_rad)
            newly_fallen = falling & (time_to_fall == float(steps))
            time_to_fall[newly_fallen] = float(step)

            if step in snap_steps:
                snapshots[step] = {
                    "jp": robot.data.joint_pos.clone(),
                    "h": heights.clone(),
                    "roll": rpy[:, 0].clone(),
                    "pitch": rpy[:, 1].clone(),
                }

            if step >= settle_start:
                jp_sum += robot.data.joint_pos
                jv_sum += robot.data.joint_vel.abs()
                if hasattr(robot.data, "applied_torque"):
                    jt_sum += robot.data.applied_torque.abs()
                h_sum += heights
                roll_sum += rpy[:, 0].abs()
                pitch_sum += rpy[:, 1].abs()
                count += 1

            if step % 50 == 0:
                survived = (time_to_fall == float(steps)).sum().item()
                print(f"  step {step}: h[0]={heights[0].item():.4f} "
                      f"survived={survived}/{n}", flush=True)

    env.close()

    # --- Averages ---
    avg_jp = jp_sum / count
    avg_jv = jv_sum / count
    avg_jt = jt_sum / count
    avg_h = h_sum / count
    avg_roll = roll_sum / count
    avg_pitch = pitch_sum / count

    # --- Scoring ---
    print(f"\n{'='*110}")
    print(f"=== LOADED EQUILIBRIUM RESULTS (last {count}/{steps} steps, deterministic) ===")
    print(f"{'='*110}")
    print(f"\n{'idx':>4} {'sh':>5} {'leg':>6} {'foot':>6} "
          f"{'h_fk':>6} {'h_ld':>6} {'ttf':>5} "
          f"{'roll':>5} {'pitch':>6} {'lr':>5} {'fr':>5} {'splay':>6} {'vel':>5} {'trq':>5} {'SCORE':>7}")
    print("-" * 110)

    scores = []
    for i, c in enumerate(candidates):
        _, fk_h = compute_fk(c["leg"], c["foot"])
        h_ld = avg_h[i].item()
        h_drop = fk_h - h_ld
        roll_d = math.degrees(avg_roll[i].item())
        pitch_d = math.degrees(avg_pitch[i].item())
        vel_t = avg_jv[i].sum().item()
        trq_t = avg_jt[i].sum().item()
        sym = symmetry_penalty(avg_jp, joint_pos_init, short_names, i)
        ttf = time_to_fall[i].item()

        # Score: time-to-fall dominates (longer = better)
        score = 0.0
        score += ttf * 1.0                          # survival time (most important)
        score += h_ld * 5.0                         # tall stance
        score -= abs(h_drop) * 10.0                 # close to equilibrium
        score -= vel_t * 0.1                        # settled
        score -= trq_t * 0.02                       # energy efficient
        score -= sym["lr_deg"] * 0.10               # left-right symmetric
        score -= sym["fr_deg"] * 0.05               # front-rear symmetric
        score -= sym["splay_deg"] * 0.30            # no outward splay

        scores.append(score)
        print(f"{i:4d} {c['shoulder']:5.3f} {c['leg']:6.3f} {c['foot']:6.3f} "
              f"{fk_h * 1000:6.1f} {h_ld * 1000:6.1f} {ttf:5.0f} "
              f"{roll_d:5.2f} {pitch_d:6.2f} {sym['lr_deg']:5.1f} {sym['fr_deg']:5.1f} {sym['splay_deg']:6.2f} "
              f"{vel_t:5.3f} {trq_t:5.2f} {score:7.3f}")

    best_idx = max(range(n), key=lambda i: scores[i])
    c_best = candidates[best_idx]
    print(f"\n>>> BEST: idx={best_idx}  sh={c_best['shoulder']:.3f} leg={c_best['leg']:.3f} "
          f"foot={c_best['foot']:.3f}  score={scores[best_idx]:.3f}")

    # --- Best candidate detail ---
    print(f"\n{'joint':>10} {'init':>8} {'loaded':>8} {'drift':>8} {'drift_d':>8} {'vel':>8} {'torque':>8}")
    print("-" * 68)
    for j in range(nj):
        iv = joint_pos_init[best_idx, j].item()
        lv = avg_jp[best_idx, j].item()
        dr = lv - iv
        print(f"{short_names[j]:>10} {iv:8.4f} {lv:8.4f} {dr:+8.4f} {math.degrees(dr):+8.2f} "
              f"{avg_jv[best_idx, j].item():8.4f} {avg_jt[best_idx, j].item():8.4f}")

    # Symmetry detail
    print(f"\n--- Symmetry (|asym| < 1d=GOOD, <3d=OK, >=3d=BAD) ---")
    for pair in [("FL", "FR"), ("RL", "RR")]:
        for jtype in ["sho", "leg", "foo"]:
            li = short_names.index(f"{pair[0]}_{jtype}")
            ri = short_names.index(f"{pair[1]}_{jtype}")
            lv = avg_jp[best_idx, li].item()
            rv = avg_jp[best_idx, ri].item()
            asym = (lv + rv) if jtype == "sho" else (lv - rv)
            ad = abs(math.degrees(asym))
            tag = "GOOD" if ad < 1 else ("OK" if ad < 3 else "BAD")
            print(f"  {pair[0]}_{jtype} vs {pair[1]}_{jtype}: "
                  f"{lv:+.4f} vs {rv:+.4f} | {math.degrees(asym):+.2f}d [{tag}]")

    print(f"\n  Front vs Rear:")
    for jtype in ["leg", "foo"]:
        fl = avg_jp[best_idx, short_names.index(f"FL_{jtype}")].item()
        rl = avg_jp[best_idx, short_names.index(f"RL_{jtype}")].item()
        print(f"  FL_{jtype}={fl:+.4f}  RL_{jtype}={rl:+.4f}  diff={math.degrees(fl - rl):+.2f}d")

    # Splay detail
    print(f"\n--- Shoulder Splay ---")
    for j_idx, sn in enumerate(short_names):
        if "sho" in sn:
            iv = joint_pos_init[best_idx, j_idx].item()
            lv = avg_jp[best_idx, j_idx].item()
            spread = abs(lv) - abs(iv)
            label = "SPREAD" if spread > 0.005 else ("TUCK" if spread < -0.005 else "HOLD")
            print(f"  {sn}: init={iv:+.4f} loaded={lv:+.4f} "
                  f"{label} ({math.degrees(spread):+.2f}d)")

    # Time-to-fall ranking (all candidates)
    print(f"\n--- Time-to-Fall Ranking (all candidates) ---")
    ttf_order = sorted(range(n), key=lambda i: time_to_fall[i].item(), reverse=True)
    print(f"{'rank':>5} {'idx':>4} {'sh':>5} {'leg':>6} {'foot':>6} {'ttf':>6} {'h_fk':>7}")
    for rank, i in enumerate(ttf_order):
        c = candidates[i]
        _, fk_h = compute_fk(c["leg"], c["foot"])
        marker = " <-- BEST" if i == best_idx else ""
        print(f"{rank+1:5d} {i:4d} {c['shoulder']:5.3f} {c['leg']:6.3f} {c['foot']:6.3f} "
              f"{time_to_fall[i].item():6.0f} {fk_h*1000:7.1f}{marker}")

    # All candidates height at snapshot times
    print(f"\n--- Height at Key Steps (all candidates) ---")
    header = f"{'idx':>4} {'ttf':>5}"
    for st in sorted(snapshots.keys()):
        header += f" {'s'+str(st):>7}"
    print(header)
    for i in range(n):
        line = f"{i:4d} {time_to_fall[i].item():5.0f}"
        for st in sorted(snapshots.keys()):
            line += f" {snapshots[st]['h'][i].item()*1000:7.1f}"
        print(line)

    # Time evolution (best only)
    print(f"\n--- Time Evolution (best) ---")
    fl_sho_i = short_names.index("FL_sho")
    fl_leg_i = short_names.index("FL_leg")
    fl_foo_i = short_names.index("FL_foo")
    print(f"{'step':>6} {'height':>8} {'roll_d':>7} {'pitch_d':>8} {'FL_sh':>7} {'FL_leg':>7} {'FL_foo':>7}")
    for st in sorted(snapshots.keys()):
        s = snapshots[st]
        print(f"  {st:5d} {s['h'][best_idx].item():8.4f} "
              f"{math.degrees(s['roll'][best_idx].item()):+7.2f} "
              f"{math.degrees(s['pitch'][best_idx].item()):+8.2f} "
              f"{s['jp'][best_idx, fl_sho_i].item():+7.4f} "
              f"{s['jp'][best_idx, fl_leg_i].item():+7.4f} "
              f"{s['jp'][best_idx, fl_foo_i].item():+7.4f}")

    # Candidate output
    print(f"\n{'='*70}")
    print(f"=== CANDIDATE LOADED EQUILIBRIUM (requires --mode=fine validation) ===")
    print(f"{'='*70}")
    _, fk_h = compute_fk(c_best["leg"], c_best["foot"])
    h_ld = avg_h[best_idx].item()
    print(f"# Init (FK): h={fk_h * 1000:.1f}mm, Loaded: h={h_ld * 1000:.1f}mm, drop={((fk_h - h_ld) * 1000):+.1f}mm")
    for j in range(nj):
        lv = avg_jp[best_idx, j].item()
        iv = joint_pos_init[best_idx, j].item()
        print(f'#   {joint_names[j]}: {lv:.4f}  (init={iv:.4f}, drift={math.degrees(lv - iv):+.1f}d)')

    # Score breakdown
    print(f"\n--- Score Breakdown ---")
    _, fk_h = compute_fk(c_best["leg"], c_best["foot"])
    h_ld = avg_h[best_idx].item()
    h_drop = fk_h - h_ld
    roll_d = math.degrees(avg_roll[best_idx].item())
    pitch_d = math.degrees(avg_pitch[best_idx].item())
    sym = symmetry_penalty(avg_jp, joint_pos_init, short_names, best_idx)
    vel_t = avg_jv[best_idx].sum().item()
    trq_t = avg_jt[best_idx].sum().item()
    print(f"  height:   {h_ld:.4f}m         -> {h_ld * 10:.3f}")
    print(f"  h_drop:   {h_drop * 1000:+.1f}mm       -> {-abs(h_drop) * 20:.3f}")
    print(f"  tilt:     R={roll_d:.2f} P={pitch_d:.2f}d  -> {-(roll_d + pitch_d) * 0.5:.3f}")
    print(f"  lr_sym:   {sym['lr_deg']:.1f}d           -> {-sym['lr_deg'] * 0.20:.3f}")
    print(f"  fr_sym:   {sym['fr_deg']:.1f}d           -> {-sym['fr_deg'] * 0.10:.3f}")
    print(f"  splay:    {sym['splay_deg']:.2f}d         -> {-sym['splay_deg'] * 0.50:.3f}")
    print(f"  velocity: {vel_t:.3f}            -> {-vel_t * 0.2:.3f}")
    print(f"  torque:   {trq_t:.2f}             -> {-trq_t * 0.05:.3f}")
    print(f"  TOTAL:                       {scores[best_idx]:.3f}")


if __name__ == "__main__":
    main()
    simulation_app.close()
