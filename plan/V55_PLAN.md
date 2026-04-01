# V55 Plan: Baseline Recovery First, Phase Probe Second

> 작성: 2026-03-30
> 상태: B1.1B phase 2.0 공존성 검증 + 후반 splay drift 억제 설계/구현 완료
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

### 원칙 5: 한 실험 = 한 가설

`V55`에서는 한 실험이 무엇을 검증하는지 명확해야 한다.

```text
A5.1 = posture/splay 2개 soft-ramp 가설
A5.2 = shock group 7개 soft-ramp 가설
A5.3 = conservative STAND forward 가설
A5.4 = A5.2 + A5.3 교차 실험
```

즉 한 번 실패했다고 바로 "원인이 아니다"라고 말하지 않고,
항상 다음처럼 표현한다.

```text
- 이 조건만으로는 충분하지 않았다
- 다음 최소 조합이 무엇인지 본다
```

### 원칙 6: iteration은 checkpoint 기준으로만 말한다

TensorBoard scalar의 내부 `step`과 학습 checkpoint iteration을 섞지 않는다.

이 문서에서 `iter 500`이라고 할 때는 항상 다음을 뜻한다.

```text
- model_500.pt
- curriculum_500.pt
- 또는 그에 대응하는 checkpoint iteration
```

`TensorBoard`에서 보이는 scalar step 숫자는 보조 정보일 뿐,
핵심 판정 기준으로 쓰지 않는다.

### 원칙 7: env_cfg / snapshot / runtime / TensorBoard를 분리해서 해석한다

이 프로젝트에서 같은 항목이라도 네 층위가 다를 수 있다.

```text
1. env_cfg 값
   - 코드에 적은 의도값

2. checkpoint snapshot 값
   - curriculum_0.pt / 500.pt / 600.pt 안의 저장값

3. runtime direct weight
   - reward_manager.get_term_cfg(...).weight
   - 실제 그 iteration에 policy가 받는 값

4. TensorBoard episode scalar
   - weight × raw score × episode 집계 결과
```

해석 규칙:

```text
- env_cfg만 보고 "구현됐다"고 말하지 않는다
- curriculum_x.pt만 보고 runtime 성공/실패를 단정하지 않는다
- TensorBoard scalar만 보고 실제 weight를 역산해 확정하지 않는다
- 중요한 충돌은 반드시 direct weight debug 로그로 본다
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

## 7. V55 실험 일지

이 섹션은 `A1 -> A5.6`까지의 흐름을 시간순으로 정리한 것이다.
핵심은 "처음 계획이 무엇이었고, 실제로 무엇이 구현됐고, 결과가 어땠으며,
그래서 왜 다음 실험으로 넘어갔는가"를 한 번에 읽히게 하는 것이다.

### 7.1 출발점: 왜 V55를 따로 만들었는가

처음 계획은 단순했다.

```text
1. V54의 handoff collapse를 피한다
2. 먼저 baseline locomotion을 복구한다
3. 그 다음 phase를 약하게 얹어서 probe로 검증한다
```

즉 `V55`는 처음부터 `phase-centric run`이 아니라
`baseline recovery first, phase probe second`를 위한 새 family였다.

### 7.2 A1: baseline recovery 첫 시도

원래 의도:

```text
- phase OFF
- phase reward OFF
- baseline locomotion만 복구
- penalty는 임시 시작값으로 약하게 시작
```

하지만 실제 구현/런타임에서는
`env_cfg`에서 설정한 penalty 값이 `STAND phase table`에 의해 다시 덮였다.

이 실험이 남긴 핵심 교훈:

```text
1. 코드에 적힌 값과 실제 적용값은 다를 수 있다
2. curriculum_0.pt를 보지 않으면 구현 성공 여부를 말할 수 없다
3. A1은 완전한 의도 실험은 아니었지만,
   초기 ep_len 상승 자체는 가장 좋았던 축이었다
