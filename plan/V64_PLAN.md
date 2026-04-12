# V64 PLAN: Mirror Symmetry Augmentation (실패)

## 1. 배경

V63.I(최고 보행 품질)의 대각 편향(12.6%p) 원인 진단:
- URDF 물리 대칭: **완벽** (`scripts/urdf_symmetry_check.py` 검증)
- Tensorboard per-leg 진단: **iter 500에서 정책 symmetry breaking 시작** (`scripts/v63i_per_leg_diagnosis.py`)
- iter 3000~3500에서 일시 대칭 수렴(diff 0.5%p) → 4000 이후 재발 → **balanced 해는 존재하지만 불안정**

### 왜 편향이 생기는가
모든 4096 env가 동일한 phase(FL=0, FR=π)에서 시작 → FL+RR이 항상 "첫 stance" → 초기 탐색에서 FL+RR 약간 유리 → 모든 env에서 동시 강화 → self-reinforcing bias.

### 기존 시도 실패
- V63.I.1: `leg_lr_symmetry` -2→-3 → **L/R 축을 찌르는데 실제 편향은 대각 축** → 효과 없음
- V63.I.2: `diagonal_pair_balance` -4 → **대각 축 직접 공격했지만 EMA gradient 100x 감쇠** + **true_trot이 편향 보상** → 효과 없음

## 2. V64 설계

### Isaac Lab 내장 symmetry 인프라 발견
`RslRlSymmetryCfg` — `data_augmentation_func` 정의만으로 mirror augmentation 적용 가능.

### Mirror 매핑 (코덱스 리뷰 2회 반영)
- Joint permutation: `[3,4,5,0,1,2,9,10,11,6,7,8]` (FL↔FR, RL↔RR)
- Shoulder sign flip: `[-1,1,1,-1,1,1,-1,1,1,-1,1,1]`
- Phase clock: **8차원** per-leg permutation `[1,0,3,2,5,4,7,6]`
  - 코덱스 1차 리뷰에서 "phase_clock은 2차원이 아닌 8차원, permutation 필수" 발견
- Reward 내부 contact permutation: **하지 않음** (Wrapper A는 policy 인터페이스만 mirror)

### 구현 파일
- `source/.../mdp/mirror_symmetry.py`: mirror_obs_tensor, mirror_action_tensor, spot_micro_mirror_augmentation
- `agents/rsl_rl_ppo_cfg.py`: V64 조건부 symmetry_cfg 활성화
- `scripts/verify_v64_mirror.py`: involution + symmetric pose + config 자동 검증

## 3. 실험 과정

### V64 첫 시도: `use_data_augmentation=True`
**결과**: FL 65.8%, FR 23.0%, RL 1.4%, RR 46.1% — **frozen diagonal 악화**

| 지표 | V63.I | V64 |
|------|------|------|
| 대각 diff | 12.6%p | **87.5%p** |
| timeout | 99.95% | **46.4%** |
| RL contact | 45.0% | **1.4%** |

**원인 1 — 반환값 버그**: `data_augmentation_func`이 mirror 데이터만 반환 → rsl_rl PPO가 `num_aug=1`로 인식 → augmentation 안 됨, mirror 데이터로만 학습.
**수정**: `torch.cat([original, mirrored], dim=0)` 연결 반환 → `num_aug=2`.

**원인 2 — leg_lr_symmetry 제거**: "mirror가 대체한다"며 제거 → frozen diagonal 방어 +2.70/step 상실.

### V64-fix: augmentation 수정
**결과**: 여전히 FL 80%, RR 77% frozen diagonal.
**분석**: augmentation은 정상 동작(symmetry loss 0.0002)하지만 **phase clock과 data augmentation이 충돌** — mirrored obs의 phase가 실제 env에서 발생하지 않는 phantom 상태.

### V64.2: mirror loss + leg_lr_symmetry 복원
**설정**: `use_data_augmentation=False`, `use_mirror_loss=True`, `mirror_loss_coeff=1.0`
**결과**: iter 417에서 FL 61.5%, FR 27.9%, RL 4.0%, RR 46.5% — **여전히 frozen diagonal**

leg_lr_symmetry(-2.27)가 활성이지만 policy가 벌점 감당하며 exploit 유지.
**데이터 확정**: leg_lr_symmetry 제거는 악화 요인이지만 **root cause가 아님**.

## 4. 근본 원인 분석 (데이터 기반)

### Reward budget 비교
```
V63.I (balanced):  reward 386.12
V64   (frozen):    reward 385.78
차이: 0.34 (0.09%)
→ 두 basin이 reward에서 거의 동등 → tiebreaker 하나로 방향 결정
```

### true_trot_pattern이 frozen diagonal 보상
| Run | 상태 | true_trot |
|------|------|------|
| V63.I | balanced | +6.51 |
| V64 fail 1824 | frozen (FL 79%, RL 6%) | **+6.07** (거의 동일!) |

**frozen diagonal에서도 true_trot 만점** — `intra × inter`가 "매 순간 두 쌍이 다르면 만점"이라 시간축 교대 불요.

### Phase clock과 mirror augmentation 충돌
Mirror data augmentation에서:
- 원본: FL phase=θ (stance) → 높은 reward → advantage +10
- Mirror: FL phase=θ+π (swing) → **같은 advantage +10 복사**
- 하지만 미러 상태는 실제 env에서 **발생하지 않음** (phantom)
- Policy가 모순 신호로 학습 → 혼란

## 5. 최종 판정

| 구분 | V64 | V64-fix | V64.2 |
|------|------|------|------|
| 방법 | data aug (buggy) | data aug (fixed) | mirror loss |
| 대각 diff | 87.5%p | ~130%p | ~76%p |
| 판정 | 실패 | 실패 | 실패 |

**V64 시리즈 전체 실패**. Mirror augmentation/loss 모두 이 환경(per-leg phase clock + true_trot reward)에서는 효과 없음.

## 6. 교훈

1. **PPO update-level symmetry constraint로는 per-step reward gradient를 대체 못 함**
2. **Phase clock이 있는 환경에서 data augmentation은 phantom 데이터 → 모순 신호**
3. **Reward를 제거하기 전 반드시 reward budget 수치 검증** — leg_lr_symmetry 제거 시 frozen diagonal net-positive
4. **Mirror loss는 soft constraint** — reward가 exploit을 강하게 밀면 뚫림
5. **"cross-diagonal exploit"** — 전체 L/R은 대칭이지만 앞/뒤 개별 L/R이 반대로 무너짐 → `leg_lr_symmetry`의 `|FL-FR|+|RL-RR|` 구조가 이를 잡는 이유
