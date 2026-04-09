"""V63.G 구현 검증."""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REWARDS = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py"
ENV_CFG = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py"
TRAIN_CMD = REPO / "train.cmd"


def main() -> int:
    ok = True

    for p, lbl in [(REWARDS, "rewards.py"), (ENV_CFG, "env_cfg.py")]:
        try:
            with open(p) as f:
                ast.parse(f.read())
            print(f"[OK] {lbl}: SYNTAX")
        except SyntaxError as e:
            print(f"[FAIL] {lbl}: {e}")
            ok = False

    with open(REWARDS) as f:
        tree = ast.parse(f.read())
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    new_funcs = [
        "asymmetric_joint_target_reward",
        "intra_pair_sync_reward",
        "leg_usage_cv_penalty",
        "per_leg_propulsion_balance_reward",
    ]
    for fn in new_funcs:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} new func: {fn}")
        if fn not in funcs:
            ok = False

    with open(ENV_CFG) as f:
        cfg = f.read()
    train_ver = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_ver.strip()}")
    if 'TRAIN_VERSION = "V63.G"' not in cfg:
        print("  [FAIL] TRAIN_VERSION != V63.G")
        ok = False

    checks = [
        ("_IS_V63G = TRAIN_VERSION.startswith", "V63.G flag"),
        ("if _IS_V63G:", "V63.G block"),
        ("self.rewards.asymmetric_joint_target = RewTerm", "asymmetric_joint_target RewTerm"),
        ("self.rewards.intra_pair_sync = RewTerm", "intra_pair_sync RewTerm"),
        ("self.rewards.leg_usage_cv = RewTerm", "leg_usage_cv penalty RewTerm"),
        ("self.rewards.per_leg_propulsion_balance = RewTerm", "per_leg_balance RewTerm"),
        ("weight=5.0,", "asym_target weight 5.0"),
        ("weight=4.0,  # dominant", "intra_pair_sync weight 4.0"),
        ("weight=-3.0,  # V63.F 1e-4", "leg_usage_cv weight -3.0"),
        ('"A_leg_lift_end": 0.40', "A_leg_lift_end 0.40 (23deg)"),
        ('"A_foot_bend_end": 0.50', "A_foot_bend_end 0.50 (28deg)"),
        ('"cv_threshold": 0.3', "cv_threshold 0.3"),
    ]
    for tok, lbl in checks:
        marker = "[OK]" if tok in cfg else "[FAIL]"
        print(f"  {marker} {lbl}")
        if tok not in cfg:
            ok = False

    with open(TRAIN_CMD) as f:
        if "RUN_NAME=V63.G" in f.read():
            print("  [OK] train.cmd RUN_NAME=V63.G")
        else:
            print("  [FAIL] train.cmd")
            ok = False

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
