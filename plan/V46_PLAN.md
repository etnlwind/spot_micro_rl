# V46 Plan: V38.3 기반 + 한 달의 교훈 통합

> 작성: 2026-03-26
> 상태: **설계 완료, 구현 대기**

---

## 1. 전략 전환

### 왜 V38.3 기반으로 돌아가는가

한 달간 V42~V44 (8+ 실험)에서 배운 것:

| 접근 | 결과 | 교훈 |
|------|------|------|
| 50개→15개 (V42~V43-E) | splay 0.40 (좋음), stride 0.39 (나쁨) | clean = splay 해결, 보행 부족 |
| 15개+coupling+pose완화 (V44) | stride 1.69 (개선), splay 0.53 (나쁨) | trade-off 미해결 |
| 15개에서 계속 추가 (V45 방향) | 미실행 | 결국 50개로 수렴할 것 |

**핵심 발견**: reward 수를 줄이는 것이 정답이 아니라, **어떤 reward가 있는가**가 핵심.

- V38.3의 50개 reward → stride 6.94, coupling 0.52 (좋은 보행)
- V43-E의 15개 reward → stride 0.39, coupling 0.0 (나쁜 보행)
- 차이: `leg_lift`, `rear_alternation`, `swing_stride` 등 **구체적 보행 신호**

### V46 전략

> **V38.3의 검증된 보행 품질 (stride 6.94, coupling 0.52)**
> **+ V42~V44에서 발견한 개선점 (boot gating, shoulder-leg 분리, boot standing)**
> **- V42에서 확인한 문제 reward (band/residency/validity 복잡 상호작용)**

---

## 2. V38.3 → V46 변경 사항

### KEEP: 28개 (V38.3에서 검증된 핵심)

```
[생존/안정] 6개
  alive_bonus(+10), base_height_l2(-15), flat_orientation_l2(-7),
  undesired_contacts(ramp), standing_height(+), height_bonus(+)

[전진] 4개
  forward_velocity(+8), forward_velocity_bootstrap(+),
  track_lin_vel_xy(+1), track_ang_vel_z(+0.5)

[보행 품질] 12개 — V38.3 stride 6.94의 핵심
  leg_lift(+)         — V38.3 최대 positive (7.15)
  stride_length(+5)   — 보폭
  rear_alternation(+) — 뒷발 교대 (stride의 핵심, 4.38)
  rear_joint_vel(+)   — 뒷발 움직임 (9.98)
  rear_fwd_stride(+)  — 뒷발 전진 보폭
  rear_swing(+)       — 뒷발 스윙
  swing_stride(+)     — 스윙 중 보폭
  foot_clearance(+)   — 발 높이
  swing_gate_vel(+)   — 스윙 속도
  trot_gait(+)        — trot 패턴
  diagonal_coupling(+10) — 대각 커플링 (V38.3에서 0.52 작동!)
  stance_propulsion(+8)  — 추진력

[정규화] 5개
  action_rate_l2(-0.5), dof_acc_l2(-), dof_pos_limits(-5),
  ang_vel_xy_l2(-), lin_vel_z_l2(-)
```

### REMOVE: ~25개 (V42에서 확인된 문제)

```
[band/residency/validity] ~15개 — "복잡한 상호작용 → splay 유지 인센티브"
  per_leg_contact_target_band, per_leg_propulsion_target_band,
  limb_usage_target_band, late_phase_band_exit(-15.57!),
  contact_residency, prop_residency, usage_residency,
  residency_ema_*(4개), per_leg_contact_floor,
  limb_usage_min_penalty, single_limb_validity_penalty

[좌우/앞뒤 차이 벌칙] ~7개
  front_left_right_*_penalty(2개), rear_left_right_*_penalty(2개),
  front_rear_support_balance, rear_pair_*(3개)

[중복/비활성] ~8개
  joint_vel_l2(dof_acc 중복), joint_deviation(pose 중복),
  joint_oscillation, foot_extension(-6.89, 큰 보폭 억제!),
  stance_width_penalty(-10.99, shoulder_neutral이 대체),
  dof_torques_l2, feet_below_knees, 비활성 8개
```

### MODIFY: 2개

```
shoulder_neutral: -6.0 → -3.0 (V44 교훈: shoulder만 타겟, leg 자유)
joint_default_pose: 제거 (shoulder_neutral이 대체)
```

### ADD: 3개 (V43-E에서 검증)

