# V54 Plan: Phase Clock 기반 구조 전환

> 작성: 2026-03-29
> 상태: **설계 중**

---

## 1. 왜 구조 전환이 필요한가

### V49~V53: reward 패치의 한계

| 버전 | 패치 | 결과 | 새 문제 |
|------|------|------|--------|
| V49 | baseline | 귀뚜라미 (front_lift 0.08) | - |
| V50 | boot 연장 + height 강화 | 높이 하락 반복 | walking(60) vs height(4) |
| V51 | soft height gate | 초반 성공, 장기 하락 | anti-crouch만 성공 |
| V52 | min_height + data-driven weight | leg_lift 평균 문제 발견 | perverse incentive |
| V53 | front_leg_lift 추가 | FL 독점, FR 안 들림 | 앞뒤 역전 |

**패턴**: 하나를 고치면 다른 곳이 깨짐. reward로 보행 구조를 가르치는 것 자체가 한계.

### 근본 원인

77개 reward가 각각 "이렇게 해라"를 **제안**하지만, 로봇은 **가장 싼 방법으로 점수를 최대화**.
우리가 원하는 trot은 77개 reward의 합산 최적해가 아님.

### 성공 사례와의 차이

| | 우리 (V53) | legged_gym | Walk These Ways | AllGaits |
|---|---|---|---|---|
| reward 수 | 77+ | **15** | ~28 | **4** |
| 보행 구조 | reward로 유도 | feet_air_time | **phase clock** | **CPG** |
| 각 다리 타이밍 | 간접 유도 | 간접 유도 | **직접 지정** | **직접 지정** |

**핵심 차이**: 성공 사례는 보행 타이밍을 **architecture(phase clock/CPG)로 강제**,
reward는 **실행 품질만** 평가.

---

## 2. V39 교훈

V39에서 phase clock을 시도했으나 실패 (stride -39%):

```
V39 실패 원인:
  × phase clock을 77개 reward 위에 "조연"으로 추가
  × 기존 band/residency/gait reward와 phase clock이 신호 충돌
  × policy가 phase를 따르기보다 기존 local optimum 유지 + stride만 희생

V39에서 배울 것:
  ○ phase clock 철학 자체는 유효
  ○ gait timing을 architecture로 강제하는 접근은 맞음
  ○ 단, 기존 reward 더미 위에 얹으면 안 됨 — "주연"으로 써야 함
```

---

## 3. 설계 원칙

### 원칙 1: Phase clock이 주연

기존 reward의 조연이 아니라, **보행 구조의 중심 축**.
gait timing(언제 어떤 발을 들고 내리는지)은 phase clock이 결정.
reward는 "phase clock을 얼마나 잘 따르는가"만 평가.

### 원칙 2: 충돌하는 gait reward 제거

phase clock과 겹치는 기존 reward를 제거하여 신호 충돌 방지:

| 제거 대상 | 이유 | phase clock 대체 |
|----------|------|----------------|
| band rewards (contact/propulsion/usage) | stance/swing 타이밍과 직접 충돌 | phase contact reward |
| residency rewards | 접지 시간 지정 ↔ phase duty_factor | phase duty_factor |
| gait_phase, trot_gait | gait 패턴 간접 유도 ↔ phase clock 직접 지정 | phase clock observation |
| diagonal_coupling | 대각선 교대 유도 ↔ phase가 이미 trot 지정 | phase offset (FL/RR=0, FR/RL=π) |
| leg_lift, front_leg_lift | 다리 들기 유도 ↔ phase swing에서 clearance | phase-conditioned clearance |
| rear_alternation | 뒷다리 교대 ↔ phase가 교대 강제 | phase clock |

### 원칙 3: Forward reward 과도 금지

velocity tracking은 유지하되, **보행 품질 reward보다 낮은 비중**.
"빨리 가라"보다 "제대로 가라"가 우선.

### 원칙 4: 검증된 자산 유지

- boot_standing / boot_contact: 부팅 안정성 (V43-E에서 검증)
- alive_bonus: 기본 생존 보상 (V35.5에서 검증)
- min_height_termination: 크롤링 차단 (V52에서 검증)
- bad_orientation: 뒤집힘 차단

### 원칙 5: SpotMicro에 맞게 조정

Walk These Ways / AllGaits를 그대로 베끼지 않음.
SpotMicro는 ANYmal/Go1 대비:
- 토크 마진이 훨씬 작음 (effort 15 vs ANYmal 80)
- 기구학/질량 비율이 다름
- 이전 local optimum이 더 심함

**철학만 가져오고, 숫자는 실측 데이터로 검증.**

---

## 4. 예상 Reward 구조 (~15개)

### Phase Clock 중심 (주연)

| # | reward | weight (TBD) | 역할 |
|---|--------|-------------|------|
| 1 | **phase_contact_reward** | 높음 | stance에서 접지, swing에서 이탈 |
| 2 | **phase_foot_clearance** | 중간 | swing phase에서 발 높이 |

### Velocity Tracking

| # | reward | weight (TBD) | 역할 |
|---|--------|-------------|------|
| 3 | track_lin_vel_xy_exp | 중간 | 속도 추종 |
| 4 | track_ang_vel_z_exp | 중간 | 회전 추종 |

### 자세/안정성

