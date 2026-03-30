# V44 Plan: Trot Quality — Coupling 복원 + Pose 완화

> 작성: 2026-03-26
> 상태: **수렴 확정 — stride 진동(1.3~2.4), splay 0.52 고착, coupling 0.0**

---

## 실험 일지

### 출발점

`V43-E`는 boot 자체는 해결했지만, `clean reward` 위에서 실제 trot 구조는 만들지 못했다.
즉 `V44`의 출발점은 `boot를 유지한 채 stride와 coupling을 다시 살리는 것`이었다.

### 처음 가설

처음 가설은 단순했다.

```text
1. diagonal_coupling을 복원하면 trot 구조가 살아날 것이다
2. joint_default_pose를 약하게 하면 stride가 열릴 것이다
```

### 실제로 한 변경

`V44`는 사실상 아래 두 축을 동시에 건드린 실험이었다.

```text
- coupling 복원
- pose penalty 완화
```

### 결과

결과는 "부분 성공 + 새 trade-off 발견"이었다.

```text
- stride는 0.39 -> 1.69로 개선
- 하지만 coupling은 여전히 0.0
- shoulder/splay는 0.53으로 악화
```

### 이 실험이 남긴 교훈

`V44`는 `stride와 splay를 같이 만지면 원인 분리가 안 된다`는 것을 확인한 버전이다.
즉 이후 `V45`, `V46`은 같은 문제를 더 작은 가설로 나눠서 시험하게 된다.

## 1. V43-E 결과 분석

### 성과

V43-E는 **V43 시리즈 6회 반복 끝에 boot를 해결**한 역사적 버전:

| 지표 | V43-E | 판정 |
|------|:-----:|:----:|
| ep_len | **248** | PASS (목표 230) |
| forward_velocity | **5.88** | PASS (목표 1.0) |
| shoulder_dev | **0.40** | 역대 최고 (V38.3: 0.45) |
| bad_orientation | **0.8%** | 거의 완벽 |

### 한계: 종종걸음 수렴

| 지표 | V43-E | V38.3 (기준) | 배율 |
|------|:-----:|:----------:|:----:|
| stride | 0.39 | 6.94 | **18배 부족** |
| diagonal_coupling | 0.0 | 0.52 | **완전 미형성** |
| feet_air_time | -0.87 | -5.87 | 발 들기 부족 |

### 종종걸음이 수학적 최적해인 3가지 이유

**1. forward_velocity(5.97) >> stride(0.42) = 14배 불균형**
```
로봇의 계산: "보폭 없이 빠르게" = forward_velocity 극대화
stride를 2배 늘려봤자 +0.42 추가, forward_velocity는 이미 5.97
→ 보폭 늘릴 인센티브 없음
```

**2. joint_default_pose(-11.69) = 전체 penalty의 51%**
```
큰 보폭 시도: stride +1.58 vs pose_penalty -6.31 = net -4.73 손해
작은 보폭 유지: 현상 유지가 합리적
→ pose penalty가 큰 보폭을 차단
```

**3. diagonal_coupling reward 부재**
```
V43에서 "gait_phase가 대체" 기대하며 제거
실제 결과: gait_phase(12.1)는 높지만 coupling(0.0) = 완전 실패
→ phase timing만 맞추고 실제 대각 교대는 안 함
```

---

## 2. V43-E vs V38.3 보행 패턴 비교

### V38.3: "비대칭 trot" (stride 6.94)
```
앞발: 거의 안 듦 (swing 0.05~0.07), 접지 유지하며 추진 (prop 0.61~0.67)
뒷발: 크게 들어서 멀리 뻗음 (lift 0.49~0.75, swing 0.37~0.49)
→ 비대칭이지만 보폭 크고 효율적
→ diagonal_coupling 0.52 (대각 교대 형성)
```

### V43-E: "4발 균등 종종걸음" (stride 0.39)
```
4발 모두: 비슷하게 작게 듦 (lift 0.20~0.40, swing 0.48~0.67)
4발 모두: 비슷한 추진력 (prop 0.32~0.52)
→ 대칭적이지만 보폭 없고 비효율적
→ diagonal_coupling 0.0 (교대 패턴 없음)
```

### 핵심 통찰: "15개 clean reward는 splay는 해결했지만 보행은 가르치지 못함"

V42의 가설 "reward 수를 줄이면 자연스러운 trot이 나온다"는 **절반만 맞았다**:
- splay 해결: ✓ (shoulder_dev 0.45→0.40)
- trot 형성: ✗ (coupling 0.52→0.0, stride 6.94→0.39)

