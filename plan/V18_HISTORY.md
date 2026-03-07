# V18~V18.1: 3-Phase 커리큘럼과 벌레걸음 데드락
> **기간**: 2026-03-06 ~ 2026-03-07  
> **환경**: Flat, From-scratch, 24,576 envs  
> **핵심**: Phase별 보상 가중치 커리큘럼 도입 → Phase 2에서도 gait/stride=0 데드락

---

## 1. V18: 3-Phase Curriculum 설계 (2026-03-06)

### 동기
V17.1의 "정지 함정"에서 배운 것:
- 단일 가중치 세트로는 서기→걷기→트롯 단계를 유도할 수 없음
- **Phase별로 보상 가중치를 전환**하는 커리큘럼 필요

### 3-Phase 구조

| Phase | iter 범위 | 목표 | 핵심 전략 |
|:-----:|:---------:|------|-----------|
| **1: STAND** | 0~2,000 | 안정적 서기 | standing_height↑, 페널티 약함, gait/stride=0 |
| **2: WALK** | 2,000~6,000 | 걷기 시작 | standing↓, velocity/gait/stride↑ |
| **3: TROT** | 6,000+ | 트롯 완성 | standing 최소, gait/stride 최대 |

### `reward_weight_curriculum()` 구현 (rewards.py L1123)
```python
def reward_weight_curriculum(env, current_iter: int) -> dict:
    """iteration에 따라 Phase별 보상 가중치를 반환"""
    PHASE_WEIGHTS = {
        # Phase 1: STAND (0~2000)
        1: {
            'standing_height': 40.0,
            'forward_velocity': 5.0,
            'gait_cycle_period': 0.0,   # 비활성
            'stride_length': 0.0,       # 비활성
            'joint_vel_l2': -0.05,      # 약한 페널티
            'diagonal_coupling': 2.0,
            # ... (19개 항목)
        },
        # Phase 2: WALK (2000~6000)
        2: {
            'standing_height': 20.0,    # ↓ 절반
            'forward_velocity': 8.0,    # ↑
            'gait_cycle_period': 8.0,   # 활성화
            'stride_length': 6.0,       # 활성화
            'joint_vel_l2': -0.2,       # ↑ 강화
            'diagonal_coupling': 5.0,
            # ...
        },
        # Phase 3: TROT (6000+)
        3: {
            'standing_height': 10.0,    # ↓↓
            'forward_velocity': 8.0,
            'gait_cycle_period': 15.0,  # ↑↑ 최대
            'stride_length': 12.0,      # ↑↑ 최대
            'joint_vel_l2': -0.5,       # ↑↑ 최대
            'diagonal_coupling': 8.0,
            # ...
        },
    }
```

### env_cfg.py 연동: `SpotMicroRewardCurriculumCfg`
```python
class SpotMicroRewardCurriculumCfg:
    """PPO runner의 on_policy_transition에서 호출"""
    phase_boundaries = [2000, 6000]
    # 매 iteration마다 PHASE_WEIGHTS에서 현재 phase 가중치를 적용
```

---

## 2. V18.1: 버그 수정 + 훈련 시작 (2026-03-06)

### 발견된 버그
- `joint_vel_l2`의 Phase 1 가중치가 잘못됨
- 코드에서 `-0.5`로 설정되어 있었으나, Phase 1 의도는 `-0.05`
- Phase별 스케줄링에서 PHASE_WEIGHTS dict 값이 올바르게 적용되는지 확인 필요

### 수정 내용
- `PHASE_WEIGHTS[1]['joint_vel_l2']` = -0.5 → **-0.05** 로 수정
- 커리큘럼 전환 로그 추가 (Phase 전환 시점 확인용)

### 훈련 설정
```
- From scratch (새 네트워크 초기화)
- 24,576 envs, headless
- max_iterations = 15,000
- PPO: gamma=0.97, clip=0.1, lr=1e-4
- Network: [512, 256, 128] ELU
- 예상 소요: ~104시간 (7 sec/iter)
```

---

## 3. V18.1 훈련 결과 분석 (iter 4,488에서 중지)

### TensorBoard 데이터 (tb_full_analysis.py)

| 지표 | iter 100 | iter 2000 | iter 4488 | 추세 |
|------|:--------:|:---------:|:---------:|:----:|
| **Mean Reward** | ~28 | ~35 | ~32 | 횡보 |
| **forward_velocity** | 1.71 | 1.50 | 1.01 | **↓ 감소** |
| **standing_height** | 1.37 | 5.2 | **12.62** | **↑↑ 폭증** |
| **gait_cycle_period** | 0.000 | 0.000 | **0.000** | **영구 0** |
| **stride_length** | 0.000 | 0.000 | **0.000** | **영구 0** |
| **diagonal_coupling** | ~0.5 | ~0.3 | ~0.2 | **↓ 감소** |
| **rear_alternation** | ~0.1 | ~0.05 | ~0.03 | **↓ 감소** |