```
boot_standing_reward(+15↓): boot phase positive gradient
boot_foot_contact(+5↓): boot phase 접지 보상
boot gating curriculum: walking reward OFF during boot, 순차 활성화
```

### 최종: ~30개 reward

---

## 3. Boot Gating Curriculum (V43-E에서 검증)

V38.3에는 기존 `reward_weight_curriculum`(80+ params)의 gait_gate가 있었음.
V46에서는 V43-E의 경량 boot curriculum으로 대체:

```
Phase 1 (iter 0~300): Boot only
  - boot_standing(+15) + boot_contact(+5) active
  - walking rewards (leg_lift, rear_*, stride, coupling 등) = OFF
  - contacts ramp -20→-100, velocity ramp

Phase 2 (iter 300~800): Direction
  - forward_velocity + stance_propulsion ramp up
  - boot rewards ramp down

Phase 3 (iter 800~2000): Gait quality
  - leg_lift, rear_alternation, diagonal_coupling, stride 등 ramp up
  - trot_gait, swing_stride, foot_clearance 등 ramp up

Phase 4 (iter 1000~2500): Refinement
  - feet_air_time ramp up
```

### V38.3의 기존 gait_gate vs V46의 boot curriculum

| 항목 | V38.3 gait_gate | V46 boot curriculum |
|------|----------------|-------------------|
| Gate 기준 | ep_len < 200 | iteration 기반 + boot_standing |
| 적용 범위 | 전체 gait reward 일괄 | 그룹별 순차 활성화 |
| Boot positive | 없음 | boot_standing(+15) + boot_contact(+5) |
| Ramp | 없음 (hard gate) | smooth ramp |

V46은 V38.3의 gait_gate보다 **더 정교**: boot positive reward + 순차 활성화.

---

## 4. Shoulder-Leg 분리 (V44에서 확인)

### V38.3의 문제

```
shoulder_neutral(-6.0) + stance_width_penalty(-10.99) + joint_default_pose
= shoulder는 잡히지만, 이 벌칙들이 leg 움직임도 간접 억제
= shoulder_dev 0.46 (벌칙 -6에서도 splay)
```

### V46의 해결

```
shoulder_neutral(-3.0) — shoulder 4개 joint만 타겟
joint_default_pose — 제거 (leg 자유)
stance_width_penalty — 제거 (shoulder_neutral이 대체)
```

V44 교훈: joint_default_pose가 12개 관절을 동시 제어하면 stride↔splay trade-off 발생.
V46: shoulder_neutral이 4개 shoulder만 제어 → leg는 자유 → trade-off 해소.

shoulder_neutral weight -3.0 선택 이유:
```
V38.3: -6.0 → shoulder_dev 0.46 (50개 reward에서)
V43-E: joint_default_pose 없이 → shoulder_dev 0.40 (15개 clean reward에서)
V46: -3.0 (중간값) + 문제 reward 제거 → shoulder_dev ~0.40 기대
```

---

## 5. 제거 reward의 영향 분석

### 제거 시 가장 큰 변화

```
제거되는 큰 Positive:
  per_leg_contact_target_band:  +13.39
  per_leg_propulsion_target_band: +9.21
  limb_usage_target_band:       +8.04
  → 총 +30.64 positive 소실

제거되는 큰 Negative:
  late_phase_band_exit:         -15.57
  stance_width_penalty:         -10.99
  foot_extension:               -6.89
  joint_vel_l2:                 -7.32
  → 총 -40.77 negative 소실
```

**Net 효과**: negative(-40.77)가 positive(+30.64)보다 더 많이 제거됨.
→ 전체적으로 net reward 증가 (positive 방향).
→ boot 안정성 + 학습 속도 개선 기대.

### 보행 품질 핵심 reward는 유지

```
유지되는 보행 Positive (V38.3 검증):
  rear_joint_velocity:  +9.98
  leg_lift:             +7.15
  stride_length:        +6.94
  stance_propulsion:    +4.92
  rear_alternation:     +4.38
  forward_vel_bootstrap: +3.80
  four_limb_cooperation: +2.71
  diagonal_coupling:    +1.54
  → 이것들이 stride 6.94의 핵심
```

---

## 6. 예상 결과

