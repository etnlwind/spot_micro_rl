# V55 Plan: Baseline Recovery First, Phase Probe Second

> 작성: 2026-03-30
> 상태: A5.1 release-shock soft ramp 버그 수정 완료, fresh start 재검증 대기
> 목적: `V54`에서 드러난 handoff collapse를 피하고, 검증된 baseline locomotion을 먼저 복구한 뒤, 분리된 실험군에서 phase 신호의 실제 기여를 검증한다.

---

## 1. 결론

`V55`는 `V54`의 하위 튜닝이 아니다.

- `V54`: clean phase-centric handoff 실험
- `V55`: baseline recovery + phase probe 실험

핵심 판단:

1. `V54` 실패의 본질은 `phase 수식`보다 `phase를 받아낼 locomotion 기반 부재`였다.
2. 따라서 지금 우선순위는 `clean V54 미세조정`이 아니라 `baseline 복구`다.
3. phase는 처음부터 주연 reward가 아니라 `probe`로 다뤄야 한다.

---

## 2. 목표

### 2.1 단기 목표

`V47/V53급 baseline locomotion`을 다시 확보한다.

### 2.2 중기 목표

분리된 Track B에서 phase가 baseline을 망치지 않는지, 그리고 추가 구조 이득을 주는지 검증한다.

### 2.3 장기 목표

phase의 실제 구조 기여가 확인되면, 그때만 handoff와 phase-centric 축소를 다시 설계한다.

---

## 3. V54 실패 해석

현재 `V54.4` 런에서 확인된 사실:

- `_crr_gate_paused=True`가 유지된 상태에서도 `iter 500 fallback`으로 handoff가 시작됨
- `mean_episode_length`가 `21.35 -> 11.65 -> 10.38 -> 11.06 -> 8.71 -> 4.94 -> 4.36`으로 하락
- `phase_contact`는 `step 600`에서도 사실상 0에 가까움
- `diagonal_coupling_raw = 0.0`

해석:

1. boot가 성공하지 못했다
2. 그런데 handoff가 강제 시작됐다
3. phase reward는 아직 locomotion 주연 역할을 못 했다

즉 `V54`의 문제는 `phase 집계 방식` 이전에 `기반 locomotion이 약한 상태에서 handoff가 시작된 것`이다.

---

## 4. 설계 원칙

### 원칙 1: baseline을 먼저 복구한다

`작동하는 시스템을 고치지 말 것`이라는 기존 교훈을 따른다.

### 원칙 2: Track A와 Track B를 분리한다

이번 플랜은 하나의 run family가 아니다.

```text
Track A: Baseline Recovery
- phase observation 없음
- phase reward 없음
- 목적: baseline locomotion 복구

Track B: Phase Probe
- phase observation 있음
- phase auxiliary reward 있음
- 목적: baseline 위에서 phase의 추가 기여 검증
```

### 원칙 3: handoff는 이번 단계에서 제거한다

이번 단계에서는:

- `iter 500 fallback` 사용 안 함
- bridge ramp-out / phase ramp-in 사용 안 함
- phase는 상수 auxiliary weight로만 켠다

### 원칙 4: abort는 절대값만으로 결정하지 않는다

반드시 함께 볼 것:

```text
1. 절대 기준 미달 여부
2. V54.4 동일 iter 대비 개선 여부
3. 최근 2~3 체크포인트의 회복 추세
```

예:

```text
iter 150에서 ep_len = 25
- 절대 기준 30 미달
- 하지만 V54.4보다 개선
- 추세도 상승

=> 즉시 abort가 아니라 보류 + 추가 관찰
```

---

## 5. Baseline 정의

이번 문서의 `baseline`은 막연히 "옛 reward를 많이 남긴 상태"가 아니다.

정확한 의미:

1. `V47`이 검증한 강한 boot/locomotion ecology를 유지한다
2. `V53`까지 확인된 front-leg / one-leg 문제는 관찰 대상으로 유지한다
3. `V54`의 handoff, phase-only inventory, legacy phase table 차단은 baseline의 기본축이 아니다

즉 `V55`는:

`V54를 약하게 돌리는 버전`

이 아니라,

`V47/V53 기반 위에 phase probe를 추가하는 새 실험군`

이다.

---

