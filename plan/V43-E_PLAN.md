# V43-E Plan: Boot Standing Rewards + Walking Gating

> 작성: 2026-03-25
> 상태: **훈련 중** (run: 2026-03-25_20-37-59)

---

## 1. V43-D 분석 — 방향은 맞지만 부족

### V43-D가 증명한 것

Walking reward boot gating은 올바른 방향:
- forward_velocity **7배** 개선 (V43: 0.015 → V43-D: 0.107)
- gait_phase **35%** 개선 (0.17 → 0.23)
- feet_air_time = 0 (gating 작동 확인)

### V43-D가 해결 못한 것

ep_len = **10.0** (V43의 8.3에서 20% 개선, 하지만 목표 30에 미달)

### 근본 원인: Boot Phase "Penalty 사막"

V43-D iter 100 net reward 분석:

```
Total positive:  +0.43 (alive_bonus 0.41 + track 0.02)
Total negative:  -1.36 (penalties)
Net total:       -0.61 ← NEGATIVE!
Ratio:            0.32 (penalty 3배 우세)
```

비교:
```
V38.3 (boot 성공): positive 13.7 / negative 16.8 → ratio 0.82
V43-D (boot 실패): positive  0.4 / negative  1.4 → ratio 0.32
                    Positive signal 32배 부족
```

**핵심 문제**: Walking reward를 끄면 충돌은 해결되지만, positive signal이 거의 0이 됨.
PPO는 positive reward가 없는 방향으로 행동을 발명하지 않음.
→ "하지 마"만 있고 "이렇게 해"가 없는 penalty 사막.

---

## 2. V41 철학의 적용

### V41의 핵심 통찰

> "초기 gait 형성 조건이 잘못되면, 후반에 아무리 교정해도 한계가 있다"

V41은 splay 문제를 위해 설계되었지만, 핵심 개념이 boot 문제에 직접 적용 가능:
- V41 Phase 1: 저속 직진 + **gait bootstrap** (feet_air_time, foot_clearance, contact-phase)
- V43-D: walking reward OFF는 했지만 **대체할 positive signal이 없었음**

### V43-E = V43-D (walking gating) + V41 (boot bootstrap)

V41의 "gait bootstrap" 개념을 15-reward clean 구조에 맞게 변환:
- 50개 reward 복원이 아님
- **2개의 boot 전용 positive reward 추가**

---

## 3. V43-E 설계

### Boot Standing Rewards (2개 추가)

#### boot_standing_reward (+15)

```python
def boot_standing_reward(env, asset_cfg, target_height=0.23, height_k=100.0):
    height_score = exp(-100 * (height - 0.23)^2)
    orientation_score = exp(-7 * gravity_xy^2)
    return height_score * orientation_score
```

| 상태 | height | height_score | orient_score | 곱 | weighted |
|------|--------|:-----------:|:----------:|:---:|:-------:|
| 서있음 | 0.23 | 1.00 | ~0.95 | 0.95 | +14.3 |
| 반쯤 | 0.14 | 0.44 | ~0.50 | 0.22 | +3.3 |
| 넘어짐 | 0.05 | 0.04 | ~0.10 | 0.004 | +0.06 |

**alive_bonus와의 차이**: alive_bonus는 flat +10 (gradient 없음). boot_standing은 높이/자세에 비례 (gradient 있음).

**height_k=100 선택 이유** (SpotMicro 실측 기반):
```
k=20:  fallen(0.05m)에서 score=0.52 → 넘어져도 절반 보상 (gradient 약함)
k=100: fallen(0.05m)에서 score=0.04 → 넘어지면 거의 0 (gradient 강함)
k=200: fallen(0.05m)에서 score=0.002 → 너무 steep, intermediate 학습 어려움
```

#### boot_foot_contact (+5)

```python
def boot_foot_contact(env, sensor_cfg, contact_threshold=1.0):
    is_contact = _contact_state(sensor, body_ids, threshold)
    return is_contact.float().mean(dim=1)  # 4발 평균 접지율 [0, 1]
```

