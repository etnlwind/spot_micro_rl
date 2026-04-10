"""V63.J 코드 레벨 검증 스크립트.

1. TRAIN_VERSION, _IS_V63J 플래그 확인
2. rewards.py 에 alternation_trot_reward, per_leg_role_variance_penalty 존재 확인
3. env_cfg.py V63.J 블록 내 reward weight 검증
4. train.cmd RUN_NAME 확인
5. custom_mdp export 확인
"""
import sys
from pathlib import Path

BASE = Path("/mnt/d/project/spot_micro_rl")
REWARDS_PY = BASE / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py"
ENV_CFG_PY = BASE / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py"
INIT_PY = BASE / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/__init__.py"
TRAIN_CMD = BASE / "train.cmd"

errors = []
warnings = []

def check(cond, msg, warn=False):
    if not cond:
        if warn:
            warnings.append(msg)
        else:
            errors.append(msg)
    return cond

# === 1. TRAIN_VERSION ===
env_cfg = ENV_CFG_PY.read_text(encoding="utf-8")
check('TRAIN_VERSION = "V63.J"' in env_cfg, 'TRAIN_VERSION should be "V63.J"')
check('_IS_V63J = TRAIN_VERSION.startswith("V63.J")' in env_cfg, '_IS_V63J flag missing')
check('_IS_V63J' in env_cfg and 'if _IS_V63I or _IS_V63J:' in env_cfg, 'V63.J→V63.H inheritance missing')
check('_IS_V63J' in env_cfg and '_IS_V62 = True' in env_cfg, 'V63.J→V62 inheritance check')

# === 2. rewards.py functions ===
rewards = REWARDS_PY.read_text(encoding="utf-8")
check('def alternation_trot_reward(' in rewards, 'alternation_trot_reward function missing')
check('def per_leg_role_variance_penalty(' in rewards, 'per_leg_role_variance_penalty function missing')
check('def diagonal_pair_balance_penalty(' in rewards, 'diagonal_pair_balance_penalty should still exist (but None in cfg)')

# Ring buffer check
check('_v63j_contact_buf' in rewards, 'alternation ring buffer variable missing')
check('_v63j_buf_idx' in rewards, 'alternation ring buffer index missing')
check('half_cycle_steps' in rewards, 'half_cycle_steps calculation missing')

# Role variance EMA check
check('_v63j_push_ema' in rewards, 'push EMA variable missing')
check('_v63j_lift_ema' in rewards, 'lift EMA variable missing')
check('cv_push' in rewards, 'CV push calculation missing')
check('cv_lift' in rewards, 'CV lift calculation missing')

# Logging check
check('log_alternation_a' in rewards, 'alternation_a logging missing')
check('log_alternation_b' in rewards, 'alternation_b logging missing')
check('log_role_cv_push' in rewards, 'role_cv_push logging missing')
check('log_role_cv_lift' in rewards, 'role_cv_lift logging missing')
check('log_push_ema_fl' in rewards, 'per-leg push EMA logging missing')
check('log_lift_ema_fl' in rewards, 'per-leg lift EMA logging missing')

# === 3. env_cfg.py V63.J block ===
check('if _IS_V63J:' in env_cfg, 'V63.J conditional block missing')
check('alternation_trot' in env_cfg and 'weight=5.0' in env_cfg, 'alternation_trot weight=5.0 missing')
check('true_trot_pattern.weight = 2.0' in env_cfg, 'true_trot_pattern weight reduction 7→2 missing')
check('per_leg_role_variance' in env_cfg and 'weight=-2.0' in env_cfg, 'per_leg_role_variance weight=-2.0 missing')
check('diagonal_pair_balance = None' in env_cfg, 'diagonal_pair_balance removal missing')

# === 4. train.cmd ===
train_cmd = TRAIN_CMD.read_text(encoding="utf-8")
check('RUN_NAME=V63.J' in train_cmd, 'train.cmd RUN_NAME should be V63.J')

# === 5. __init__.py wildcard import ===
init = INIT_PY.read_text(encoding="utf-8")
check('from .rewards import *' in init, 'wildcard import missing — new functions wont be exported')

# === 6. Weight budget estimation ===
print("=" * 60)
print("V63.J REWARD WEIGHT BUDGET (estimated)")
print("=" * 60)
print()
print("POSITIVE rewards:")
print("  alternation_trot:        +5.0  (NEW, 주연)")
print("  true_trot_pattern:       +2.0  (7→2 약화)")
print("  swing_body_forward:      +4.0")
print("  effective_stride:        +5.0")
print("  clearance_lift:          +3.0")
print("  base_height_target:      +4.0")
print("  asymmetric_joint_target: +5.0")
print("  per_leg_stance_push_min: +2.0")
print("  stance_ratio_balance:    +5.0")
print("  track_lin_vel_xy_exp:    +4.0")
print("  track_ang_vel_z_exp:     +1.0")
print("  forward_velocity:        +3.0")
print("  flat_orientation_bonus:  +3.0")
print("  TOTAL POSITIVE:         ~46")
print()
print("NEGATIVE penalties:")
print("  per_leg_role_variance:   -2.0  (NEW)")
print("  per_leg_contact_min:     -8.0")
print("  shoulder_neutral:        -4.0")
print("  anti_pace:               -3.0")
print("  lateral_balance:         -2.0")
print("  leg_lr_symmetry:         -2.0")
print("  action_rate_l2:          -0.10")
print("  lin_vel_z_l2:            -2.0")
print("  ang_vel_xy_l2:           -1.0")
print("  flat_orientation_l2:     -2.0")
print("  dof_torques_l2:          -0.0001")
print("  TOTAL NEGATIVE:         ~-26")
print()
print("NET BUDGET:               ~+20 (healthy positive margin)")
print()

# === Results ===
print("=" * 60)
if errors:
    print(f"ERRORS: {len(errors)}")
    for e in errors:
        print(f"  [X] {e}")
else:
    print("ALL CHECKS PASSED")

if warnings:
    print(f"\nWARNINGS: {len(warnings)}")
    for w in warnings:
        print(f"  [!] {w}")

print("=" * 60)
sys.exit(1 if errors else 0)
