"""V63.F metric 함수 추가 검증.

- rewards.py 문법 OK
- 새 함수 3개 존재
- 기존 함수(phase_joint_target_linear_reward 등) 건재
- env_cfg.py 건드리지 않았는지 (V63.E.1 영향 0)
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REWARDS = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py"
ENV_CFG = REPO / "source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py"


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

    # rewards.py functions check
    with open(REWARDS) as f:
        tree = ast.parse(f.read())
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}

    new_metrics = [
        "metric_clearance_mean_reward",
        "metric_anti_phase_contact_reward",
        "metric_leg_usage_cv_reward",
    ]
    for fn in new_metrics:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} new metric: {fn}")
        if fn not in funcs:
            ok = False

    # Existing critical functions intact
    critical = [
        "phase_joint_target_linear_reward",  # V63.E/E.1
        "phase_joint_target_reward",         # V63.D
        "phase_foot_reach_reward",           # V63.B/C
        "stance_slip_penalty",               # V63.B+
        "pair_lr_symmetry_penalty",          # V63.B+
        "phase_contact_reward",              # V54+
        "phase_gated_diagonal_propulsion_reward",  # V62
    ]
    for fn in critical:
        marker = "[OK]" if fn in funcs else "[FAIL]"
        print(f"  {marker} existing critical: {fn}")
        if fn not in funcs:
            ok = False

    # env_cfg.py should NOT have any metric_ references yet (V63.F 아직 미적용)
    with open(ENV_CFG) as f:
        cfg = f.read()
    v63f_tokens = [
        "_IS_V63F",
        "metric_clearance_mean_reward",
        "metric_anti_phase_contact_reward",
        "metric_leg_usage_cv_reward",
        "if _IS_V63F:",
    ]
    for tok in v63f_tokens:
        if tok in cfg:
            print(f"  [WARN] env_cfg still references V63.F: {tok}")

    # TRAIN_VERSION 확인 (V63.E.1 유지)
    train_ver_line = [l for l in cfg.split("\n") if l.startswith("TRAIN_VERSION")][0]
    print(f"  [INFO] {train_ver_line.strip()}")
    if 'TRAIN_VERSION = "V63.E.1"' not in cfg:
        print(f"  [WARN] TRAIN_VERSION != V63.E.1 (현재 V63.E.1 실행 중이어야 함)")

    print("\n" + ("SUCCESS" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
