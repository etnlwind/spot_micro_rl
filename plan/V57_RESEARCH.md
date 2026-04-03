# V57 Research: 문헌 기반 Reward 재설계

> 작성: 2026-04-02
> 상태: 문헌 조사 완료, 설계 대기
> 목적: V55~V56에서 드러난 구조적 한계를 극복하기 위해, 4족 RL 문헌에서 검증된 reward 구조를 기반으로 재설계한다.

---

## 1. 왜 V57이 필요한가

### 1.1 V55~V56의 성과

V55~V56에서 확인된 것:

```text
✓ gait_gate release collapse 해결 (min_height 0.10 + soft ramp)
✓ phase clock이 contact timing을 만들 수 있음 (phase_contact 0.77)
✓ phase 2.0이 baseline과 공존 가능
✓ RL 바닥 고착 탈출 (0.01 → 0.34)
✓ pitch penalty가 앞다리 lift를 유도 (FL 0.04 → 0.14)
```

### 1.2 V55~V56의 한계

동시에 확인된 구조적 한계:

```text
✗ 앞다리 과부하 — 매 걸음 nose-down oscillation
✗ 몸체 비틀림 — 앞발 오른쪽, 뒷발 왼쪽 twist
✗ penalty 추가 → 새로운 exploit 반복
✗ 수치 개선이 보행 품질 개선을 보장하지 않음
✗ 35~40개 reward의 arms race
```

### 1.3 근본 원인

```text
V38.3의 77개 reward 위에 계속 패치
→ reward끼리 충돌/경쟁
→ weight가 -150까지 상승 (arms race)
→ penalty 추가할 때마다 로봇이 새 exploit 발견
→ "걷는 모양"은 나오지만 "자연스러운 보행"은 아님
```

이것은 reward 개수나 weight의 문제가 아니라, **reward 구조 자체의 문제**다.

---

## 2. 문헌 조사 결과

### 2.1 주요 프레임워크 비교

| 프레임워크 | 연도 | 로봇 | reward 수 | gait 방식 |
|:---|:---:|:---|:---:|:---|
| Google Minitaur | 2018 | Minitaur | **4** | 없음 (자연 발현) |
| ETH ANYmal | 2019 | ANYmal | **8~10** | curriculum + actuator net |
| Legged Gym | 2022 | 범용 | **8** | feet_air_time |
| Walk These Ways | 2023 | Unitree Go1 | **12~15** | **phase clock command** |
| DreamWaQ | 2023 | Unitree A1 | **10** | 표준 10개 |
| Barrier-Based | 2024 | HOUND 45kg | **소수** | barrier function |
| **우리 (SpotMicro)** | **2026** | **SpotMicro** | **35~40** | **77개 heuristic + phase 보조** |

### 2.2 Google Minitaur (2018) — 4개 reward로 gait 발현

