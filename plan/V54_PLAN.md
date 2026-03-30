# V54 Plan: Phase Clock 기반 구조 전환

> 작성: 2026-03-29
> 상태: **V54.2 훈련 중 — boot-gated phase + bridge + gait_gate 120**

---

## 실험 일지

### 출발점

`V49~V53`의 흐름을 거치며 남은 결론은 하나였다.

```text
reward를 계속 패치하면
한 문제를 고칠 때마다 다른 exploit가 나온다
```

즉 `V54`의 출발점은 `reward patch`가 아니라
`보행 구조 자체를 architecture로 가져가자`였다.

### 처음 가설

```text
1. gait timing을 reward가 아니라 phase clock이 주도하면
   exploit가 줄어들 것이다
2. 기존 reward는 phase를 보조하는 정도로만 남기면 된다
```

### 실제로 한 일

`V54`는 이전 계열과 달리 구조 전환 버전이었다.

```text
- phase clock 관측 추가
- phase contact / clearance 축 도입
- 기존 gait reward 다수를 제거하거나 약화
- handoff / bridge / gait_gate를 섞은 전환 구조 설계
```

### 결과와 한계

실제 런에서는 phase 수식 자체보다
`phase를 받아낼 baseline locomotion이 없는 상태에서 handoff가 강제된 것`이 더 큰 문제로 드러났다.

즉 `V54`가 남긴 핵심 교훈은:

```text
phase 구조 자체가 틀렸다기보다
baseline이 없는 상태에서 phase를 주연으로 올린 것이 너무 빨랐다
```

### 이후로 이어진 이유

이 결론이 바로 `V55`의 출발점이 된다.

```text
V54
- phase-centric handoff 실험

V55
- baseline recovery first
- phase probe second
```

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

## 4. Phase Clock 수학 명세

### Phase Variable

```
phi_i(t) = 2π × f × t + offset_i

f = 2.0 Hz (1 cycle = 0.5s, V39 기본값)
```

### 다리별 Phase Offset (Trot)

```
FL (Front Left):  offset = 0
FR (Front Right): offset = π
RL (Rear Left):   offset = π
RR (Rear Right):  offset = 0

→ FL+RR 동위상, FR+RL 동위상 (대각선 쌍)
```

### Stance/Swing 판정

```
duty_factor = 0.55 (stance 55%, swing 45%)
  → SpotMicro의 낮은 토크 마진 고려, 접지 시간을 약간 길게

stance: phi_norm in [0, 2π × 0.55) = [0, 3.46)
swing:  phi_norm in [3.46, 6.28)

phi_norm = phi_i(t) mod 2π
```

### phase_contact_reward 합산 방식

```
교훈 #30: mean-only 금지 (다수파가 소수파 사용을 penalty화)

phase_contact는 4발 개별 점수를 SUM:
  reward = sum(match_i for i in [FL,FR,RL,RR]) / 4
  → 단, 각 leg의 match는 binary(0 or 1)이므로
    mean과 sum은 비례관계. 문제는 "variable-magnitude mean"임.

V54 원칙: raw score가 다리별로 크게 다른 reward에서는
  mean 금지, sum 또는 min 사용.
  phase_contact는 binary match이므로 mean OK,
  하지만 clearance 등 magnitude가 다른 reward는 sum.
```

### Standing Command 처리

```
|vel_cmd| < 0.1 m/s → all-stance (4발 접지)
  → phase_contact_reward에서 expected_contact = 1 for all legs
  → 서있을 때 발을 들면 penalty
```

### Velocity-Frequency 관계 (Phase 3 고도화용, 초기에는 고정)

```
초기: f = 2.0 Hz 고정
고도화: f = f_base + k × |vel_cmd| (속도 비례 주파수)
```

---

## 5. Reward 구조 — 최종 Inventory

### Weight 설계 원칙

```
1. Phase cluster(보행 구조) > Tracking cluster(속도 추종)
   → phase 총합 ≥ tracking 총합 × 4

2. alive_bonus(10)를 anchor로 상대 스케일링

3. legged_gym 비율 참조 + V52 실측 기반 조정
   - V52 실측: movement penalty 14.36/step이 앞다리 사용 차단
   → penalty를 대폭 축소 (-0.5~-1.0 수준)
```