```

즉 `A1`은 "구현은 어긋났지만 baseline recovery는 잘 되는 방향"이라는
첫 단서를 줬다.

### 7.3 A2: penalty ownership 정리 시도

문제 의식:

```text
A1은 penalty가 의도대로 적용되지 않았다.
그럼 V55가 의도한 penalty를 runtime에서 강제로 유지해보자.
```

실제로 한 것:

```text
- action_rate / joint_vel / dof_acc를 V55 값으로 runtime override
```

결과:

```text
- boot가 급격히 약해짐
- ep_len이 짧아짐
- dof_acc penalty dominance가 다시 커짐
```

결론:

```text
A1의 상대적 성공은 "penalty를 STAND table에 맡겼기 때문"일 가능성이 높다.
즉 penalty ownership을 V55가 직접 가져가는 방향은 baseline recovery에 불리했다.
```

### 7.4 A3: penalty를 일부 풀고 forward를 더 올린 시도

문제 의식:

```text
A2는 penalty가 너무 강했다.
그럼 dof_acc를 완화하고, locomotion drive를 더 올려보자.
```

실제로 의도한 것:

```text
- dof_acc 완화
- forward_velocity / bootstrap 강화
```

하지만 실제 런타임에서는
`forward` 2개가 다시 `STAND phase table` 값으로 덮였다.

결론:

```text
A3는 가설을 제대로 시험한 run이 아니었다.
penalty 일부만 바뀌고, forward 강화는 실적용되지 않았다.
```

### 7.5 A4: forward ownership까지 정리한 시도

문제 의식:

```text
A3가 무효였던 이유는 forward 2개가 runtime에서 유지되지 않았기 때문이다.
그럼 forward까지 ownership을 V55가 직접 가져오자.
```

실제로 한 것:

```text
- forward_velocity / bootstrap runtime override 고정
- penalty는 A3 계열 유지
```

결과:

```text
- forward 2개는 실제로 적용됨
- 하지만 boot quality는 좋지 않았음
- 살아 있으면서 걷기보다는, penalty에 눌린 채 짧게 끝나는 패턴
```

결론:

```text
forward 자체를 강하게 미는 것만으로는 해결되지 않았다.
오히려 STAND phase penalty와 forward 공격성이 서로 잘 맞지 않는다는 의심이 생겼다.
```

### 7.6 A5: penalty는 STAND table로 되돌리고, forward 16/12만 유지

문제 의식:

```text
A2~A4를 보면, penalty는 V55가 직접 쥐는 것보다
legacy STAND table에 맡기는 쪽이 baseline recovery에 유리해 보였다.
```

실제로 한 것:

```text
- penalty 3개는 STAND phase table 관리로 복귀
- forward_velocity / bootstrap만 16 / 12로 유지
```

결과:

```text
- STAND phase에서는 역대 V55 최고
- ep_len 248
- stride_length 2.06
- diagonal_coupling_raw 0.52
```

하지만 `iter 500` 직후 붕괴:

```text
- _v47_boot_gate_released_iter = 500
- termination이 time_out 중심에서 min_height 중심으로 급변
- release 이후 walking penalty와 충돌
```

즉 `A5`는
"STAND phase baseline recovery는 성공"
"release 이후 transition은 실패"
를 동시에 보여줬다.

### 7.7 A5.1: 2개 shock source만 완화

처음 해석:

```text
iter 500에서 직접 점프가 확인된 핵심은
- shoulder_neutral
- stance_width_penalty
```

그래서 `A5.1`의 가설은:

```text
이 2개만 soft ramp 하면 collapse가 완화될 것이다.
```

첫 시도 결과는 해석하면 안 됐다.
왜냐하면 이후 재검증에서 구조적 버그가 발견됐기 때문이다.

### 7.8 A5.1 첫 시도는 왜 무효였는가

`reward_weight_curriculum()` 내부에서:

```text
1. gait_gate release 이후 walking weight 적용
2. _all_alphas_done 또는 "실제 변화 없음"이면 조기 return
3. 그 아래쪽의 V55 soft ramp/override 코드에 도달 못 함
```

즉 첫 `A5.1`은
가설 실패 run이 아니라
`soft ramp 지속 적용 버그가 섞인 run`이었다.

### 7.9 A5.1 재검증: 버그 수정 후에도 충분하지 않음

버그 수정 후 다시 fresh start로 검증한 결과:

```text
- iter 500 이후 collapse 재발
- min_height termination이 다시 지배적
```

중요한 해석:

```text
"shoulder_neutral / stance_width_penalty가 원인이 아니다"
가 아니라
"그 2개만으로는 충분하지 않았다"
```

### 7.10 A5.2: shock group을 7개로 확대

문제 의식:

```text
A5.1은 2개 shock source만 완화했지만 충분하지 않았다.
그럼 다음으로 유력한 diff / floor 항목을 추가해보자.
```

실제로 추가한 항목:

```text
기존 유지
- shoulder_neutral
- stance_width_penalty

