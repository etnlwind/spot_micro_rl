# V43-D Plan: Boot-First Walking Reward Gating

> 작성: 2026-03-25
> 상태: **훈련 완료 — boot 개선(+20%) but 부족, V43-E로 발전**

---

## 1. 근본 원인

### V43/V43-B/V43-C 3회 연속 boot 실패의 근본 원인

**V42 "clean restart"에서 기존 `reward_weight_curriculum`의 gait_gate 메커니즘을 제거.**

기존 (V35.5~V38.3, boot 성공):
```
reward_weight_curriculum에 gait_gate 포함:
  ep_len < 200이면 walking reward OFF
  → 먼저 서기 학습, 선 다음에 걷기 학습
```

V42~V43 (boot 실패):
```
v42_boot_curriculum으로 교체 (경량화):
  contacts ramp + velocity ramp만 구현
  gait_gate 제거됨
  → walking reward가 iter 0부터 full weight로 active
  → "서라"(alive_bonus +10)와 "걸어라"(feet_air_time +20) 충돌
```

### 결정적 증거

```
V38.3 iter 50: ep_len=44.9, feet_air_time=0.0000 (GATED!)
V43-C iter 50: ep_len=14.1, feet_air_time=-0.0284 (ACTIVE!)
```

### Phase별 Reward 충돌 매트릭스 (V43-C iter 100 실측)

| Reward | Weight | Episode값 | Boot역할 | V43-D 활성화 |
|--------|--------|----------|:--------:|:-----------:|
| alive_bonus | +10 | 0.392 | HELPFUL | iter 0 |
| base_height_l2 | -15 | -0.002 | HELPFUL | iter 0 |
| flat_orientation_l2 | -7 | -0.016 | HELPFUL | iter 0 |
| undesired_contacts | ramp | -0.051 | HELPFUL | iter 0 |
| track_lin_vel_xy | +1 | 0.016 | NEUTRAL | iter 0 |
| track_ang_vel_z | +0.5 | 0.002 | NEUTRAL | iter 0 |
| action_rate_l2 | -0.5 | -0.310 | HELPFUL | iter 0 |
| dof_acc_l2 | -0.001 | -0.456 | HELPFUL | iter 0 |
| dof_pos_limits | -5 | -0.083 | HELPFUL | iter 0 |
| joint_default_pose | -0.3 | -0.416 | MILD | iter 0 (ramp) |
| **forward_velocity** | **+8** | 0.014 | **HARMFUL** | **iter 300** |
| **stance_propulsion** | **+8** | 0.156 | **HARMFUL** | **iter 300** |
| **gait_phase** | **+15** | 0.092 | **HARMFUL** | **iter 800** |
| **stride_length** | **+5** | 0.000 | **HARMFUL** | **iter 800** |
| **feet_air_time** | **+20** | -0.028 | **VERY HARMFUL** | **iter 1000** |

Boot 해로운 총 weight: **56** vs Boot 도움 총 weight: **~57** → 50:50 충돌

---

## 2. V43-D 핵심 설계

### 철학: "서기 → 전진 → 걷기 → 정제" 순서

기존 V38.3의 gait_gate를 V43의 clean reward 구조에 통합.
15개 reward는 유지하되, **활성화 시점을 phase별로 분리**.

### 5-Phase Curriculum

```
Phase 1: Boot (iter 0~300)
  → 생존/안정 reward만 active (10개)
  → walking reward 전부 weight=0
  → contacts ramp -20→-100, velocity ramp
  → 목표: 서기 학습, ep_len 50+ 달성

Phase 2: Direction (iter 300~800)
  → forward_velocity_gated: 0 → 8 (전진 방향 먼저)
  → stance_propulsion: 0 → 8 (추진력)
  → 나머지 walking reward 아직 OFF
  → 목표: 전진 학습, 서기→걷기 전환

Phase 3: Walking (iter 800~2000)
  → gait_phase: 0 → 15 (보행 패턴)
  → stride_length: 0 → 5 (보폭)
  → 목표: trot 패턴 형성

Phase 4: Air Time (iter 1000~2500)
  → feet_air_time: 0 → 20 (가장 위험, 가장 마지막)
  → 목표: 발 들기 학습 (서고 걷는 상태에서)

Phase 5: Refinement (iter 1000~2500, 동시)
  → joint_default_pose: -0.3 → -2.0 (자세 교정)
  → gate_alpha: 0 → 1 (propulsion gating 활성화, iter 500~1500)
```

### 활성화 순서와 이유

| 순서 | Reward | Ramp 구간 | 이유 |
|:----:|--------|----------|------|
| 1st | forward_velocity | 300~800 | 전진 방향 → "서기만" 방지 |
| 1st | stance_propulsion | 300~800 | 추진력 = 전진과 함께 |
| 2nd | gait_phase | 800~2000 | 패턴은 걸은 후에 |
| 2nd | stride_length | 800~2000 | 보폭도 걸은 후에 |
| 3rd | feet_air_time | 1000~2500 | **가장 위험, 가장 마지막** |