### Phase Clock 중심 (주연) — 총합 25

| # | reward | weight | 역할 |
|---|--------|--------|------|
| 1 | **phase_contact_reward** | **20.0** | stance→접지, swing→이탈. 최대 positive |
| 2 | **phase_foot_clearance** | **5.0** | swing에서 발 높이 유도 (k=1000, 삼각파 target) |

### Velocity Tracking — 총합 5

| # | reward | weight | 역할 |
|---|--------|--------|------|
| 3 | track_lin_vel_xy_exp | **2.0** | 속도 추종 |
| 4 | track_ang_vel_z_exp | **3.0** | 회전 추종 (앞다리 사용 유도) |

**Phase(25) : Tracking(5) = 5:1** → phase 확실히 우선.

### 자세/부팅

| # | reward | weight | 비고 |
|---|--------|--------|------|
| 5 | alive_bonus | **10.0** | anchor |
| 6 | boot_standing | **20.0** | floor=10, ramp-down 1500, height_k=500 |
| 7 | standing_height | **15.0** | sigma=0.03, target=0.23 |
| 8 | flat_orientation_l2 | **-8.0** | V52 pitch 문제 반영 |
| 9 | base_height_l2 | **-15.0** | target=0.23 |

### Penalty (움직임 품질)

| # | reward | weight | 근거 |
|---|--------|--------|------|
| 10 | action_rate_l2 | **-0.5** | V52: -6.08 과도 → 대폭 축소 |
| 11 | dof_acc_l2 | **-0.001** | legged_gym -2.5e-7 참조, SpotMicro 스케일 |
| 12 | undesired_contacts | **-5.0** | boot ramp: -1→-5 |
| 13 | shoulder_neutral | **-4.0** | V38.3: -6 → 약간 완화 |
| 14 | stance_width_penalty | **-1.5** | V52.1 실측 기반 (원래 -3.0) |

### Termination

| # | termination | 파라미터 |
|---|------------|---------|
| 15 | bad_orientation | limit_angle=1.5 |
| 16 | min_height | 0.15m, boot-gated |
| 17 | shoulder_splay (Soft CaT) | threshold=0.3, margin=0.3, prob=0.0015 |

### Observation

| observation | 차원 |
|------------|------|
| 기존 (joint_pos, vel, gravity 등) | 48 |
| **phase_clock_obs (sin/cos × 4)** | **8** |
| **총** | **56** |

### 제거 목록 (V38.3 → V54에서 비활성화)

| 제거 reward | V52 실측 값 | 이유 |
|------------|-----------|------|
| per_leg_contact_target_band | +15.0 | phase_contact가 대체 |
| per_leg_propulsion_target_band | +10.1 | phase가 stance/swing 관리 |
| limb_usage_target_band | +9.0 | phase가 대체 |
| rear_joint_velocity | +11.8 | phase+tracking이 대체 |
| leg_lift / front_leg_lift | +9.9 | phase_clearance가 대체 |
| rear_alternation | +6.3 | phase offset이 교대 강제 |
| four_limb_cooperation | +5.5 | phase_contact가 4발 강제 |
| feet_air_time | -6.3 | phase_clearance가 대체 |
| stride_length | +5.1 | tracking이 대체 |
| forward_velocity / bootstrap | +7.0 | tracking이 대체 |
| diagonal_coupling | +1.5 | phase offset이 대체 |
| trot_gait / gait_cycle_period | +1.1 | phase clock이 대체 |
| band_exit / residency 계열 | - | phase와 충돌 |
| swing_stride / swing_gate | - | phase가 대체 |
| height_walking_gate | - | phase 구조에서 불필요 |
| front_rear_symmetry | - | phase가 대칭 강제 |
| 기타 diff/raw 로깅 전용 | - | reward 아님, 로깅 유지 |

### 유지 목록

