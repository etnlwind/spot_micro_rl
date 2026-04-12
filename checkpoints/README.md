# Checkpoints

This directory holds **preserved best checkpoints** from training runs.
Only checkpoints that represent a meaningful milestone (successful version,
best-of-run, deployable policy) are committed to the repository.

## Current contents

### `V68_model_2500_best.pt`

| Field | Value |
|-------|-------|
| Source run | `logs/rsl_rl/spot_micro_flat/2026-04-12_12-26-08_V68/model_2500.pt` |
| Training version | V68 (Reference Trajectory Tracking) |
| Iteration | 2500 / 5000 |
| Size | 4,682,677 B (≈4.47 MB) |
| Format | rsl_rl PPO checkpoint (`model_state_dict` + `optimizer_state_dict` + `iter`) |
| Task | `Isaac-Velocity-Flat-SpotMicro-v0` |
| num_envs (train) | 4096 |
| Observation | 48-dim |
| Action | 12-dim joint position target |
| Gait frequency | 2.00 Hz |
| Forward speed | 0.308 m/s |
| Symmetry diff | 1.5 %p |
| Stride | 4.40 |
| Timeout | 100 % |
| GUI judgment | "looks like proper walking" (user) |

**Why this checkpoint, not `model_4999`**: V68 training reaches its best
symmetric trot around iter 2000~2700 and then the symmetry re-biases in
the late phase (see `plan/V68_PLAN.md` §5.2). The mid-training checkpoint
is the deployable one, not the final one.

**Required companion file**: `logs/ideal_trot_reference.json` (7.1 KB).
This checkpoint's policy was trained against that reference trajectory;
playing or resuming requires the same file to be present at the same path.

## How to play

From the project root on Windows:

```cmd
:: If you have the original run directory
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt

:: Or restore the preserved copy into the run directory first
copy checkpoints\V68_model_2500_best.pt logs\rsl_rl\spot_micro_flat\2026-04-12_12-26-08_V68\model_2500.pt
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt
```

Internally this runs `scripts/rsl_rl/play.py` with 16 environments by
default and opens an Isaac Sim GUI window.

## How to resume

```cmd
resume.cmd 2026-04-12_12-26-08_V68 model_2500.pt 5000 V69.A
```

Note: because V68's late-phase re-biasing is not yet solved, a simple
resume without structural changes is likely to reproduce the same
degradation. Consider pairing resume with domain randomization, rough
terrain, or a modified reward schedule.

## License

All trained weights in this directory are original works produced by
training on the author's hardware, and are released under the same
**Apache License, Version 2.0** as the rest of this repository.
See `LICENSE` and `NOTICE` in the project root.

When using these weights in publications or derivative work, please
also cite this repository as described in `CITATION.cff`.
