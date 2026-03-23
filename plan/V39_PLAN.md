# V39 Plan: CPG/Phase Clock + Soft CaT

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

### 핵심 가설 (검증 필요)

**"splay는 비정상 보행(앞발 고정+셔플)의 부산물이다. 정상 trot을 강제하면 splay가 자연스럽게 해결된다."**

근거:
- V38.3에서 FL contact 0.86→0.75, shoulder dev 0.54→0.45가 **동시에** 감소
- 정상 trot 기구학에서 어깨는 좌우 대칭으로 모이는 것이 자연스러움

반론:
- 상관관계일 뿐 인과관계는 미확인
- splay가 URDF 기구학/reward 구조의 독립적 문제일 가능성

→ **가설 검증이 V39의 핵심 목표**

### V39 목표

- **1차**: 정상 trot 달성 (앞발 과고정 해결, phase reward > 0)
- **2차**: shoulder dev 0.45 → 0.30 이하 (가설 A 입증 시)
- ep_len > 200, stride > 6.0 유지

---

## 2. 핵심 설계: CPG/Phase Clock

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

각 다리에 sin(phase), cos(phase) 2개씩 × 4다리 = 8개
- sin/cos 인코딩 → 0/2π 경계 불연속 없음
- 현재 48차원 → 56차원

### Phase-Conditioned Reward

```python
def phase_contact_reward(env):
    """swing phase에서 발이 들려있고, stance phase에서 닿아있으면 reward"""
    for each leg:
        if phase in swing_range:
            reward += (foot_not_touching) * weight
        else:  # stance
            reward += (foot_touching) * weight
```

### Soft CaT 유지

- V38.3의 Soft CaT 그대로 포함 (threshold 0.3, margin 0.3, prob 0.0015)
- CPG(positive: 올바른 gait 보상) + CaT(negative: splay 벌칙) 보완적 구조

---

## 3. 구현 단계 (교훈 #12: 한 번에 하나만)

### Phase 1: CPG만 추가 (V39.0)

- Phase clock observation 8차원 추가
- phase_contact_reward 1개만 추가
- **기존 50개 reward 그대로 유지** (정리는 나중)
- Soft CaT 그대로 유지
- from-scratch

**판정**: iter 1000에서 phase_contact_reward > 0이면 Phase 2 진행

### Phase 2: 주파수 확정 (V39.0~V39.2)

3개 주파수 병렬 테스트 (각 iter 1000에서 판정):
- V39.0: 1.5 Hz
- V39.1: 2.0 Hz
- V39.2: 2.5 Hz

**판정**: phase_contact_reward가 가장 높은 주파수 선택

### Phase 3: Reward 정리 (V39.3)

Phase 1~2에서 확정된 CPG 설정 위에 reward 정리:
- 50→25개 (중복 제거, front/rear 통합)
- 부팅 확인 후 진행

---

## 4. Phase Clock 주파수

SpotMicro 기구학에 맞는 trot 주파수:
- Solo-12 (2.5kg, 다리 20cm): 2.0 Hz
- SpotMicro (~0.5kg, 다리 ~10cm): **미확인 — 실험 필요**
- 후보: 1.5 Hz / 2.0 Hz / 2.5 Hz

**주파수가 틀리면 학습 실패**. iter 1000에서 phase reward가 0이면 주파수 불일치.

---

## 5. 예상 결과

### Best Case (~20%)

| 지표 | iter 3000 | iter 8000 | iter 15000 |
|------|-----------|-----------|------------|
| shoulder dev | 0.40 | 0.32 | 0.28 |
| splay% | 15% | 8% | 5% |
| ep_len | 230 | 240 | 245 |
| FL contact | 0.65 | 0.55 | 0.50 |
| phase reward | > 0 | 안정 상승 | 수렴 |

CPG가 trot 유도 성공, splay 자연 교정. **가설 A 입증**.

### Realistic Case (~40%)

| 지표 | iter 3000 | iter 8000 | iter 15000 |
|------|-----------|-----------|------------|
| shoulder dev | 0.45 | 0.42 | 0.40 |
| splay% | 20% | 18% | 15% |
| ep_len | 220 | 215 | 210 |
| FL contact | 0.72 | 0.68 | 0.65 |
| phase reward | > 0 | 소폭 상승 | 정체 |

Trot 부분 학습, 앞발 소폭 개선. shoulder dev는 V38.3(0.45)보다 소폭 개선.
**진전은 있지만 목표(0.30) 미달. Fallback(CaT prob 상향) 필요.**

### Worst Case (~40%)

| 지표 | iter 3000 |
|------|-----------|
| shoulder dev | 0.52 |
| ep_len | < 180 |
| phase reward | ~0 |

부팅 실패 또는 phase 학습 실패. 가능한 원인:
1. phase 주파수 불일치 → 다른 주파수로 재시도
2. phase reward와 기존 reward 충돌 (feet_air_time vs phase timing)
3. observation 해석 시간 부족 → iter 5000까지 연장

---

## 6. 리스크

1. **"trot하면 splay 해결" 가설이 틀릴 수 있음** (핵심 리스크)
   - 감지: trot은 되는데 shoulder dev 변화 없음
   - Fallback: CaT prob 0.0015→0.003 추가 상향

2. **phase 주파수 불일치**
   - 완화: 1.5/2.0/2.5 Hz 3개 실험
   - 감지: phase reward ≈ 0

3. **phase reward와 기존 feet_air_time 충돌**
   - feet_air_time: "발을 들어라" (타이밍 무관)
   - phase reward: "이 타이밍에 들어라"
   - 완화: 충돌 시 feet_air_time weight 하향

4. **from-scratch + observation 변경 → 부팅 불안정**
   - 완화: 48→56차원은 소폭. 기존 boot 3결합 유지

5. **reward 정리를 동시에 하면 원인 분리 불가** (교훈 #12)
   - **대응: Phase 1에서 reward 정리 안 함. CPG만 먼저 추가.**

---

## 7. 판정 기준

### Phase 1 판정 (iter 1000)

| 지표 | 통과 | 실패 |
|------|------|------|
| phase_contact_reward | > 0 | ≈ 0 → 주파수 변경 |
| ep_len | > 200 | < 150 → 부팅 실패 |

### 최종 판정 (iter 5000+)

필수:
1. phase_contact_reward > 0 (trot 학습됨)
2. ep_len > 200
3. shoulder dev 감소 추세 확인 (가설 검증)

보조:
4. stride > 6.0
5. FL/FR contact ratio < 0.70

가설 검증:
6. shoulder dev가 phase reward와 동시에 감소 → 가설 A (splay = gait 부산물)
7. shoulder dev 변화 없이 FL contact만 감소 → 가설 B (splay 독립 문제) → CaT prob 추가 상향

---

## 8. Fallback 전략

| 상황 | 대응 |
|------|------|
| phase 학습 실패 (reward ≈ 0) | 주파수 변경 (1.5→2.0→2.5) |
| trot 성공 + splay 미변화 | CaT prob 0.0015→0.003 상향 |
| 부팅 실패 | phase reward weight 하향 또는 기존 reward 복원 |
| 전체 실패 | reward 구조 근본 재설계 (후보 B 단독) |

---

## 9. 참고 논문

- CaT: Constraints as Terminations (IROS 2024) — [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)
- Barrier-Based Style Rewards (KAIST, ICRA 2025) — [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)
- 교훈 #11: Gait 패턴은 "발견"보다 "지시"가 안정적
- Solo-12: phase clock + CaT로 2.5kg 로봇 trot 달성