추가
- rear_left_right_propulsion_diff_penalty
- front_left_right_propulsion_diff_penalty
- rear_left_right_usage_diff_penalty
- front_left_right_usage_diff_penalty
- per_leg_contact_floor
```

결과:

```text
- 추가한 5개는 실제로 ramp 흔적이 보임
- 하지만 전체적으로는 다시 min_height collapse
```

결론:

```text
release shock 항목을 더 늘리는 것만으로는 충분하지 않았다.
```

### 7.11 A5.2가 남긴 더 근본적인 질문

`A5`, `A5.1`, `A5.2`를 묶어 보면
반복되는 패턴이 보인다.

```text
STAND phase에서는 매우 잘 감
iter 500 gait_gate release 이후에는 반복 붕괴
```

그래서 질문이 바뀌었다.

```text
"어떤 penalty가 shock를 주는가?"
보다
"release 이전에 어떤 policy를 학습했는가?"
를 먼저 봐야 하는 것 아닌가?
```

### 7.12 현재 최우선 가설

가장 유력한 설명은 다음이다.

```text
V47
- STAND phase에서 보수적 forward policy
- gait_gate release 이후 walking penalty와 양립 가능

A5 계열
- STAND phase에서 forward 16 / bootstrap 12 override
- 넓고 낮게 벌리고 빠르게 미는 공격적 전략 학습
- gait_gate release 이후 walking penalty와 근본적으로 충돌
```

즉 현재 문제의 본질은:

```text
"release 후 penalty jump" 자체보다
"release 전에 학습한 공격적 forward policy"가
walking phase 요구와 양립 불가한 것일 수 있다.
```

### 7.13 A5.3: 현재 최우선 실험

그래서 다음 실험(`A5.3` 또는 별도 `A7`)의 목표는
shock 항목을 더 늘려보는 것이 아니라,
`STAND phase에서 무엇을 학습하게 할지`를 바꾸는 것이다.

실험 정의:

```text
STAND phase
- forward_velocity = phase table STAND 값 (2.0)
- forward_velocity_bootstrap = STAND 값 (8.0)
- 즉 STAND에서는 공격적 forward override 제거

gait_gate release 이후 500 iter soft-ramp
- forward_velocity: 2.0 -> 16.0
- forward_velocity_bootstrap: 8.0 -> 12.0

공통 원칙
- forward 항목도 ownership 충돌 없이 V55 전용 경로에서만 제어
- iter 499 / 500 / 501 실제 weight direct debug log 기록
- A5.2의 shock 완화 가설과는 분리해서 해석
```

이 실험이 중요한 이유:

```text
1. A5.1 / A5.2는 "release shock 완화" 축을 이미 충분히 보여줬다
2. 이제는 "STAND에서 공격적 policy를 학습시키는 것이 문제인가"를 직접 시험해야 한다
3. 이건 V47과 A5의 차이를 가장 직접적으로 검증하는 경로다
```

### 7.14 A5.3 결과: 가설 약화

`A5.3`의 실제 데이터는 다음을 보여줬다.

```text
iter 400
- ep_len 250
- stride 3.24
- diagonal_coupling_raw 0.53
- min_height 0.0

iter 500
- ep_len 3.75
- min_height 0.999
- time_out 사실상 0
```

그리고 snapshot 기준:

```text
curriculum_0.pt
- forward_velocity = 2.0
- forward_velocity_bootstrap = 8.0

curriculum_600.pt
- forward_velocity = 4.8
- forward_velocity_bootstrap = 8.8
```

의미:

```text
1. STAND에서 forward 2/8이어도 pre-release baseline은 충분히 강했다
2. 즉 "STAND forward 16/12가 A5 성공의 핵심"은 아니었다
3. 그럼에도 iter 500 collapse는 그대로 재발했다
4. 따라서 conservative forward only도 충분조건이 아니었다
```

### 7.15 A5.4: 현재 최우선 실험

현재까지의 두 분리 실험 결과:

```text
A5.2
- shock 완화 only
- 실패

A5.3
- conservative forward only
- 실패
```

따라서 다음 최소 합리적 조합은 `A5.4`다.

정의:

```text
STAND phase
- forward_velocity = 2.0
- forward_velocity_bootstrap = 8.0

