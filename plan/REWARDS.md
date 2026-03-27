# REWARDS.md — V47 전체 Reward 분석

> 마지막 업데이트: 2026-03-27
> 기준: V47 iter 5897 (V38.3 순정 + boot_standing + boot_contact)

---

## 1. 요약

| 항목 | 값 |
|------|-----|
| 전체 reward 수 | 125 (tags 기준) |
| 활성 positive | 69 (합계 +106.04) |
| 활성 negative | 30 (합계 -80.70) |
| 비활성 (0) | 26 |
| Net | **+25.34** |
| Ratio (pos/\|neg\|) | **1.31** |

---

## 2. Positive Reward 상위 20 (보행 동력)

| 순위 | Reward | 값 | 카테고리 | 역할 |
|:----:|--------|:---:|:--------:|------|
| 1 | per_leg_contact_target_band | **+12.52** | Band | 각 다리별 접지 패턴이 목표 범위 내일 때 보상 |
| 2 | rear_joint_velocity | **+9.34** | Gait | 뒷발 관절 움직임 → stride의 핵심 동력 |
| 3 | per_leg_propulsion_target_band | **+8.86** | Band | 각 다리별 추진력이 목표 범위 내일 때 보상 |
| 4 | alive_bonus | **+7.89** | 생존 | 매 step 생존 보상 (boot 필수) |
| 5 | limb_usage_target_band | **+7.51** | Band | 다리 사용률이 목표 범위 내일 때 보상 |
| 6 | leg_lift | **+6.66** | Gait | 발 들기 높이 → 보폭의 전제조건 |
| 7 | stride_length | **+6.21** | Gait | 보폭 직접 보상 |
| 8 | stance_propulsion | **+4.80** | Gait | 접지 중 전진 추진력 |
| 9 | rear_alternation | **+4.01** | Gait | 뒷발 교대 → trot 패턴 핵심 |
| 10 | forward_velocity_bootstrap | **+3.48** | 전진 | 초기 전진 부트스트랩 |
| 11 | boot_contact | **+3.15** | Boot | 4발 접지율 (V47 추가) |
| 12 | contact_residency | **+2.89** | Residency | 접촉 지속성 보상 |
| 13 | four_limb_cooperation | **+2.55** | Gait | 4발 협동 보상 |
| 14 | boot_standing | **+1.66** | Boot | 높이+자세 gradient (V47 추가) |
| 15 | diagonal_coupling | **+1.40** | Gait | 대각 커플링 (FL↔RR, FR↔RL) |
| 16 | rear_forward_stride | **+1.28** | Gait | 뒷발 전진 보폭 |
| 17 | swing_stride | **+1.23** | Gait | 스윙 중 보폭 |
| 18 | rear_swing | **+1.05** | Gait | 뒷발 스윙 |
| 19 | prop_residency | **+0.81** | Residency | 추진 지속성 |
| 20 | forward_velocity | **+0.87** | 전진 | 전진 속도 보상 |

### 핵심 발견

- **Band reward 3개 (1,3,5위)** = +28.89 → 전체 positive의 **27%**. stride의 핵심 동력.
- V42~V46에서 이것들을 제거했을 때 stride가 6.79→0.39로 급락한 이유.
- **Gait reward 8개** (2,6,7,8,9,13,15,16,17,18위) = +37.79 → 전체 positive의 **36%**.
- **Boot reward 2개** (11,14위) = +4.81 → V47에서 추가, boot 가속 효과.

---

## 3. Negative Reward 상위 15 (제약/억제)