## 6. Reward 설계

### 6.1 Track A

Track A는 baseline recovery다.

- phase observation: OFF
- phase reward: OFF
- 목적: V47/V53 계열 baseline locomotion이 실제로 복구되는지 확인

### 6.2 Track B

Track B는 단일 실험이 아니라 3단 probe다.

- phase observation: ON
- phase reward: ON
- handoff: 없음
- phase_contact aggregation: `mean_min`

핵심 원칙:

```text
B1 = additive probe
- baseline locomotion을 거의 유지
- phase가 읽히는지만 확인

B2 = soft replacement
- 기존 heuristic timing 일부 감쇠
- phase가 구조 기여를 하는지 확인

B3 = hard phase test
- 기존 timing heuristic을 더 크게 줄임
- phase가 구조 주도권을 가질 수 있는지 확인
```

### 6.3 phase_contact 집계

`V54.4`의 `floor-only`는 초기 reward가 너무 sparse했다.

따라서 B1 단계는:

```text
score = 0.5 * mean(c_i) + 0.5 * min(c_i)
```

여기서 `c_i`는 per-leg compliance EMA.

이 선택의 의미:

- one-leg exploit 완전 차단이 목적이 아님
- 초기 phase probe에서 reward density를 확보하는 것이 우선
- exploit 억제 강도는 `floor`보다 약하지만 B1 단계에는 충분

### 6.4 Track B에서 줄일 reward

이 수치는 추측이 아니라 `plan/REWARDS.md`의 `V47 iter 5897` 실측을 기준으로 정한다.

V47 실측에서 직접 timing/gait 지정에 가까운 positive 기여:

- `rear_joint_velocity = +9.34`
- `leg_lift = +6.66`
- `stance_propulsion = +4.80`
- `rear_alternation = +4.01`
- `diagonal_coupling = +1.40`
- `rear_swing = +1.05`

이 군집을 그대로 두면 `phase_contact + phase_clearance` probe가 묻힌다.

현재 `A5` 실측 기준으로 `forward_velocity`, `trot_gait`, `diagonal_coupling_raw`,
`leg_lift`, `rear_joint_velocity`가 모두 baseline 동력으로 작동하고 있다.
따라서 `B1`에서 이것들을 처음부터 크게 깎으면 phase probe가 아니라 baseline 약화 실험이 된다.

```text
Reward               | Track A | B1  | B2  | B3
---------------------+---------+-----+-----+----
forward_velocity     | 16.0    | 16  | 16  | 16
fwd_vel_bootstrap    | 12.0    | 12  | 12  | 12
trot_gait            | 유지    | 5   | 2   | 0
diagonal_coupling    | 유지    | 5   | 2   | 0
gait_cycle_period    | 유지    | 0   | 0   | 0
feet_air_time        | 유지    | 20  | 15  | 10
leg_lift             | 유지    | 20  | 12  | 8
rear_alternation     | 유지    | 15  | 8   | 5
rear_joint_velocity  | 유지    | 12  | 8   | 4
stance_propulsion    | 유지    | 8   | 6   | 4
foot_clearance       | 유지    | 2   | 2   | 2
rear_swing           | 유지    | 6   | 4   | 3
phase_contact        | OFF     | 1.5 | 3.0 | 5.0
phase_clearance      | OFF     | 0.5 | 1.0 | 1.5
```

주의:

```text
위 표는 설정 weight 기준이다.
실제 reward contribution은 policy 분포에 따라 비선형적으로 바뀐다.
```

따라서 `B1 iter 100 audit`에서 반드시 다시 확인한다.

### 6.5 penalty

Penalty는 `V47/V52 값으로 기계적으로 복원`하지 않는다.

이유:

- 현재 세션 실측상 `dof_acc_l2=-0.001`은 boot를 과하게 눌렀다
- 하지만 `V47 ecology + -2e-5` 조합도 아직 미실측이다

따라서 원칙은:

```text
A1 초기값:
  V54.4 완화값을 임시 시작점으로 사용

A1 iter 100 audit:
  active reward / penalty 실측 후 최종 확정
```

초기값:

```text
action_rate_l2 = -0.30
joint_vel_l2   = -0.10
dof_acc_l2     = -2e-5
```

---

## 7. A5 / A5.1 최신 판정

