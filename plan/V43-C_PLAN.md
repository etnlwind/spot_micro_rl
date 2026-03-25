# V43-C Plan: Joint Default Pose Weight 완화

> 작성: 2026-03-25
> 상태: **훈련 중 — boot 실패 확인 (V43/V43-B와 동일)**

---

## 1. V43-B 실패 분석

V43-B에서 propulsion gating을 완전 비활성화해도 boot 실패 → gating이 원인 아님.

### 가설

joint_default_pose weight -2.0이 초기 탐색을 억제:
- 로봇이 서려면 관절을 기본 자세에서 벗어나야 함
- -2.0 penalty가 움직임 자체를 벌칙 → "안 움직이는 게 낫다" → 넘어짐

V42 PLAN 원래 설계: -0.5
V43에서 -2.0으로 4배 강화 (exploit 억제 목적)

---

## 2. V43-C 변경

| 항목 | V43-B | V43-C |
|------|-------|-------|
| joint_default_pose 초기값 | -2.0 | **-0.3** |
| pose ramp | 없음 | iter 1000~2500: **-0.3 → -2.0** |
| 나머지 | 그대로 | 그대로 (gate_alpha ramp 유지) |

### 설계 의도

- Boot phase: -0.3으로 자유 탐색 허용
- Refinement phase: -2.0까지 올려 자세 교정
- 원인 분리: gate 구조 유지 + pose weight만 변경

---

## 3. 훈련 결과

- **Run**: `2026-03-25_17-47-00`
- **결과**: **boot 실패 — V43/V43-B와 동일**

### 3버전 비교 (iter 500 기준)

| 지표 | V43 | V43-B | V43-C |
|------|-----|-------|-------|
| ep_len | 8.3 | 8.3 | 8.3 |
| forward_velocity | 0.015 | 0.016 | 0.017 |
| gait_phase | 0.17 | 0.17 | 0.19 |

**3회 연속 동일 결과.** joint_default_pose도 boot 실패의 원인이 아님.

---

## 4. 근본 원인 발견

V43-C 실패 후 심층 분석에서 **진짜 원인 발견**:

### Phase별 Reward 충돌 분석

| Reward | Weight | Boot(서기)에서 역할 |
|--------|--------|:-------------------:|
| alive_bonus | +10 | **서있어라** |
| base_height_l2 | -15 | **높이 맞춰라** |
| flat_orientation_l2 | -7 | **넘어지지 마** |
| **feet_air_time** | **+20** | **발을 들어라** ← 서야 하는데?? |
| **gait_phase** | **+15** | **phase 맞춰라** ← 서지도 못하는데?? |
| **stride_length** | **+5** | **보폭 넓혀라** ← 의미 없음 |
| **forward_velocity** | **+8** | **앞으로 가라** ← 설 수가 없는데?? |

Boot에서 해로운 reward 총 weight: **56** (8+20+15+5+8)
Boot에서 도움되는 reward 총 weight: **~57** (10+15+7+20+...)

**50:50 충돌** — "서라"와 "걸어라"가 동등하게 싸움.

### 결정적 증거: V38.3 vs V43-C 비교

```
V38.3 (50 rewards, boot SUCCESS):
  iter 50: ep_len=44.9, feet_air_time=0.0000 (GATED!)

V43-C (15 rewards, boot FAILURE):
  iter 50: ep_len=14.1, feet_air_time=-0.0284 (ACTIVE!)
```

**V38.3의 기존 reward_weight_curriculum에는 gait_gate가 있었다!**
- `ep_len < 200`이면 feet_air_time 등 walking reward를 OFF
- V42 "clean restart"에서 80개 파라미터 curriculum 제거 시 이 핵심 메커니즘도 함께 제거

### 추가: feet_air_time weight 문제

| 프로젝트 | feet_air_time weight |
|---------|---------------------|
| Isaac Lab flat 예제 | **0.75** |
| legged_gym 기본 | **1.0** |
| V43 | **20.0** (20~27배) |

Weight 20은 전체 positive reward budget의 30%를 차지. Boot에서 이것이 "발 들어라"를 가장 강하게 외치고 있었음.

---

## 5. 결론 및 다음 단계

**3번의 실험(V43/V43-B/V43-C)으로 확인:**
1. propulsion gating → 원인 아님 (V43-B)
2. joint_default_pose → 원인 아님 (V43-C)
3. **walking reward가 boot에서 active** → 근본 원인 (V38.3 증거)

→ **V43-D: Walking reward boot gating** (서기 → 걷기 순서 복원)

---

## 6. 교훈

1. **V42 clean restart의 진짜 실수**: reward 수를 줄인 것이 아니라, **gait_gate 메커니즘을 함께 제거**한 것
2. **reward 설계 시 phase별 충돌 분석 필수**: 개별 reward는 모두 합리적이지만, boot phase에서 함께 작동하면 충돌
3. **3회 실패가 필요했던 이유**: 표면 분석(gating 문제, pose 문제)으로 넘어가면 근본 원인을 놓침
4. **기존 검증된 메커니즘을 제거할 때는 왜 그것이 있었는지 먼저 이해해야 함**