| 순위 | Reward | 값 | 카테고리 | 역할 |
|:----:|--------|:---:|:--------:|------|
| 1 | late_phase_band_exit | **-12.57** | Band | band 이탈 벌칙 (가장 큰 negative) |
| 2 | stance_width_penalty | **-10.99** | 자세 | 다리 벌림 벌칙 (splay 억제) |
| 3 | joint_vel_l2 | **-7.09** | 정규화 | 과도한 관절 속도 억제 |
| 4 | feet_air_time | **-6.36** | Gait | 발이 충분히 오래 공중에 있지 않으면 벌칙 |
| 5 | shoulder_neutral | **-5.65** | 자세 | 어깨 벌어짐 벌칙 (splay 핵심 제어) |
| 6 | foot_extension | **-5.10** | 자세 | 발 과도 뻗기 벌칙 |
| 7 | action_rate_l2 | **-4.90** | 정규화 | 부드러운 동작 강제 |
| 8 | dof_pos_limits | **-3.87** | 정규화 | 관절 한계 보호 |
| 9 | dof_acc_l2 | **-3.55** | 정규화 | 관절 가속도 억제 |
| 10 | rear_pair_contact_diff | **-3.02** | 대칭 | 뒷발 좌우 접촉 차이 벌칙 |
| 11 | joint_oscillation | **-2.00** | 정규화 | 관절 진동 억제 |
| 12 | joint_deviation | **-1.93** | 자세 | 기본 자세 편차 벌칙 |
| 13 | front_rear_support_balance | **-1.88** | 대칭 | 앞뒤 지지 균형 벌칙 |
| 14 | ang_vel_xy_l2 | **-1.76** | 정규화 | 회전 안정 |
| 15 | rear_L/R_prop_diff | **-1.51** | 대칭 | 뒷발 좌우 추진 차이 벌칙 |

### 핵심 발견

- **late_phase_band_exit (-12.57)** = 가장 큰 벌칙. band에서 이탈하면 큰 penalty.
- **stance_width_penalty (-10.99)** + **shoulder_neutral (-5.65)** = -16.64 → splay 제어의 두 축.
- **정규화 4개** (3,7,8,9위) = -19.41 → 전체 negative의 **24%**. 부드러운 동작 강제.

---

## 4. 카테고리별 Reward Budget

| 카테고리 | Positive | Negative | Net | 비중 |
|---------|:--------:|:--------:|:---:|:----:|
| **Gait (보행 품질)** | +37.79 | -6.36 | **+31.43** | 가장 큰 동력 |
| **Band (목표 범위)** | +28.89 | -12.57 | **+16.32** | stride 핵심 |
| **자세 (splay)** | — | -23.68 | **-23.68** | splay 억제 |
| **정규화** | — | -19.41 | **-19.41** | 부드러운 동작 |
| **생존/전진** | +12.24 | — | **+12.24** | boot + 전진 |
| **대칭** | — | -6.41 | **-6.41** | 좌우/앞뒤 균형 |
| **Residency** | +4.51 | — | **+4.51** | 접촉 지속성 |
| **Boot (V47 추가)** | +4.81 | — | **+4.81** | boot 가속 |
| **Monitoring (raw)** | +4.87 | -0.85 | +4.02 | 관찰용 |

---

## 5. 비활성 Reward (26개, 값 = 0)

```
contact_count, feet_on_ground, front_alternation, front_both_ground,
front_joint_frozen, front_joint_velocity, front_swing, gait_cycle_period,
leg_pose_symmetry, min_swing_ratio, rear_both_ground, rear_joint_frozen,
rear_pair_residency_gap, residency_ema_contact_fl/fr/rl/rr,
residency_ema_prop_rl/rr, same_side_penalty, stationary_penalty
```

이들은 이전 버전에서 실험 후 weight=0으로 비활성화된 reward. 코드에 남아있지만 학습에 영향 없음.

---

## 6. V47 vs V38.3 Reward 비교

| Reward | V38.3 (iter 6527) | V47 (iter 5897) | 변화 |
|--------|:-----------------:|:---------------:|:----:|
| per_leg_contact_target_band | 12.60 | 12.52 | ~동일 |
| rear_joint_velocity | 9.98 | 9.34 | -6% |
| alive_bonus | 8.28 | 7.89 | -5% |
| leg_lift | 7.15 | 6.66 | -7% |
| stride_length | 6.79 | 6.21 | -9% |
| stance_propulsion | 4.92 | 4.80 | -2% |
| diagonal_coupling | 1.40 | 1.40 | 동일 |
| shoulder_neutral | -5.94 | -5.65 | +5% (약간 완화) |
| **boot_standing** | 없음 | **+1.66** | **V47 추가** |
| **boot_contact** | 없음 | **+3.15** | **V47 추가** |