### 7.1 A5 결과

`A5`는 STAND phase에서는 가장 좋은 baseline recovery를 보였다.

- `ep_len`이 `248`까지 상승
- `stride_length`가 `2.06`까지 열림
- `diagonal_coupling_raw`가 `0.52` 수준까지 상승

하지만 `iter 500`에서 gait gate release가 기록된 직후 붕괴했다.

확인된 사실:

- `_v47_boot_gate_released_iter = 500`
- `time_out -> min_height`로 termination 패턴 급변
- `shoulder_neutral`, `stance_width_penalty` 등 posture/splay 관련 항목이 release 이후 walking 값으로 강해짐

즉 현재 1차 문제는 `phase`가 아니라 `iter 500 release shock`다.

### 7.2 A5.1 첫 시도에서 확인된 것

`A5.1`의 목적은 `A5` baseline은 유지하고,
release 이후 `shoulder_neutral`, `stance_width_penalty` 두 항목만 `500 iter`에 걸쳐 soft ramp 하는 것이었다.

첫 시도에서 확인된 사실:

- `curriculum_500.pt`에는 여전히
  - `shoulder_neutral = -6.0`
  - `stance_width_penalty = -3.0`
  이 저장됨
- `iter 500` 이후 collapse도 재발

처음에는 이것을 "`soft ramp 가설 실패`"로 볼 수 있었지만,
코드 재검증 결과 그 해석은 틀렸다.

### 7.3 구조적 버그 원인

`reward_weight_curriculum()` 내부에서:

```text
1. gait_gate release 이후 walking weight 적용
2. _all_alphas_done 또는 "실제 변화 없음"이면 조기 return
3. 그 아래쪽의 V55 runtime override / soft ramp 코드에 도달하지 못함
```

즉 첫 `A5.1`은 가설을 시험한 run이 아니라,
`soft ramp가 지속 적용되지 못하는 구현 버그가 섞인 run`이었다.

### 7.4 수정 완료 사항

현재 코드에서는 다음을 수정했다.

- `_all_alphas_done` 조기 return 전에 V55 runtime override 실행
- `실제 변화 없음` 조기 return 전에 V55 runtime override 실행
- 따라서 `A5.1` soft ramp가 iter 500 이후에도 매 호출마다 계속 적용됨

이제야 `A5.1`이 실제로 검증 가능한 상태가 되었다.

### 7.5 다음 검증 규칙

`A5.1`은 반드시 fresh start로 다시 돌린다.

검증 포인트:

```text
iter 500 직후
- reward_manager weight 기준으로
  shoulder_neutral = pre 값 근처
  stance_width_penalty = pre 값 근처

iter 500 ~ 1000
- 두 항목이 목표 post 값으로 점진적으로 이동
- A5처럼 즉시 min_height 99% 붕괴가 재발하는지 여부 확인
```

주의:

```text
curriculum_500.pt만으로 runtime soft ramp 성공 여부를 단정하지 않는다.
가능하면 iter 499/500/501의 실제 term weight 로그를 직접 본다.
```

해석 주의:

```text
이 값들은 "V47 값을 복원한 표"가 아니다.
특히 dof_acc_l2는 V47 계열과 다른 임시 시작값이다.
```

따라서 구현 시:

- `action_rate_l2`, `joint_vel_l2`는 현재 시작점으로 사용
- `dof_acc_l2`는 `iter 100 audit` 후 조건부 조정 대상으로 본다

중요:

- 이 중 `leg_lift 15 -> 8`은 40%가 아니라 `53%`
- 수치 표현은 문서에서 정확히 유지한다

---

## 7. 실험 단계

### Experiment A1: Pure Baseline Recovery

설정:

```text
phase observation = OFF
phase reward      = OFF
handoff           = 없음
fallback          = 없음
penalty           = STAND phase table의 점진 ramp를 그대로 사용
forward drive     = V55 override로만 보강
```

V54 코드 처리 방침:

```text
1. _PHASE_CLOCK=False 만으로 끝내지 않는다
2. A1은 "V47 baseline inventory를 명시적으로 복원"하는 실험이어야 한다
3. _phase_remove, phase_table_enabled, phase ramp/bridge 잔재가 A1에 개입하지 않도록 확인한다
```

