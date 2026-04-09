"""V63.C 구현 검증 스크립트.

- rewards.py, env_cfg.py 문법 검증
- 새 함수 정의 확인
- V63.C 블록 / weight 재균형 확인
"""
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

    # rewards.py function check
    with open(REWARDS) as f:
        tree = ast.parse(f.read())
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for fn in [
        "pair_lr_symmetry_penalty",
        "stance_slip_penalty",
        "phase_foot_reach_reward",
    ]:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} func: {fn}")
        if fn not in funcs:
            ok = False

    # Check phase_foot_reach_reward has lift_amplitude param
    with open(REWARDS) as f:
        src = f.read()
    if "lift_amplitude: float" in src:
        print("  [OK] phase_foot_reach_reward: lift_amplitude param 존재")
    else:
        print("  [FAIL] phase_foot_reach_reward: lift_amplitude param 누락")
        ok = False

    if "target_z" in src and "_v63_nominal_foot_z" in src:
        print("  [OK] phase_foot_reach_reward: z 축 로직 존재")
    else:
        print("  [FAIL] phase_foot_reach_reward: z 축 로직 누락")
        ok = False

    # env_cfg.py checks
    with open(ENV_CFG) as f:
        cfg = f.read()
    train_version = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_version.strip()}")
    if 'TRAIN_VERSION = "V63.C"' not in cfg:
        print("  [FAIL] TRAIN_VERSION != V63.C")
        ok = False

    checks = [
        ("_IS_V63C", "V63.C 플래그"),
        ("if _IS_V63B or _IS_V63C", "V63B/V63C → V62 활성화"),
        ("if _IS_V63C:", "V63.C 블록"),
        ("self.rewards.phase_contact.weight = 6.0", "phase_contact 6.0"),
        ("self.rewards.propulsion.weight = 4.0", "propulsion 4.0"),
        ("self.rewards.feet_air_time.weight = 6.0", "feet_air_time 6.0"),
        ("weight=5.0,  # V63.B +1.0 → V63.C +5.0", "foot_reach 5.0"),
        ('"lift_amplitude": 0.04', "lift_amplitude 0.04"),
        ('"reach_amplitude": 0.05', "reach_amplitude 0.05"),
        ('"std": 0.035', "std 0.035"),
        ("self.rewards.pair_lr_symmetry = RewTerm(", "V63.C pair_lr_symmetry"),
        ("self.rewards.stance_slip = RewTerm(", "V63.C stance_slip"),
    ]
    for token, label in checks:
        marker = "[OK]" if token in cfg else "[FAIL]"
        print(f"  {marker} env_cfg: {label}")
        if token not in cfg:
            ok = False

    # train.cmd
    with open(TRAIN_CMD) as f:
        tc = f.read()
    if "RUN_NAME=V63.C" in tc:
        print("  [OK] train.cmd: RUN_NAME=V63.C")
    else:
        print("  [FAIL] train.cmd: RUN_NAME mismatch")
        ok = False

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
