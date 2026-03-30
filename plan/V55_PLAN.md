# V55 Plan: Baseline Recovery First, Phase Probe Second

> 작성: 2026-03-30
> 상태: 설계 확정
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

Track B는 phase probe다.

- phase observation: ON
- phase reward: ON
- handoff: 없음
- phase_contact aggregation: `mean_min`

초기 phase weight:

```text
phase_contact   = 3.0
phase_clearance = 0.75
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

따라서 Track B는:

- `pattern-defining reward`는 OFF
- `movement-enabling reward`는 1/3~1/2로 감쇠

```text
Reward               | Track A | Track B
---------------------+---------+--------
trot_gait            | 유지    | 0.0
diagonal_coupling    | 유지    | 0.0
gait_cycle_period    | 유지    | 0.0
feet_air_time        | 유지    | 10.0
leg_lift             | 유지    | 8.0
rear_alternation     | 유지    | 5.0
rear_joint_velocity  | 유지    | 4.0
stance_propulsion    | 유지    | 4.0
foot_clearance       | 유지    | 3.0
rear_swing           | 유지    | 3.0
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
penalty           = 임시 완화값으로 시작
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
- `dof_acc_l2`, `joint_vel_l2`, `action_rate_l2` 실효 크기
- `dof_acc_l2` raw magnitude
- `boot_standing`, `standing_height`, `feet_air_time`, `trot_gait`, `diagonal_coupling` 우세 항목
- 비의도 reward dominance 여부

`dof_acc_l2` 판단 로직:

```text
1. raw magnitude 확인
2. weighted contribution 확인
3. boot positive 대비 비율 확인

판정:
- 과도하면 현재 완화값 유지
- 안정적이면 상향 조정 검토
- 강한 복원은 "조건부 검토"이지 기본값이 아님
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
B1은 반드시 from-scratch다.
A1 checkpoint에서 resume하지 않는다.
```

이유:

- A1은 phase observation OFF
- B1은 phase observation ON
- observation dimension과 input distribution이 다르다

설정:

```text
base          = A1 성공 설정
phase_obs     = ON
phase_contact = 3.0
phase_clear   = 0.75
handoff       = 없음
fallback      = 없음
phase agg     = mean_min
timing reward = Track B table 기준으로 감쇠/일부 OFF
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
phase_contact = 5.0
phase_clear   = 1.5
```

성공 기준:

- A1/B1 대비 stride/coupling 개선
- ep_len 유지 또는 개선
- phase reward 상승

### Experiment B3: Delayed Handoff Reintroduction

전제:

- B2까지 성공

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

## 10. 최종 추천

바로 실행할 1순위는 `Experiment A1`이다.

한 줄 요약:

`지금은 clean V54를 더 밀 때가 아니라, 먼저 baseline을 복구하고, 그 다음 분리된 Track B에서 phase가 실제로 구조를 만드는가를 검증해야 한다.`
