"""V63.F 구현 최종 검증."""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REWARDS = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py"
ENV_CFG = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py"
TRAIN_CMD = REPO / "train.cmd"


def main() -> int:
    ok = True

    # Syntax
    for p, lbl in [(REWARDS, "rewards.py"), (ENV_CFG, "env_cfg.py")]:
        try:
            with open(p) as f:
                ast.parse(f.read())
            print(f"[OK] {lbl}: SYNTAX")
        except SyntaxError as e:
            print(f"[FAIL] {lbl}: {e}")
            ok = False

    # Functions exist
    with open(REWARDS) as f:
        tree = ast.parse(f.read())
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in [
        "phase_joint_target_linear_reward",
        "metric_clearance_mean_reward",
        "metric_anti_phase_contact_reward",
        "metric_leg_usage_cv_reward",
        "pair_lr_symmetry_penalty",
        "stance_slip_penalty",
    ]:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} func: {fn}")
        if fn not in funcs:
            ok = False

    # env_cfg
    with open(ENV_CFG) as f:
        cfg = f.read()

    train_ver_line = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_ver_line.strip()}")
    if 'TRAIN_VERSION = "V63.F"' not in cfg:
        print("  [FAIL] TRAIN_VERSION != V63.F")
        ok = False

    checks = [
        ("_IS_V63F = TRAIN_VERSION.startswith", "V63.F flag"),
        ("_IS_V63B or _IS_V63C or _IS_V63D or _IS_V63E or _IS_V63F", "V62 activation"),
        ("if _IS_V63F:", "V63.F block"),
        ("self.rewards.phase_contact.weight = 3.0", "phase_contact 3.0"),
        ("self.rewards.propulsion.weight = 1.0", "propulsion 1.0"),
        ("self.rewards.feet_air_time.weight = 4.0", "feet_air 4.0"),
        ("weight=8.0,  # V63.E.1 3.0 → V63.F 8.0", "joint_target 8.0"),
        ('"A_leg_end": 0.20', "A_leg_end 0.20"),
        ('"A_foot_end": 0.28', "A_foot_end 0.28"),
        ('"curriculum_iters": 3500', "curriculum 3500"),
        ('"err_max": 4.0', "err_max 4.0"),
        ("metric_clearance_mean_reward", "clearance metric"),
        ("metric_anti_phase_contact_reward", "anti_phase metric"),
        ("metric_leg_usage_cv_reward", "leg_usage_cv metric"),
        ("self.rewards.metric_clearance = RewTerm", "clearance RewTerm"),
        ("self.rewards.metric_anti_phase = RewTerm", "anti_phase RewTerm"),
        ("self.rewards.metric_leg_usage_cv = RewTerm", "leg_usage_cv RewTerm"),
        ("weight=1e-4", "metric weight 1e-4"),
    ]
    for token, label in checks:
        marker = "[OK]" if token in cfg else "[FAIL]"
        print(f"  {marker} env_cfg: {label}")
        if token not in cfg:
            ok = False

    # train.cmd
    with open(TRAIN_CMD) as f:
        if "RUN_NAME=V63.F" in f.read():
            print("  [OK] train.cmd: RUN_NAME=V63.F")
        else:
            print("  [FAIL] train.cmd")
            ok = False

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