| 유지 reward | weight | 이유 |
|------------|--------|------|
| **phase_contact_reward** | 20.0 | 신규 — gait 주연 |
| **phase_foot_clearance** | 5.0 | 신규 — swing 품질 |
| track_lin_vel_xy_exp | 2.0 | 속도 명령 추종 |
| track_ang_vel_z_exp | 3.0 | 회전 명령 추종 |
| alive_bonus | 10.0 | 생존 기본 |
| boot_standing | 20.0 | 부팅 가속 |
| boot_contact | 5.0 | 부팅 4발 접지 |
| standing_height | 15.0 | 높이 유지 |
| flat_orientation_l2 | -8.0 | 수평 유지 |
| base_height_l2 | -15.0 | 높이 penalty |
| action_rate_l2 | -0.5 | 행동 변화율 |
| dof_acc_l2 | -0.001 | 관절 가속도 |
| undesired_contacts | -5.0 | 비정상 접촉 |
| shoulder_neutral | -4.0 | splay 억제 |
| stance_width_penalty | -1.5 | 과도한 벌림 억제 |
| dof_pos_limits | (기존값) | 관절 한계 |
| lin_vel_z_l2 | (기존값) | 수직 속도 억제 |

### Per-step 예상 reward budget

```
Boot phase (iter 0~300):
  alive(10) + boot_standing(~15) + standing_height(~5) = ~30
  penalties: ~-5
  net: ~+25/step → 부팅 안정

Walking phase (iter 500+):
  alive(10) + phase_contact(~12) + phase_clearance(~3) + tracking(~3)
  + standing_height(~3) + boot_standing(floor ~5)
  = ~36
  penalties: ~-8
  net: ~+28/step → 안정

최악(phase 무시):
  alive(10) + standing(~3) - penalties(~-5) = ~+8
  phase_contact = 0 → 기회비용 ~12 상실
  → phase 따르는 게 확실히 이득
```

### Standing/Walking 경계 처리

```
입력: raw command (env.command_manager.get_command("base_velocity")[:, 0])
  → filtered가 아닌 raw. Isaac Lab command는 에피소드별 샘플링이므로
    step 내 oscillation은 없지만, 에피소드 경계에서 모드 전환 발생.

standing enter: |vel_cmd| < 0.08 → all-stance
walking enter:  |vel_cmd| > 0.12 → phase clock 활성
hysteresis 구간: 0.08~0.12 → 이전 모드 유지
→ 에피소드 경계에서 standing/walking 출렁임 방지
```

---

## 6. 구현 계획: 점진적 전환 (Exit Criteria 포함)

### Phase 1: Phase clock 중심 구조 (V54)

**구현:**
1. phase_clock_obs를 observation에 추가 (8차원 → 총 56차원)
2. phase_contact_reward(w=15) + phase_foot_clearance(w=5)를 핵심 reward로
3. 충돌하는 gait reward 제거 (비활성화):
   - band rewards (per_leg_contact_target_band, per_leg_propulsion_target_band, limb_usage_target_band)
   - residency rewards (contact_residency, usage_residency, prop_residency, residency_ema_*)
   - gait pattern (gait_phase, trot_gait, diagonal_coupling, diagonal_coupling_raw)
   - leg lift (leg_lift, front_leg_lift, rear_alternation, rear_swing, rear_forward_stride)
   - band exit (late_phase_band_exit)
   - four_limb_cooperation
4. velocity tracking(w=3,2) + penalty + 자세/boot reward 유지
5. from-scratch 훈련

**Exit Criteria (→ Phase 2):**
- ep_len > 180
- standing_height > 0.20
- phase_contact_reward > 5.0 (per-step weighted)
- 4발 contact_ratio 분산 < 0.1 (대칭 확인)

**Abort Criteria (중단):**
- iter 500에서 ep_len < 50 → boot 실패, Fallback C
- iter 500에서 phase_contact < 1.0 → phase 무시, Fallback A/B
- iter 300에서 standing_height < 0.15 → 크롤링 회귀

### Phase 2: 튜닝 + 검증

**구현:**
1. Phase 1 데이터 기반 weight 조정
2. phase_foot_clearance 튜닝 (target height, weight)
3. boot phase curriculum 조정 (필요 시)