대부분 V38.3과 매우 유사. boot reward 2개가 유일한 차이.

---

## 7. Stride 동력 분석

V42~V46에서 stride가 죽었을 때(0.39~1.45) 없었던 reward 중 V47에서 복원된 것:

| Reward | V47 값 | V46-B에서 | stride 기여 |
|--------|:------:|:---------:|:-----------:|
| per_leg_contact_target_band | +12.52 | 없음 (제거) | **1위 — 접지 패턴 유도** |
| per_leg_propulsion_target_band | +8.86 | 없음 (제거) | **3위 — 추진 패턴 유도** |
| limb_usage_target_band | +7.51 | 없음 (제거) | **5위 — 사용률 유도** |
| forward_velocity_bootstrap | +3.48 | 없음 (제거) | **10위 — 초기 전진** |
| four_limb_cooperation | +2.55 | 없음 (제거) | **13위 — 4발 협동** |
| contact_residency | +2.89 | 없음 (제거) | **12위 — 접촉 지속** |
| **합계** | **+37.81** | **0** | **전체 positive의 36%** |

이 +37.81이 V38.3/V47의 stride 6+ 동력. V42에서 "복잡한 상호작용"으로 제거한 것이 stride를 죽인 직접 원인.

---

## 8. Splay 제어 메커니즘

V47의 shoulder_dev = 0.43 (V38.3의 0.45보다 개선)을 만드는 reward들:

| Reward | 값 | 메커니즘 |
|--------|:---:|---------|
| shoulder_neutral | -5.65 | 어깨 4개 관절 직접 벌칙 |
| stance_width_penalty | -10.99 | 다리 벌림 폭 벌칙 |
| foot_extension | -5.10 | 발 과도 뻗기 벌칙 |
| joint_deviation | -1.93 | 기본 자세 편차 벌칙 |
| Soft CaT (DoneTerm) | — | shoulder_dev > threshold면 확률적 에피소드 종료 |

CaT가 iter 3000 이후 shoulder를 0.53→0.43으로 눌러내림 (V38.3에서 검증된 메커니즘).

---

## 9. Boot 가속 메커니즘 (V47 추가)

| Reward | Weight | 역할 | Ramp |
|--------|:------:|------|------|
| boot_standing | +15 → 0 | 높이+자세 gradient | gait_gate 해제 시 ramp down |
| boot_contact | +5 → 0 | 4발 접지율 | gait_gate 해제 시 ramp down |

V38.3 boot: iter 500에서 ep_len 243
V47 boot: **iter 300에서 ep_len 193** (2배 빠름)

boot_standing은 alive_bonus(flat +10, gradient 없음)와 달리 **높이에 비례한 gradient** 제공 → "어떻게 서는가"를 가르침.

---

## 10. 교훈: "어떤 reward가 있는가"가 핵심

### 15개 clean (V43-E): stride 0.39

```
Positive: alive(10) + gait_phase(12) + fwd_vel(6) + prop(7) + stride(0.4) = ~36
→ 충분한 positive, 하지만 "어떻게 걸을지"를 가르치는 구체적 signal 없음
→ 로봇이 가장 쉬운 방법(종종걸음) 선택
```

### 25개 선별 (V46-A): stride 1.45

```
+ leg_lift, rear_alternation 등 8개 추가 = ~69
→ 방향은 맞지만, band/residency (+37.81) 없이는 stride 2.0 미달
→ pose penalty가 큰 보폭 차단 (이중 문제)
```

### 77개 순정 + boot (V47): stride 6.29

```
V38.3 전체 + boot_standing/contact = ~111
→ band/residency가 접지/추진/사용 패턴을 구체적으로 유도
→ 이 "구체적 유도"가 stride 6+의 핵심
→ reward 수가 아니라, 접지·추진·사용 패턴을 "목표 범위"로 가르치는 reward의 존재가 핵심
```
