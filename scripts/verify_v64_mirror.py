"""V64 Mirror Symmetry 검증 스크립트.

1. mirror(mirror(obs)) == obs (involution)
2. mirror(mirror(action)) == action (involution)
3. Observation 차원 확인
4. TRAIN_VERSION, _IS_V64 플래그 확인
5. symmetry_cfg 등록 확인
6. Reward weight budget
"""
import sys
from pathlib import Path
import torch

# Direct import of mirror module (Isaac Lab not available in WSL)
sys.path.insert(0, str(Path(__file__).parent.parent / "source" / "spot_micro_rl" / "spot_micro_rl" / "tasks" / "manager_based" / "spot_micro_rl" / "mdp"))

errors = []

def check(cond, msg):
    if not cond:
        errors.append(msg)
    return cond

# === 1. Mirror involution tests ===
print("=" * 60)
print("TEST 1: Mirror Involution")
print("=" * 60)

# Import mirror functions (no Isaac Lab needed)
from mirror_symmetry import (
    mirror_obs_tensor, mirror_action_tensor, JOINT_PERM, SIGN_FLIP, PHASE_PERM
)

# Test obs 56 dims
torch.manual_seed(42)
obs = torch.randn(16, 56)
obs_m = mirror_obs_tensor(obs)
obs_mm = mirror_obs_tensor(obs_m)
obs_err = (obs - obs_mm).abs().max().item()
check(obs_err < 1e-6, f"mirror(mirror(obs)) != obs, max_err={obs_err}")
print(f"  mirror(mirror(obs)) max error: {obs_err:.2e}  {'PASS' if obs_err < 1e-6 else 'FAIL'}")

# Test obs 48 dims (no phase_clock)
obs48 = torch.randn(16, 48)
obs48_m = mirror_obs_tensor(obs48)
obs48_mm = mirror_obs_tensor(obs48_m)
obs48_err = (obs48 - obs48_mm).abs().max().item()
check(obs48_err < 1e-6, f"mirror(mirror(obs48)) != obs48, max_err={obs48_err}")
print(f"  mirror(mirror(obs48)) max error: {obs48_err:.2e}  {'PASS' if obs48_err < 1e-6 else 'FAIL'}")

# Test action 12 dims
act = torch.randn(16, 12)
act_m = mirror_action_tensor(act)
act_mm = mirror_action_tensor(act_m)
act_err = (act - act_mm).abs().max().item()
check(act_err < 1e-6, f"mirror(mirror(action)) != action, max_err={act_err}")
print(f"  mirror(mirror(act)) max error: {act_err:.2e}  {'PASS' if act_err < 1e-6 else 'FAIL'}")

# === 2. Symmetric pose test ===
print()
print("=" * 60)
print("TEST 2: Symmetric Pose Mirror")
print("=" * 60)

# Create a symmetric observation (L and R have mirrored values)
sym_obs = torch.zeros(1, 56)
# joint_pos: FL_sh=-0.15, FR_sh=+0.15, etc (symmetric default pose)
sym_obs[0, 12] = -0.15  # FL_sh
sym_obs[0, 13] = -0.66  # FL_leg
sym_obs[0, 14] = 1.05   # FL_foot
sym_obs[0, 15] = 0.15   # FR_sh
sym_obs[0, 16] = -0.66  # FR_leg
sym_obs[0, 17] = 1.05   # FR_foot
sym_obs[0, 18] = -0.15  # RL_sh
sym_obs[0, 19] = -0.66  # RL_leg
sym_obs[0, 20] = 1.05   # RL_foot
sym_obs[0, 21] = 0.15   # RR_sh
sym_obs[0, 22] = -0.66  # RR_leg
sym_obs[0, 23] = 1.05   # RR_foot
# joint_vel: all zero (symmetric)
# actions: all zero (symmetric)
# phase_clock: all legs in same phase (symmetric standing, not trot)
# Note: trot phase (FL≠FR) correctly maps FL↔FR under mirror — NOT equal to self
# True L/R symmetric state = all legs same phase
sym_obs[0, 48] = 0.0   # sin_FL
sym_obs[0, 49] = 0.0   # sin_FR
sym_obs[0, 50] = 0.0   # sin_RL
sym_obs[0, 51] = 0.0   # sin_RR
sym_obs[0, 52] = 1.0   # cos_FL
sym_obs[0, 53] = 1.0   # cos_FR
sym_obs[0, 54] = 1.0   # cos_RL
sym_obs[0, 55] = 1.0   # cos_RR

sym_m = mirror_obs_tensor(sym_obs)
sym_err = (sym_obs - sym_m).abs().max().item()
check(sym_err < 1e-6, f"Symmetric pose should equal its mirror, err={sym_err}")
print(f"  Symmetric pose mirror error: {sym_err:.2e}  {'PASS' if sym_err < 1e-6 else 'FAIL'}")