**Exit Criteria (→ Phase 3):**
- stride > 4.0
- front/rear lift 비율 0.5~2.0 (대칭 범위)
- front_clearance > 0.01
- ep_len > 220

**Abort Criteria (중단):**
- iter 1500에서 stride < 2.0 → stride 사망, Fallback A/B
- phase_contact가 iter 500 이후 하락 추세 → phase 무시 진행
- front/rear lift 비율 > 5.0 → 비대칭 재발 (V53 패턴)

### Phase 3: 고도화

**구현:**
1. duty_factor를 command로 파라미터화
2. frequency를 command로 파라미터화
3. Raibert heuristic 발 배치 (Walk These Ways 참고)

**Exit Criteria:**
- shoulder_dev < 0.45
- stride > 5.0 안정
- 4발 대칭 보행 영상 확인

---

## 7. V39 코드 재활용 범위

### 재사용 가능 (utility만)

- `phase_clock_obs` 함수의 sin/cos 생성 로직 → 그대로 사용
- phase variable 계산 (`2π × f × t + offset`) → 그대로 사용
- **"V39 코드 재사용"이 아니라 "V39에서 utility만 가져옴"**

### 재검증 필수 (reward 로직 전체)

- `phase_contact_reward`: V39에서 match/mismatch +1/-1로 구현
  - **reward scale**: weight 20에서 ±1이면 ±20/step — 다른 reward와 균형 확인 필수
  - **duty_factor**: V39는 0.5, V54는 0.55 → 동작 차이 검증
  - **4발 합산 방식**: V39는 4발 mean → **교훈 #30(평균은 다수파 지배) 재발 위험**
  - **standing command**: V39에 없음 → 별도 구현 (hysteresis 포함)
- clipping / normalization → 첫 실험 후 실측 조정
- action interaction → phase가 action space에 미치는 간접 영향 확인

---

## 8. 리스크 + Fallback

### 리스크 1: stride 사망 (V42~V46 재발)

band/residency 제거 시 stride engine 상실 가능.

- 감지: iter 500에서 stride < 1.0
- **Fallback A**: track_lin_vel weight 3→6 (velocity 추종 강화)
- **Fallback B**: forward_velocity reward 복원 (w=5, phase와 비충돌)

### 리스크 2: Phase clock 무시

policy가 phase clock을 무시하고 자유보행.

- 감지: phase_contact_reward per-step < 3.0
- **Fallback A**: phase_contact weight 15→25
- **Fallback B**: 다른 positive reward 축소 (standing_height 10→5)

### 리스크 3: 부팅 실패

reward 구조 변경으로 boot phase 불안정.

- 감지: iter 300에서 ep_len < 50
- **Fallback A**: boot_standing weight 20→30
- **Fallback B**: undesired_contacts 초기값 -1→-0.5 (더 완화)
- **Fallback C**: phase_contact를 boot phase에서 비활성 (boot_standing에 집중)

### 리스크 4: SpotMicro 토크 한계

토크 마진 부족으로 phase clock 추종 자체가 물리적으로 불가능.

- 감지: phase_contact score < 0.3이면서 관절 토크 포화 빈번
- **Fallback A**: frequency 2.0→1.5 Hz (더 느린 보행)
- **Fallback B**: duty_factor 0.55→0.65 (stance 시간 증가, 부하 분산)
- **Fallback C**: phase_foot_clearance target height 낮춤

### Abort Window 기준

```
abort 판정은 단일 iter가 아닌 연속 구간으로:
  - "ep_len < 50이 100 iter 연속" → abort
  - "phase_contact < 1.0이 200 iter 연속" → abort
  - 단발성 하락은 무시 (학습 중 noise)
```

### 구현 후 검증 체크리스트

```
□ standing/walking mode 전환 빈도 로그 확인 (0.08~0.12 경계 출렁임)
  → "보류 가능"이지만 초반 관찰 항목으로 우선순위 높음
  → 초반 run에서 mode flicker 여부 반드시 확인
□ phase_contact_reward 합산 방식이 mean-only가 아닌지 코드 리뷰
  → binary match의 mean은 OK (교훈#30 해당 없음)
  → 하지만 구현 후 실제 코드에서 aggregation 방식 재확인 필수
□ phase_foot_clearance에서 다리별 magnitude 차이 → sum/4 사용 확인
□ 훈련 시작 직후 active/disabled reward list 로그 출력
  → 하나라도 잘못 살아있으면 V39식 충돌 재발
```