gait_gate release 이후 500 iter
- forward_velocity 2.0 -> 16.0 soft-ramp
- forward_velocity_bootstrap 8.0 -> 12.0 soft-ramp

동시에 유지
- A5.2의 7개 release shock term soft-ramp
  * shoulder_neutral
  * stance_width_penalty
  * rear/front propulsion diff penalties
  * rear/front usage diff penalties
  * per_leg_contact_floor
```

왜 이게 지금 맞는가:

```text
1. A5.2와 A5.3은 이미 분리 검증한 두 가설이다
2. A5.4는 무작정 변수 추가가 아니라 두 가설의 교차 실험이다
3. STAND baseline은 보수적으로 유지하면서,
   release shock와 post-release forward recovery를 동시에 시험할 수 있다
```

### 7.16 A5.4 결과: 결합만으로도 collapse는 막지 못함

`A5.4`는 `A5.2`의 7개 shock soft-ramp와 `A5.3`의 conservative forward를 결합했지만,
checkpoint `500`에서 다시 붕괴했다.

확인된 사실:

```text
curriculum_0.pt
- forward_velocity = 2.0
- forward_velocity_bootstrap = 8.0
- 7개 shock term = pre 값

iter 500 latest
- mean_episode_length 4.37
- min_height termination 0.997
- stride_length 0.032
- diagonal_coupling_raw 0.0067
```

의미:

```text
1. A5.4의 초기 설정은 의도대로 들어갔다
2. 그럼에도 iter 500에서 다시 min_height collapse가 발생했다
3. 따라서 "shock 완화 + conservative forward" 결합도 충분조건은 아니었다
```

### 7.17 A5.5: min_height 증폭기 가설 검증

`V47`과 `A5.x`의 중요한 차이가 하나 더 확인됐다.

```text
V47
- iter 500에서도 ep_len이 높게 유지
- min_height termination 없음

A5.x
- iter 500에서 min_height termination이 99% 가까이 지배
```

현재 가장 타당한 해석:

```text
release 직후 자세가 잠깐 흔들리는 것은 V47에서도 있었을 수 있다.
하지만 V47은 회복할 시간이 있었고,
A5.x는 min_height termination이 그 순간을 즉사로 바꿔버리는
"collapse amplifier" 역할을 할 수 있다.
```

그래서 다음 실험은 `A5.5`다.

정의:

```text
A5.5 = A5.4 유지
     + min_height termination threshold 완화
       0.15 -> 0.12
```

왜 `비활성`이 아니라 `threshold 완화`부터 하는가:

```text
1. 일시적 release 흔들림은 허용
2. 실제 심한 낙하는 여전히 termination으로 잡음
3. 원인 분리가 더 깨끗함
```

### 7.18 A5.5 결과: 증폭기 가설 지지

`A5.5`는 collapse를 완전히 막지는 못했지만, 패턴을 바꿨다.

```text
iter 500
- A5 / A5.4: ep_len 약 4
- A5.5:      ep_len 6.2

iter 600
- A5 / A5.4: ep_len 약 5
- A5.5:      ep_len 18.4
```

의미:

```text
1. iter 500 release collapse 자체는 남아 있다
2. 하지만 collapse의 깊이와 회복 속도는 분명히 개선됐다
3. 따라서 min_height는 근본 원인이라기보다
   collapse를 더 깊고 회복 불가능하게 만드는 증폭기였을 가능성이 높다
```

### 7.19 A5.6: 현재 최우선 실험

`A5.5`가 유의미한 완화를 보여줬으므로,
다음 최소 단계는 min_height threshold를 한 번 더 낮추는 것이다.

정의:

```text
A5.6 = A5.5 유지
     + min_height termination threshold
       0.12 -> 0.10
