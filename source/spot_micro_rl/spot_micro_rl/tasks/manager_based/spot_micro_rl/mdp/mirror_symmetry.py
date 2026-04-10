"""V64: Mirror Symmetry Data Augmentation for SpotMicro.

Isaac Lab 내장 RslRlSymmetryCfg.data_augmentation_func 에 전달할 함수.
PPO 학습 시 rollout 데이터를 좌우 반전하여 augmented batch를 생성.

설계 근거:
- V63.I 진단: 대각선 페어 편향은 물리가 아닌 정책의 symmetry breaking
- reward penalty로는 이미 굳은 basin을 못 깸 (V63.I.1/I.2/J 실패)
- data augmentation으로 policy가 구조적으로 좌우 대칭 표현 학습

코덱스 리뷰 반영:
- phase_clock은 8차원 per-leg → permutation 필수
- reward 내부 contact permutation은 하지 않음 (augmentation은 policy 학습에만 적용)

Observation layout (56 dims):
  [ 0: 3] base_lin_vel      → vy flip
  [ 3: 6] base_ang_vel      → wx, wz flip
  [ 6: 9] projected_gravity  → gy flip
  [ 9:12] velocity_commands  → cmd_vy, cmd_wz flip
  [12:24] joint_pos          → permute + shoulder sign flip
  [24:36] joint_vel          → permute + shoulder sign flip
  [36:48] actions            → permute + shoulder sign flip
  [48:56] phase_clock        → per-leg permute [1,0,3,2, 5,4,7,6]
"""
import torch
try:
    from tensordict import TensorDict
except ImportError:
    TensorDict = None  # WSL 검증용 fallback

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

# Joint order: FL_sh, FL_leg, FL_foot, FR_sh, FR_leg, FR_foot,
#              RL_sh, RL_leg, RL_foot, RR_sh, RR_leg, RR_foot
JOINT_PERM = [3, 4, 5, 0, 1, 2, 9, 10, 11, 6, 7, 8]

# Shoulder joints need sign flip (roll axis, L/R opposite convention)
# Leg/foot joints keep sign (pitch axis, same convention)
SIGN_FLIP = [-1.0, 1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0]

# Phase clock: 8 dims = [sin_FL, sin_FR, sin_RL, sin_RR, cos_FL, cos_FR, cos_RL, cos_RR]
# Mirror: FL↔FR, RL↔RR within each sin/cos block
PHASE_PERM = [1, 0, 3, 2, 5, 4, 7, 6]

# Pre-computed tensors (lazily initialized on first call)
_JOINT_PERM_T = None
_SIGN_FLIP_T = None
_PHASE_PERM_T = None


def _ensure_tensors(device):
    """Lazy init of permutation/sign tensors on correct device."""
    global _JOINT_PERM_T, _SIGN_FLIP_T, _PHASE_PERM_T
    if _JOINT_PERM_T is None or _JOINT_PERM_T.device != device:
        _JOINT_PERM_T = torch.tensor(JOINT_PERM, dtype=torch.long, device=device)
        _SIGN_FLIP_T = torch.tensor(SIGN_FLIP, dtype=torch.float32, device=device)
        _PHASE_PERM_T = torch.tensor(PHASE_PERM, dtype=torch.long, device=device)


def mirror_obs_tensor(obs: torch.Tensor) -> torch.Tensor:
    """Mirror a flat observation tensor (N, D) where D=48 or 56.

    Supports both 48-dim (no phase_clock) and 56-dim (with phase_clock).
    """
    _ensure_tensors(obs.device)
    m = obs.clone()
    D = obs.shape[-1]

    # [0:3] base_lin_vel: vy flip
    m[:, 1] *= -1

    # [3:6] base_ang_vel: wx, wz flip
    m[:, 3] *= -1
    m[:, 5] *= -1

    # [6:9] projected_gravity: gy flip
    m[:, 7] *= -1

    # [9:12] velocity_commands: cmd_vy, cmd_wz flip
    m[:, 10] *= -1
    m[:, 11] *= -1

    # [12:24] joint_pos: permute + sign_flip
    m[:, 12:24] = obs[:, 12:24][:, _JOINT_PERM_T] * _SIGN_FLIP_T

    # [24:36] joint_vel: permute + sign_flip
    m[:, 24:36] = obs[:, 24:36][:, _JOINT_PERM_T] * _SIGN_FLIP_T

    # [36:48] actions: permute + sign_flip
    m[:, 36:48] = obs[:, 36:48][:, _JOINT_PERM_T] * _SIGN_FLIP_T

    # [48:56] phase_clock: per-leg permutation (if present)
    if D > 48:
        m[:, 48:56] = obs[:, 48:56][:, _PHASE_PERM_T]

    return m


def mirror_action_tensor(action: torch.Tensor) -> torch.Tensor:
    """Mirror an action tensor (N, 12): permute joints + sign flip shoulders."""
    _ensure_tensors(action.device)
    return action[:, _JOINT_PERM_T] * _SIGN_FLIP_T


def spot_micro_mirror_augmentation(env, obs=None, actions=None):
    """Isaac Lab RslRlSymmetryCfg.data_augmentation_func compatible function.

    Args:
        env: VecEnv wrapper (unused, required by interface)
        obs: TensorDict with key "policy" → (N, D) tensor, or None
        actions: (N, 12) tensor, or None

    Returns:
        (mirrored_obs_dict, mirrored_actions) tuple
    """
    mirrored_obs = None
    mirrored_actions = None

    if obs is not None:
        mirrored_obs = obs.clone()
        if "policy" in obs.keys():
            mirrored_obs["policy"] = mirror_obs_tensor(obs["policy"])

    if actions is not None:
        mirrored_actions = mirror_action_tensor(actions)

    return mirrored_obs, mirrored_actions