### 모니터링 필수 항목 (iter 300~800)

```
phase_contact_reward   — phase 추종 여부 (핵심)
track_lin_vel_xy_exp   — velocity tracking raw (phase 5:1 비율 유지 확인)
track_ang_vel_z_exp    — angular tracking raw
4발 개별 contact_ratio — FL/FR/RL/RR 대칭 여부
standing_height        — 높이 유지
front/rear leg_lift    — 비대칭 재발 감시
```

### Fallback 우선순위 (실패 패턴별)

| 실패 패턴 | 증상 | 1순위 | 2순위 | 3순위 |
|----------|------|-------|-------|-------|
| 부팅 실패 | ep_len < 50 | boot_standing 30 | undesired -0.5 | phase boot OFF |
| stride 사망 | stride < 1.0 | track_lin 6 | forward_vel 복원 | band 일부 복원 |
| phase 무시 | phase_contact < 3 | phase weight 25 | standing 축소 | — |
| 토크 한계 | phase < 0.3 + 포화 | freq 1.5Hz | duty 0.65 | clearance 낮춤 |
| 비대칭 재발 | FR/RL ratio > 5 | phase weight 확인 | duty_factor 조정 | — |

---

## 9. 구현 검증에서 발견된 버그 (사전 수정)

| # | 버그 | 수정 |
|---|------|------|
| 1 | phase_foot_clearance k=100 → gradient 너무 약 (0mm에서 0.85 점수) | k=1000 (0mm→0.20, 40mm→1.0) |
| 2 | stance_propulsion이 제거 목록에서 누락 → phase stance와 충돌 | 제거 목록에 추가 |
| 3 | curriculum=None → boot_standing ramp-down 소실 | curriculum 유지 (boot ramp만 동작, 나머지는 try/except 안전) |

---

## 10. 파일 변경 (실제 구현)

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | `_PHASE_CLOCK=True` 플래그, phase_contact(w=20)+phase_clearance(w=5) 추가, 50+ gait reward None 비활성화, phase_clock observation 추가, tracking/penalty weight 재설정, curriculum은 유지(boot ramp) |
| `rewards.py` | phase_contact_reward 수정(duty=0.55, standing처리, 범위[0,1]), phase_foot_clearance 신규(k=1000, 삼각파, sum/4), 기존 함수 삭제 안 함 |
| `rsl_rl_ppo_cfg.py` | 변경 없음 (Isaac Lab이 observation 차원 자동 감지) |
| `train.py` | 변경 없음 |

---

## 11. V49~V53 교훈 반영

| 교훈 | V54 적용 |
|------|---------|
| #29 추정 금지, 실측 먼저 | weight는 Phase 1 결과 데이터로 결정 |
| #30 평균 함수 → 다수파 지배 | phase_contact는 4발 개별 점수 합산, 평균 아님 |
| #25 penalty > alive_bonus 금지 | net reward 부호 검증 |
| #28 "잘 가라" > "앞으로 가라" | phase 추종이 velocity tracking보다 높은 weight |
| V39 | phase clock을 주연으로, 충돌 reward 제거 |

---

## 12. 구현 이력 (V54 → V54.2)

### V54 (초기): phase-only, boot 미고려

```
phase_contact(20) + phase_clearance(5) 항상 활성
→ boot phase에서 phase가 boot_standing과 충돌 → ep_len=14 즉사
```

### V54 boot-gated: phase를 boot phase에서 OFF

```
boot: boot_standing만 → phase OFF
walking: phase ON
→ 여전히 ep_len=13 고착 — boot positive 부족 (제거된 +6.50/step)
```

### V54.1: bridge rewards 추가

```
stride_length(5) + forward_velocity_bootstrap(5) 추가
→ outcome-based, phase와 비충돌
→ 하지만 boot phase에서는 효과 부족 (이것들도 boot에서 미미)
→ ep_len=20, 느린 부팅
```