성공 기준:

```text
iter 300: ep_len > 80
iter 500: ep_len > 120
특정 발 contact_ratio 바닥 고착 없음
```

abort 판단:

```text
1. 절대 기준 미달
2. V54.4 동일 iter 대비 개선 없음
3. 최근 2~3 체크포인트에서 회복 추세 없음
```

A1 필수 audit:

```text
iter 0
- phase observation OFF 확인
- phase reward OFF 확인
- A1 observation dimension이 baseline과 동일한지 확인

iter 100
- active reward audit
- active penalty audit
- dof_acc_l2 raw magnitude 확인
- dof_acc_l2 weighted contribution 확인
- 교훈 #34: 설정값이 아니라 실제 활성 reward 기준 판단

iter 500
- A1 종료 가능 여부 최종 판정
```

iter 100에서 반드시 볼 것:

- 실제 active reward weight
- `dof_acc_l2`, `joint_vel_l2`, `action_rate_l2`가 STAND table 값으로 유지되는지
- `dof_acc_l2` raw magnitude
- `forward_velocity`, `forward_velocity_bootstrap`가 override 값으로 유지되는지
- `boot_standing`, `standing_height`, `feet_air_time`, `trot_gait`, `diagonal_coupling` 우세 항목
- 비의도 reward dominance 여부

`A5` 판단 로직:

```text
1. penalty 3개는 override하지 않는다
2. STAND phase table의 점진 ramp를 baseline 기준으로 사용한다
3. override는 phase table이 충분히 밀지 못하는 forward drive 2개에만 적용한다
4. iter 100에서 raw magnitude와 weighted contribution을 보고 penalty 조정 필요성을 재판정한다

판정:
- STAND table만으로도 붕괴하면 그때 penalty 재조정을 검토
- 기본값은 "penalty override 최소화"다
```

A1 -> B1 전환 조건:

```text
1. 최소 iter 500 도달
2. iter 300, 400, 500 구간에서 ep_len 하락 추세가 아님
3. min(contact_ratio_*)가 바닥 고착이 아님
4. iter 100 active reward audit 통과
5. iter 500 active reward audit에서 비의도 dominance 없음
```

A1 실패 시 fallback:

```text
1. V54 잔재 처리 상태 점검
   - _phase_remove
   - phase_table_enabled
   - phase ramp/bridge params

2. V47 기준 env_cfg / reward inventory 명시 복원

3. penalty만 audit 기반으로 재설정

4. A1 재시도
```

### Experiment B1: Baseline + Weak Phase Probe

중요:

```text
B1/B2/B3는 반드시 from-scratch다.
A5 checkpoint에서 resume하지 않는다.
```

이유:

- A1은 phase observation OFF
- B1은 phase observation ON
- observation dimension과 input distribution이 다르다

설정:

```text
base          = A1 성공 설정
phase_obs     = ON
phase_contact = 1.5
phase_clear   = 0.5
handoff       = 없음
fallback      = 없음
phase agg     = mean_min
timing reward = additive probe 수준
```

성공 기준:

```text
iter 400: ep_len > 80
iter 500: ep_len > 120 또는 A1 대비 20~25% 지연 이내
A1 대비 성능 급락 없음
phase_contact 0 고착 아님
diagonal_coupling_raw > 0.05
특정 발 contact_ratio 바닥 고착 없음
```

B1 필수 audit:

```text
iter 100
- 감쇠 reward의 실제 contribution이 예상 범위인지 확인
- phase cluster가 완전히 묻히지 않았는지 확인
- rear bias 또는 front 사용 악화가 생겼는지 확인
- feet_air_time과 phase_contact의 timing 충돌 여부 확인
- A5 대비 ep_len 급락이 없는지 확인
- trot_gait / diagonal_coupling이 유지되는지 확인
```

B1 추가 모니터링:

- `front_leg_lift_mean_raw`
- `rear_leg_lift_mean_raw`
- `front/rear leg_lift ratio`

판정:

```text
front/rear ratio가 A1 대비 나빠지면
rear-side timing reward 감쇠가 역효과일 수 있음
```

### 운영 계획

기본 원칙:

```text
A1 -> B1 -> B2는 순차 실행이 기본
```

이유:

- A1이 baseline 복구 여부를 먼저 증명해야 한다
- B1/B2는 A1 성공 이후에만 해석 가치가 있다
- Track 간 observation / reward 구조가 달라 순차가 더 안전하다

병렬 실행은 예외적으로만 허용:

```text
조건:
- GPU 자원이 충분함
- Track A와 Track B를 독립 run family로 관리 가능
- 비교 기준이 혼동되지 않음
```

### Experiment B2: Stronger Phase Probe

전제:

- B1 성공

설정:

```text
forward_velocity            = 16.0
forward_velocity_bootstrap  = 12.0
phase_contact               = 3.0
phase_clear                 = 1.0
trot_gait                   = 2.0
diagonal_coupling           = 2.0
feet_air_time               = 15.0
leg_lift                    = 12.0
rear_alternation            = 8.0
rear_joint_velocity         = 8.0
stance_propulsion           = 6.0
rear_swing                  = 4.0
```

성공 기준:

- A1/B1 대비 stride/coupling 개선
- ep_len 유지 또는 개선
- phase reward 상승

### Experiment B3: Delayed Handoff Reintroduction

전제:

- B2까지 성공

설정:

```text
forward_velocity            = 16.0
forward_velocity_bootstrap  = 12.0
phase_contact               = 5.0
phase_clear                 = 1.5
trot_gait                   = 0.0
diagonal_coupling           = 0.0
feet_air_time               = 10.0
leg_lift                    = 8.0
rear_alternation            = 5.0
rear_joint_velocity         = 4.0
stance_propulsion           = 4.0
rear_swing                  = 3.0
```

release 조건 예시:

```text
mean_episode_length > 150
and diagonal_coupling_raw > 0.08
and min(contact_ratio_*) > 0.03
for N updates
```

---

## 8. 모니터링 지표

필수:

- `Train/mean_episode_length`
- `Train/mean_reward`
- `Episode_Reward/phase_contact`
- `Episode_Reward/phase_clearance`
- `Episode_Reward/diagonal_coupling_raw`
- `Episode_Reward/contact_ratio_fl`
- `Episode_Reward/contact_ratio_fr`
- `Episode_Reward/contact_ratio_rl`
- `Episode_Reward/contact_ratio_rr`
- `front_leg_lift_mean_raw`
- `rear_leg_lift_mean_raw`
- `front/rear leg_lift ratio`

보조:

- `boot_standing`
- `standing_height`
- `track_lin_vel_xy_exp`
- `dof_acc_l2`
- `joint_vel_l2`
- `action_rate_l2`

---

## 9. 구현 전 체크리스트

구현 전에 아래 6가지를 반드시 확인한다.

1. `A1`에서 `_phase_remove`가 실질적으로 비활성화되는가
2. `A1`의 observation dimension이 baseline과 정확히 같은가
3. `A1 iter 100`에서 `dof_acc_l2` raw magnitude와 weighted contribution을 반드시 확인하는가
4. `B1/B2`는 반드시 from-scratch인가
5. `Track B` 감쇠 수치는 weight 기준이며, 실측 contribution은 `B1 iter 100`에서 다시 검증하는가
6. `A1` 실패 시 fallback은 `V47 원본 env/reward inventory 명시 복원 후 재시도`인가

---

## 10. 구현 상태

현재 코드 기준 구현 상태:

```text
기본 실행 버전
- TRAIN_VERSION = V55.A6

구현 완료
- Track A / Track B / B2 / B3 분기
- A-track: phase observation OFF
- A-track: phase reward OFF
- B-track: phase auxiliary ON
- V55 전용 forward override 유지
- A5: penalty는 legacy STAND table ramp 유지
- A6: A5 core + posture override + gait_gate release soft-ramp
- iter 0 / 100 / 500 V55 audit 로그

주의
- A5는 iter 500 이전까지 baseline recovery에 성공했지만
  gait_gate release 직후 min_height collapse가 발생했다
- 다음 단계는 A6 fresh start 기준 runtime validation이다
```

### 10.1 A5에서 실제로 막은 경로

`env_cfg` 값만 바꾸는 것으로는 충분하지 않았다.

실제 문제:

```text
legacy STAND phase table이 runtime에서 아래 항목을 다시 덮어썼다
- action_rate_l2
- joint_vel_l2
- dof_acc_l2
- forward_velocity
- forward_velocity_bootstrap
```

`A2/A4`는 penalty까지 override했지만, `A5`는 forward 2개만 `V55 runtime override`로 유지한다.
penalty 3개는 다시 STAND phase table이 관리하게 둔다.

### 10.2 A5에서 새로 드러난 붕괴 경로

`A5`는 STAND phase에서 잘 올라갔지만, `iter 500`에서 gait gate release가 기록된 직후 붕괴했다.

확인된 직접 shock source:

```text
curriculum_400.pt -> curriculum_500.pt

stance_width_penalty   0.0  -> -3.0
shoulder_neutral      -1.0  -> -6.0
```

붕괴 직후 termination:

```text
min_height       ~99%
time_out          0%
bad_orientation   ~1%
```

따라서 `A6`의 1차 목적은 posture reward를 새로 많이 추가하는 것이 아니라,
`gait_gate release shock`를 직접 만든 두 항목만 `500 iter`에 걸쳐 soft-ramp하는 것이다.

### 10.3 A6 구현 내용

`A6`는 `A5 + posture correction + release shock 완화`다.

```text
유지
- action_rate_l2 / joint_vel_l2 / dof_acc_l2: STAND table 관리
- forward_velocity / forward_velocity_bootstrap: 16 / 12 runtime override 유지
- trot_gait / diagonal_coupling / stride 동력 유지

즉시 보강
- standing_height: 40 -> 48 runtime override
- height_bonus: 25 -> 30 runtime override
- base_height_l2: -20.0 -> -23.0 env_cfg 직접 조정
- front_rear_support_balance_penalty: -8.0 -> -9.6 env_cfg 직접 조정

release 후 500 iter soft-ramp
- shoulder_neutral: -1.0 -> -6.0
- stance_width_penalty: 0.0 -> -3.0
```

원칙:

```text
첫 실험은 shock source 2개만 soft-ramp한다.
undesired_contacts 등 다른 항목은 같이 건드리지 않는다.
그래야 iter 500 collapse의 직접 원인을 분리해서 검증할 수 있다.
```

### 10.4 A6 fresh start 검증 규칙

`코드값`이 아니라 `curriculum_0.pt`의 `_reward_weights`로 판정한다.

초기 fresh start에서 반드시 확인할 값:

```text
action_rate_l2             = -0.3
joint_vel_l2               = -0.05
dof_acc_l2                 = -5e-7
forward_velocity           = 16.0
forward_velocity_bootstrap = 12.0
standing_height            = 48.0
height_bonus               = 30.0
shoulder_neutral           = -1.0
stance_width_penalty       = 0.0
phase_contact              = 없음
phase_clearance            = 없음
```

판정 원칙:

```text
env_cfg에 적혀 있어도 충분하지 않다.
curriculum_0.pt에서 실제 적용값이 맞아야 구현 완료로 본다.
```

추가 확인:

```text
base_height_l2                        = -23.0
front_rear_support_balance_penalty    = -9.6
```

이 두 항목은 phase table 관리 대상이 아니므로
`reward_manager` snapshot 또는 audit 로그에서 확인한다.

### 10.5 A6 초기 학습 판정

초기 `A6` 런은 아래 순서로 판정한다.

```text
iter 0
- version = V55.A6
- phase OFF
- forward 2개 + standing/height override 실제 적용 확인
- shoulder_neutral=-1.0, stance_width_penalty=0.0 확인

iter 100
- active reward / penalty dominance 확인
- dof_acc_l2 weighted contribution 확인
- forward_velocity / forward_velocity_bootstrap 실효 확인
- shoulder_left_right_diff, rear contact ratio, front/rear support imbalance 확인

iter 500
- release 직후 shock가 완화되는지 확인
- min_height collapse 재발 여부 확인
- shoulder_neutral / stance_width_penalty ramp 중간값 확인
```

---

## 11. 최종 추천

바로 실행할 1순위는 `Experiment A6`이다.

한 줄 요약:

`지금은 clean V54를 더 밀 때가 아니라, 먼저 baseline을 복구하고, 그 다음 분리된 Track B에서 phase가 실제로 구조를 만드는가를 검증해야 한다.`