50개 reward에 있던 `leg_lift`, `rear_alternation`, `swing_stride`, `diagonal_coupling` 등이 **"어떻게 걸을지"를 구체적으로 가르치는 역할**이었다. 이것들을 제거하면 로봇은 가장 쉬운 방법(종종걸음)을 찾는다.

---

## 3. V44 설계

### 핵심 변경 2가지 (독립적 축)

**변경 1: diagonal_coupling 복원 (+10)**
```
역할: trot 패턴의 "방향" 제공
  → "FL+RR / FR+RL 대각선 다리를 교대하면 보상"
  → V43에서 제거: "gait_phase가 대체" → 실패 증명됨 (coupling=0.0)
  → V38.3에서 0.52로 검증됨

V43에서 제거한 이유: gait_phase_contact에 흡수
실패 증거: gait_phase 12.1인데 coupling 0.0 → phase는 맞추지만 교대는 안 함
```

**변경 2: joint_default_pose 완화 (-2.0→-0.5)**
```
역할: 큰 보폭의 "허가"
  → 현재 penalty 51% (-11.69) → 약 13% (-2.92)로 감소
  → 큰 관절 변위가 허용되어 보폭 증가 가능

리스크: shoulder_dev 증가 가능
  → 현재 0.40, V38.3은 0.46. 0.05 여유 있음
  → -0.5 weight면 여전히 극단적 자세는 억제됨
```

### 왜 두 변경을 동시에?

| 단독 변경 | 예상 결과 | 문제 |
|----------|----------|------|
| coupling만 | 작은 trot (교대는 하지만 보폭 작음) | pose penalty가 큰 보폭 차단 |
| pose만 | 큰 종종걸음 (큰 움직임이지만 교대 없음) | trot 방향 신호 없음 |
| **둘 다** | **정상 trot (교대 + 큰 보폭)** | — |

두 변경은 독립적 축:
- coupling → 패턴 (어떤 순서로)
- pose → 크기 (얼마나 크게)

결과 분석으로 원인 분리 가능:
- stride 올라가면 → pose 완화 효과
- coupling 올라가면 → coupling reward 효과
- 둘 다 올라가면 → 두 변경 모두 필요했음

### 분석팀 피드백 반영

**1. coupling은 walking ramp에 포함 (iter 800~2000)**
- 처음부터 full on이면 boot 회귀 위험
- V43-E의 boot 성공을 보호하는 것이 최우선
- walk_ramp_config에 `"diagonal_coupling": {"target": 10.0, "start": 800, "end": 2000}` 추가

**2. pose -0.5 직행 + adaptive safety**
- 수학적으로 -1.0은 불충분 (net -0.17, 여전히 BLOCKED)
- -0.5에서 비로소 net +0.70 (POSSIBLE)
- 대신 adaptive safety로 splay/boot 퇴행 감지 시 -1.0 fallback

**3. Adaptive safety: smoothed 평균 + 이중 조건**
- 단일 시점값은 PPO 탐색 노이즈에 과민 반응 → EMA(alpha=0.03, ~230 iter 반응) 사용
- shoulder_dev > 0.45 (splay 축) OR ep_len < 200 (boot 축) → pose -1.0 fallback
- V44 문서의 다른 판정도 구간 기반 → EMA로 일관성 유지
- 두 조건 OR: V44의 핵심 리스크 2개(splay 복귀, boot 퇴행)를 동급으로 방어

### 나머지 V43-E 구조 유지

- boot_standing + boot_contact ramp: 그대로
- walking reward gating (5-Phase): 그대로
- gate_alpha ramp: 그대로
- forward_velocity_gated: 그대로
- 8192 envs: 그대로
- 기능 플래그: `_CLEAN_REWARDS=True`, `_CONNECTED_TROT=True`

---

## 4. Reward Budget 예상 (V44)

### 현재 V43-E (iter 2672)

```
Positive:  gait(12.1) + alive(10.0) + prop(7.4) + fwd(6.0) + stride(0.4) = 36.5
Negative:  pose(-11.7) + action(-3.7) + limits(-3.6) + acc(-3.0) + feet(-0.8) = -22.8
Net:       +13.7
```

### V44 예상 (coupling 추가, pose 완화)

```
Positive:  gait(12) + alive(10) + coupling(~3) + prop(7) + fwd(5) + stride(~2) = ~39
Negative:  pose(-2.9) + action(-3.7) + limits(-3.6) + acc(-3.0) + feet(-0.8) = -14.0
Net:       +25 (현재보다 +11 개선)
```

pose penalty가 -11.7→-2.9로 감소하면 **net reward가 크게 증가**하여 로봇이 더 적극적으로 큰 동작을 시도할 여유가 생김.

---

## 5. 판정 기준

### iter 500: Boot 유지 확인

| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 200 | < 100 (boot 퇴행) |

### iter 1500: Trot 형성

| 지표 | 성공 | 부분 | 실패 |
|------|------|------|------|
| stride | > 2.0 | 1.0~2.0 | < 0.5 (V43-E 동일) |
| diagonal_coupling | > 0.2 | 0.05~0.2 | 0.0 |

### iter 3000: 최종 판정

| 지표 | 목표 |
|------|------|
| ep_len | > 230 |
| stride | > 3.0 (V38.3의 절반 수준이면 성공) |
| diagonal_coupling | > 0.3 |
| shoulder_dev | < 0.45 (V38.3 수준 이내) |

---

## 6. 리스크

### 1. shoulder_dev 증가 (splay 복귀)
- **원인**: pose penalty 완화로 어깨 벌어짐 허용
- **감지**: shoulder_dev > 0.45
- **대비**: pose weight -0.5→-1.0 중간값

### 2. ep_len 감소 (boot 퇴행)
- **원인**: coupling reward가 초기 학습을 불안정하게
- **감지**: iter 500에서 ep_len < 100
- **대비**: coupling을 walking ramp에 포함 (iter 800+ 활성화)

### 3. stride 여전히 정체
- **원인**: stride reward 함수 자체의 한계 또는 weight 부족
- **감지**: iter 2000에서 stride < 1.0
- **대비**: stride weight 5→15 상향 또는 V38.3 stride 관련 reward 복원

### 4. coupling은 올라가지만 stride는 안 올라감
- **원인**: 대각 교대는 하지만 보폭은 여전히 작음 → pose penalty는 여전히 작용
- **감지**: coupling > 0.2, stride < 1.0
- **대비**: pose weight 추가 완화 또는 stride weight 상향

---

## 7. V43 시리즈 → V44 전체 여정

| 버전 | 핵심 변경 | 결과 | 해결한 것 | 남은 것 |
|------|----------|------|----------|--------|
| V43 | 15개 connected reward | boot 실패 | - | boot 자체 |
| V43-B | gate_alpha ramp | boot 실패 | - | boot (gating ≠ 원인) |
| V43-C | pose -2.0→-0.3 | boot 실패 | - | boot (pose ≠ 원인) |
| V43-D | Walking reward gating | ep_len 10 (+20%) | walking 충돌 제거 | positive 부족 |
| V43-E | boot_standing + boot_contact | **ep_len 248, shoulder 0.40** | **boot, splay** | **stride, coupling** |
| **V44** | **coupling + pose 완화** | **stride 1.3~2.4 진동, splay 0.52, coupling 0.0** | pose↓→stride↑ 확인 | **shoulder-leg 분리 필요** |

### V44 최종 결과 (iter 4467)

| 지표 | V43-E | V44 | 변화 |
|------|:-----:|:---:|:----:|
| ep_len | 248 | **250** | 유지 |
| forward_vel | 5.88 | **6.91** | +18% |
| stride | 0.39 | **1.3~2.4** | 개선 but 진동 |
| coupling | 0.0 | **0.0** | 변화 없음 |
| shoulder_dev | **0.40** | **0.52** | 악화 |
| bad_orient | 0.8% | **0.3%** | 개선 |

**결론**: pose 완화가 stride를 풀어준 것은 확인 (가설 맞음). 하지만 pose↔splay trade-off와 coupling 실패는 해결 못함.

→ **V45**: shoulder와 leg를 분리하여 trade-off 해소 + pair coupling + leg_lift 복원

### 핵심 교훈 누적

1. reward 충돌 분석이 설계 전에 필수 (V43 boot 실패)
2. reward를 끄는 것 ≠ 대체하는 것 (V43-D positive 부족)
3. net reward 부호가 학습 방향 결정 (V43-D net negative)
4. positive/negative ratio가 boot 예측 변수 (V38.3: 0.82)
5. **reward 수를 줄이는 것 ≠ 정답. 핵심은 "어떤 reward"** (V43-E 종종걸음)
6. **종종걸음은 reward 불균형의 수학적 최적해** (forward >> stride, pose penalty 51%)
7. **joint_default_pose는 shoulder와 leg를 분리해야 함** (V44 trade-off 확인)
8. **output=0 reward는 weight를 올려도 0** (V44 coupling 1500+ iter 무효)

---

## 8. 참고

- V43-E: Boot 성공, 종종걸음 수렴 분석
- V38.3: 보행 품질 기준 (stride 6.94, coupling 0.52)
- V42: "reward 수 줄이기" 가설의 절반 성공 (splay ✓, trot ✗)
- V41: 초기 형성 조건 재설계 철학 (boot standing에 적용됨)