[arXiv:1804.10332](https://arxiv.org/abs/1804.10332)

```text
reward 항목 (단 4개):
  1. forward_speed = delta_x / dt
  2. drift_penalty = -abs(delta_y)
  3. shake_penalty = -abs(delta_z)
  4. energy_penalty = -dot(torque, joint_vel)

결과:
  - 1.18 m/s 실기 전이
  - galloping/trotting 자연 발현
  - 에너지 23~35% 절감
```

핵심: gait를 reward로 "지시"하지 않아도, energy penalty + forward velocity만으로 **policy가 효율적 gait를 스스로 발견**한다.

### 2.3 Legged Gym (ETH RSL) — 8개 기본 reward

[github.com/leggedrobotics/legged_gym](https://github.com/leggedrobotics/legged_gym)

```text
활성 reward (weight != 0):
  tracking_lin_vel     +1.0
  tracking_ang_vel     +0.5
  lin_vel_z            -2.0
  ang_vel_xy           -0.05
  torques              -1e-5
  dof_acc              -2.5e-7
  feet_air_time        +1.0
  action_rate          -0.01
  collision            -1.0

특징:
  - only_positive_rewards = True (총 reward를 0에서 clip)
  - phase/CPG 없음 — feet_air_time만으로 gait 간접 유도
  - 총 8~9개 항목
```

### 2.4 Walk These Ways (CMU, 2023) — phase clock command

[arXiv:2212.03238](https://arxiv.org/abs/2212.03238)

```text
핵심 혁신:
  - gait phase clock을 observation/command에 내장
  - tracking_contacts_shaped: phase에 맞는 접촉 패턴을 단일 reward로 추적
  - raibert_heuristic: 물리 기반 foot placement 유도

reward 구조 (~12~15개):
  tracking_lin_vel           +1.0
  tracking_ang_vel           +0.5
  lin_vel_z                  -2.0
  ang_vel_xy                 -0.05
  orientation                -5.0
  torques                    -0.0001
  dof_acc                    -2.5e-7
  action_rate                -0.01
  feet_air_time              +1.0
  collision                  -1.0
  tracking_contacts_shaped   핵심 (phase clock 기반)
  raibert_heuristic          핵심 (foot placement)
```

핵심 교훈:

```text
- phase clock이 observation에 있으면, policy가 "지금 어느 발이 접지해야 하는지" 직접 인지
- tracking_contacts_shaped 1개가
  trot_gait + same_side_penalty + rear_alternation + rear_both_ground 등
  5개+를 대체
```

### 2.5 DreamWaQ (KAIST, 2023) — 표준 10개

[arXiv:2301.10602](https://arxiv.org/abs/2301.10602)

```text
reward 10개:
  lin_vel_tracking     -1.0
  ang_vel_xy           -0.05
  orientation          -0.2
  dof_acc              -2.5e-7
  joint_power          -2e-5
  body_height          -1.0
  foot_clearance       -0.01
  action_rate          -0.01
  smoothness           -0.01
  power_distribution   -1e-5  (var(tau * theta_dot) — 대칭 유도)

핵심:
  "기존 연구와 동일한 reward를 사용"
  → 표준 10개 항목으로 충분히 robust locomotion 달성
```

### 2.6 Barrier-Based Style Rewards (KAIST, 2024)

[arXiv:2409.15780](https://arxiv.org/abs/2409.15780)

```text
구조:
  task reward: velocity tracking 등 소수 핵심 항목
  style reward: relaxed logarithmic barrier function
    -log(margin - |x - target|)

장점:
  - margin 하나만 tuning하면 됨
  - shoulder_neutral(-6) + stance_width(-1.5) + shoulder_symmetry(-3) 3개를
    barrier 1개로 통합 가능

결과:
  4.67 m/s galloping, 58cm 장애물 극복
```

---

## 3. 우리 프로젝트와의 차이 분석

### 3.1 수치 비교

```text
                      우리 (SpotMicro)      표준 프레임워크
활성 reward:          35~40개              8~15개
weight 범위:          -150 ~ +50           -5.0 ~ +2.0
다리별 전용 reward:   10개+                없음 (4발 공통)
gait 구조:            reward로 "유도"       command로 "지시"
undesired_contacts:   -100                 -1.0
alive_bonus:          10.0                 없음 (only_positive_rewards)
```

### 3.2 왜 이것이 문제인가

**1) Reward 충돌과 gradient 희석**

35개 이상의 reward가 동시에 gradient를 제공하면, policy gradient의 방향이 혼란.
rear_joint_frozen(-60) vs rear_swing(+8) vs feet_air_time(+30)이 동일 행동에 상충 신호.

**2) Weight arms race**

표준에서 가장 큰 weight는 -5.0 수준인데, 우리는 -150, -100, +40 등 극단적 값.
reward를 추가할 때마다 기존 reward와 "경쟁"시키기 위해 weight를 올린 결과.
reward landscape이 non-smooth해져서 학습 불안정의 직접 원인.

**3) 다리별 전용 reward의 비효율**

rear_swing, rear_frozen, rear_alternation 등 뒷다리 전용 5개+.
표준에서는 feet_air_time 하나로 4발 공통 유도.
다리별 reward는 RL의 탐색 공간을 부적절하게 제한.

**4) Phase가 "보조"에 머무름**

우리: trot_gait(w=40) + same_side_penalty(w=-30)으로 패턴을 사후 보상/처벌.
Walk These Ways: phase clock을 observation에 넣어 policy가 직접 인지.
차이: reward로 "유도" vs 구조로 "지시".

---

## 4. V57 재설계 방향

### 4.1 핵심 원칙

```text
1. Reward는 15개 이하
2. Gait는 reward가 아니라 구조(phase clock command)로 제공
3. Weight는 -5.0 ~ +2.0 범위 내
4. 다리별 전용 reward 제거 (4발 공통)
5. Hard constraint는 CaT/Barrier로 처리
6. only_positive_rewards 도입 검토
```

### 4.2 제안 Reward 구조 (15개)

```text
Category                | Term                        | Weight    | 역할
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Velocity Tracking (2)   | tracking_lin_vel_xy_exp     | +1.0      | 전진 속도 추적
                        | tracking_ang_vel_z_exp      | +0.5      | 회전 속도 추적
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Stability (3)           | lin_vel_z_l2                | -2.0      | 수직 진동 억제
                        | ang_vel_xy_l2               | -0.5      | roll/pitch 억제
                        | flat_orientation_l2         | -1.0      | 수평 유지
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Energy/Smoothness (3)   | dof_torques_l2              | -1e-5     | 토크 최소화
                        | dof_acc_l2                  | -2.5e-7   | 관절 가속도
                        | action_rate_l2              | -0.01     | 액션 평활
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Body (2)                | base_height_l2              | -1.0      | 목표 높이 유지
                        | undesired_contacts          | -1.0      | 접촉 회피
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Gait (3)                | tracking_contacts_shaped    | +1.0      | phase clock 기반 접촉 추적
                        | feet_air_time               | +1.0      | 체공 시간 (4발 공통)
                        | foot_clearance              | -0.5      | swing 중 발 높이
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Posture (2)             | joint_deviation             | -0.3      | 기본 자세 편차
                        | shoulder_neutral            | -0.5      | 어깨 벌림 억제
────────────────────────┼─────────────────────────────┼───────────┼─────────────
Total: 15개             | Weight 범위: -2.0 ~ +1.0
```

### 4.3 삭제 대상 (현재 35~40개 → 15개)

```text
삭제 이유: phase clock command가 대체

  trot_gait, diagonal_coupling, gait_cycle_period
  same_side_penalty, rear_both_ground, front_both_ground
  rear_alternation, rear_swing, rear_forward_stride
  swing_stride, swing_gate_velocity
  min_swing_ratio, leg_pose_symmetry

삭제 이유: 4발 공통 reward로 통합

  rear_joint_velocity, rear_joint_frozen
  front_joint_velocity, front_joint_frozen
  front_swing, front_alternation
  front_leg_lift, leg_lift (per-leg)

삭제 이유: band/floor/residency 시스템 전체

  per_leg_contact_target_band, per_leg_propulsion_target_band
  limb_usage_target_band, late_phase_band_exit
  per_leg_contact_floor, per_leg_propulsion_floor
  contact_residency, usage_residency, prop_residency
  rear_pair_residency_symmetry, rear_pair_residency_gap
  residency_ema_* (6개)

삭제 이유: barrier/CaT로 대체

  stance_width_penalty → barrier function
  shoulder_symmetry → shoulder_neutral에 통합
  foot_extension → barrier function

삭제 이유: diff/validity 시스템 전체

  rear_pair_contact_diff
  front_left_right_propulsion_diff_penalty
  rear_left_right_propulsion_diff_penalty
  front_left_right_usage_diff_penalty
  rear_left_right_usage_diff_penalty
  limb_usage_min_penalty
  single_limb_validity_penalty
  front_rear_support_balance_penalty
  four_limb_cooperation
```

### 4.4 핵심 신규 요소: tracking_contacts_shaped

Walk These Ways의 핵심 reward를 SpotMicro에 적용:

```text
설계:
  - phase clock (sin, cos)이 observation에 포함 (이미 V55에서 구현됨)
  - 각 다리의 expected contact state를 phase에서 계산
  - 실제 contact와 expected의 일치도를 reward

구현 (의사코드):
  phase = 2π * frequency * t
  for each leg i:
    phase_i = phase + offset_i  (trot: 대각선 쌍 offset = π)
    expected_contact_i = 1 if (phase_i % 2π) < duty_factor * 2π else 0
    match_i = (actual_contact_i == expected_contact_i)
  reward = mean(match) 또는 mean_min(match)

효과:
  - trot_gait, diagonal_coupling, rear_alternation 등 5개+ reward를 1개로 대체
  - 앞다리도 swing phase에서 "들어야 정답"이 됨 → 앞다리 lift 자동 유도
  - 비틀림/비대칭이 구조적으로 불이익
```

### 4.5 단계별 실행 계획

```text
Phase 1: 기초 검증 (V57.A1)
  - 15개 reward + phase clock command
  - tracking_contacts_shaped 구현
  - only_positive_rewards 도입
  - 기대: 자연스러운 trot 발현, ep_len > 100

Phase 2: 품질 개선 (V57.A2~)
  - Phase 1에서 부족한 항목만 소폭 추가
  - energy efficiency 검증
  - foot placement regularity 확인

Phase 3: Constraint 추가 (V57.B)
  - CaT/Barrier로 splay, min_height 등 hard constraint
  - posture safety 보장

Phase 4: Sim-to-Real 준비
  - domain randomization 강화
  - action smoothness 최적화
  - 실물 로봇 테스트
```

---

## 5. V55/V56에서 가져갈 것

### 5.1 유지

```text
- phase clock observation (sin/cos 8-dim) — 이미 구현됨
- min_height termination threshold 0.10 — 검증됨
- conservative STAND forward + post-release ramp 구조
- gait_gate release 생존 메커니즘
- curriculum phase table 덮어쓰기 대응법
- runtime override + ownership 분리
```

### 5.2 폐기

```text
- 77개 reward 생태계 (V38.3~V47)
- band/floor/residency 시스템
- diff/validity 시스템
- 다리별 전용 reward
- weight -100 ~ +40 범위의 극단적 값
```

### 5.3 재설계

```text
- trot_gait → tracking_contacts_shaped (phase clock 기반)
- 10개+ posture/symmetry penalty → shoulder_neutral 1개 + barrier
- alive_bonus 10.0 → only_positive_rewards (또는 제거)
- boot_standing/boot_contact → 축소 또는 curriculum 흡수
```

---

## 6. SpotMicro 특화 고려사항

```text
- 서보 모터: 토크 부족 → energy penalty를 너무 크게 하면 움직임 자체 억제
- 가벼운 무게: 관성 작음 → feet_air_time threshold를 낮게 (0.15~0.25s, 표준 0.5s 대비)
- sim-to-real gap: 큼 → domain randomization + action smoothness에 비중
- 작은 스케일: contact force가 작음 → contact threshold 조정 필요
```

---

## 7. 참고 문헌

```text
[1] Sim-to-Real: Learning Agile Locomotion (Google, 2018)
    arXiv:1804.10332

[2] Learning Agile and Dynamic Motor Skills (ETH/Hwangbo, 2019)
    arXiv:1901.08652

[3] Legged Gym (ETH RSL, 2022)
    github.com/leggedrobotics/legged_gym

[4] Walk These Ways (CMU/MIT, 2023)
    arXiv:2212.03238
    github.com/Improbable-AI/walk-these-ways

[5] DreamWaQ (KAIST, 2023)
    arXiv:2301.10602

[6] Barrier-Based Style Rewards (KAIST, 2024)
    arXiv:2409.15780

[7] CaT: Constraints as Terminations (2023)
    arXiv:2308.12517

[8] ROGER: Gain Tuning Is Not What You Need (2025)
    arXiv:2510.10759

[9] Isaac Lab ANYmal-D rough_env_cfg
    github.com/isaac-sim/IsaacLab

[10] AllGaits: Periodic Reward Composition (2020)
     arXiv:2011.01387
```

---

## 8. 최종 추천

```text
V57의 1순위는
"V56.M1.1 패치"가 아니라
"문헌 기반 15개 reward + tracking_contacts_shaped로 처음부터 재설계"다.

V54에서 시도했던 clean phase-centric 방향이 근본적으로 맞았다.
그때 실패한 것은 구현 문제(boot failure, phase table 덮어쓰기)였지
방향의 문제가 아니었을 수 있다.

V55~V56에서 얻은 인프라(release ramp, min_height, ownership 분리)는
V57에서 그대로 활용하되,
reward 구조 자체는 문헌 표준으로 교체한다.
```
