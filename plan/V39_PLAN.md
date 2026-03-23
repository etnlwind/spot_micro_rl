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

**V39 1차 실험의 현실적 관심사는 0.30 즉시 달성이 아니라, 0.45 장벽을 구조적으로 깨고 0.38~0.42 구간에 안정 진입하는지 확인하는 것이다.**

### Step 1: 주파수 스크리닝 (V39.1 / V39.2 / V39.3)

3개 주파수 후보의 **부팅 + 초기 phase 반응**을 짧게 확인:
- **V39.1**: **2.0 Hz** (Solo-12 기준, 첫 시도)
- **V39.2**: **1.5 Hz** (SpotMicro 짧은 다리 보정)
- **V39.3**: **2.5 Hz** (빠른 주기)

공통 설정:
- Phase clock observation 8차원 추가
- phase_contact_reward 1개만 추가
- **기존 50개 reward 그대로 유지** (정리는 나중)
- Soft CaT 그대로 유지
- from-scratch

각 iter 1000 (구간 평균 iter 800~1000 기준)에서 판정:
- phase_contact_reward가 **전체 reward의 5% 이상** 기여하는 주파수 선택
- 복수 통과 시: FL/FR contact ratio가 가장 낮은 주파수 선택

**주파수 스크리닝은 리스크 완화가 아닌 필수 운영 계획.**

### Step 2: 확정 주파수 본실험

Step 1에서 선정된 주파수로 **단일 run 15000 iter 완주**:
- 확정 주파수의 V39.x run을 그대로 이어서 진행 (이미 1000 iter 완료)
- iter 5000+ 시점에서 2축 판정 (최근 500 iter 평균 기준)

### Step 3: Reward 정리 (V39.4+)

Step 2 완료 후 확정된 CPG 설정 위에 reward 정리:
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

### Best Case (~15~20%)

| 지표 | iter 3000 | iter 8000 | iter 15000 |
|------|-----------|-----------|------------|
| shoulder dev | 0.40 | 0.32 | 0.28 |
| splay% | 15% | 8% | 5% |
| ep_len | 230 | 240 | 245 |
| FL contact | 0.65 | 0.55 | 0.50 |
| phase reward | >5% | 안정 상승 | 수렴 |

CPG가 trot 유도 성공, splay 자연 교정. **가설 A 입증**.

### Realistic Case (~55%)

| 지표 | iter 3000 | iter 8000 | iter 15000 |
|------|-----------|-----------|------------|
| shoulder dev | 0.45 | 0.42 | 0.40 |
| splay% | 20% | 18% | 15% |
| ep_len | 220 | 215 | 210 |
| FL contact | 0.72 | 0.68 | 0.65 |
| phase reward | >5% | 소폭 상승 | 정체 |

Trot 부분 학습, 앞발 소폭 개선. shoulder dev는 V38.3(0.45)보다 소폭 개선.
**진전은 있지만 목표(0.30) 미달. Fallback(CaT prob 상향) 필요.**

### Worst Case (~25~30%)

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

### Step 1 판정: 주파수 스크리닝 (iter 800~1000 구간 평균)

| 지표 | 측정 방법 | 통과 | 실패 |
|------|----------|------|------|
| phase_contact_reward | **iter 800~1000 구간 평균** | 전체 reward의 5% 이상 기여 | ≈ 0 또는 미미 → 다음 주파수 |
| ep_len | iter 800~1000 구간 평균 | > 200 | < 150 → 부팅 실패 |
| diagonal_coupling_raw | iter 800~1000 구간 평균 | phase reward와 동시 상승 | 하락 → phase/gait 충돌 |

구간 평균을 사용하여 단일 시점 노이즈에 의한 오판을 방지한다.

### Step 2 판정: 본실험 (iter 5000+, 최근 500 iter 평균) — 2축 분리

모든 판정 지표는 **최근 500 iter smoothed 평균** 기준으로 측정한다.

**Axis 1: Splay/Posture 개선**
1. shoulder dev < 0.42 (V38.3의 0.45 대비 개선)
2. splay% 감소 추세 (CaT 작동 확인)

**Axis 2: Gait 구조 개선**
3. phase_contact_reward 전체 reward의 5% 이상 (최근 500 iter 평균)
4. FL/FR contact ratio < 0.70 (최근 500 iter 평균)
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

## 8. Fallback 전략 (실행 순서)

### 주파수 실패 시

1. V39.1 (2.0 Hz) iter 1000 판정 → 실패
2. V39.2 (1.5 Hz) + V39.3 (2.5 Hz) 동시 판정
3. 전부 실패 → 1.0 Hz / 3.0 Hz 확장 스윕
4. 그래도 실패 → phase_contact_reward weight 조정 (10→5 또는 15)
5. 그래도 실패 → feet_air_time과 phase reward 충돌 점검 (feet_air_time weight 하향)

### 본실험 결과별

| 상황 | 다음 행동 |
|------|----------|
| Axis 1+2 동시 개선 | 성공. Step 3 (reward 정리)로 진행 |
| Axis 2만 개선 (gait OK, splay 정체) | CaT prob 0.0015→0.003 상향 |
| Axis 1만 개선 (의외) | 원인 분석 후 판단 |
| 전체 미변화 | reward 구조 근본 재설계 |

---

## 9. 참고 논문

- CaT: Constraints as Terminations (IROS 2024) — [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)
- Barrier-Based Style Rewards (KAIST, ICRA 2025) — [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)
- 교훈 #11: Gait 패턴은 "발견"보다 "지시"가 안정적
- Solo-12: phase clock + CaT로 2.5kg 로봇 trot 달성
