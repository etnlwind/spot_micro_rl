"""V63.E 구현 검증 스크립트."""
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

    with open(REWARDS) as f:
        rw_src = f.read()
    tree = ast.parse(rw_src)
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in [
        "phase_joint_target_linear_reward",
        "phase_joint_target_reward",
        "phase_foot_reach_reward",
        "pair_lr_symmetry_penalty",
        "stance_slip_penalty",
    ]:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} func: {fn}")
        if fn not in funcs:
            ok = False

    # phase_joint_target_linear 주요 토큰
    linear_tokens = [
        "A_leg_start",
        "A_leg_end",
        "A_foot_start",
        "A_foot_end",
        "curriculum_iters",
        "err_max",
        "torch.clamp(1.0 - err_total / err_max",
        "_v63e_leg_ids",
        "_v63e_foot_ids",
        "log_curriculum_frac",
    ]
    for token in linear_tokens:
        marker = "[OK]" if token in rw_src else "[FAIL]"
        print(f"  {marker} linear token: {token}")
        if token not in rw_src:
            ok = False

    with open(ENV_CFG) as f:
        cfg = f.read()
    train_version = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_version.strip()}")
    if 'TRAIN_VERSION = "V63.E"' not in cfg:
        print("  [FAIL] TRAIN_VERSION != V63.E")
        ok = False

    env_checks = [
        ("_IS_V63E = TRAIN_VERSION.startswith", "V63.E 플래그"),
        ("_IS_V63B or _IS_V63C or _IS_V63D or _IS_V63E", "V62 활성화 조건"),
        ("if _IS_V63E:", "V63.E 블록"),
        ("self.rewards.phase_contact.weight = 6.0", "phase_contact 6.0"),
        ("self.rewards.propulsion.weight = 2.0", "propulsion 2.0"),
        ("self.rewards.feet_air_time.weight = 4.0", "feet_air_time 4.0"),
        ("phase_joint_target_linear = RewTerm", "phase_joint_target_linear RewTerm"),
        ("weight=3.0,  # balanced", "joint_target weight 3.0"),
        ('"A_leg_start": 0.05', "A_leg_start 0.05"),
        ('"A_leg_end": 0.25', "A_leg_end 0.25"),
        ('"A_foot_start": 0.10', "A_foot_start 0.10"),
        ('"A_foot_end": 0.35', "A_foot_end 0.35"),
        ('"curriculum_iters": 1500', "curriculum_iters 1500"),
        ('"err_max": 1.5', "err_max 1.5"),
        ("self.rewards.phase_foot_reach = None", "V63.B/C reward 제거"),
        ("self.rewards.phase_joint_target = None", "V63.D reward 제거"),
    ]
    for token, label in env_checks:
        marker = "[OK]" if token in cfg else "[FAIL]"
        print(f"  {marker} env_cfg: {label}")
        if token not in cfg:
            ok = False

    with open(TRAIN_CMD) as f:
        tc = f.read()
    if "RUN_NAME=V63.E" in tc:
        print("  [OK] train.cmd: RUN_NAME=V63.E")
    else:
        print("  [FAIL] train.cmd: RUN_NAME mismatch")
        ok = False

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
