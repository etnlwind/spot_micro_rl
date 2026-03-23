# V39 Plan: Splay 교정 0.45→0.30 — 3가지 접근 후보

> 작성: 2026-03-23
> 상태: 설계 중

---

## 1. Context

### V38 시리즈 결론

| 접근 | shoulder dev | 한계 |
|------|-------------|------|
| L2 penalty (V37.2) | 0.54 고착 | reward 채널 — agent가 상쇄 |
| Soft CaT prob 0.0015 (V38.3) | **0.45 정체** | discount 채널 — local optimum |

**CaT가 달성한 것**: 0.54 → 0.45 (-16%). Soft CaT framework은 안정적으로 작동.
**CaT가 못한 것**: 0.45 이하 진입. agent가 30% 에피소드 손실을 감수하는 전략 선택.

### 근본 원인 분석

agent가 0.45에서 멈추는 이유:
- **어깨를 더 모으면 보행 효율이 떨어짐** — 현재 reward 구조에서 "벌어진 자세로 걷기"가 "모은 자세로 걷기"보다 총 보상이 높음
- **CaT는 벌칙 채널** — "나쁜 자세를 벌주는" 것이지 "좋은 자세를 보상하는" 것이 아님
- **reward 항목 50개** — 상호작용이 복잡하여 shoulder penalty가 다른 reward에 묻힘

### V39 목표

shoulder dev 0.45 → **0.30 이하**, ep_len > 200, stride > 6.0 유지

---

## 2. 후보 A: CaT + L2 병행 강화

### 설계

CaT(discount 채널)는 유지하면서 L2 penalty(reward 채널)를 동시 강화.
두 채널의 동시 압력으로 local optimum의 균형점을 이동.

### 변경

- Soft CaT: prob 0.0015 유지 (V38.3 그대로)
- shoulder_neutral_penalty weight: -6.0 → **-12.0** (2배)
- 나머지 모든 파라미터 동일

### 근거

- V37.2에서 L2 단독으로는 -10까지 올려도 효과 없었음
- 하지만 CaT와 병행하면 상황이 다름:
  - CaT가 이미 0.45까지 밀어넣은 상태에서 L2를 강화
  - agent가 "30% CaT 손실 + L2 penalty 증가"를 동시에 받으면 균형점 이동 가능
- V37.2 실패는 "L2 단독"이었기 때문이지 "L2 자체"가 무의미한 것은 아님

### 리스크

- **낮은 리스크**: 코드 변경 최소 (weight 하나), from-scratch 아닌 V38.3 checkpoint resume 가능
- **중간 리스크**: L2 -12가 다른 reward와 간섭 — reward 총합 변동으로 학습 불안정
- **가능한 결과**: 0.45에서 소폭 감소 (0.40~0.42) 하지만 또 다른 local optimum

### 소요

- 코드 변경: 1줄 (env_cfg.py weight)
- 검증: prob 파라미터 변경 없으므로 수치 검증 불필요
- 예상 판정: iter 3000~4000 (기존 V38.3에서 ramp 이미 완료 상태로 resume)

---

## 3. 후보 B: Reward 구조 개편

### 설계

50개 reward를 25개로 정리하면서, "올바른 자세로 걷기"에 대한 positive incentive를 강화.
CaT는 유지하되 핵심은 reward 구조 변경.

### 핵심 변경 방향

1. **중복 reward 제거**:
   - front/rear 개별 항목 축소 (front_swing, rear_swing 등 → 4발 공통)
   - residency 관련 5~6개 → 1~2개로 통합
   - propulsion_floor, contact_floor 등 floor 항목 → band 항목으로 통합

2. **Positive posture reward 추가**:
   - "shoulder dev < 0.3이면 bonus" — 올바른 자세에 대한 직접 보상
   - 현재는 penalty만 있고 reward가 없음 → "좋은 자세를 찾을 동기" 부재

