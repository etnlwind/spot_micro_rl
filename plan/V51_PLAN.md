# V51 Plan: Soft Height Gate Hybrid

> 작성: 2026-03-28
> 상태: **완료 — boot-gated w=40으로 front_lift 0.257 달성 (역대 최고), 이후 하락 → V52로 이관**

---

## 1. 왜 Soft Height Gate가 필요한가

### V50 시리즈의 결론

V50, V50.1, V50.2 모두 동일 패턴: **초반 높이 달성 → walking 활성화 후 하락**.

### Reward Budget 분석 (V50 실측 기반)

```
Walking rewards:    +60.8/step
  stride, coupling, band, propulsion, alternation 등

Tracking rewards:    +1.3/step
  forward_vel, track_ang 등

Penalties:          -76.0/step
  joint_vel, joint_acc, action_rate, stance_width, foot_extension 등

Alive bonus:        +10.0/step

Standing rewards:    +3.9/step
  standing_height, boot_standing 등

━━━━━━━━━━━━━━━━━━━━━━━━━━━
Walking vs Height 비율: 60.8 : 3.9 = 15.6 : 1
→ "낮아도 앞으로 가면 보상" 구조
```

**구조적 변경이 필요**: walking reward 자체에 높이 조건을 거는 방식.

### 분석팀 협업

분석팀과의 협의를 통해 **Standing-First + Soft Gate** hybrid 접근법 도출:

1. **Standing reward는 항상 풀 보상** (ungated) — 서 있는 것 자체를 항상 보상
2. **Walking reward에 높이 조건부 penalty** — 낮으면 walking 보상 감소
3. **Boot phase에서는 gate OFF** — 부팅 시 penalty 없이 먼저 서기

---

## 2. Soft Height Gate 설계

### Gate 함수

```python
gate = clamp((h - 0.17) / 0.04, 0.2, 1.0)
penalty = (gate - 1.0) * weight
```

| 높이 h | gate 값 | penalty (w=40) |
|:------:|:-------:|:--------------:|
| > 0.21 | 1.0 | 0 (영향 없음) |
| 0.19 | 0.5 | -20 |
| 0.17 | 0.0 → 0.2 | -32 |
| < 0.17 | 0.2 | -32 |

### 핵심 설계 원칙

```
1. Standing/Survival reward: ungated (항상 풀 보상)
   → alive_bonus, boot_standing, standing_height 등
   → 높이와 관계없이 "살아있으면 보상"

2. Walking reward: gated (높이 조건부)
   → stride, coupling, band reward 등
   → 낮으면 penalty → "낮게 걸으면 손해"

3. Boot phase: gate OFF
   → gait_gate 해제 전에는 height gate도 비활성
   → 부팅 시 penalty로 죽는 것 방지
```

---

## 3. 구현 이력: 3번의 시행착오

### 시도 1: V51 w=40, 항상 활성

```python
height_walking_gate_weight = 40.0
boot_gated = False  # 항상 ON
```

**결과**: ep_len = 10 고착 (즉사)

#### Per-step net reward 계산 (w=40, 항상 활성)

```
Boot phase (h < 0.17, 아직 서지 못함):
  height_gate penalty: (0.2 - 1.0) × 40 = -32.0/step
  alive_bonus:                            +10.0/step
  boot_standing:                          +20.0/step (초기값)
  기타 penalty (joint 등):               ~-5.0/step
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  net = -32.0 + 10.0 + 20.0 - 5.0 = -7.0/step
  → ep_len 10 기준: 10 × (-7.0) = -70 총 보상
  → 즉시 죽으면: 0 총 보상 → 죽는 게 이득!
```

**교훈 #25**: penalty weight는 alive_bonus 초과 금지 (죽는 게 이득 방지)
→ 이 경우 penalty 자체가 문제가 아니라, **boot phase에서 적용되는 것**이 문제.

### 시도 2: V51 w=15, 항상 활성

```python
height_walking_gate_weight = 15.0
boot_gated = False  # 항상 ON
```

**결과**: ep_len = 30, 느린 부팅, "수갑 자세"

#### Per-step net reward 계산 (w=15, 항상 활성)

```
Boot phase (h < 0.17):
  height_gate penalty: (0.2 - 1.0) × 15 = -12.0/step
  alive_bonus:                            +10.0/step
  boot_standing:                          +20.0/step
  기타 penalty:                           ~-5.0/step
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  net = -12.0 + 10.0 + 20.0 - 5.0 = +13.0/step
  → 죽지는 않지만, "움직이면 penalty 증가" → 수갑 자세
  → ep_len=30 겨우 살아남, 진행 안 됨
```

