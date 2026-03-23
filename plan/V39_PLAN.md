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

- **궁극 목표**: shoulder dev 0.30 이하
- **V39 1차 기대치**: shoulder dev **0.38~0.42** (V38.3의 0.45 대비 명확한 개선)
- **최소 성공 기준**: shoulder dev < 0.45 + 정상 trot (V38.3 대비 개선)
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

### Phase 1: CPG + 주파수 스윕 (V39.1~V39.3)

- Phase clock observation 8차원 추가
- phase_contact_reward 1개만 추가
- **기존 50개 reward 그대로 유지** (정리는 나중)
- Soft CaT 그대로 유지
- from-scratch
- **3개 주파수 병렬 테스트** (각 iter 1000 판정)

**판정**: phase_contact_reward가 전체 reward의 5% 이상 기여하는 주파수 선택

### Phase 2: 주파수 확정 — 필수 스윕 (V39.1~V39.3)

**Phase 1 결과에 관계없이** 3개 주파수를 짧게 테스트:
- **V39.1**: **2.0 Hz** (Solo-12 기준, 첫 시도)
- **V39.2**: **1.5 Hz** (SpotMicro 짧은 다리 보정)
- **V39.3**: **2.5 Hz** (빠른 주기)

각 iter 1000에서 판정:
- phase_contact_reward 전체 reward의 5% 이상 기여하는 주파수 선택
- 복수 통과 시: FL/FR contact ratio가 가장 낮은 주파수 선택
- 전부 실패 시: 1.0 Hz / 3.0 Hz 확장 스윕

**주파수 스윕은 리스크 완화가 아닌 필수 운영 계획**

### Phase 3: Reward 정리 (V39.4+)

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

**판정 원칙: V39의 최종 성공은 Axis 1(splay/posture)과 Axis 2(gait 구조) 2축의 동시 개선으로만 판정한다. 한 축만 개선된 경우 부분 성공으로 분류하고, 미개선 축에 대한 추가 전략을 설계한다.**

### Phase 1 판정 (iter 1000)

| 지표 | 통과 | 실패 |
|------|------|------|
| phase_contact_reward | **전체 reward의 5% 이상 기여** | ≈ 0 또는 미미 → 주파수 변경 |
| ep_len | > 200 | < 150 → 부팅 실패 |
| diagonal_coupling_raw | phase reward와 동시 상승 | 하락 → phase/gait 충돌 |

### 최종 판정 (iter 5000+) — 2축 분리 판정

**Axis 1: Splay/Posture 개선**
1. shoulder dev < 0.42 (V38.3의 0.45 대비 개선)
2. splay% 감소 추세 (CaT 작동 확인)

**Axis 2: Gait 구조 개선**
3. phase_contact_reward 전체 reward의 5% 이상 (phase를 실질적으로 따르는지)
4. FL/FR contact ratio < 0.70 (앞발 과고정 해결)
5. diagonal_coupling_raw 유지 또는 개선
6. gait_symmetry: rear pair 비대칭 감소

**공통:**
7. ep_len > 200
8. stride > 6.0

**판정 매트릭스:**

| Axis 1 (splay) | Axis 2 (gait) | 판정 |
|----------------|---------------|------|
| 개선 | 개선 | **완전 성공** — 가설 A 입증 |
| 미변화 | 개선 | **부분 성공** — gait OK, splay는 독립 문제 → CaT 상향 |
| 개선 | 미변화 | **의외** — phase 없이 splay 감소? 원인 분석 필요 |
| 미변화 | 미변화 | **실패** — 주파수/weight 조정 또는 구조 재설계 |

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
