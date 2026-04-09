"""V63.D 구현 검증 스크립트."""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REWARDS = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py"
ENV_CFG = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py"
TRAIN_CMD = REPO / "train.cmd"


def syntax_check(path: Path, label: str) -> bool:
    try:
        with open(path) as f:
            ast.parse(f.read())
        print(f"[OK] {label}: SYNTAX OK")
        return True
    except SyntaxError as e:
        print(f"[FAIL] {label}: {e}")
        return False


def main() -> int:
    ok = True
    ok &= syntax_check(REWARDS, "rewards.py")
    ok &= syntax_check(ENV_CFG, "env_cfg.py")

    # rewards.py: new function
    with open(REWARDS) as f:
        rw_src = f.read()
    tree = ast.parse(rw_src)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in [
        "phase_joint_target_reward",
        "phase_foot_reach_reward",
        "pair_lr_symmetry_penalty",
        "stance_slip_penalty",
    ]:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} func: {fn}")
        if fn not in funcs:
            ok = False

    # phase_joint_target_reward specific checks
    required = [
        "A_leg: float",
        "A_foot: float",
        "_v63d_leg_ids",
        "_v63d_foot_ids",
        "_v63d_leg_defaults",
        "_v63d_foot_defaults",
        "leg_target",
        "foot_target",
        "front_left_leg",
        "front_left_foot",
        "log_joint_target_reward",
    ]
    for token in required:
        marker = "[OK]" if token in rw_src else "[FAIL]"
        print(f"  {marker} joint_target token: {token}")
        if token not in rw_src:
            ok = False

    # env_cfg.py
    with open(ENV_CFG) as f:
        cfg = f.read()
    train_version = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_version.strip()}")
    if 'TRAIN_VERSION = "V63.D"' not in cfg:
        print("  [FAIL] TRAIN_VERSION != V63.D")
        ok = False

    env_checks = [
        ("_IS_V63D = TRAIN_VERSION.startswith", "V63.D 플래그"),
        ("_IS_V63B or _IS_V63C or _IS_V63D", "V62 활성화 조건"),
        ("if _IS_V63D:", "V63.D 블록"),
        ("self.rewards.phase_contact.weight = 4.0", "phase_contact 4.0"),
        ("self.rewards.propulsion.weight = 4.0", "propulsion 4.0"),
        ("self.rewards.feet_air_time.weight = 4.0", "feet_air_time 4.0"),
        ("self.rewards.phase_joint_target = RewTerm", "phase_joint_target RewTerm"),
        ("weight=10.0,  # dominant", "joint_target weight 10.0"),
        ('"A_leg": 0.25', "A_leg 0.25"),
        ('"A_foot": 0.35', "A_foot 0.35"),
        ('"std": 0.3,', "std 0.3"),
        ("phase_joint_target_reward", "함수 참조"),
    ]
    for token, label in env_checks:
        marker = "[OK]" if token in cfg else "[FAIL]"
        print(f"  {marker} env_cfg: {label}")
        if token not in cfg:
            ok = False

    # train.cmd
    with open(TRAIN_CMD) as f:
        tc = f.read()
    if "RUN_NAME=V63.D" in tc:
        print("  [OK] train.cmd: RUN_NAME=V63.D")
    else:
        print("  [FAIL] train.cmd: RUN_NAME mismatch")
        ok = False

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