```

이 순서를 택하는 이유:

```text
1. A5.5가 완전 무효가 아니라 부분 성공이었다
2. 완전 비활성화보다 작은 변경이라 해석력이 좋다
3. collapse 깊이와 회복 속도의 추가 개선 여부를 보기 좋다
```

---

## 8. 실험 단계

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
base          = A6 baseline quality gate 통과 설정
phase_obs     = ON
phase_contact = 1.5
phase_clear   = 0.5
handoff       = 없음
fallback      = 없음
phase agg     = mean_min
timing reward = additive probe 수준

구체적으로는 아래를 그대로 계승한다
- min_height threshold 0.10
- STAND forward 2 / 8
- post-release forward ramp 2->16, 8->12
- 7개 release shock soft-ramp
- A6 posture gate
  - shoulder_neutral post -8
  - stance_width_penalty post -4
  - base_height_l2 -23.0
  - front_rear_support_balance_penalty -9.6
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
- A6 대비 ep_len 급락이 없는지 확인
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

지금 기준으로는 더 정확히:

```text
front/rear ratio가 A6 대비 나빠지면
phase probe가 baseline quality를 해치고 있을 가능성이 높다
```

### Experiment B1.1: Weak Phase Probe + Slightly Stronger Posture Gate

목적:

```text
B1의 phase 강도는 유지하되,
후반에 다시 커진 shoulder_splay와 front-heavy drift만
작게 눌러서 baseline quality를 회복할 수 있는지 확인한다.
```

가설:

```text
현재 B1의 병목은 phase 자체보다
posture gate가 약해서 뒤로 갈수록 shoulder_splay가 다시 커지는 것이다.

따라서
- phase_contact / phase_clearance는 그대로 두고
- shoulder_neutral / stance_width / front_rear_support
만 소폭 강화하면

1. shoulder_splay termination이 감소하고
2. time_out / diagonal / stride가 다시 안정되며
3. RL contact 바닥 고착 없이 B2 진입 가능한 baseline을 유지할 수 있다.
```

설정:

```text
base          = B1과 동일한 A6 baseline 계승
phase probe   = B1과 동일
변경 항목     = posture gate 3개만 소폭 강화

구체적으로는
- shoulder_neutral post  -8.0 -> -9.0
- stance_width post      -4.0 -> -4.5
- front_rear_support_balance_penalty  -9.6 -> -10.5
```

변경하지 않는 항목:

```text
- phase_contact / phase_clearance
- STAND forward 2 / 8
- post-release forward ramp
- 7개 release shock soft-ramp
- min_height threshold 0.10
```

성공 기준:

```text
iter 900 이후
- shoulder_splay termination < 0.20
- time_out > 0.75
- diagonal_coupling_raw > 0.45
- stride > 4.0
- RL contact_ratio > 0.20 유지
```

실패 기준:

```text
- shoulder_splay가 여전히 0.30+로 높음
- time_out / stride / diagonal이 B1보다 더 나빠짐
- RL contact가 다시 바닥 쪽으로 내려감
```

해석:

```text
B1.1은 B1 반복 실험이 아니다.

가설은 하나다:
"phase 강도는 유지하고 posture gate만 소폭 강화하면
B1 후반 품질 저하를 줄일 수 있는가?"

이 한 번으로 효과가 없으면
B1.2, B1.3처럼 길게 끌지 않고
B2 또는 다른 방향을 재검토한다.
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

### Experiment B1.1A: Phase 2.0 Coexistence Test

전제:

- B1.1 성공

설정:

```text
base                        = B1.1 baseline 계승
forward_velocity            = STAND 2.0 / post-release 2->16 ramp 유지
forward_velocity_bootstrap  = STAND 8.0 / post-release 8->12 ramp 유지
min_height threshold        = 0.10 유지

posture gate 유지:
- shoulder_neutral post     = -9.0
- stance_width post         = -4.5
- front_rear_support        = -10.5
- base_height_l2            = -23.0

phase_contact               = 2.0
phase_clearance             = 0.75
trot_gait                   = 5.0
diagonal_coupling           = 5.0
feet_air_time               = 20.0
leg_lift                    = 20.0
rear_alternation            = 15.0
rear_joint_velocity         = 12.0
stance_propulsion           = 8.0
rear_swing                  = 6.0
```

성공 기준:

- time_out > 0.75
- diagonal_coupling_raw > 0.45
- stride > 4.0
- phase_contact가 B1.1보다 분명히 높거나 최소 유지
- shoulder_splay < 0.20
- RL contact_ratio > 0.20 유지

실패 기준:

- time_out < 0.60
- diagonal_coupling_raw < 0.40
- shoulder_splay > 0.30
- RL contact_ratio < 0.15
- phase는 올랐는데 baseline 품질만 악화

해석:

```text
B1.1A는 "phase가 gait를 주도하는가"를 보는 실험이 아니다.

목표는 하나다:
"phase 2.0이 B1.1 baseline과 공존 가능한가?"

즉 B1.2 실패 원인이
- phase 3.0 자체인지
- heuristic 감쇠가 너무 급했던 것인지
를 본 뒤, phase 강도를 한 단계 낮춘 공존성 실험이다.
```