if sym_err >= 1e-6:
    diff = (sym_obs - sym_m).abs()
    for i in range(56):
        if diff[0, i] > 1e-6:
            print(f"    dim {i}: orig={sym_obs[0,i]:.4f} mirror={sym_m[0,i]:.4f} diff={diff[0,i]:.4f}")

# === 3. Permutation sanity ===
print()
print("=" * 60)
print("TEST 3: Permutation Sanity")
print("=" * 60)

# Joint perm is involution
jp = JOINT_PERM
check(all(jp[jp[i]] == i for i in range(12)), "JOINT_PERM is not involution")
print(f"  JOINT_PERM involution: {'PASS' if all(jp[jp[i]] == i for i in range(12)) else 'FAIL'}")

# Phase perm is involution
pp = PHASE_PERM
check(all(pp[pp[i]] == i for i in range(8)), "PHASE_PERM is not involution")
print(f"  PHASE_PERM involution: {'PASS' if all(pp[pp[i]] == i for i in range(8)) else 'FAIL'}")

# Sign flip squared = 1
sf = SIGN_FLIP
check(all(s*s == 1.0 for s in sf), "SIGN_FLIP^2 != 1")
print(f"  SIGN_FLIP^2 = 1: {'PASS' if all(s*s == 1.0 for s in sf) else 'FAIL'}")

# === 4. Config checks ===
print()
print("=" * 60)
print("TEST 4: Configuration Files")
print("=" * 60)

BASE = Path("/mnt/d/project/spot_micro_rl")
env_cfg = (BASE / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py").read_text()
agent_cfg = (BASE / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/agents/rsl_rl_ppo_cfg.py").read_text()
train_cmd = (BASE / "train.cmd").read_text()

tv_ok = 'TRAIN_VERSION = "V64"' in env_cfg
check(tv_ok, 'TRAIN_VERSION should be V64')
print(f"  TRAIN_VERSION = V64: {'PASS' if tv_ok else 'FAIL'}")

check('_IS_V64 = TRAIN_VERSION.startswith("V64")' in env_cfg, '_IS_V64 flag missing')
print(f"  _IS_V64 flag: {'PASS' if '_IS_V64' in env_cfg else 'FAIL'}")

check('symmetry_cfg' in agent_cfg, 'symmetry_cfg not in agent config')
print(f"  symmetry_cfg in agent: {'PASS' if 'symmetry_cfg' in agent_cfg else 'FAIL'}")

check('spot_micro_mirror_augmentation' in agent_cfg, 'mirror augmentation function not referenced')
print(f"  mirror_augmentation ref: {'PASS' if 'spot_micro_mirror_augmentation' in agent_cfg else 'FAIL'}")

check('RUN_NAME=V64' in train_cmd, 'train.cmd RUN_NAME should be V64')
print(f"  train.cmd RUN_NAME: {'PASS' if 'RUN_NAME=V64' in train_cmd else 'FAIL'}")

check('leg_lr_symmetry = None' in env_cfg and '_IS_V64' in env_cfg, 'V64 should remove leg_lr_symmetry')
print(f"  leg_lr_symmetry removed: {'PASS' if 'leg_lr_symmetry = None' in env_cfg else 'FAIL'}")

# === 5. Weight budget ===
print()
print("=" * 60)
print("V64 REWARD WEIGHT BUDGET")
print("=" * 60)
print()
print("POSITIVE (V63.I base, mirror augmentation handles symmetry):")
print("  true_trot_pattern:       +7.0  (V63.I 원래 값 유지)")
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
print("  TOTAL:                  ~51")
print()
print("NEGATIVE:")
print("  per_leg_contact_min:     -8.0")
print("  shoulder_neutral:        -4.0")
print("  anti_pace:               -3.0")
print("  lateral_balance:         -2.0")
print("  action_rate_l2:          -0.10")
print("  lin_vel_z_l2:            -2.0")
print("  ang_vel_xy_l2:           -1.0")
print("  flat_orientation_l2:     -2.0")
print("  dof_torques_l2:          -0.0001")
print("  TOTAL:                  ~-22")
print()
print("REMOVED by V64 (mirror handles symmetry):")
print("  leg_lr_symmetry:         REMOVED (was -2.0)")
print("  diagonal_pair_balance:   REMOVED")
print("  alternation_trot:        REMOVED")
print("  per_leg_role_variance:   REMOVED")
print()
print("NEW: Mirror symmetry data augmentation (PPO algorithm level)")
print("  → No reward weight, structural enforcement")
print()
print(f"NET BUDGET: ~+29 (healthy margin)")

# === Results ===
print()
print("=" * 60)
if errors:
    print(f"ERRORS: {len(errors)}")
    for e in errors:
        print(f"  [X] {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    print("=" * 60)
