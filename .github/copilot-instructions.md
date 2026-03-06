# Copilot Instructions — SpotMicro RL

## Project Overview

Reinforcement learning (PPO via RSL-RL) training for a **SpotMicro quadruped robot** to walk with a **trot gait** (diagonal alternating) using **NVIDIA Isaac Lab v2.3.0**. The project follows the Isaac Lab extension template pattern — an installable Python package (`source/spot_micro_rl/`) registered as a Gymnasium environment.

## Tech Stack & Environment

- **Isaac Lab v2.3.0** / Isaac Sim 5.1.0.0, Python 3.10, conda env `env_isaaclab`
- **GPU**: NVIDIA RTX 5080 Laptop 16GB — runs 24,576 parallel envs headless
- **Isaac Lab path**: `C:\IsaacLab\isaaclab.bat` (Windows)
- **Branch**: `develop`

### Critical Execution Rules

```bash
# Always activate conda first (background terminals start in base)
conda activate env_isaaclab
cd D:\project\spot_micro_rl
pip install -e source/spot_micro_rl --quiet   # editable install

# Training (use isaaclab.bat -p, NOT python directly)
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=24576 --headless --max_iterations=15000

# Play/evaluate
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\play.py --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=50 --checkpoint=<path_to_model.pt>
```

- **NEVER** use `conda run` — it hangs. Always `conda activate` then run directly.
- **NEVER** pipe `Select-Object -First N` to a training process — it kills it. Use `isBackground: true`.
- No `wmic` on this system — use `psutil` for all process management.

## Architecture & Key Files

| Path | Role |
|------|------|
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py` | **Central config** — all reward weights, terrain, observations, terminations in `__post_init__()` |
| `source/.../mdp/rewards.py` | 25+ custom reward functions (torch tensors, `(num_envs,)` shape) |
| `source/.../mdp/__init__.py` | Re-exports: `from isaaclab.envs.mdp import *` then `from .rewards import *` |
| `source/.../agents/rsl_rl_ppo_cfg.py` | PPO hyperparameters (gamma=0.97, clip=0.1, lr=1e-4, network [512,256,128] ELU) |
| `source/.../robots/spot_micro.py` | URDF articulation config, DC motor, 12 joints (3 per leg × 4 legs) |
| `source/.../__init__.py` | Gymnasium env registration (4 envs: Flat, Rough, Rough-Play, SteepSlope-Play) |
| `scripts/rsl_rl/train.py` | Training entry point (uses Hydra + RSL-RL `OnPolicyRunner`) |
| `scripts/rsl_rl/play.py` | Evaluation/video recording entry point |
| `scripts/training_supervisor.py` | 3-hour cycle: stop→record video→analyze→Telegram report→resume |
| `scripts/training_heartbeat.py` | Non-invasive TensorBoard monitor, 100-iter Telegram reports |
| `.env` | Telegram creds, paths, training params (TASK, TRAIN_ENVS, MAX_ITERATIONS, etc.) |
| `plan/MEMORY.md` | AI session handoff — project context, version history, current state |

## Registered Environments

| ID | Use |
|----|-----|
| `Isaac-Velocity-Flat-SpotMicro-v0` | Primary flat terrain training |
| `Isaac-Velocity-Rough-SpotMicro-v0` | Rough terrain training (adds height_scan, 102-dim obs) |
| `Isaac-Velocity-Rough-SpotMicro-Play-v0` | Rough terrain evaluation |
| `Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0` | Flat model on steep slopes (48-dim obs) |

## Code Patterns & Conventions

### Reward Function Pattern
All custom rewards in `mdp/rewards.py` follow this signature:
```python
def my_reward(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg, ...) -> torch.Tensor:
    """Docstring in Korean or English."""
    asset: Articulation = env.scene[asset_cfg.name]
    # ... compute per-environment scalar reward
    return tensor_of_shape_num_envs  # (num_envs,)
```
- Velocity-gated rewards use `min_vel` param — reward is zero below this base velocity threshold
- Rewards are registered via `RewTerm(func=custom_mdp.xxx, weight=W, params={...})` in env_cfg `__post_init__()`
- Comments use Korean (한국어) for domain-specific notes; version tags like `# V17:` mark changes

### Environment Config Inheritance
```
LocomotionVelocityRoughEnvCfg (Isaac Lab base)
  └─ SpotMicroFlatEnvCfg          # Flat terrain, 48-dim obs, curriculum=None
       ├─ SpotMicroFlatEnvCfg_PLAY
       ├─ SpotMicroFlatOnSteepSlopePlayCfg
       └─ SpotMicroRoughEnvCfg     # Adds height_scan (102-dim obs), terrain curriculum
            └─ SpotMicroRoughEnvCfg_PLAY
```
Flat→Rough transfer uses `scripts/transfer_flat_to_rough.py` (48→102 obs dim, Xavier init for new height_scan weights).

### Naming Conventions
- Joint names: `{front|rear}_{left|right}_{shoulder|leg|foot}` (12 total)
- Body names: `base_link`, `*_shoulder_link`, `*_leg_link`, `*_foot_link`
- Sensor pattern in `SceneEntityCfg`: `body_names=".*foot_link"` for all 4 feet

### Logs & Checkpoints
- Training logs: `logs/rsl_rl/spot_micro_flat/<timestamp>/` (TensorBoard events + model_*.pt)
- Outputs: `outputs/<date>/<time>/` (Hydra)
- PID files: `logs/training_heartbeat.pid`, `logs/training_supervisor.pid`
- Maintenance flag: `logs/maintenance.flag` (mutual watchdog between supervisor & heartbeat)

## Lessons Learned (Critical for Reward Design)

1. **Contact-sensor rewards are exploitable** — robot learns micro-vibration to cheat. Use kinematic (joint velocity) rewards instead.
2. **Too many simultaneous penalties cause "stillness trap"** — robot minimizes loss by not moving. Use phased curriculum.
3. **PPO stability = gamma × reward_scale** — gamma 0.99→0.97 reduced returns 3×, fixing value_loss divergence.
4. **Critic reset + fine-tune fails with large reward changes** — train from scratch instead.
5. **Multiplication rewards `(A × B)` enforce "must do both"** — e.g., `rear_forward_stride = height × velocity`.

## Version History Context

Versions V1–V17.1 tracked in `plan/MEMORY.md`. Key milestones:
- V8: Flat baseline → V9–V12: Rough terrain (rear leg dragging problem)
- V13–V14: Critic reset attempts (all diverged)
- V15d: From-scratch stable PPO params (gamma=0.97, clip=0.1)
- V16: `diagonal_joint_coupling_reward` — kinematic trot enforcement
- V17/V17.1: Gait cycle period, stride length, action rate penalties