### Experiment B1.1B: Phase 2.0 Coexistence + Late Splay Drift Suppression

전제:

- B1.1A는 완전 실패는 아니었지만,
  후반으로 갈수록 shoulder_splay drift가 다시 커졌다

설정:

```text
base                        = B1.1A baseline 계승
forward_velocity            = STAND 2.0 / post-release 2->16 ramp 유지
forward_velocity_bootstrap  = STAND 8.0 / post-release 8->12 ramp 유지
min_height threshold        = 0.10 유지

phase_contact               = 2.0
phase_clearance             = 0.75
trot_gait                   = 5.0
diagonal_coupling           = 5.0
feet_air_time               = 20.0
leg_lift                    = 20.0
rear_alternation            = 15.0
rear_joint_velocity         = 12.0
stance_propulsion           = 8.0
rear_swing                  = 6.0

posture gate 추가 강화:
- shoulder_neutral post     = -10.0
- stance_width post         = -5.0
- front_rear_support        = -11.5
- base_height_l2            = -23.0 유지
```

성공 기준:

- time_out > 0.75
- diagonal_coupling_raw > 0.45
- stride > 4.0
- phase_contact가 B1.1A 수준 유지
- shoulder_splay < 0.25
- RL contact_ratio > 0.20 유지

실패 기준:

- time_out < 0.60
- diagonal_coupling_raw < 0.40
- shoulder_splay > 0.30
- RL contact_ratio < 0.15
- phase는 유지되는데 baseline 품질만 나빠짐

해석:

```text
B1.1B는 phase 파라미터를 더 바꾸는 실험이 아니다.

목표는 하나다:
"phase 2.0 공존성은 유지한 채,
 후반 shoulder_splay drift만 posture gate로 더 누를 수 있는가?"

즉 B1.1A의 부분 성공을 유지하면서,
후반 품질 저하를 만든 splay drift를 직접 겨냥하는
가장 작은 다음 실험이다.
```

### Experiment B1.2: Phase 3.0 Coexistence Test

결과:

```text
- shoulder_splay는 낮게 유지됐지만
- min_height / time_out / diagonal_raw가 무너졌다
- 즉 phase 3.0은 현재 baseline에 과한 쪽으로 판정됐다
```

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

## 9. 모니터링 지표

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

## 10. 구현 전 체크리스트

구현 전에 아래 6가지를 반드시 확인한다.

1. `A1`에서 `_phase_remove`가 실질적으로 비활성화되는가
2. `A1`의 observation dimension이 baseline과 정확히 같은가
3. `A1 iter 100`에서 `dof_acc_l2` raw magnitude와 weighted contribution을 반드시 확인하는가
4. `B1/B2`는 반드시 from-scratch인가
5. `Track B` 감쇠 수치는 weight 기준이며, 실측 contribution은 `B1 iter 100`에서 다시 검증하는가
6. `A1` 실패 시 fallback은 `V47 원본 env/reward inventory 명시 복원 후 재시도`인가

---

## 11. 구현 상태

현재 코드 기준 구현 상태:

```text
기본 실행 버전
- TRAIN_VERSION = V55.B1.1B

구현 완료
- Track A / Track B / B2 / B3 분기
- A-track: phase observation OFF
- A-track: phase reward OFF
- B-track: phase auxiliary ON
- V55 전용 forward override 유지
- A5: penalty는 legacy STAND table ramp 유지
- A5.1: posture/splay 2항목 release soft-ramp
- A5.2: 7항목 release soft-ramp
- A5.3: STAND forward 제거 + post-release forward ramp
- A5.4: A5.2 7항목 shock soft-ramp + A5.3 forward ramp 결합
- A5.5: A5.4 유지 + min_height termination threshold 0.12 완화
- A5.6: A5.5 유지 + min_height termination threshold 0.10 완화
- A6: A5.6 유지 + posture/usage correction(B1 진입용 baseline quality gate)
- B1: A6 baseline 계승 + weak phase probe 실행
- B1.1: B1 유지 + posture gate만 소폭 강화
- B1.1A: B1.1 baseline 유지 + phase 2.0 공존성 검증(부분 성공, 후반 splay drift 남음)
- B1.1B: B1.1A 유지 + posture gate만 한 단계 더 강화
- B1.2: B1.1 baseline 유지 + phase 3.0 공존성 검증(실패)
- iter 0 / 100 / 500 V55 audit 로그

주의
- A5는 iter 500 이전까지 baseline recovery에 성공했지만
  gait_gate release 직후 min_height collapse가 발생했다
- 현재 기본 실행 버전은 B1.1B이며,
  다음 검증 우선순위는 B1.1A에서 확인된 phase 2.0 공존성을 유지한 채
  후반 shoulder_splay drift를 posture gate 강화로 줄일 수 있는지 확인하는 것이다
```