3. **4발 공통 신호 중심 재정렬**:
   - front/rear 비대칭 reward 최소화 (교훈 #9: 역할 분리 유발)
   - trot_gait, diagonal_coupling 등 전체 gait 보상 강화

### 리스크

- **높은 리스크**: reward 구조 대폭 변경은 부팅 실패 가능성 있음 (교훈 #10, #12)
- **높은 리스크**: reward 항목 간 상호작용 예측 불가
- **from-scratch 필수**: resume 불가

### 소요

- 코드 변경: rewards.py + env_cfg.py 대규모 (100줄+)
- 검증: 각 reward weight의 예상 기여도 테이블 작성 필수
- 예상 판정: iter 3000~5000 (부팅+안정화+CaT ramp)

---

## 4. 후보 C: 구조적 Gait 유도 (CPG/Phase Clock)

### 설계

reward로 유도하는 것이 아니라, **보행 패턴 자체를 구조적으로 강제**.
CPG(Central Pattern Generator) 또는 phase clock을 observation에 추가하여
agent가 "언제 어떤 발을 들어야 하는지"를 명시적으로 알 수 있게 함.

### 핵심 변경

1. **Phase clock observation 추가**:
   - 4개 다리 각각의 phase (0~2π)를 observation에 추가
   - Trot 패턴: FL-RR 동위상, FR-RL 동위상, 두 쌍은 반위상
   - Agent가 phase에 맞춰 다리를 움직이면 reward

2. **Phase-conditioned reward**:
   - swing phase에서 발이 들려있으면 reward
   - stance phase에서 발이 닿아있으면 reward
   - 이것이 자연스럽게 trot을 유도하고, 앞발 과고정도 해결

3. **어깨 각도는 CaT + phase reward로 간접 제어**:
   - trot으로 걸으면 어깨가 자연스럽게 모임 (정상 보행 기구학)
   - 현재 splay는 "비정상 보행(앞발 고정+셔플)"의 부산물일 가능성

### 근거 (논문)

- Solo-12 (IROS 2024): phase clock + CaT로 자연스러운 trot 달성
- Barrier-Based Style Rewards (ICRA 2025): gait phase로 자세 유도
- 교훈 #11: Gait 패턴은 "발견"보다 "지시"가 안정적

### 리스크

- **높은 리스크**: observation space 변경 → 기존 policy 전부 호환 불가, from-scratch 필수
- **중간 리스크**: phase clock 주파수 설정 — 로봇 기구학에 맞는 trot 주기 필요
- **높은 보상**: splay + 앞발 과고정 + 셔플링 3가지 문제를 동시에 해결할 가능성

### 소요

- 코드 변경: observation 추가 + reward 함수 추가 + env_cfg 변경 (200줄+)
- 검증: phase clock 주파수 계산, observation dim 변경 확인
- 예상 판정: iter 5000+ (완전 새 구조)

---

## 5. 비교 요약

| | 후보 A: CaT+L2 | 후보 B: Reward 개편 | 후보 C: CPG/Phase |
|---|---|---|---|
| **변경 규모** | 1줄 | 100줄+ | 200줄+ |
| **리스크** | 낮음 | 높음 | 높음 |
| **예상 효과** | 0.40~0.42 (소폭) | 불확실 | 0.30 이하 가능 |
| **resume 가능** | O (V38.3 checkpoint) | X | X |
| **앞발 과고정 해결** | X | 부분적 | O |
| **판정 시간** | ~3000 iter | ~5000 iter | ~5000 iter |
| **교훈 #12 준수** | O (최소 변경) | X (대규모) | X (대규모) |

---

## 6. 추천 순서

**단계적 접근 (리스크 최소화)**:

1. **먼저 후보 A** — 가장 빠르고 저위험. V38.3 checkpoint에서 resume 가능.
   - 성공 시: 0.40 달성 → 후보 C로 이동 (gait 구조화)
   - 실패 시: L2+CaT 병행도 한계 확인 → 후보 B 또는 C로 이동

2. **후보 A 실패 시 후보 C** — splay가 "비정상 보행의 부산물"이라면 gait 구조화가 근본 해결
   - reward 개편(B)보다 CPG(C)가 더 직접적
   - B는 "어떤 reward를 얼마나"의 탐색 공간이 너무 넓음

3. **후보 B는 C와 병행** — reward 정리는 C 구현 시 함께 진행 (50→25개)

---

## 7. 판정 기준 (공통)

필수:
1. shoulder dev < 0.35 또는 baseline(0.45) 대비 20% 이상 감소
2. splay% peak 대비 30% 이상 감소 (정책 적응 확인)
3. ep_len > 200

보조:
4. stride > 6.0
5. forward_velocity > 1.0

관찰:
6. FL/FR contact ratio
7. diagonal_coupling_raw
