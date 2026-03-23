# V39 Plan: CPG/Phase Clock + Reward 정리 + Soft CaT

> 작성: 2026-03-23
> 상태: 설계 중

---

## 1. Context

### V38 시리즈 결론

| 접근 | shoulder dev | 한계 |
|------|-------------|------|
| L2 penalty (V37.2) | 0.54 고착 | reward 채널 — agent가 상쇄 |
| Soft CaT prob 0.0015 (V38.3) | **0.45 정체** | discount 채널 — local optimum |
| CaT + L2 병행 (V38.3.1) | **실패** | resume 중 weight 변경 → critic 무효화 + curriculum 미복원 |

**CaT가 달성한 것**: 0.54 → 0.45 (-16%). Soft CaT framework은 안정적으로 작동.
**CaT가 못한 것**: 0.45 이하 진입. 벌칙만으로는 local optimum 탈출 불가.
**V38.3.1 교훈**: resume 중 reward weight 변경 불가 (critic 무효화), Isaac Lab resume은 curriculum 미복원.

### 근본 원인 분석

agent가 0.45에서 멈추는 이유:
- **어깨를 더 모으면 보행 효율이 떨어짐** — "벌어진 자세로 걷기"가 현재 reward 구조에서 최적
- **비정상 보행(앞발 고정+셔플)이 splay의 원인** — 정상 trot이면 어깨가 자연스럽게 모임
- **CaT는 벌칙 채널** — "나쁜 자세를 벌주는" 것이지 "좋은 자세로 걷는 법을 가르치는" 것이 아님
- **reward 항목 50개** — 상호작용이 복잡하여 개별 penalty 효과 예측 불가

### V39 목표

- shoulder dev 0.45 → **0.30 이하**
- 앞발 과고정 해결 (FL/FR contact < 0.70)
- ep_len > 200, stride > 6.0 유지
- **정상 trot 보행 달성**

---

## 2. 핵심 설계: CPG/Phase Clock

### 개념

reward로 유도하는 것이 아니라, **보행 패턴 자체를 구조적으로 강제**.
Phase clock을 observation에 추가하여 agent가 "언제 어떤 발을 들어야 하는지"를 명시적으로 안다.

### Phase Clock 구조

```
Trot 패턴:
  FL ████░░░░  (stance → swing)
  RR ████░░░░  (FL과 동위상)
  FR ░░░░████  (반위상)
  RL ░░░░████  (FR과 동위상)

phase(t) = 2π × (t × frequency) mod 1.0
- FL/RR: phase(t)
- FR/RL: phase(t) + π
```

### Observation 추가 (8차원)

각 다리에 sin(phase), cos(phase) 2개씩 × 4다리 = 8개 observation 추가
- sin/cos로 인코딩하면 0/2π 경계의 불연속 없음
- 현재 48차원 → 56차원

### Phase-Conditioned Reward (핵심)

```python
def phase_contact_reward(env):
    """swing phase에서 발이 들려있고, stance phase에서 발이 닿아있으면 reward"""
    for each leg:
        if phase in swing_range:
            reward += (foot_not_touching) * weight
        else:  # stance
            reward += (foot_touching) * weight
```

- 이것이 자연스럽게 trot를 유도
- 앞발도 swing phase에서 반드시 들어야 하므로 과고정 해결
- trot으로 걸으면 어깨가 자연스럽게 모임 → splay 간접 교정

### Phase Clock 주파수

SpotMicro 기구학에 맞는 trot 주파수 결정 필요:
- 일반적인 소형 4족 로봇: 1.5~3.0 Hz
- Solo-12 논문: 2.0 Hz
- SpotMicro 다리 길이 ~10cm → **2.0 Hz에서 시작**, 학습 중 조정 가능하게 설계

### Soft CaT 유지

- V38.3의 Soft CaT framework 그대로 포함 (threshold 0.3, margin 0.3, prob 0.0015)
- CPG가 자세를 유도하고, CaT가 여전히 벌칙으로 보완
- 두 메커니즘이 보완적: CPG(positive) + CaT(negative)

---

## 3. Reward 정리 (50→~25개)

CPG 도입과 함께 reward 구조를 정리. 독립 작업이 아닌 CPG와 함께 진행.

### 제거 대상

| 카테고리 | 현재 | 제거/통합 | 잔여 |
|---------|------|----------|------|
| front/rear 개별 항목 | ~10개 | 4발 공통으로 통합 | ~3개 |
| residency 관련 | ~6개 | 1~2개로 통합 | ~2개 |
| floor 항목 (contact_floor, propulsion_floor) | ~4개 | band 항목으로 통합 | 0개 |
| validity/gate 항목 | ~5개 | 간소화 | ~2개 |

### 추가 대상

| 항목 | 용도 |
|------|------|
| phase_contact_reward | CPG 핵심 — phase에 맞는 접지/이탈 |
| phase_velocity_reward | swing phase에서 다리 속도 |
| gait_symmetry_reward | 대각 쌍 동기화 |

### 목표: ~20~25개 reward

---

## 4. 구현 계획

### 파일 변경

| 파일 | 변경 | 규모 |
|------|------|------|
| `env_cfg.py` | TRAIN_VERSION, observation 추가, phase clock params, reward 정리 | ~50줄 |
| `rewards.py` | phase_contact_reward, phase_velocity_reward 추가, 중복 reward 제거 | ~100줄 |
| observation 설정 | policy observation에 phase clock 8차원 추가 | ~10줄 |

### 단계적 구현

1. **Phase clock observation 추가 + phase_contact_reward만** (최소 변경)
2. 부팅 확인 후 reward 정리 진행
3. 교훈 #12: 한 번에 너무 많이 바꾸지 않되, 구조 자체가 틀리면 재설계

---

## 5. 리스크

1. **observation space 변경** — from-scratch 필수, 기존 policy 호환 불가
   - 완화: 48→56차원은 소폭 변경, 학습에 큰 영향 없을 것

2. **phase clock 주파수 불일치** — SpotMicro 기구학에 안 맞으면 학습 실패
   - 완화: 2.0 Hz에서 시작, 1.5~3.0 Hz 범위에서 실험
   - 감지: phase reward가 0 근처이면 주파수 불일치

3. **reward 대폭 정리로 부팅 실패** — 교훈 #10
   - 완화: phase reward만 먼저 추가, reward 정리는 부팅 확인 후
   - 대비: 기존 reward 유지하면서 phase reward만 추가하는 보수적 버전

4. **splay가 gait 교정으로 자동 해결 안 될 수 있음**
   - 완화: Soft CaT 유지하여 이중 안전망
   - 감지: trot은 되는데 shoulder dev 변화 없으면 → splay는 보행과 독립된 문제

---

## 6. 판정 기준

필수:
1. shoulder dev < 0.35 또는 baseline(0.45) 대비 20% 이상 감소
2. ep_len > 200
3. phase_contact_reward > 0 (phase에 맞춰 걷고 있음)

보조:
4. stride > 6.0
5. FL/FR contact ratio < 0.70 (앞발 과고정 해결)
6. diagonal_coupling 개선

관찰:
7. splay% (CaT 작동 여부)
8. forward_velocity

---

## 7. 참고 논문

- CaT: Constraints as Terminations (IROS 2024) — [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)
- Barrier-Based Style Rewards (KAIST, ICRA 2025) — [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)
- 교훈 #11: Gait 패턴은 "발견"보다 "지시"가 안정적
- Solo-12: phase clock + CaT로 2.5kg 로봇 trot 달성
