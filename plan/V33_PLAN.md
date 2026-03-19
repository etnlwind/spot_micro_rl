# V33 Plan — 근본적 보상 구조 재설계

**작성일**: 2026-03-19
**상태**: V33 ❌ 실패 → V33.1 훈련 중

---

## 배경 — 왜 근본적 전환인가

V1~V32.1까지 32번의 점진적 개선을 시도했지만, V32.1 영상 관찰에서 근본적 문제를 발견:

1. **거미 형상** — 어깨 부착점(7.2cm)이 몸체(11cm)보다 좁아서 다리를 벌려야 안정
2. **보수적 셔플링** — 보폭이 정상의 ~20%, 넘어짐 회피 학습
3. **보상 122개** — 상호작용 예측 불가, 충돌하는 보상 다수
4. **rear bias** — rear 전용 보상(20+30+15=65)이 전체를 지배, 앞발 체공 불가

점진적 접근(weight 조정, 보상 추가)은 한계에 도달. 구조 자체가 문제이므로 **대폭 재설계**가 필요.
(교훈 #12 "한 번에 하나만"은 기존 구조가 작동할 때의 규칙 — 구조 자체가 틀리면 적용 불가)

## URDF 구조 분석 (V32_ANALYSIS 참조)

| 항목 | 값 | 문제 |
|------|-----|------|
| 어깨 부착점 간격 (Y축) | ±0.036m (총 7.2cm) | 몸체 너비(11cm)의 66% — 너무 좁음 |
| 어깨 관절 범위 | ±31.4° | 좁은 부착점에서 이 범위 = 벌어짐 |
| 기본 어깨 각도 | -0.04 rad | 거의 중립 → 서있으려면 밖으로 벌려야 함 |
| 기본 다리 각도 | -0.71 rad (-40.7°) | 뒤로 구부린 자세 |
| 기본 발 각도 | +1.31 rad (75.1°) | 앞으로 뻗은 자세 |

→ 좁은 부착점에서 높이 0.24m를 유지하려면 다리를 벌릴 수밖에 없음 = 거미 형상이 물리적 필연

## 보상 구조 충돌 (V32.1 기준)

| 보상 | weight | 효과 | 문제 |
|------|--------|------|------|
| standing_height | +10 | 높이 유지 | 좁은 부착점에서 높이 = 벌림 강제 |
| base_height_l2 | -15 | 높이 편차 패널티 | 위와 동일 |
| stance_width_penalty | -2.5 | 넓은 자세 패널티 | 높이 유지와 **모순** |
| foot_extension | -10.0 | 발 과신장 패널티 | 보폭 제한 |
| rear 전용 보상 합계 | +65 | rear 활성화 | front 무시 → **rear bias** |

→ 로봇이 학습한 전략: "넘어지지 않으려면 다리를 벌리되 보폭은 줄이자" = **보수적 셔플링**

## 설계 철학

**legged_gym 스타일로 회귀** — ~28개 핵심 보상, 충돌 없는 역할 분담

### 3대 원칙
1. **자세 먼저** — shoulder_neutral + joint_deviation 대폭 강화로 벌어짐 차단
2. **4발 공통** — rear/front 전용 보상 전부 제거, feet_air_time이 4발 swing 유도
3. **단순화** — Layer B/C/residency 커리큘럼 제거, 직접 weight 설정

### 냉정한 자기 비판 후 보완한 점
초기 22개 설계에서 다음 문제를 발견하고 보완:
- **양/음 보상 불균형** (음이 3배) → standing_height 유지, forward_velocity 유지
- **joint_deviation -3.0 과다** → -1.0으로 완화 (보행 억제 방지)
- **shoulder_neutral -20.0 과다** → -15.0으로 완화 (첫 시도 보수적)
- **셔플링 방지 부재** → stride_length 활성화, 최소 속도 패널티 추가
- **주기 제어 부재** → gait_cycle_period 유지

---

## V33 최종 보상 목록 (28개)

### 과제 보상 (Task)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 1 | track_lin_vel_xy_exp | **+1.5** | 1.0 | ↑ | 주 과제 — 속도 추적 |
| 2 | track_ang_vel_z_exp | **+1.0** | 1.5 | ↓ | 회전 추적 |
| 3 | forward_velocity | **+5.0** | 8.0 | ↓ | 전진 인센티브 (제거 시 신호 부족) |

### 자세 제어 (Posture) — V33 핵심
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 4 | **shoulder_neutral** | **-15.0** | -4.0 | ×3.75 | 벌어짐 차단 핵심 (legged_gym dof_pos_dev) |
| 5 | **joint_deviation** | **-1.0** | -0.3 | ×3.3 | 기본 자세 유지 (보행 억제 않도록 보수적) |
| 6 | base_height_l2 | **-15.0** | -15.0 | target 0.24→**0.20m** | 높이 하향 → 벌림 감소 |
| 7 | standing_height | **+8.0** | 10.0 | ↓, target **0.20m** | 서있기 양의 인센티브 (제거 시 정지 학습) |
| 8 | flat_orientation_l2 | **-5.0** | -7.0 | ↓ | 수평 유지 (약간 완화) |

### 안전 (Safety)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 9 | undesired_contacts | **-100.0** | -100.0 | = | 몸체/어깨/다리 접촉 패널티 |
| 10 | feet_below_knees | **-150.0** | -150.0 | = | 안전 |
| 11 | dof_pos_limits | **-7.0** | -7.0 | = | 관절 한계 |

### 부드러움 (Smoothness)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 12 | action_rate_l2 | **-2.0** | -3.0 | ↓ | 액션 변화율 (완화 — 보폭 허용) |
| 13 | joint_vel_l2 | **-0.3** | -0.5 | ↓ | 관절 속도 (완화 — 움직임 허용) |
| 14 | dof_acc_l2 | **-5e-6** | -5e-6 | = | 가속도 |
| 15 | dof_torques_l2 | **-3e-5** | -3e-5 | = | 토크/에너지 |

### 안정성 (Stability)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 16 | lin_vel_z_l2 | **-2.0** | -2.0 | = | 수직 진동 억제 |
| 17 | ang_vel_xy_l2 | **-1.0** | -1.0 | = | 롤/피치 억제 |

### Gait 패턴 (4발 공통)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 18 | feet_air_time | **+20.0** | 20.0 | = (thr=0.1) | 4발 체공 유도 (rear 경쟁 없이 더 효과적) |
| 19 | trot_gait | **+40.0** | 40.0 | = | 대각선 gait 패턴 |
| 20 | same_side_penalty | **-30.0** | -30.0 | = | 비트로트 억제 |
| 21 | diagonal_coupling | **+25.0** | 25.0 | = | 대각선 커플링 |
| 22 | gait_cycle_period | **+8.0** | 15.0 | ↓ | 주기 0.3~0.5초 (trot_gait은 상태만 체크) |

### 보폭/추진 (Stride)
| # | 보상 | weight | V32.1 | 변경 | 역할 |
|---|------|--------|-------|------|------|
| 23 | foot_clearance | **+10.0** | 8.0 | ↑ | swing 중 발 높이 (Walk These Ways) |
| 24 | foot_extension | **-3.0** | -10.0 | ↓↓ | 과신장만 제한 (보폭 확대 허용) |
| 25 | stance_propulsion | **+5.0** | 8.0 | ↓ | 추진력 |
| 26 | stride_length | **+6.0** | 0 (curriculum) | 신규 활성 | 셔플링 방지 핵심 (target 0.10m) |
| 27 | stationary_penalty | **-3.0** | 0.0 | 신규 활성 | "안 움직이면 안전" 학습 방지 |

### 예비 (비활성화 확인)
| # | 보상 | weight | 이유 |
|---|------|--------|------|
| 28 | forward_velocity_bootstrap | 0 | 불필요 |

### 양/음 균형 점검

| 구분 | 합계 |
|------|------|
| 양의 보상 | +1.5+1.0+5.0+8.0+20.0+40.0+25.0+8.0+10.0+5.0+6.0 = **+129.5** |
| 음의 보상 | -15.0-1.0-15.0-5.0-100.0-150.0-7.0-2.0-0.3-0.000005-0.00003-2.0-1.0-30.0-3.0-3.0 = **-334.3** |
| 양/음 비율 | **0.39** (V32.1 초기 설계 0.30에서 개선) |

※ undesired_contacts(-100)과 feet_below_knees(-150)은 "사고 시에만" 발동하므로, 정상 보행 시 실효 음의 보상은 ~-84 수준 → 양/음 비율 ~1.5

---

## 제거 항목 (V32.1 → V33, ~94개 비활성화)

### Rear 전용 보상 (6개) — rear bias 근본 원인
| 보상 | V32.1 | V33 | 대체 |
|------|-------|-----|------|
| rear_swing | 15.0 | **0** | feet_air_time + foot_clearance |
| rear_joint_velocity | 20.0 | **0** | 교훈 #9 적용 |
| rear_joint_frozen | -60.0 | **0** | joint_deviation |
| rear_alternation | 30.0 | **0** | trot_gait |
| rear_both_ground | -80.0 | **0** | trot_gait + same_side_penalty |
| rear_forward_stride | 10.0 | **0** | stance_propulsion |

### Front 전용 보상 (6개) — 이미 V32에서 비활성화
front_swing, front_alternation, front_both_ground, min_swing_ratio, front_joint_velocity, front_joint_frozen — 모두 0 유지

### Layer B/C/Residency 커리큘럼 (16개)
limb_usage_min_penalty, per_leg_contact_floor, per_leg_propulsion_floor, single_limb_validity_penalty,
per_leg_contact_target_band, per_leg_propulsion_target_band, limb_usage_target_band, four_limb_cooperation,
contact_residency, prop_residency, usage_residency,
rear_pair_residency_symmetry, late_phase_band_exit, rear_pair_contact_diff, swing_gate_velocity — 모두 0

### 중복/충돌 보상
| 보상 | V32.1 | V33 | 이유 |
|------|-------|-----|------|
| height_bonus | 7.0 | **0** | standing_height + base_height_l2로 충분 |
| knee_height | 7.0 | **0** | joint_deviation이 대체 |
| shoulder_symmetry | -3.0 | **0** | shoulder_neutral이 대체 |
| stance_width_penalty | -2.5 | **0** | shoulder_neutral이 직접 차단 |
| swing_stride | 2.0 | **0** | stride_length가 대체 |
| joint_oscillation | -5.0 | **0** | action_rate_l2 + joint_vel_l2 |
| leg_lift | 15.0 | **0** | feet_air_time + foot_clearance |
| front_rear_support_balance | -8.0 | **0** | 4발 공통 구조에서 불필요 |
| load sharing 5개 | 0→curriculum | **0** | 커리큘럼 제거 |

### 커리큘럼 단순화
현재 커리큘럼의 ~50개 파라미터를 **전부 no-op**으로 변경.
모든 weight를 직접 설정, ramp 없음.
커리큘럼 함수는 코드에 남기되, 실질적으로 비활성화.

---

## 리스크

### 리스크 #1: Rear 보상 제거 시 rear 붕괴
- V32에서 rear 축소 → 즉시 붕괴 경험
- **차이점**: V33은 4발 공통 보상(feet_air_time+20, trot_gait+40, diagonal_coupling+25)이 rear도 커버. V32는 rear 축소와 동시에 다른 변경.
- **대비**: iter 200에서 ep_length > 30이면 붕괴 아님. < 20이면 중단

### 리스크 #2: shoulder_neutral -15.0이 너무 강해서 움직임 억제
- 어깨를 -0.04에 고정하면 걸을 수 없을 수 있음
- **대비**: L2이므로 ±5° 편차의 패널티는 -0.11 수준 (미미). ±15° 이상에서만 큰 패널티.
- iter 200에서 관절 속도가 0에 가까우면 -10.0으로 완화

### 리스크 #3: from-scratch 수준의 변경
- 122→28개는 사실상 새로운 환경
- **대비**: 교훈 #4에 따라 from-scratch 훈련 (resume 아님)

### 리스크 #4: joint_deviation -1.0이 보행 방해
- **대비**: L1 norm + weight -1.0이므로, 12관절 각 ±0.3rad 편차 시 총 패널티 -3.6
- feet_air_time(+20) + trot_gait(+40) 대비 충분히 작음
- iter 200에서 mean_reward < 0이면 -0.5로 완화

### 리스크 #5: "정지가 최선" 학습
- stationary_penalty(-3.0)와 forward_velocity(+5.0)로 대비했지만, 여전히 가능
- **대비**: iter 200에서 전진 속도 ~0이면 forward_velocity +8.0으로 복구

---

## 성공/실패 기준

### 성공
- mean_reward > 300 @iter 1000
- **어깨 각도가 ±10° 이내** (벌어짐 해소)
- 보폭 > V32.1의 2배 (영상으로 판단)
- F-R contact gap < 0.15

### 부분 성공 → V33.1
- 자세는 개선되었으나 보행 불안정 → 개별 weight 미세 조정

### 실패 → 재설계
- mean_reward < 50 @iter 500 (붕괴)
- 어깨 고정이 너무 강해서 완전 정지

---

## 체크 포인트

| iter | 확인 내용 |
|------|----------|
| 200 | 붕괴 여부 (ep_length > 30?), 관절 움직임 유무, 정지 학습 여부 |
| 500 | mean_reward 추세, shoulder 각도, feet_air_time, 전진 속도 |
| 1000 | 최종 판단 — 자세/보폭/gait 패턴, 영상 확인 |

---

## V33 실패 기록 (iter 200에서 중단)

### 실측 데이터
| iter | mean_reward | ep_length |
|------|------------|-----------|
| 0 | -78.2 | 21.8 |
| 50 | -46.8 | 14.0 |
| 100 | -36.9 | 10.8 |
| 200 | -30.9 | 10.4 |

### 실패 원인
1. **높이 목표 0.20m이 너무 낮음** — 기본 자세 높이가 0.192m이므로 거의 기본 자세. 좁은 부착점에서 어깨를 -0.04로 고정하면 안정성 부족.
2. **서있기 인센티브 부족** — standing_height +8.0 vs 움직임 패널티 합계 -3.6 (ang_vel+joint_vel+dof_acc+action_rate). 넘어지는 게 더 나은 상황.
3. **양/음 비율 1:3.15** — 양의 보상 +1.27, 음의 보상 -4.02. "아무것도 안 하는 게 최선" 학습.
4. **교훈 #13 (신규)**: 높이 목표와 서있기 보상은 반드시 함께 충분해야 함. 패널티 위주 구조에서는 양의 보상이 패널티의 50% 이상 필요.

---

## V33.1 조정 (V33 실패 기반)

### 변경 사항 (V33 대비 3개만 변경)
| 파라미터 | V33 | V33.1 | 이유 |
|---------|-----|-------|------|
| base_height_l2 target | 0.20m | **0.22m** | 기본 자세(0.192m)보다 충분히 높아야 안정 |
| standing_height weight | +8.0 | **+15.0** | 서있기 인센티브 대폭 강화 |
| standing_height target | 0.20m | **0.22m** | 위와 동일 |
| height_bonus weight | 0.0 | **+5.0** | 추가 서있기 인센티브 |
| dof_acc_l2 | -5e-6 | **-2.5e-6** | TOP3 패널티 → 완화 |
| joint_vel_l2 | -0.3 | **-0.15** | TOP2 패널티 → 완화 |

### V33.1 실측 데이터
| iter | mean_reward | ep_length |
|------|------------|-----------|
| 0 | -79.2 | 21.8 |
| 100 | -39.5 | 10.9 |
| 176 | -33.9 | 10.4 |

### V33.1 실패 원인
V33과 완전히 동일한 패턴. 서있기 보상 강화(+15, +5)와 패널티 완화는 효과 없음.
**핵심 원인은 rear 전용 보상 제거** — rear가 초기 학습에서 "부팅 신호"를 제공하는 역할이었음.

---

## V33.2 조정 (V33/V33.1 실패 기반)

### 핵심 발견
- V32.1(ep_len=90 @iter100) vs V33(ep_len=10) 유일한 차이 = rear 전용 보상
- 4발 공통 보상(feet_air_time, trot_gait)은 "이미 걷고 있을 때" 효과적이지만 "초기 부팅"에는 부족
- **교훈 #14**: rear 전용 보상은 역할 분리의 원인이면서 동시에 초기 부팅의 핵심

### 변경 사항 (V33.1 대비)
| 보상 | V33/V33.1 | V33.2 | V32.1 | 근거 |
|------|----------|-------|-------|------|
| rear_joint_velocity | 0 | **+10.0** | 20.0 | 절반 복구 (부팅 신호) |
| rear_alternation | 0 | **+15.0** | 30.0 | 절반 복구 |
| rear_both_ground | 0 | **-40.0** | -80.0 | 절반 복구 |
| rear_joint_frozen | 0 | **-30.0** | -60.0 | 절반 복구 |
| rear_swing | 0 | **0** | 15.0 | foot_clearance가 대체 |
| rear_forward_stride | 0 | **0** | 10.0 | stance_propulsion이 대체 |

### V33.2 유지 항목 (V33 anti-splay 핵심)
- shoulder_neutral: **-15.0** (유지)
- joint_deviation: **-1.0** (유지)
- 높이 목표: **0.22m** (V33.1에서 조정)
- Layer B/C 커리큘럼: **전부 비활성화** (유지)
- front 전용 보상: **전부 0** (유지)

### V33.2 활성 보상: ~32개

---

## 프로젝트 교훈 (V1~V33.1, V33.2 설계 시 참조)

1. output=0 reward는 weight를 올려도 0 — band 밖이면 gradient 소멸
2. 패널티만으로는 고착된 local optimum 탈출 불가 — 인센티브 구조 변경 필요
3. 비대칭 보호는 붕괴를 이동시킬 뿐 — 전체 다리에 동일 기준 적용
4. critic reset + 대규모 reward 변경 = 발산 — from-scratch가 안전
5. 물리적 비대칭이 있으면 reward로 극복 불가 — 초기 자세 대칭이 전제조건
6. 특정 행동의 부재는 패널티로 해결 불가 — 해당 행동에 대한 명시적 보상이 필요
7. step-level alternation은 역할 분리를 보상 — temporal alternation과 다름
8. contact-level 패널티는 대각 역할 분리를 유발 — joint-level 접근이 필요
9. **다리별 전용 보상(front_*, rear_*)은 역할 분리 유발** — 4발 공통 보상이 안전 ★ V31.2
10. **보상 50개+는 항목 간 상호작용 예측 불가** — 성공한 프레임워크는 15~20개 ★ 연구조사
11. Gait 패턴은 "발견"보다 "지시"가 안정적 — phase clock/CPG 구조적 강제 ★ 연구조사
12. 한 번에 하나만 변경 — 단, 구조 자체가 틀리면 대폭 재설계 필요 ★ V32→V33
13. **높이 목표와 서있기 보상은 충분해야 함** — 패널티 위주 구조에서 양의 보상 부족 시 "정지/넘어짐이 최선" 학습 ★ V33
14. **4발 공통 보상은 초기 부팅 신호를 제공하지 못함** — rear 전용 보상이 역할 분리의 원인이면서 동시에 초기 학습의 핵심 ★ V33/V33.1

---

## V33.3 조정 (V33.2 실패 기반)

### 배경
V33.2에서 rear 절반 복구 → 3발 exploit (RR 완전 고정, FL/FR/RL만 사용).
ep_length는 올랐으나 RR이 사실상 사망.

### 변경 사항
| 보상 | V33.2 | V33.3 | 이유 |
|------|-------|-------|------|
| rear_joint_frozen | -30 | **-60** | V32.1 수준 복원, 관절 동결 강력 억제 |
| rear_both_ground | -40 | **-60** | 동시 접지 강화 |
| limb_usage_min_penalty | 0 | **-10** | per-limb 최소 사용률 강제 |
| single_limb_validity_penalty | 0 | **-15** | 최악 다리 validity gradient |
| min_swing_ratio | 0 | **-25** | 4발 개별 swing 강제 |

### V33.3 결과
- mean_reward: **-13** @iter 585
- **실패**: per-limb 페널티가 3발 exploit은 차단했지만 학습 자체가 억제됨
- 교훈 #15: "서기도 못 하는 상태에서 4발 보행 + 전진"을 동시 요구하면 어떤 보상 구조도 실패

---

## V33.4 시도 → V34로 대체

### 아이디어
reward weight를 0으로 두고 커리큘럼으로 점진 활성화하여 서기→걷기 2-Phase 학습.

### 구현했으나 분석 결과 문제 발견
1. **관측-보상 불일치**: velocity command는 관측에 들어가지만 tracking reward=0이므로 policy가 command를 무시하도록 학습
2. **500 iter 순수 서기**: "안 움직이면 최적"으로 critic이 깊이 수렴, Phase 2 전환 시 critic shock
3. **Isaac Lab 설계 의도와 불부합**: `rel_standing_envs`를 사용해야 standing env에 command=0이 자동 할당됨

### 결론
V33.4 접근법(reward weight zeroing)을 폐기하고, Isaac Lab 내장 `rel_standing_envs` + command range 커리큘럼 기반의 **V34**로 전환.

---

## 프로젝트 교훈 (V33.3/V33.4 추가)

15. **서기도 못 하는 상태에서 보행+전진 동시 요구는 불가능** — 단계적 학습(서기→걷기) 필요 ★ V33.3
16. **reward weight=0으로 Phase 분리하면 관측-보상 불일치** — standing env에서는 command=0이어야 tracking reward가 서기 보상 역할 가능. Isaac Lab `rel_standing_envs` 사용 ★ V33.4→V34