### V54.2: boot-only bridge + penalty 축소 + curriculum fix

3개 수정:

| 수정 | 원인 | 효과 |
|------|------|------|
| leg_lift(15) + rear_joint_vel(12) boot bridge | boot positive +6.50 부족 | boot net -10.76→-2.3 |
| joint_vel_l2 -0.5→-0.3 | boot 최대 단일 penalty(-10.45) | penalty 4.2 절감 |
| curriculum return None 제거 | all_alphas_done에서 gait_gate 체크 스킵 | gait_gate 해제 가능 |
| gait_gate_min_ep_len 200→120 | episode_length_buf.mean은 mid-episode 평균 | phase 활성화 threshold 현실화 |

Boot bridge ramp-down: gait_gate 해제 후 500 iter에 걸쳐 0으로 감소 (phase가 대체).

### V54.2 결과 (iter 465)

```
ep_len: 214 (부팅 성공)
stride: 2.87 (성장 중)
front/rear lift: 0.817/0.602 = 1.36 (대칭)
phase_contact: 0.00 (gait_gate 미해제 — threshold 120으로 수정 후 재시작)
```

### 핵심 교훈 (V54 추가)

| # | 교훈 | 출처 |
|---|------|------|
| 34 | phase reward를 boot phase에서 활성화하면 boot 실패 | V54 boot-gate 전 |
| 35 | boot phase에도 "다리를 움직여라" positive signal 필요 | V54.1 boot bridge |
| 36 | curriculum return None이 하위 로직(gait_gate, boot ramp)을 스킵 | V54.2 curriculum fix |
| 37 | episode_length_buf.mean은 mid-episode 평균, 완료 에피소드 평균이 아님 | V54.2 gait_gate 120 |

### V54.2 추가 결과: gait_gate 해제 후 붕괴

gait_gate 120: phase가 boot 중 조기 활성화 → ep_len 5.5 즉사.
gait_gate 200 + iter 500 fallback: boot 성공(ep_len 216) → iter 500 fallback → phase 활성화 → **ep_len 216→13 붕괴.**

```
iter 458: ep_len=216, phase=0.00 (boot OK)
iter 500: gait_gate released (iter_fallback)
iter 805: ep_len=13.3, phase=0.43 (붕괴)
```

**원인**: phase_contact(w=20)가 즉시 활성화 → boot에서 학습한 보행 타이밍과 충돌 (hard switch).
분석팀 지적: "phase 활성화 이후 붕괴는 사실. hard switch가 유력 원인. ramp-in 필요."

### V54.3: Soft Handoff (Phase Ramp-In + Bridge Ramp-Out)

**변경**: phase를 즉시 20이 아닌 **0→20으로 500 iter에 걸쳐 점진 증가.**
동시에 bridge(leg_lift, rear_vel)를 **15→0으로 점진 감소.** 교차 전환.

```
gait_gate 해제 시점 (iter ~500):
  phase_contact: 0    →  bridge leg_lift: 15
  phase_clearance: 0  →  bridge rear_vel: 12

+250 iter:
  phase_contact: 10   →  bridge leg_lift: 7.5
  phase_clearance: 2.5 →  bridge rear_vel: 6.0

+500 iter:
  phase_contact: 20   →  bridge leg_lift: 0
  phase_clearance: 5.0 →  bridge rear_vel: 0
```

구현: phase boot-gate 제거, env_cfg에서 초기 weight=0, curriculum에서 ramp-in.

**판정 기준**:
- phase 활성화 구간(iter 500~1000)에서 ep_len > 100 유지 (V54.2: 13)
- stride > 2.0 유지
- phase_contact가 점진 상승

| # | 교훈 | 출처 |
|---|------|------|
| 38 | phase hard switch는 boot 보행과 충돌 → ep_len 붕괴 | V54.2 iter 500→800 |
| 39 | gait_gate threshold를 낮추면 boot 중 phase 조기 활성화 → 즉사 | V54.2 gait_gate 120 |
| 40 | phase ramp-in + bridge ramp-out의 soft handoff가 구조 전환의 안전한 방법 | V54.3 |
