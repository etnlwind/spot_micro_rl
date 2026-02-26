"""Critic 리셋 스크립트: V12 체크포인트에서 Actor만 보존하고 Critic/Optimizer/Std를 재초기화.

사용법:
    python scripts/reset_critic.py --input <V12_checkpoint.pt> --output <output.pt> [--init_std 0.5]

Actor 가중치는 그대로 유지하여 학습된 걸음걸이를 보존하고,
Critic은 Xavier uniform으로 재초기화하여 새 보상 스케일에 적응할 수 있게 한다.
"""

import argparse
import torch
import torch.nn as nn


def reset_critic_checkpoint(input_path: str, output_path: str, init_std: float = 0.5):
    """V12 체크포인트를 로드하여 critic/optimizer/std를 리셋한 새 체크포인트를 저장."""
    
    ckpt = torch.load(input_path, map_location="cpu")
    state_dict = ckpt["model_state_dict"]

    # Actor 가중치 보존, Critic 가중치 재초기화
    actor_keys = []
    critic_keys = []
    for key in state_dict:
        if key.startswith("actor."):
            actor_keys.append(key)
        elif key.startswith("critic."):
            critic_keys.append(key)

    print(f"Actor 가중치 보존: {len(actor_keys)}개 텐서")
    for key in actor_keys:
        print(f"  {key}: {state_dict[key].shape}")

    print(f"\nCritic 가중치 재초기화: {len(critic_keys)}개 텐서")
    for key in critic_keys:
        tensor = state_dict[key]
        if "weight" in key:
            # Xavier uniform 초기화
            nn.init.xavier_uniform_(tensor)
            print(f"  {key}: {tensor.shape} → Xavier uniform")
        elif "bias" in key:
            # bias는 0으로 초기화
            nn.init.zeros_(tensor)
            print(f"  {key}: {tensor.shape} → zeros")

    # Noise std 리셋
    if "std" in state_dict:
        old_std = state_dict["std"].clone()
        state_dict["std"] = torch.full_like(state_dict["std"], init_std)
        print(f"\nNoise std 리셋: {old_std.tolist()} → {state_dict['std'].tolist()}")

    # Optimizer 상태 제거
    print(f"\nOptimizer 상태: 삭제됨 (키 {len(ckpt.get('optimizer_state_dict', {}))} 개)")
    ckpt["optimizer_state_dict"] = {}

    # iteration 카운터 유지 (로그 연속성)
    print(f"Iteration: {ckpt['iter']} (유지)")

    # 저장
    torch.save(ckpt, output_path)
    print(f"\n저장 완료: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Critic 리셋: Actor 보존 + Critic/Optimizer/Std 재초기화")
    parser.add_argument("--input", type=str, required=True, help="V12 체크포인트 경로")
    parser.add_argument("--output", type=str, required=True, help="출력 체크포인트 경로")
    parser.add_argument("--init_std", type=float, default=0.5, help="리셋할 noise std 초기값 (기본: 0.5)")
    args = parser.parse_args()

    reset_critic_checkpoint(args.input, args.output, args.init_std)


if __name__ == "__main__":
    main()
