# Contributing to spot_micro_rl

Thank you for your interest in contributing to **spot_micro_rl**.
This repository is a research-oriented project that combines RL training
code, experiment plans, and analysis documents. Contributions are welcome
in the form of bug reports, reproductions, analysis, new experiments, or
documentation improvements.

## License of contributions

By submitting a contribution (pull request, patch, issue with code snippets,
etc.), you agree that your contribution will be licensed under the
**Apache License, Version 2.0**, the same license as this project.

See `LICENSE` and `NOTICE` for details.

## How to contribute

### 1. Bug reports
- Open a GitHub issue with:
  - the exact run name / checkpoint / command you used
  - the Isaac Lab / Isaac Sim / GPU / OS version
  - a minimal reproduction if possible
  - log excerpts (not entire 100 MB logs)

### 2. Reproducing a version
- Pick a `plan/VXX_PLAN.md` and try to reproduce the reported metrics
- Please open an issue or PR with your delta: "matched / did not match, reason"
- This repository values **negative reproducibility reports** as highly as successes

### 3. Code changes
- Follow the rules in `CLAUDE.md` (project conventions), notably:
  - **no inline Python** — always write `.py` files
  - **no inline bash loops** — write `.sh` scripts
  - clear `__pycache__` after editing source (WSL2 stale pyc issue)
- Keep commits focused; one logical change per commit
- Use descriptive commit messages in Korean or English — both are fine
- Avoid adding unrelated refactors to a feature/fix PR

### 4. New experiments (new version)
- Create `plan/VXX_PLAN.md` first with:
  - hypothesis
  - changed parameters
  - expected effect
  - failure criteria
  - success criteria
  - risks
- Run the experiment, then update the plan with actual results
- This "plan-first, data-after" pattern is the core discipline of this project

### 5. Documentation
- Typo fixes, clarification, translation — welcome
- If you change the meaning of an existing plan document, please add a
  dated note ("Updated YYYY-MM-DD: ...") rather than silently overwriting

## Code style

- Python: follow existing module conventions; no enforced linter yet
- Tensors: be explicit about device and dtype
- Reward functions: always log `raw` values to TensorBoard via `env.extras`
- New reward terms: must include a per-step budget estimate (positive vs negative balance)

## Research discipline

This is a research repository, not product code. Please:

- **Distinguish "works on my machine" from "reproducible"** — provide seeds, num_envs, MAX_ITER
- **Never claim a version "succeeds" without GUI verification** — contact ratio alone is not enough (V67 lesson)
- **Preserve best checkpoints, not final checkpoints** — V68 lesson: `model_2500` was best, not `model_4999`
- **Document failures** — negative results save future time

## Questions

Open an issue or email <etnlwind@gmail.com>.
