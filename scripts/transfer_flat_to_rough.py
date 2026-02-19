"""Transfer Learning: V8 Flat → Rough Terrain

V8 flat 모델의 가중치를 러프 지형 모델로 전이합니다.
- Flat 관측: 48차원 (base_lin_vel 3 + base_ang_vel 3 + projected_gravity 3 + 
              velocity_commands 3 + joint_pos 12 + joint_vel 12 + actions 12)
- Rough 관측: 102차원 (위 48차원 + height_scan 54차원)

첫 번째 레이어(actor.0, critic.0)만 확장:
  - 기존 48차원 가중치 → 그대로 복사
  - 새 54차원(height_scan) → 작은 값으로 초기화 (Xavier uniform)
나머지 레이어는 그대로 복사.
Optimizer state는 리셋 (새 차원에 맞지 않으므로).
"""

import torch
import torch.nn.init as init
import os
import shutil
import argparse


def transfer_weights(src_path: str, dst_path: str, old_obs_dim: int = 48, new_obs_dim: int = 102):
    """Flat 모델 가중치를 Rough 모델로 전이."""
    
    print(f"Loading source model: {src_path}")
    ckpt = torch.load(src_path, map_location="cpu")
    
    model_sd = ckpt["model_state_dict"]
    
    # 확장할 레이어들
    layers_to_expand = ["actor.0.weight", "critic.0.weight"]
    extra_dims = new_obs_dim - old_obs_dim
    
    print(f"\n=== Weight Transfer ===")
    print(f"Old obs dim: {old_obs_dim}")
    print(f"New obs dim: {new_obs_dim}")
    print(f"Extra dims (height_scan): {extra_dims}")
    print()
    
    for layer_name in layers_to_expand:
        old_weight = model_sd[layer_name]  # [out_features, old_obs_dim]
        out_features = old_weight.shape[0]
        
        # 새 가중치 텐서 생성
        new_weight = torch.zeros(out_features, new_obs_dim)
        
        # 기존 가중치 복사
        new_weight[:, :old_obs_dim] = old_weight
        
        # 새 차원(height_scan)에 대해 Xavier uniform 초기화
        # 기존 레이어의 fan_in을 new_obs_dim으로 설정
        new_part = torch.empty(out_features, extra_dims)
        init.xavier_uniform_(new_part, gain=0.1)  # gain=0.1: 작은 값으로 초기화 → 기존 행동 보존
        new_weight[:, old_obs_dim:] = new_part
        
        model_sd[layer_name] = new_weight
        print(f"  {layer_name}: {old_weight.shape} → {new_weight.shape}")
        print(f"    Old weights norm: {old_weight.norm():.4f}")
        print(f"    New part norm: {new_part.norm():.4f}")
        print(f"    Combined norm: {new_weight.norm():.4f}")
    
    # noise std: 약간 높여서 탐색 허용 (러프 지형 적응을 위해)
    old_std = model_sd["std"].clone()
    # std를 약간 증가 (현재값의 1.5배, 최대 0.5)
    new_std = torch.clamp(old_std * 1.5, min=0.1, max=0.5)
    model_sd["std"] = new_std
    print(f"\n  std: {old_std.mean():.4f} → {new_std.mean():.4f}")
    
    # 새 체크포인트 저장
    new_ckpt = {
        "model_state_dict": model_sd,
        "optimizer_state_dict": {},  # Optimizer state 리셋
        "iter": 0,  # Iteration 리셋
        "infos": ckpt.get("infos", {}),
    }
    
    # 저장 디렉토리 생성
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    torch.save(new_ckpt, dst_path)
    
    print(f"\n=== Saved transferred model to: {dst_path} ===")
    print(f"  Optimizer state: RESET (fresh start)")
    print(f"  Iteration: RESET to 0")
    
    return dst_path


def main():
    parser = argparse.ArgumentParser(description="Transfer flat model weights to rough terrain model")
    parser.add_argument("--src", type=str, 
                       default="logs/rsl_rl/spot_micro_flat/2026-02-19_20-40-30/model_1400.pt",
                       help="Source flat model checkpoint path")
    parser.add_argument("--dst_dir", type=str,
                       default="logs/rsl_rl/spot_micro_rough/transferred_from_v8_flat",
                       help="Destination directory for transferred model")
    parser.add_argument("--old_dim", type=int, default=48, help="Old observation dimension")
    parser.add_argument("--new_dim", type=int, default=102, help="New observation dimension")
    args = parser.parse_args()
    
    dst_path = os.path.join(args.dst_dir, "model_0.pt")
    
    transfer_weights(args.src, dst_path, args.old_dim, args.new_dim)
    
    print(f"\n=== Usage ===")
    print(f"Train with transferred weights:")
    print(f"  python scripts/rsl_rl/train.py --task Isaac-Velocity-Rough-SpotMicro-v0 \\")
    print(f"    --num_envs 24576 --headless --max_iterations 5000 \\")
    print(f"    --resume --load_run transferred_from_v8_flat --checkpoint model_0.pt")


if __name__ == "__main__":
    main()