**교훈 #26**: height gate는 boot phase에서 비활성, walking phase에서만 적용.

### 시도 3: V51 w=40, boot-gated (성공)

```python
height_walking_gate_weight = 40.0
boot_gated = True  # gait_gate 해제 후에만 활성
```

**결과**: ep_len = 246, front_lift = 0.257 (역대 최고)

#### Boot-gated timeline

```
Boot phase (gait_gate 미해제):
  height_gate: OFF → penalty 0
  boot_standing: 20.0 → "서기" 학습만 담당
  alive_bonus: 10.0
  → 정상 부팅 진행

Walking phase (gait_gate 해제 후):
  height_gate: ON → 낮으면 penalty
  boot_standing: ramp-down 진행
  → "높게 서서 걸어야" 보상 극대화
```

```
Boot phase (gait_gate 미해제):
  → height gate OFF → 정상 부팅
  → boot_standing이 "서기" 학습 담당

Walking phase (gait_gate 해제):
  → height gate ON → 낮으면 penalty
  → "높게 서서 걸어야" 보상 극대화
```

---

## 4. 결과: V51 boot-gated iter 331

### 주요 지표

| 지표 | V50 (iter 1074) | V51 (iter 331) | 변화 |
|------|:---------------:|:--------------:|:----:|
| ep_len | 246 | 246 | 유사 |
| **front_leg_lift** | **0.092** | **0.257** | **179% 개선** |
| front_clearance | 0.003 | **0.012** | 4배 |
| front_rear_symmetry | - | 2.55 | (첫 측정) |
| standing_height | 0.197 | **0.213** | 높이 개선 |
| stride | 6.59 | 2.03 | (아직 초반) |

**front_leg_lift 0.257은 V43 이후 모든 버전 통틀어 최고 기록**.

### 시간 경과에 따른 변화

그러나 시간이 지나면서 front_lift가 다시 하락:

```
iter 331:  front_lift = 0.257 (역대 최고)
iter 800:  front_lift = 0.15 (하락 시작)
iter 3300: front_lift = 0.035 (귀뚜라미 재발)
```

height gate가 초반에는 효과적이지만, **장기적으로 "낮아도 penalty 범위 내에서 최적화"하는 전략**을 학습.

---

## 5. V51의 한계: 왜 장기적으로 실패하나

### Height gate의 구조적 한계

```
gate 함수: h > 0.21이면 penalty=0
→ h=0.19~0.21 사이에서 "약간 낮지만 penalty 적음" 지점 발견
→ 그 높이에서 walking 최적화 → 뒷다리 밀기 + 앞다리 고정
→ 귀뚜라미 재발
```

height gate는 **크롤링(h<0.17) 차단에는 성공**했지만, **적당히 낮은 자세(h=0.19)에서의 귀뚜라미는 차단 못함**.

### V52로의 방향

- min_height termination (0.15m) 추가: 극단적 크롤링 완전 차단
- weight 재설계: 앞다리 포기의 경제적 이점을 데이터로 분석하여 대응

---

## 6. 핵심 교훈

| # | 교훈 | 출처 |
|---|------|------|
| 25 | penalty weight는 alive_bonus 초과 금지 (죽는 게 이득 방지) | V51 w=40 즉사 |
| 26 | height gate는 boot phase에서 비활성, walking phase에서만 적용 | V51 수갑 자세 |
| 27 | reward 변경 시 per-step net reward 부호 검증 필수 | V51 w=40 수치 검증 실패 |
| 28 | "잘 가라" > "앞으로 가라" — 보행 품질 우선 reward 철학 | V49~V51 전체 |

---

## 7. 판정 기준 (사후 평가)

| 시점 | 기준 | 결과 | 판정 |
|------|------|------|------|
| iter 300 | ep_len > 200 | 246 | 성공 |
| iter 300 | front_lift > 0.15 | 0.257 | **성공** |
| iter 1000 | front_lift 유지 | 하락 시작 | **부분 성공** |
| iter 3300 | front_lift > 0.10 | 0.035 | **실패** |

초반 성공, 장기 실패 → height gate 단독으로는 귀뚜라미 해결 불가.

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `rewards.py` | `height_walking_gate_penalty` 함수 추가 (soft gate) |
| `env_cfg.py` | height_walking_gate reward 등록 (w=40, boot-gated) |
| `curriculum.py` | height gate boot-gating 로직 (gait_gate 연동) |