### 치명적 문제: gait_cycle=0, stride=0이 4,488 iter 동안 한 번도 발동 안 됨

Phase 2 (iter 2000~6000) 진입 후에도 **완전히 0**.

---

## 4. "벌레 걸음" 데드락 진단

### 로봇의 학습된 전략
```
Phase 1 (0~2000):
  standing_height(40) >> 나머지 모든 보상
  → "서기"가 최적 → 다리를 빠르게 진동시켜 높이 유지
  → 초고속 미세진동 (관절 속도 매우 높음, 변위 매우 작음)
  → gait_cycle: period ≈ 0.02s → target 0.3~0.5s에서 극히 멂 → exp(-d²)≈0
  → stride: 발 이동거리 ≈ 0mm → 0.001 필터 미통과 → 0

Phase 2 (2000~6000):
  standing_height(20)은 여전히 지배적
  gait_cycle(8)/stride(6) 활성화 → 그러나 기존 전략에서 0 출력
  → weight × 0 = 0 → **가중치가 아무리 커도 0인 보상은 학습 신호 없음**
  → Phase 1의 "벌레" 전략이 Phase 2에서도 그대로 유지
```

### min_vel은 문제가 아님
- gait_cycle과 stride 모두 `min_vel=0.05` (m/s)의 vel_gate 있음
- 로봇의 vel_x ≈ 1.0~1.7 m/s → vel_gate = min(vel_x/0.05, 1.0) = 1.0
- **속도 게이트는 완전히 통과 중** → 문제는 다른 곳

### 진짜 원인: 보상 출력 자체가 0
1. **gait_cycle**: period가 ~0.02s, target이 0.3~0.5s → 거리가 너무 멀어 exp(-d²/2σ²) ≈ 0
2. **stride**: 발이 거의 안 움직임 → XY 이동 ≈ 0mm → 0.001m 최소 필터 미통과

### 구조적 한계
```
문제의 인과 구조:

  standing_height 지배적 → "떨기" 전략 학습
  → 떨기는 유효한 gait event 미생성
  → gait_cycle/stride 보상 = 0
  → Phase 2에서 가중치 올려도 0×8 = 0
  → PPO에게 "걷기를 시도하면 보상이 더 나올 것"이라는 gradient 없음
  → 탐색(엔트로피)만으로 탈출 확률 ≈ 0
  → **데드락**
```

---

## 5. 중지 결정

- iter 4,488 (Phase 2의 약 62% 진행) 시점에서 **전면 중지**
- 마지막 체크포인트: `model_4400.pt`
- 이유: Phase 2에서도 gait/stride=0이면 Phase 3까지 가도 동일
- **총 ~8.7시간 소요 (낭비)**

---

## 6. V18.2 수정 방향 도출

### 핵심 인사이트
> "가중치를 올리는 것"만으로는 "출력이 0인 보상"을 활성화할 수 없다.  
> 떨기 전략 **자체를 벌해야** 한다.

### V18.2 수정안 (4가지)

| 수정 | 내용 | 우선순위 |
|------|------|:--------:|
| **B. `excessive_joint_oscillation_penalty`** | 관절 속도 > 5 rad/s 시 페널티 | ★★★ |
| **C. standing_height 감소** | Phase 2: 20→8, Phase 3: 10→3 | ★★ |
| **D. joint_vel_l2 강화** | Phase 2: -0.2→-0.5, Phase 3: -0.5→-1.0 | ★★ |
| **forward_velocity 증가** | Phase 2/3: 8→12 | ★ |

→ V18.2 상세 계획: [plan/V18.2_PLAN.md](V18.2_PLAN.md) 참조

---

## 7. 이 시기의 핵심 교훈

| 교훈 | 근거 |
|------|------|
| **출력=0인 보상은 가중치를 올려도 무의미** | weight × 0 = 0, gradient 없음 |
| **Phase 전환만으로 기존 전략 탈출 불가** | Phase 2에 들어가도 "벌레" 유지 |
| **지배적 보상은 다른 보상을 압살** | standing(20) >> gait(8)+stride(6) |
| **"나쁜 행동 벌하기"가 "좋은 행동 보상하기"보다 효과적일 수 있음** | 미세진동 직접 페널티 필요 |
| **긴 훈련 전 조기 분석 필수** | iter 500~1000에서 gait/stride=0 확인했어야 함 |

---

## 8. 관련 파일

| 파일 | 내용 |
|------|------|
| `plan/V18.1_ANALYSIS.md` | iter 4488 TensorBoard 상세 분석 |
| `plan/V18.2_PLAN.md` | 수정안 상세 (PHASE_WEIGHTS 비교표 포함) |
| `scripts/tb_full_analysis.py` | 텐서보드 전체 분석 스크립트 |
| `rewards.py` L1123~1240 | `reward_weight_curriculum()` 및 PHASE_WEIGHTS |