### 11.1 A5에서 실제로 막은 경로

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

### 11.2 A5에서 새로 드러난 붕괴 경로

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

### 11.3 다음 우선 실험 방향

다음 우선 실험(`A5.6`)은
`A5.5`를 유지한 채 `min_height termination` threshold를 한 단계 더 내리는 작은 ablation이다.

```text
STAND phase
- forward_velocity = phase table STAND 값 (2.0)
- forward_velocity_bootstrap = STAND 값 (8.0)
- 즉 STAND에서는 공격적 forward override를 제거

gait_gate release 이후 500 iter soft-ramp
- forward_velocity: 2.0 -> 16.0
- forward_velocity_bootstrap: 8.0 -> 12.0

동시에 유지
- shoulder_neutral soft-ramp
- stance_width_penalty soft-ramp
- rear/front propulsion diff penalty soft-ramp
- rear/front usage diff penalty soft-ramp
- per_leg_contact_floor soft-ramp

추가 변경
- min_height termination threshold: 0.12 -> 0.10

공통 원칙
- forward 항목도 ownership 충돌 없이 V55 전용 경로에서만 제어
- iter 499 / 500 / 501의 실제 weight를 직접 로그로 확인
- posture correction(A6)은 이 실험 이후 보류/재평가
```

이 방향을 우선하는 이유:

```text
1. A5.5는 collapse 자체는 남았지만 깊이와 회복 속도를 개선했다
2. 따라서 min_height 증폭기 가설은 지지된다
3. 다음은 더 작은 threshold 완화로 추가 개선 여부를 본다
```

### 11.4 다음 우선 실험 검증 규칙

`코드값`이 아니라 `curriculum_0.pt`, `curriculum_500.pt`, runtime weight 로그로 판정한다.

초기 fresh start에서 반드시 확인할 값:

```text
action_rate_l2             = -0.3
joint_vel_l2               = -0.05
dof_acc_l2                 = -5e-7
forward_velocity           = 2.0
forward_velocity_bootstrap = 8.0
shoulder_neutral           = -1.0
stance_width_penalty       = 0.0
rear_left_right_propulsion_diff_penalty  = 0.0
front_left_right_propulsion_diff_penalty = 0.0
rear_left_right_usage_diff_penalty       = 0.0
front_left_right_usage_diff_penalty      = 0.0
per_leg_contact_floor      = -1.0
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
iter 499 / 500 / 501
- reward_manager.get_term_cfg(\"forward_velocity\").weight
- reward_manager.get_term_cfg(\"forward_velocity_bootstrap\").weight
- reward_manager.get_term_cfg(\"shoulder_neutral\").weight
- reward_manager.get_term_cfg(\"stance_width_penalty\").weight
- reward_manager.get_term_cfg(\"rear_left_right_propulsion_diff_penalty\").weight
- reward_manager.get_term_cfg(\"front_left_right_propulsion_diff_penalty\").weight
- reward_manager.get_term_cfg(\"rear_left_right_usage_diff_penalty\").weight
- reward_manager.get_term_cfg(\"front_left_right_usage_diff_penalty\").weight
- reward_manager.get_term_cfg(\"per_leg_contact_floor\").weight
```

가능하면 로그 형식도 고정한다:

```text
[ReleaseDebug] iter 499
  forward_velocity=...
  forward_velocity_bootstrap=...
  shoulder_neutral=...
  stance_width_penalty=...
  rear_left_right_propulsion_diff_penalty=...
  front_left_right_propulsion_diff_penalty=...
  rear_left_right_usage_diff_penalty=...
  front_left_right_usage_diff_penalty=...
  per_leg_contact_floor=...
```

### 11.5 다음 우선 실험 초기 학습 판정

초기 새 런은 아래 순서로 판정한다.