**feet_air_time을 마지막으로 둔 이유:**
- Weight 20 = 전체 positive budget의 30%
- Boot에서 "발 들어라" = 넘어짐 직결
- Isaac Lab 기본 0.75, legged_gym 1.0 대비 20~27배
- 로봇이 충분히 서고 걷는 상태에서만 활성화해야 안전

**forward_velocity를 1순위로 둔 이유 (분석AI 피드백):**
- "서기만 하는 정책"으로 수렴 방지
- Boot 후 즉시 전진 신호 제공 → 서기→걷기 전환 유도

---

## 3. 코드 변경

### rewards.py — v42_boot_curriculum 확장

```python
# 새 파라미터:
walk_rewards = {
    "forward_velocity": {"target": 8.0, "start": 300, "end": 800},
    "stance_propulsion": {"target": 8.0, "start": 300, "end": 800},
    "gait_phase": {"target": 15.0, "start": 800, "end": 2000},
    "stride_length": {"target": 5.0, "start": 800, "end": 2000},
    "feet_air_time": {"target": 20.0, "start": 1000, "end": 2500},
}

# 각 walking reward의 weight를 iteration에 따라 0→target으로 ramp
for name, cfg in walk_rewards.items():
    alpha = clamp((iteration - cfg["start"]) / (cfg["end"] - cfg["start"]), 0, 1)
    current_weight = cfg["target"] * alpha
    env.reward_manager.set_term_cfg(name, weight=current_weight)
```

### env_cfg.py 변경

- TRAIN_VERSION = "V43-D"
- Walking reward 초기 weight는 target 값 유지 (curriculum이 iter 0에서 즉시 0으로 override)
- Curriculum params에 walking reward ramp 파라미터 추가

---

## 4. V38.3 gait_gate vs V43-D 비교

| 항목 | V38.3 gait_gate | V43-D |
|------|----------------|-------|
| Gate 기준 | ep_len < 200 | iteration 기반 |
| 적용 범위 | 전체 gait reward | 5개 walking reward 개별 |
| 활성화 순서 | 일괄 ON/OFF | **3단계 순차 활성화** |
| Ramp | 없음 (hard gate) | smooth ramp |
| Reward 구조 | 50개 | 15개 (clean) |

V43-D는 V38.3의 gait_gate 철학을 계승하면서, 더 정교한 순차 활성화를 적용.

---

## 5. 리스크

### 1. Boot는 되지만 walking 전환 실패
- **감지**: iter 800에서 ep_len > 50이지만 forward_velocity 정체
- **대비**: forward_velocity ramp를 더 일찍 시작 (200~)

### 2. feet_air_time weight 20이 여전히 과도
- **감지**: iter 2500에서 feet_air_time 활성화 후 ep_len 급락
- **대비**: target weight 20 → 10 또는 5로 하향 (V43-E)

### 3. Iteration 기반 vs ep_len 기반
- 현재: iteration 기반 (단순, 예측 가능)
- ep_len이 target까지 안 올라가도 시간이 되면 walking reward 활성화
- **대비**: ep_len safety check 추가 (V43-E)

### 4. "서기만 하는 정책" 수렴
- **감지**: iter 500에서 ep_len > 100이지만 velocity = 0
- **완화**: forward_velocity를 iter 300에서 1순위 복원 (분석AI 피드백)

---

## 6. 판정 기준

### iter 300: Boot 성공 여부
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 30 | < 15 (V43과 동일) |
| bad_orientation | < 80% | 100% |

### iter 800: Direction 학습
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 100 | < 50 |
| forward_velocity | 증가 추세 | 정체 |

### iter 2000: Walking 패턴
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 200 | < 100 |
| gait_phase | > 0 | ≤ 0 |
| stride_length | > 2.0 | 0 |

### iter 3000: 최종
| 지표 | 목표 |
|------|------|
| ep_len | > 230 |
| stride | > 6.0 |
| forward_velocity | > 1.0 |
| gait_phase | > 0 |

---

## 7. 설계 원칙

1. **"서기 → 전진 → 걷기 → 정제"** 자연스러운 순서
2. **15개 reward 유지** — clean 구조 + boot gating
3. **가장 위험한 reward(feet_air_time)를 가장 마지막에**
4. **기존 검증된 gait_gate 철학 계승**
5. **원인 분리 유지**: V43-B(gate), V43-C(pose)는 그대로, walking ramp만 추가

---

## 8. 참고

- V43: Connected Trot (boot 실패 → reward 충돌 발견)
- V43-B: gate_alpha ramp (propulsion gating ≠ 원인)
- V43-C: joint_default_pose 완화 (pose ≠ 원인)
- V38.3: gait_gate 작동 증거 (feet_air_time=0 at boot)
- 분석AI 피드백: feet_air_time 20 공격적, forward_velocity 먼저 복원
