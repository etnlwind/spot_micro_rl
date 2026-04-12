# V64 PLAN: Mirror Symmetry Augmentation (실패)

## 1. 배경

V63.I 진단에서 대각선 페어 편향(12.6%p)의 근본 원인이 **정책의 symmetry breaking**임을 확인.
URDF는 물리적으로 완벽 대칭 (scripts/urdf_symmetry_check.py 검증).

## 2. 접근

Isaac Lab 내장 `RslRlSymmetryCfg`를 활용한 mirror symmetry augmentation.
PPO 학습 시 observation/action을 좌우 반전하여 대칭 학습 유도.

### Mirror 매핑
- Joint permutation: `[3,4,5,0,1,2,9,10,11,6,7,8]` (FL↔FR, RL↔RR)
- Shoulder sign flip: `[-1,1,1,-1,1,1,-1,1,1,-1,1,1]`
- Phase clock (8D): `[1,0,3,2,5,4,7,6]` (per-leg permutation)
- Contact sensor: `[1,0,3,2]` (FL↔FR, RL↔RR)

### 구현
- `mirror_symmetry.py`: mirror_obs_tensor, mirror_action_tensor, spot_micro_mirror_augmentation
- `rsl_rl_ppo_cfg.py`: V64 조건부 symmetry_cfg 활성화

## 3. 실패 과정

### V64 (data augmentation): RL contact 1.4%, timeout 46%
- **구현 버그 1**: augmented data를 [original, mirror] 연결 반환해야 하는데 mirror만 반환
- **구현 버그 2**: `leg_lr_symmetry`를 제거 → frozen diagonal 방어벽 상실

### V64.2 (mirror loss + leg_lr_symmetry 복원): 여전히 frozen diagonal
- mirror loss는 PPO update-level soft constraint → per-step reward gradient 대체 불가
- leg_lr_symmetry 복원해도 true_trot_pattern이 frozen diagonal 보상 → 벌점 감당 가능

## 4. 근본 원인

- **Phase clock과 data augmentation 충돌**: mirrored obs의 phase clock이 실제 env에서 발생하지 않는 phantom 상태 → 모순 학습 신호
- **mirror augmentation은 L/R 대칭만 강제, 대각 페어 교대는 못 잡음**
- **true_trot_pattern이 frozen diagonal에 높은 점수** → mirror로 못 해결

## 5. 교훈

1. PPO update-level symmetry constraint로는 per-step reward gradient를 대체 못 함
2. Phase clock이 있는 환경에서 data augmentation은 phantom 데이터 위험
3. Reward를 제거하기 전에 반드시 reward budget 수치 검증 필수
4. `leg_lr_symmetry`가 frozen diagonal 방어의 핵심 요소였음 (제거 시 즉시 붕괴)