| # | reward | weight (TBD) | 역할 |
|---|--------|-------------|------|
| 5 | alive_bonus | 10.0 | 생존 보상 |
| 6 | boot_standing | 20.0 | 부팅 높이+자세 |
| 7 | standing_height | TBD | 높이 유지 |
| 8 | flat_orientation_l2 | TBD | 수평 유지 |
| 9 | base_height_l2 | TBD | 높이 penalty |

### Penalty (품질)

| # | reward | weight (TBD) | 역할 |
|---|--------|-------------|------|
| 10 | action_rate_l2 | TBD | 행동 변화율 |
| 11 | dof_acc_l2 | TBD | 관절 가속도 |
| 12 | joint_vel_l2 | TBD | 관절 속도 |
| 13 | undesired_contacts | TBD | 비정상 접촉 |
| 14 | shoulder_neutral | TBD | shoulder splay |

### Termination

| # | termination | 역할 |
|---|------------|------|
| 15 | bad_orientation | 뒤집힘 |
| 16 | min_height | 크롤링 차단 |
| 17 | shoulder_splay (Soft CaT) | splay 차단 |

### Observation 추가

| observation | 차원 | 설명 |
|------------|------|------|
| phase_clock_obs | 8 | sin/cos × 4발 (V39 코드 재활용) |

---

## 5. 구현 계획: 점진적 전환

### Phase 1: Phase clock 추가 + 충돌 reward 제거

1. phase_clock_obs를 observation에 추가 (8차원)
2. phase_contact_reward를 핵심 reward로 등록 (높은 weight)
3. 충돌하는 gait reward 제거:
   - band rewards (per_leg_contact_target_band 등)
   - residency rewards (contact_residency 등)
   - gait_phase, trot_gait, diagonal_coupling
   - leg_lift, front_leg_lift, rear_alternation, rear_swing
4. velocity tracking + penalty + 자세 reward 유지
5. boot_standing / alive_bonus / termination 유지

### Phase 2: 튜닝 + 검증

1. Phase 1 결과 분석
2. weight 조정 (실측 데이터 기반)
3. phase_foot_clearance 추가 (필요 시)
4. boot phase curriculum 조정

### Phase 3: 고도화 (필요 시)

1. duty_factor를 command로 파라미터화
2. frequency를 command로 파라미터화
3. Raibert heuristic 발 배치 (Walk These Ways 참고)

---

## 6. 리스크

### 1. stride 사망 (V42~V46 재발)

band/residency 제거 시 stride engine 상실 가능.

- 감지: iter 500에서 stride < 1.0
- 대응: phase_contact_reward weight 증가, velocity tracking 강화
- 최악: band reward 일부 복원

### 2. Phase clock 무시

policy가 phase clock을 무시하고 자유보행 (V39 패턴).

- 감지: phase_contact_reward 점수 < 0.3
- 대응: weight 대폭 증가, 다른 positive reward 축소
- 핵심: phase clock이 "주연"이 되도록 weight 비중 확보

### 3. 부팅 실패

reward 구조 변경으로 boot phase 불안정.

- 감지: iter 300에서 ep_len < 50
- 대응: boot_standing weight 증가, 기존 boot curriculum 유지

### 4. SpotMicro 특성 문제

토크 마진 부족으로 phase clock 추종 자체가 물리적으로 불가능.

- 감지: 관절이 phase target을 따라가지 못함 (tracking error 큼)
- 대응: frequency/duty_factor 조정, target clearance 낮춤

---

## 7. 체크포인트 기준

| iter | 확인 | 성공 | 실패 |
|------|------|------|------|
| 300 | ep_len > 100, phase_contact > 0.3 | 부팅 + phase 학습 시작 | boot 점검 |
| 800 | stride > 2.0, 4발 대칭 | 보행 시작 | weight 조정 |
| 1500 | stride > 4.0, front/rear 비율 > 0.5 | 대칭 보행 | 구조 재검토 |
| 3000 | stride > 5.0, front_lift > 0.10 | **V54 성공** | |

### 핵심 판정

**iter 1500에서 4발 대칭 보행이 나오는가?**
V49~V53에서 한 번도 달성하지 못한 목표.

---

## 8. 기존 코드 재활용

| 코드 | 위치 | 상태 |
|------|------|------|
| phase_clock_obs | rewards.py line 32 | V39에서 구현, 사용 가능 |
| phase_contact_reward | rewards.py line 60 | V39에서 구현, 사용 가능 |
| gait_phase_reward (V39) | rewards.py | 참고용 |
| boot_standing_reward | rewards.py | 유지 |
| boot_foot_contact | rewards.py | 유지 |

---

## 9. 파일 변경 예상

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | reward 77→~15개 재구성, observation에 phase_clock 추가 |
| `rewards.py` | phase_foot_clearance 신규, 불필요 함수는 유지(삭제 안 함) |
| `rsl_rl_ppo_cfg.py` | observation 차원 변경 (48+8=56) |
| `train.py` | 변경 없음 |

---

## 10. V49~V53 교훈 반영

| 교훈 | V54 적용 |
|------|---------|
| #29 추정 금지, 실측 먼저 | weight는 Phase 1 결과 데이터로 결정 |
| #30 평균 함수 → 다수파 지배 | phase_contact는 4발 개별 점수 합산, 평균 아님 |
| #25 penalty > alive_bonus 금지 | net reward 부호 검증 |
| #28 "잘 가라" > "앞으로 가라" | phase 추종이 velocity tracking보다 높은 weight |
| V39 | phase clock을 주연으로, 충돌 reward 제거 |