**Weight +5 (약하게) 이유**:
- 너무 강하면 "발을 안 드는 정책"으로 수렴 위험
- Boot phase(iter 0~600)에서만 활성, feet_air_time(iter 1000+)과 500 iter 간격
- net reward를 0에서 확실한 positive(+0.3)로 전환하는 보조 역할

### Boot Phase Net Reward 예상

```
기존 V43-D:     positive 0.43 / negative 1.36 → ratio 0.32, net -0.61
V43-E 추가:     boot_standing ~+0.6, boot_contact ~+0.3 → 추가 +0.9
V43-E 예상:     positive 1.33 / negative 1.36 → ratio 0.82, net -0.03 → ~0
```

ratio 0.82 = V38.3 수준. net reward가 ~0 (negative 탈출).
alive_bonus(+10 per step)까지 포함하면 실제 per-step reward는 positive.

---

## 4. Curriculum 타임라인

```
iter    | boot_standing | boot_contact | fwd_vel | propulsion | gait | stride | feet_air | gate_α | pose
--------|--------------|-------------|---------|-----------|------|--------|---------|-------|------
0       | 15.0         | 5.0         | 0       | 0         | 0    | 0      | 0       | 0     | -0.3
200     | 15.0→        | 5.0         | 0       | 0         | 0    | 0      | 0       | 0     | -0.3
300     | 10.0         | 5.0→        | 0→      | 0→        | 0    | 0      | 0       | 0     | -0.3
500     | 0            | 1.7         | 6.4     | 6.4       | 0    | 0      | 0       | 0→    | -0.3
800     | 0            | 0           | 8.0     | 8.0       | 0→   | 0→     | 0       | 0.3   | -0.3
1000    | 0            | 0           | 8.0     | 8.0       | 3.8  | 1.3    | 0→      | 0.5   | -0.3→
1500    | 0            | 0           | 8.0     | 8.0       | 8.8  | 2.9    | 6.7     | 1.0   | -0.94
2500    | 0            | 0           | 8.0     | 8.0       | 15.0 | 5.0    | 20.0    | 1.0   | -2.0
```

### 전환 설계

1. **boot_standing ramp-down (iter 200~500)**: forward_velocity 시작(300) 전에 줄이기 시작
   → "서기만 하는 정책" 방지. 서기 보상이 줄어들면서 전진 보상이 올라오는 자연스러운 교체.
2. **boot_contact ramp-down (iter 300~600)**: forward_velocity와 동시 시작, 약간 늦게 종료
   → 전진 시작 시에도 약간의 접지 보상 유지 (넘어짐 방지)
3. **교차 구간 (iter 300~500)**: boot↓ + walk↑ 동시 진행
   → alive_bonus(+10)가 기저에 있으므로 total positive 항상 양수 유지

---

## 5. 코드 변경

| 파일 | 변경 |
|------|------|
| `env_cfg.py` line 7 | TRAIN_VERSION = "V43-E" |
| `rewards.py` line 112-147 | boot_standing_reward + boot_foot_contact 신규 |
| `rewards.py` line 284 | v42_boot_curriculum에 boot_ramp_config 파라미터 추가 |
| `rewards.py` line 344-365 | boot reward ramp-down 로직 |
| `rewards.py` line 400-405 | 로그에 boot reward 정보 추가 |
| `env_cfg.py` line 1253-1256 | boot_ramp_config curriculum params |
| `env_cfg.py` line 1333-1351 | boot_standing, boot_contact RewTerm 정의 |

### 코드 리뷰 결과

| 검증 항목 | 결과 |
|-----------|------|
| boot_standing 수학 (k=100) | ✓ |
| boot_foot_contact 구현 | ✓ |
| term 이름 매칭 | ✓ |
| boot ramp-down 수학 | ✓ |
| walking ramp-up (V43-D) | ✓ |
| target_height 일치 (0.23) | ✓ |
| gate_alpha/push_alpha (V43-B) | ✓ |
| pose weight ramp (V43-C) | ✓ |
| 교차 구간 positive 유지 | ⚠️ 모니터링 |
| Critical 버그 | 없음 |

---

## 6. 판정 기준

### iter 300: Boot 성공 여부 (핵심 판정)