```text
iter 0
- version = V55.A5.6
- phase OFF
- forward 2개가 STAND table 값(2.0 / 8.0)인지 확인
- 7개 shock term이 pre 값(-1/0/-1 계열)인지 확인
- min_height termination threshold가 0.10인지 확인

iter 100
- active reward / penalty dominance 확인
- dof_acc_l2 weighted contribution 확인
- 보수적 STAND policy가 형성되는지 확인

iter 500
- release 직후 forward ramp가 시작되는지 확인
- 7개 shock term soft-ramp가 post 값으로 즉시 점프하지 않는지 확인
- min_height collapse 깊이가 A5.5보다 더 완화되는지 확인
- forward 2개 ramp 중간값 확인

iter 600
- ep_len 회복 속도가 A5.5(18.4)보다 더 빠른지 확인
```

### 11.6 A6 준비 계획: B1 진입용 baseline quality gate

`A6`는 원래 논의됐던 "cricket gait 완전 해결" 실험이 아니다.
현재 합의된 정의는 아래와 같다.

핵심 목표:

```text
A6의 목적은
cricket gait를 A-track에서 완전히 해결하는 것이 아니라,
RL contact_ratio 바닥 고착과 shoulder_splay를 조금 완화해서
B1 phase probe로 넘어갈 수 있는 최소 baseline 품질을 만드는 것이다.
```

배경:

```text
- A5.6은 iter 500 release collapse를 상당 부분 완화했다
- 하지만 장기 구간에서는 RL(왼쪽 뒤) contact_ratio 바닥 고착과
  shoulder_splay termination이 새 병목으로 보인다
- 이 상태에서 바로 B1로 가면
  phase가 gait를 개선한 것인지,
  기존 3발 보행 위에 phase가 덧씌워진 것인지 해석이 흐려질 수 있다
```

가설:

```text
posture/splay를 소폭 교정하면
RL usage가 0.01 수준의 바닥 고착에서 0.1+ 수준으로 완화되고,
shoulder_splay termination도 줄어
B1 additive probe를 해석 가능한 baseline 위에서 시작할 수 있다.
```

예정 변경 항목:

```text
유지
- A5.6 구조 전체 유지
- min_height threshold 0.10
- STAND forward 2/8
- post-release forward ramp
- 7개 shock soft ramp

소폭 강화
- stance_width_penalty post: -3 -> -4
- shoulder_neutral post: -6 -> -8
- front_rear_support_balance_penalty: 절대값 +20%
- base_height_l2: 절대값 +10~15%
```

의도적으로 보류하는 항목:

```text
- per_leg_contact_floor 추가 강화
- limb_usage_min 추가 강화
- single_limb_validity 추가 강화
- B-track phase probe
```

이유:

```text
1. RL 미사용을 직접 penalty로 더 강하게 누르면
   release-collapse를 다시 키울 위험이 있다
2. A6는 "RL을 강제로 쓰게 하기"보다
   "자세와 지지 구조를 조금 더 자연스럽게 만들어
    RL 바닥 고착을 완화할 수 있는지"를 보는 실험이다
3. 이 실험은 해결책의 끝이 아니라
   B1 진입 가능 여부를 판단하는 분기점 실험이다
```

성공 기준:

```text
iter 400
- ep_len 220+
- stride 2.5+
- diagonal_raw 0.45+

iter 900
- RL contact_ratio > 0.10
- shoulder_splay termination < 0.20
- time_out > 0.75
- stride가 A5.6 대비 크게 악화되지 않음
```

실패 기준:

```text
- RL contact_ratio가 계속 0.01~0.05 바닥
- shoulder_splay가 그대로 높음
- stride/ep_len만 나빠짐
```

다음 분기:

```text
A6 성공
-> B1 additive probe 진입

A6 부분 성공
-> usage/contact direct correction 한 번 더

A6 실패
-> A-track에서 더 버티지 말고
   B 진입 전략 또는 direct correction 우선순위 재검토
```

---

## 12. 최종 추천

바로 실행할 다음 1순위는 `B1.1B` 검증이다.

한 줄 요약:

`A6 baseline quality gate와 B1.1 posture 보정은 확보됐고, B1.2에서 phase 3.0이 과하다는 신호를 봤다. B1.1A로 phase 2.0 공존성은 어느 정도 확인했으므로, 지금은 그 baseline 위에서 후반 shoulder_splay drift를 더 누르는 B1.1B가 맞다.`