| 지표 | V38.3 (50개) | V43-E (17개) | V44 (18개) | V46 (~30개) |
|------|:----------:|:----------:|:--------:|:----------:|
| ep_len | 206 | 248 | 250 | **> 230** |
| stride | **6.94** | 0.39 | 1.69 | **4.0~6.0** |
| coupling | **0.52** | 0.0 | 0.0 | **0.3~0.5** |
| shoulder | 0.46 | **0.40** | 0.53 | **~0.42** |
| forward_vel | 0.95 | 5.88 | 7.07 | **3.0~5.0** |

**V46 = V38.3의 보행 품질 + V43-E의 boot/splay 개선**

---

## 7. 판정 기준

### iter 300: Boot 성공
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 30 | < 15 |

### iter 1000: Boot 안정화
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 200 | < 100 |
| shoulder_dev | < 0.45 | > 0.50 |

### iter 3000: 보행 품질
| 지표 | 성공 | 부분 | 실패 |
|------|------|------|------|
| stride | > 4.0 | 2.0~4.0 | < 1.0 |
| coupling | > 0.3 | 0.1~0.3 | 0.0 |
| shoulder | < 0.43 | < 0.46 | > 0.50 |

### iter 5000: 최종
| 지표 | 목표 |
|------|------|
| ep_len | > 230 |
| stride | > 5.0 |
| coupling | > 0.4 |
| shoulder_dev | < 0.45 |

---

## 8. 리스크

### 1. 30개 reward가 다시 splay 유발
- band/residency/validity는 제거했지만, rear_* reward가 여전히 역할 분리 유발 가능
- 감지: shoulder_dev > 0.46
- 대비: rear_* weight 하향 또는 대칭 버전으로 교체

### 2. Boot 실패 (V43 재현)
- V38.3의 gait reward가 boot에서 충돌할 수 있음
- 완화: boot gating으로 walking reward OFF (V43-E 검증)
- 감지: iter 300 ep_len < 15

### 3. 제거한 reward가 사실 필요했음
- band/residency가 없으면 contact 안정성 하락 가능
- 감지: contact_ratio 불안정, ep_len 진동
- 대비: 핵심 band reward만 선별 복원

### 4. four_limb_cooperation 이 splay 유발
- V38.3에서 큰 positive (2.71), 하지만 V42에서 "복잡한 상호작용"으로 제거 후보였음
- 감지: cooperation↑ + shoulder↑ 동시 상승
- 대비: 제거하고 diagonal_coupling만 유지

---

## 9. 구현 가이드

### 접근 방식

V38.3의 기존 env_cfg.py 코드를 **대부분 유지**하되:
1. `_CLEAN_REWARDS` 플래그 대신 새로운 `_V46_HYBRID` 플래그
2. 제거 대상 reward만 `= None` 처리
3. `joint_default_pose = None`, `stance_width_penalty = None`
4. `shoulder_neutral.weight = -3.0`
5. boot curriculum 추가 (V43-E 코드 재사용)
6. boot_standing + boot_contact 추가

### 기존 V38.3 reward_weight_curriculum과의 관계

V38.3의 80+ param curriculum은 제거. V46의 경량 boot curriculum으로 대체.
V38.3의 gait_gate 기능은 V46의 walk_ramp_config로 대체.

---

## 10. V42~V46 전체 여정

| 버전 | 전략 | 결과 | 핵심 교훈 |
|------|------|------|----------|
| V38.3 | 50개 reward + CaT | stride 6.94, splay 0.46 | rich reward = 좋은 보행 |
| V42~V43 | 50개→15개 clean | boot 실패 | gait_gate 제거가 원인 |
| V43-D | + walking gating | ep_len 10→10 (20%) | positive 부족 |
| V43-E | + boot standing | **ep_len 248, splay 0.40** | boot 해결, 종종걸음 |
| V44 | + coupling + pose↓ | stride 1.69, splay 0.53 | shoulder-leg trade-off |
| V45 | shoulder 분리 (미구현) | 설계만 | - |
| **V46** | **V38.3 + 배운 것 통합** | 설계 완료 | **best of both worlds** |

---

## 11. 참고

- V38.3: 보행 품질 기준 (stride 6.94, coupling 0.52, 77개 reward)
- V43-E: boot 성공 + splay 0.40 (boot gating + boot standing)
- V44: shoulder-leg trade-off 확인 (pose↔stride 연동)
- V42 PLAN: 제거 대상 reward 분류 (band/residency/validity)
- V45 PLAN: shoulder-leg 분리 개념 (V46에 통합)