| 지표 | 성공 | 실패 (V43 동일) |
|------|------|:---:|
| ep_len | **> 30** | < 15 |
| bad_orientation | < 80% | 100% |
| boot_standing reward | > 0.5 | ~0 |

**이것이 V43-E의 핵심 판정.** V43/B/C/D 모두 iter 300에서 ep_len 8~10이었음.
ep_len > 30이면 boot standing reward가 효과가 있다는 확정적 증거.

### iter 800: Direction 학습

| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 100 | < 50 |
| forward_velocity | 증가 추세 | 정체 |
| boot_standing | ~0 (ramp down 완료) | 여전히 높음 |

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

---

## 7. 리스크

### 1. boot_standing이 "서기만 하는 정책"으로 수렴

- **원인**: boot_standing(+15)이 너무 강해서 움직이지 않는 게 최적
- **감지**: iter 500에서 ep_len > 100이지만 velocity = 0
- **완화**: ramp-down을 iter 200에서 시작 (forward_velocity 시작 전)
- **대비**: ramp-down을 더 일찍 (iter 100~300)

### 2. boot_foot_contact가 "발 안 드는 정책" 유발

- **감지**: iter 1000+ feet_air_time 활성 후에도 발을 안 듦
- **완화**: weight +5 (약함) + iter 600에서 완전 종료 + feet_air_time은 iter 1000 시작 (400 iter 간격)
- **대비**: boot_foot_contact weight 0으로 → boot_standing만으로 테스트

### 3. height_k=100이 부적절

- **감지**: boot_standing reward가 거의 binary (0 or 1)로 동작, intermediate 학습 없음
- **대비**: k=50으로 낮춤 (wider gradient but weaker separation)

### 4. 교차 구간 (iter 300~500)에서 total positive 감소

- **감지**: iter 300~500에서 ep_len 일시 하락
- **완화**: alive_bonus(+10)가 기저로 항상 positive 유지
- **대비**: boot_standing ramp-down을 더 늦게 (iter 300~600)

---

## 8. V43 시리즈 전체 경과

| 버전 | 변경 | 결과 | 교훈 |
|------|------|------|------|
| V43 | 15개 connected reward | boot 실패 (ep_len=8) | walking reward boot 충돌 |
| V43-B | gate_alpha ramp | boot 실패 (동일) | gating ≠ 원인 |
| V43-C | joint_default_pose -0.3 | boot 실패 (동일) | pose ≠ 원인 |
| V43-D | Walking reward gating (5-Phase) | ep_len=10, fwd_vel 7x↑ | 방향 맞지만 positive 부족 |
| **V43-E** | **+ boot_standing + boot_contact** | **훈련 중** | V41 bootstrap + V43-D gating |

### 근본 원인 발견 과정

1. V43: boot 실패 → "propulsion gating 문제?" (표면 분석)
2. V43-B: gating OFF해도 동일 → "pose 문제?" (표면 분석)
3. V43-C: pose 완화해도 동일 → "reward 구조 자체 문제" (깊은 분석)
4. V43-D: walking reward gating → 7x 개선 but 부족 → "positive signal 부족" (정량 분석)
5. V43-E: boot standing reward → V38.3의 ratio 0.82 복원 (데이터 기반 설계)

### 핵심 교훈

1. **reward를 끄는 것과 대체하는 것은 다르다** — V43-D는 해로운 reward를 껐지만 빈 자리를 채우지 않음
2. **net reward 부호가 학습 방향을 결정** — negative면 "빨리 죽는 게 이득"
3. **positive/negative ratio가 boot 성공의 예측 변수** — V38.3(0.82) vs V43-D(0.32)
4. **기존 검증 메커니즘 제거 시 WHY를 먼저 이해** — V42의 gait_gate 제거가 근본 원인

---

## 9. 참고

- V43-D: Walking reward gating (5-Phase curriculum)
- V41: Narrow-stance bootstrap (초기 형성 조건 재설계 철학)
- V38.3: gait_gate 작동 증거 + ratio 0.82 기준
- 분석AI 피드백: boot_standing 주력, boot_foot_contact 보조, ramp-down 필수
