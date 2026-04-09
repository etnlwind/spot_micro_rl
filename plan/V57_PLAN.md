# V57 Plan: Clean Phase-Centric Reboot

> 작성: 2026-04-02
> 상태: B1.3 설계/구현 완료, planted-stand + FK 기반 초기 자세 교정 + reset warmup 적용
> 목적: `V55/V56`에서 확인한 baseline recovery, phase coexistence, mechanics failure를 바탕으로, 77개 heuristic 생태계에서 벗어난 clean reward stack으로 사족보행을 다시 정의한다.

---

## 1. 왜 V57인가

`V55`와 `V56`의 핵심 교훈:

```text
1. release collapse는 상당 부분 해결할 수 있었다
2. phase가 읽히는 것까지는 확인했다
3. 하지만 자연스럽고 내구성 있는 gait는 얻지 못했다
4. 현재 reward 구조는 exploit를 계속 낳는다
```

즉 지금 문제는:

```text
- reward 하나씩 추가/조정하는 패치형 접근의 한계
- 77개 heuristic이 서로 다른 "걸음"을 요구하며 충돌
- policy가 그 사이에서 기괴한 타협해를 찾음
```

그래서 `V57`은:

```text
기존 reward 생태계를 더 고치는 버전이 아니라,
clean reward stack으로 다시 시작하는 메이저 버전
```

이다.

---

## 2. V55/V56에서 무엇을 배웠는가

### 2.1 V55의 성과

```text
- iter 500 gait-gate collapse 완화
- min_height는 collapse amplifier임을 확인
- RL 바닥 고착 완화
- phase coexistence 가능성 확인
```

### 2.2 V56의 의미

```text
- pitch / nose-down을 직접 억제하는 축이 필요함을 확인
- 하지만 기존 77개 구조 위 patch만으로는
  deployable mechanics까지 가기 어렵다는 것도 확인
```

### 2.3 가장 중요한 결론

```text
phase clock은 도움이 되는 도구다.
하지만 현재 reward stack에서 phase는 여전히 "보조"이고,
heuristic ecology가 gait를 주도하고 있다.
```

`V57`의 목적은 바로 이 관계를 뒤집는 것이다.

---

## 3. V57의 기본 철학

표준 quadruped RL 접근:

```text
phase/CPG가 gait timing의 주연
reward는 8~12개 핵심 축으로 정리
```

현재 우리 접근:

```text
77개 heuristic이 주연
phase는 probe / auxiliary
```

`V57`에서는 아래를 원칙으로 한다.

### 원칙 1: gait timing은 구조적으로 준다

```text
phase clock / CPG가 "주연"
reward는 그것을 보조
```

### 원칙 2: reward 수를 대폭 줄인다

목표:

```text
8 ~ 12개 수준
```

### 원칙 3: mechanics를 성공 기준에 포함한다

성공 기준:

```text
- time_out
- diagonal_raw
- stride
- front/rear contact balance
- 영상상 nose-down 감소
- 영상상 torsion gait 감소
- 앞다리 과부하 없음
```

### 원칙 4: gait는 "발견"보다 "유도"

우리가 원하는 것은 “어떤 기괴한 해도 괜찮은 최대 보상”이 아니라,
deployable trot에 가까운 구조다.

---

## 4. 문헌/프레임워크에서 가져올 것

`plan/QUADRUPED_RL_RESEARCH.md` 기준으로, V57은 아래를 적극 참조한다.

### legged_gym / ANYmal

가져올 축:

```text
- velocity tracking
- yaw tracking
- lin_vel_z penalty
- ang_vel_xy penalty
- action_rate penalty
- dof_acc / joint smoothness
- feet_air_time
- collision/contact penalty
```

### Walk These Ways

가져올 축:

```text
- phase clock 기반 desired contact structure
- swing / stance 구분
- phase-linked foot clearance
- stance width / stance length를 "reward ad-hoc"이 아니라 구조 파라미터로 보는 관점
```

### AllGaits / CPG류

가져올 축:

```text
- gait pattern은 reward가 아니라 구조적 레이어에서 관리
- reward는 tracking / smoothness / energy / stability 중심
```

---

## 5. V57 전체 흐름

### B1: Stand-first bootstrap

목표:

```text
먼저 4발로 높고 수평하게 선다.
걷기는 그 다음 단계다.
```

이 단계의 정의:

```text
서기 = zero-speed gait 가 아니다.
서기 = planted support control 이다.
```

즉 `B1`에서 policy가 배워야 하는 것은:

```text
1. 발을 붙인 상태에서
2. 몸통과 관절로 무게중심을 지지다각형 안에 유지하고
3. 정말 못 버틸 때만 발을 떼는 것
```

이건 `V55/V56`에서 반복된 다음 실패와 반대다.

```text
- 발을 계속 움직이며 버티기
- 앞발을 몸 안쪽으로 모으기
- 앞으로 밀리거나 비틀리며 쓰러지기
- phase대로 발만 흔드는 open-loop
```

### A1: Clean flat-trot bootstrap

전제:

```text
B1 성공
```

목표:

```text
정적 지지 제어가 안정된 뒤에
phase/CPG를 주연으로 둔 clean trot bootstrap으로 넘어간다.
```

### A2: Rough / robustness extension

전제:

```text
A1 성공
```

목표:

```text
rough terrain / command variation / robustness 확장
```

---

## 6. 왜 B1이 먼저인가

사용자 영상 관찰과 최근 실패 모드에서 확인된 핵심은:

```text
우리는 너무 빨리 "걷기"를 요구했다.
하지만 SpotMicro는 먼저 "서기"를 배워야 한다.
```

어린 송아지/망아지 관점에서 보면 첫 서기는 대략 이 순서다.

```text
1. 다리를 넓게 벌려 지지다각형을 확보
2. 발은 가능하면 붙인 채 유지
3. 몸통을 높이고 수평을 맞춤
4. 작은 흔들림은 관절로 흡수
5. 정말 못 버틸 때만 발을 옮겨 지지폭을 다시 만든다
```

즉 발을 계속 떼고 놓는 것은:

```text
기본 전략이 아니라
넘어짐을 늦추기 위한 마지막 보정 수단
```

이어야 한다.

`B1`은 이 순서를 학습 과제로 분리한 단계다.

---

## 7. Experiment V57.B1

### 7.1 질문

`B1`이 답할 질문은 하나다.

```text
"SpotMicro가 symmetric reset에서
 발을 붙인 채 높고 수평하게 버티는 법을
 먼저 배울 수 있는가?"
```

### 7.2 환경 설계

`B1`은 locomotion task가 아니다.

```text
- standing envs         = 100%
- lin_vel_x             = 0
- lin_vel_y             = 0
- ang_vel_z             = 0
- decimation            = 4 (50Hz)
- reset joint randomization OFF
- phase observation OFF
- phase reward OFF
```

의도:

```text
- command가 policy를 걷기로 유도하지 않게 함
- reset 직후 비대칭 착지/튐을 최대한 줄임
- "우선 서라"는 과제만 남김
```

### 7.2.1 FK 기반 초기 자세 교정

`B1.2`에서 가장 중요한 환경 교정은 초기 자세였다.

기존 init pose는 joint 값만 보면 대칭처럼 보였지만, 실제 URDF 축/원점을 반영한
toe FK로 보면 완전 대칭이 아니었다.

기존 값:

```text
FL/FR/RL/RR shoulder = -0.04
FL/FR/RL/RR leg      = -0.97
FL/FR/RL/RR foot     = 1.31
```

실측 FK 결과:

```text
current
FL toe = [-0.0380, -0.0953, -0.1823]
FR toe = [-0.0380,  0.0806, -0.1864]
RL toe = [ 0.1480, -0.0953, -0.1823]
RR toe = [ 0.1480,  0.0806, -0.1864]

support center xyz = [ 0.054982, -0.007378, -0.184354]
front pair y sum   = -0.014756
rear pair y sum    = -0.014756
z spread           = 0.004159
```

즉:

```text
- 좌우 toe y 위치가 완전 대칭이 아님
- 좌우 toe 높이도 4mm 정도 차이남
- support center x가 +5.5cm 뒤로 밀려 있음
```

그래서 `B1.2`에서는 분석팀 실측 교정값을 채택한다.

```text
front_left_shoulder   = -0.04
front_right_shoulder  = +0.04
rear_left_shoulder    = -0.04
rear_right_shoulder   = +0.04

front_left_leg        = -0.74
front_right_leg       = -0.74
rear_left_leg         = -0.72
rear_right_leg        = -0.72

front_left_foot       = 1.38
front_right_foot      = 1.38
rear_left_foot        = 1.38
rear_right_foot       = 1.38

base init z           = 0.19
```

교정 후 FK:

```text
analysis-team full fix
FL toe = [-0.0881, -0.0955, -0.1854]
FR toe = [-0.0881,  0.0955, -0.1854]
RL toe = [ 0.0941, -0.0955, -0.1854]
RR toe = [ 0.0941,  0.0955, -0.1854]

support center xyz = [0.002976, 0.000000, -0.185400]
front pair y sum   = 0.0
rear pair y sum    = 0.0
z spread           = 0.000059
front width        = 0.190921
rear width         = 0.190926
```

핵심 의미:

```text
- init pose가 실제 공간에서도 좌우 대칭이 됨
- support center가 body 중심에 거의 맞음
- planted stand 학습 전에 이미 한쪽으로 기우는 bias를 줄임
```

### 7.3 reward 설계

`B1` reward는 "걷기 구조"가 아니라 "정적 지지"를 가르친다.

```text
Positive
1. alive_bonus        +1.0
2. standing_height    +5.0
3. feet_on_ground     +2.0
4. stationary_reward  +1.0
5. contact_switch_penalty      -2.0
6. contact_foot_velocity_penalty -1.0

Negative
7. lin_vel_z_l2       -2.0
8. ang_vel_xy_l2      -0.5
9. flat_orientation   -2.0
10. base_height_l2     -1.5
11. action_rate_l2     -0.5
12. joint_vel_l2      -0.1
13. dof_acc_l2        -2.5e-7
14. undesired_contacts -1.0
```

### 7.3.0 B1.1 3관문 리뷰

#### 본질 리뷰

`B1.1`의 본질은 다음 한 줄이다.

```text
서기 = 발을 붙인 채 관절과 몸통으로 무게중심을 지지다각형 안에 유지하는 것
```

즉 `B1.1`은:

```text
- 걸음을 배우는 단계가 아니다
- 발을 떼기 전 planted support를 먼저 배우는 단계다
- 발 재배치는 마지막 수단이어야 한다
```

#### 실패모드 리뷰

`B1` 첫안에서 실제로 드러난 값과 영상은 다음 실패모드를 보여줬다.

```text
1. 발을 계속 떼고 다시 디디며 느린 걷기처럼 버팀
2. 붙인 발을 미끄러뜨리거나 끌고 가며 버팀
3. stationary_reward가 있어도 stepping이 더 쉬운 해로 남음
4. 결국 bad_orientation으로 계속 죽음
```

핵심은:

```text
결과 지표(height, orientation, feet_on_ground)는 있었지만,
행동 제약(발을 떼지 말라 / 붙인 발을 미끄러뜨리지 말라)이 없었다.
```

#### 구현 리뷰

그래서 `B1.1`에서는 reward를 많이 늘리지 않고,
행동 제약 2개만 추가한다.

```text
1. contact_switch_penalty
2. contact_foot_velocity_penalty
```

이 둘은 각각:

```text
contact_switch_penalty
- 접지 상태 변화 자체를 비용화
- "불필요한 liftoff / touchdown"을 직접 억제

contact_foot_velocity_penalty
- 접지 중인 발의 XY 속도를 비용화
- "붙인 발로 버티지 않고 끌고 가는 전략"을 직접 억제
```

즉 `B1.1`은
`높고 수평하게 서라`를 넘어서,
`붙인 발은 유지하고, 필요할 때만 떼며, 붙인 발은 미끄러뜨리지 말라`
를 실제 행동 수준으로 정의한 버전이다.

핵심 의미:

```text
standing_height
- 몸을 적정 높이까지 펴고 수평에 가깝게 유지하라

feet_on_ground
- 4발 지지를 유지하라

stationary_reward
- 앞으로 밀리거나 발을 재배치하지 말고
  제자리에서 버텨라

contact_switch_penalty
- 발 접촉 상태가 매 step 바뀌는 것을 직접 불리하게 만듦
- 불필요한 stepping / re-stepping을 막는 행동 제약

contact_foot_velocity_penalty
- 접지 중인 발의 XY 속도를 직접 불리하게 만듦
- 붙인 발을 끌고 가거나 미끄러뜨리는 전략을 막음

action_rate_l2
- 발을 마구 흔드는 전략이 standing reward와 경쟁할 만큼 비용을 가져야 한다
- B1에서는 -0.01이 너무 약해, stand-only 과제 기준으로 -0.5까지 강화한다
```

### 7.3.1 B1.1 근본 보정

`B1` 첫안의 핵심 문제는 결과 지표 중심이었다.

```text
- standing_height / feet_on_ground / stationary는 "결과"를 본다
- 하지만 "발을 떼지 말라", "붙인 발을 미끄러뜨리지 말라"는 행동 제약이 없었다
- 그래서 policy는 발 재배치로 버티는 느린 걷기 해를 계속 찾았다
```

그래서 `B1.1`에서는 reward를 많이 늘리지 않고, 행동 제약 2개만 추가한다.

```text
1. contact_switch_penalty
2. contact_foot_velocity_penalty
```

즉 `서기`를 이제 이렇게 정의한다.

```text
높고 수평하고 4발이 닿아 있을 뿐 아니라,
붙인 발은 가능하면 유지하고,
정말 필요할 때만 발을 떼며,
붙인 발은 미끄러뜨리지 않는다.
```

### 7.3.2 B1.2 FK 기반 초기 자세 보정

`B1.1` 이후에도 남은 핵심 문제는 초기 자세 그 자체였다.

```text
- joint 값은 숫자상 대칭처럼 보였지만
- 실제 URDF 축/원점을 반영한 toe FK는 좌우/높이/지지중심이 비대칭이었다
- policy는 학습 전에 이미 한쪽으로 기우는 planted-stand bias를 안고 시작했다
```

그래서 `B1.2`에서는 두 가지만 바꾼다.

```text
1. init pose를 분석팀 FK 교정값으로 변경
   -> support center를 body 중심에 가깝게 맞춤
   -> toe 좌우/높이 대칭 확보

2. joint_vel_l2 완화 (-0.5 -> -0.1)
   -> planted-stand regularizer는 유지하되
      탐색 자체를 질식시키지는 않게 함
```

주의:

```text
기존 stance_width_penalty는 "너무 넓음"만 벌하는 max-width penalty다.
현재 문제인 "너무 좁음"을 해결하지 못하므로 B1에서는 제거했다.
minimum support width가 필요하면 별도 min-width penalty를 새로 설계해야 한다.
```

### 7.3.3 B1.3 reset warmup

`B1.2` 이후에도 실제 런에서는 이런 패턴이 남았다.

```text
- reward와 init pose는 정리됐지만
- reset 직후 policy action이 바로 크게 들어간다
- planted stand를 시도하기 전에 관절/몸통이 크게 흔들리며 무너진다
```

실측 근거:

```text
2026-04-02_21-15-40 step 29
mean_episode_length            54.89
bad_orientation                1.000000
action_rate_l2                -1.352670
joint_vel_l2                  -5.494754
ang_vel_xy_l2                 -1.054588
stationary_reward              0.002715
```

즉 현재 병목은 "가만히 서는 reward가 부족하다" 이전에
`reset 직후 planted stand를 물리적으로 정착시킬 시간 없이 바로 크게 움직인다`는 점이다.

그래서 `B1.3`에서는 reward를 더 늘리지 않고,
reset 직후 짧은 action warmup만 넣는다.

```text
action_warmup_steps = 8
step_dt = 0.02s
warmup duration ≈ 0.16s
```

구현 의미:

```text
- reset 후 첫 8 step 동안 policy action을 0으로 clamp
- planted stand/contact settle 상태를 먼저 경험하게 함
- reward는 그대로 포함
  -> "가만히 서 있는 상태" 자체가 positive example이 되게 함
```

왜 8 step인가:

```text
- 너무 길면 학습이 비게 됨
- 너무 짧으면 contact settle 효과가 약함
- 현재 mean_episode_length ~55 step 수준에서
  8 step(0.16s)은 초기 planted settle에는 충분하고 과하지 않은 길이
```

### 7.3.4 각 reward의 역할 구분

`B1.1`에서는 reward를 세 층으로 본다.

```text
Primary
- standing_height
- feet_on_ground
- stationary_reward
- contact_switch_penalty
- contact_foot_velocity_penalty

Secondary
- flat_orientation_l2
- base_height_l2
- ang_vel_xy_l2
- lin_vel_z_l2

Regularizer
- action_rate_l2
- joint_vel_l2
- dof_acc_l2
- undesired_contacts
- alive_bonus
```

의미:

```text
Primary는 "서기의 본질"을 직접 정의한다.
Secondary는 몸 상태를 정리한다.
Regularizer는 과격한 해를 줄이되 주연이 되지 않는다.
```

### 7.3.5 기대되는 로그 변화

`B1.2`가 맞다면 TensorBoard에서 먼저 보여야 하는 건 다음이다.

```text
1. contact_switch_penalty magnitude 감소
   -> 발 접촉 상태 변화가 줄어듦

2. contact_foot_velocity_penalty magnitude 감소
   -> 접지 중 발 끌기/미끄럼이 줄어듦

3. stationary_reward 증가
   -> 몸이 제자리에서 더 오래 머묾

4. feet_on_ground 유지 또는 증가
   -> 4발 지지 유지

5. bad_orientation 감소
   -> planted support가 실제로 안정성을 만듦

6. joint_vel_l2 magnitude 감소
   -> 실제 관절 움직임 자체가 줄어듦
```

즉 `B1.2`의 첫 성공 신호는
`standing_height`가 아니라
`발 재배치와 접지 중 foot motion이 줄어드는 것`
이어야 한다.

### 7.3.6 기대되는 영상 변화

영상에서는 다음 차이가 보여야 한다.

```text
이전 B1:
- 발을 자주 떼고 다시 디딤
- 제자리에서 작은 느린 걷기처럼 버팀
- 붙인 발을 끌고 가는 느낌

B1.1 기대:
- 발을 먼저 붙인 채 버티려 함
- 필요 없는 stepping이 줄어듦
- 접지 중 발이 덜 미끄러짐
- 몸통 흔들림을 관절로 더 흡수하려고 함

B1.2 추가 기대:
- reset 직후 이미 한쪽으로 말려 있는 bias가 줄어듦
- planted stand 시도 전에 좌우 비대칭으로 튀는 현상이 줄어듦
- 앞/뒤 발끝 위치가 실제 공간에서 더 대칭적으로 시작됨
```

lin_vel_z / ang_vel_xy / flat_orientation
- 튀거나 기울지 말고 정적으로 버텨라

### 7.4 일부러 넣지 않은 것

`B1`에서 일부러 안 넣는 것:

```text
- phase_contact / phase_clearance
- track_lin_vel_xy_exp / track_ang_vel_z_exp
- foot_clearance / leg_lift / trot_gait
- gait_gate / phase_table / release ramp
- 다리별 heuristic ecology
```

즉 `B1`은:

```text
걷기 구조를 배우는 단계가 아니라
정적 지지 제어를 배우는 단계
```

이다.

---

## 8. 성공 기준

`B1`의 첫 성공 기준은 "안넘어진다"보다 더 구체적이어야 한다.

### 8.1 Boot viability

iter 100~300:

```text
- bad_orientation 1.0 고착 아님
- ep_len 증가 추세
- standing_height / feet_on_ground / stationary가 0에 고착되지 않음
- contact_switch_penalty가 초기보다 줄어듦
- contact_foot_velocity_penalty가 초기보다 줄어듦
```

### 8.2 Stand quality

iter 300~800:

```text
- time_out 유의미하게 발생
- 몸 높이를 유지
- 수평 유지
- 4발 접지 유지
- 발을 계속 떼지 않음
- 접지 중 발을 끌지 않음
```

### 8.3 영상 기준

필수:

```text
- 발을 붙인 상태로 먼저 버티려 함
- 발을 계속 재배치하며 버티지 않음
- 앞발을 몸 안쪽으로 과하게 모으지 않음
- 앞으로 밀리거나 옆으로 비틀리며 쓰러지지 않음
```

기각:

```text
수치가 조금 좋아도
영상상 "서기"가 아니라 "느린 걷기/헛디딤"처럼 보이면 실패
```

---

## 9. 실패 해석

`B1` 실패의 의미는 명확하다.

```text
clean stack + symmetric reset + stand-only command만으로는
SpotMicro가 planted stand를 배우기에 아직 부족하다.
```

하지만 이것도 가치가 있다.

```text
걷기 이전에
무엇이 정말 부족한지
stance / support 관점에서 분리해서 볼 수 있기 때문이다.
```

즉 실패해도:

```text
다시 77개 ecology로 회귀하지 않고
"정적 지지 제어에 무엇이 필요한가"만 좁혀서 볼 수 있다.
```

---

## 10. 구현 상태

현재 구현 상태 (2026-04-03 업데이트):

```text
TRAIN_VERSION              = V57.B1
decimation                 = 4 (50Hz)
standing envs              = 100%
lin_vel_x range            = (0.0, 0.0)
lin_vel_y range            = (0.0, 0.0)
ang_vel_z range            = (0.0, 0.0)
legacy gait_gate           = OFF
legacy phase_table         = OFF
reward curriculum          = OFF
phase observation          = OFF
only_positive_rewards      = OFF

[Actuator — 2026-04-03 전환]
actuator type              = ImplicitActuatorCfg (DCMotorCfg에서 전환)
effort_limit               = 15.0
stiffness                  = shoulder=12, leg=28, foot=8
damping                    = shoulder=4, leg=5, foot=2

[Physical Setup — 2026-04-03 디버깅 결과]
init_z                     = 0.185
init_pose                  = leg=-0.70, foot=1.32 (Z자형)
URDF velocity              = 20.0
max_depenetration_velocity = 0.2

[Rewards]
alive_bonus                = ON (+1.0)
standing_height            = ON (+5.0, target=0.18)
feet_on_ground             = ON (+2.0)
stationary_reward          = ON (+1.0)
base_height_l2             = ON (-1.5, target=0.18)
action_rate_l2             = -0.5
reset joint randomization  = OFF
```

따라서 다음 검증은:

```text
1. symmetric reset + stand-only command에서 planted stand가 가능한지 확인
2. boot viability (iter 100~300) 먼저 확인
3. 발을 붙인 정적 지지가 나오면 그 다음에 locomotion으로 넘어감
```

---

## 11. 바로 다음 작업

`V57.B1` 실행 후 바로 해야 할 것:

```text
1. fresh start
2. boot viability 검증
3. episode scalar + 영상 mechanics 함께 확인
4. "발을 붙인 채 버티는가"를 최우선 기준으로 판정
```

### 11.1 Zero-Action Stand 검증

`B1.3` 이후의 최우선 분기 질문은 이것이다.

```text
FK 교정된 기본 자세가 action 없이도 물리적으로 서 있는가?
```

이 질문에 답하기 위해 전용 진단 스크립트를 추가했다.

파일:

```text
scripts/utils/zero_stand_probe.py
```

목적:

```text
1. policy action 없이(default pose 유지)
2. zero action만 계속 보내며
3. drift / orientation / contact를 직접 측정
```

기본 실행 예:

```text
C:\IsaacLab\isaaclab.bat -p scripts/utils/zero_stand_probe.py --task Isaac-Velocity-Flat-SpotMicro-v0 --num_envs 64 --steps 300
```

로그 파일까지 남기려면:

```text
C:\IsaacLab\isaaclab.bat -p scripts/utils/zero_stand_probe.py --task Isaac-Velocity-Flat-SpotMicro-v0 --num_envs 64 --steps 300 --log_file logs/diagnostics/zero_probe_latest.log
```

`--log_file`를 주지 않으면 기본으로 아래 경로에 저장된다.

```text
logs/diagnostics/zero_stand_probe_<timestamp>.log
```

### 11.3 Standing Pose Sweep

zero-action probe에서 `step 1 toe_contact_mean = 0.0000`이 나오면,
다음 1순위는 reward 수정이 아니라 `init z` 스윕이다.

추가 스크립트:

```text
scripts/utils/standing_pose_sweep.py
```

목적:

```text
1. base init z 후보를 여러 개 시도
2. 각 후보에서 zero-action step 1 / step N의
   - toe_contact
   - height
   - drift
   - termination
   를 바로 비교
3. 실제로 발이 닿는 planted pose 후보를 먼저 찾음
```

실행 예:

```text
C:\IsaacLab\isaaclab.bat -p scripts/utils/standing_pose_sweep.py --task Isaac-Velocity-Flat-SpotMicro-v0 --steps 20 --log_file logs/diagnostics/standing_pose_sweep_latest.log
```

편의 실행:

```text
scripts\standing_pose_sweep.cmd
```

기본값:

```text
--task Isaac-Velocity-Flat-SpotMicro-v0
--steps 20
--log_file logs/diagnostics/standing_pose_sweep_latest.log
```

추가 인자를 직접 넘길 수도 있다.

```text
scripts\standing_pose_sweep.cmd --task Isaac-Velocity-Flat-SpotMicro-v0 --steps 40 --z_values 0.15 0.155 0.16 0.165
```

판정:

```text
좋은 후보:
- step 1 toe_contact_mean이 높음
- drift_xy_mean이 낮음
- step 20까지 terminated_frac가 낮음

나쁜 후보:
- step 1 toe_contact_mean이 거의 0
- 바로 drift/vel이 커짐
- step 20 이전부터 termination이 빠르게 증가
```

실측 결과 (`standing_pose_sweep_latest.log`):

```text
z=0.150
- drift_xy_mean   0.2216
- vel_xy_mean     0.7922
- ang_xy_mean     1.0434
- height_mean     0.1572
- toe_contact     0.1344
- terminated      0.0000
```

비교 결론:

```text
- 현재 후보 중 z=0.150이 최선
- step 20 기준 toe_contact가 가장 높고
- height가 가장 높고
- ang_xy가 가장 낮다
```

따라서 `SPOT_MICRO_CFG.init_state.pos.z`는

```text
0.19 -> 0.15
```

로 조정한다.

주의:

```text
z=0.150도 아직 완전한 정적 서기는 아니다.
하지만 현 후보군에서는 가장 좋은 planted-stand 시작점이다.
다음 판정은 이 값으로 zero-action probe를 다시 돌려서 한다.
```

### 11.4 Standing Joint Sweep

`z=0.150`으로 zero-action 생존 시간은 크게 개선됐다.
하지만 여전히:

```text
- toe_contact_mean이 낮다
- drift_xy가 계속 커진다
- semi-stable pose에 가깝다
```

그래서 다음 단계는 `z`가 아니라 `leg / foot` 미세 조정이다.

추가 스크립트:

```text
scripts/utils/standing_joint_sweep.py
scripts/standing_joint_sweep.cmd
```

목적:

```text
1. base_z=0.150 고정
2. front_leg / rear_leg / foot 후보를 좁은 범위로 스윕
3. step 1 / step N에서
   - toe_contact
   - drift
   - vel
   - ang_xy
   - height
   를 비교
4. 가장 planted-stand에 가까운 각도 조합을 고른다
```

기본 실행:

```text
scripts\standing_joint_sweep.cmd
```

기본 로그:

```text
logs/diagnostics/standing_joint_sweep_latest.log
```

현재 기본 스윕 범위는 "더 펴는 쪽"까지 포함한다.

```text
front_leg: -0.74, -0.70, -0.66, -0.62
rear_leg:  -0.72, -0.68, -0.64, -0.60
foot:       1.38,  1.44,  1.50,  1.56
```

또한 로그 끝에 상위 후보를 자동 정렬해서 출력한다.

정렬 기준:

```text
1. toe_contact_mean 높을수록 우선
2. terminated_frac 낮을수록 우선
3. drift_xy_mean 낮을수록 우선
4. ang_xy_mean 낮을수록 우선
5. height_mean 높을수록 우선
```

이 스크립트가 출력하는 핵심 값:

```text
- drift_xy_mean / max
- vel_xy_mean / max
- ang_xy_mean / max
- grav_xy_mean / max
- height_mean / min
- toe_contact_mean / min
- terminated_frac / time_out_frac
```

해석:

```text
zero-action에서도 drift_xy, ang_xy, terminated_frac가 빠르게 커지면
-> reward 문제가 아니라 default pose / contact physics / plant model 문제

zero-action에서는 안정인데 policy를 넣자마자 무너지면
-> reward / action / command 설계 문제
```

### 11.2 Zero-Action Probe 오염 원인과 수정

첫 zero-action probe는 그대로 해석하면 안 된다.

실제 확인 결과, `V57.B1`에도 parent locomotion cfg의 아래 이벤트가 남아 있었다.

```text
- physics_material (startup)
- add_base_mass (startup)
- base_com (startup)
- reset_base (reset)
- base_external_force_torque (reset)
```

특히 `reset_base` 기본값은 아래 범위다.

```text
pose_range:
- x:   (-0.5, 0.5)
- y:   (-0.5, 0.5)
- yaw: (-3.14, 3.14)

velocity_range:
- x/y/z:         (-0.5, 0.5)
- roll/pitch/yaw:(-0.5, 0.5)
```

즉 이 상태의 probe는
`정지 자세가 서는가`가 아니라
`랜덤 root pose + 랜덤 root velocity에서 action=0으로 버티는가`
를 보고 있었다.

drift 계산도 잘못되어 있었다.

기존 probe:

```python
drift_xy = root_pos_w[:, :2] - env.scene.env_origins[:, :2]
```

이 값은 reset 직후 root의 초기 offset까지 포함한다.
그래서 `step 1 drift_xy_mean≈0.386`은 실제 이동이 아니라
reset_base가 준 초기 위치 오프셋이 섞인 값일 가능성이 크다.

수정 내용:

```text
1. V57.B1에서는 아래 이벤트를 끈다.
   - physics_material
   - add_base_mass
   - base_com
   - reset_base
   - base_external_force_torque

2. zero_stand_probe는 drift를
   "reset 직후 root pose" 기준으로 계산한다.
```

따라서 이제부터의 zero-action probe만
`기본 planted pose가 정말 정적으로 서는가`
에 대한 정식 판정으로 사용한다.

---

## 12. Zero-Action Stand 디버깅 결과 (2026-04-03)

> 상세 로그: `plan/V57_ZERO_STAND_DEBUG.md` (20개 테스트, 시간순)

### 12.1 발견된 근본 원인 3개

```text
원인 1: init_z에 toe collision sphere radius(0.02m) 미포함
- FK는 toe link center까지만 계산 (0.1937m)
- sphere 바닥이 지면 아래 20mm → PhysX depenetration impulse
- 수정: init_z = 0.185 (loaded eq 근처, 4mm 관통 + 느린 depenetration)

원인 2: URDF velocity(10) = DCMotor velocity_limit(10) → bang-bang 진동
- PhysX가 관절속도를 10 rad/s에서 하드 클램프
- DCMotor: vel=vel_limit일 때 한쪽 방향 토크만 가능
- 저관성 foot 관절이 1 substep(5ms)에 velocity_limit 도달
- 수정: URDF velocity=20, DCMotor velocity_limit=20

원인 3: DCMotor velocity-dependent saturation이 standing의 구조적 병목 ★★★
- DCMotor의 torque = saturation × (1 - vel/vel_limit)이
  관절이 움직일 때 가용 토크를 줄여서 정적 평형으로 수렴 불가
- 증거: 동일 gain/pose에서 actuator만 교체
  DCMotor → height 0.10 (귀뚜라미)
  ImplicitActuator → height 0.144 (완벽 정지!)
- effort_limit=15를 걸어도 결과 동일 (정적 토크 최대 5.9 Nm < 15)
- 수정: ImplicitActuatorCfg 전환 (PhysX 연속시간 PD)
```

### 12.2 최종 물리 설정

```text
actuator          = ImplicitActuatorCfg (DCMotorCfg에서 전환)
effort_limit      = 15.0 (토크 제한 유지, 현실성 보존)
stiffness         = shoulder=12, leg=28, foot=8 (관절별 차등)
damping           = shoulder=4, leg=5, foot=2 (관절별 차등)
init_z            = 0.185 (loaded eq 근처 시작)
URDF velocity     = 20.0 (PhysX vel clamp 여유)
max_depenetration = 0.2 (부드러운 착지)
init pose         = leg=-0.70, foot=1.32 (Z자형 유지)
```

### 12.3 zero-action standing 결과

```text
step=50:  height=0.1440, vel_xy=0.0002, ang_xy=0.11, terminated=0%
step=100: height=0.1441, vel_xy=0.0006, terminated=0%
step=200: height=0.1441, 소수점 4자리 고정
step=300: height=0.1441, 완벽 정지
step=500: episode timeout → reset → step=550: height=0.1441 (복귀!)
```

GUI 확인: "잘 서있다가 살짝 내려앉은 상태에서 주욱 끝남"
= init height(0.185) → loaded equilibrium(0.144) → 영구 안정.
4cm 하강은 중력 하 관절 압축 (자동차 서스펜션과 동일 원리).

### 12.4 env_cfg 수정사항

```text
standing_height target_height: 0.22 → 0.18
base_height_l2 target_height:  0.22 → 0.18
(loaded equilibrium 0.144 위의 도달 가능한 목표)
```

---

## 13. 최종 추천

바로 실행할 다음 1순위는 `V57.B1` fresh start 검증이다.

현재 상태:

```text
- zero-action standing 달성 (ImplicitActuator + effort_limit=15)
- 물리 기반 안정화 완료 (bang-bang 해결, toe 관통 해결, actuator 전환)
- env_cfg target_height 조정 완료
- 로봇이 죽지 않는 안정적 기반 확보
```

한 줄 요약:

`V57.B1은 ImplicitActuator 전환으로 zero-action standing을 달성했다. 이제 이 안정적 물리 기반 위에서 planted stand RL 학습을 시작한다.`

---

## 14. V57.B1 RL 학습 결과 및 V58 전환 (2026-04-03)

### 14.1 V57.B1 RL 학습 실패

zero-action standing은 성공했으나, **RL 학습은 die-fast로 실패.**

```text
IdealPDActuator + stand-only(14개 reward) → per-step reward 음수 → ep_len=1 고착

die-fast 원인: penalty가 Isaac Lab 표준 대비 10~50배 과다
- joint_vel_l2(-0.1): die-fast의 61% 지배 (Isaac Lab 표준에 없음)
- ang_vel_xy_l2(-0.5): 표준(-0.05)의 10배
- action_rate_l2(-0.5): 표준(-0.01)의 50배
- flat_orientation_l2(-2.0): 표준은 0.0 (비활성)

추가 시도:
- bad_orientation 0.5→0.7→1.0 조정
- action_scale 1.0→0.25 조정
- min_height 0.10→0.12 조정
→ 모두 근본 해결 안 됨 (reward 구조 자체가 문제)
```

### 14.2 핵심 깨달음

```text
1. 물리가 정상이면 표준 구조가 작동한다
2. 77개 heuristic보다 Isaac Lab 표준 10개 reward가 낫다
3. stand-first보다 velocity tracking이 더 자연스러운 학습 경로
4. penalty는 Isaac Lab 표준 수준으로 유지해야 die-fast 방지
```

### 14.3 V58 전환 결정

```text
V57의 성과: 물리 디버깅 (actuator, init_z, velocity_limit, depenetration)
V57의 한계: stand-only reward 구조로는 RL 학습 불가

→ V58: Isaac Lab 표준 locomotion으로 전환
   - ImplicitActuator + 표준 10개 reward
   - velocity tracking 주연
   - standing 50% + locomotion 50%
   - 상세: plan/V58_PLAN.md
```


---

# 부록 A: V57 연구 노트 (V57_RESEARCH)

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


---

# 부록 B: V57 zero-stand 디버그 로그

# V57 Zero-Action Stand Debug Log

## 날짜: 2026-04-03


## 목표
SpotMicro가 zero-action(action=0)으로 서 있을 수 있는지 확인한다.
4족 로봇은 support polygon 안에 CoM이 있으면 테이블처럼 수동적으로 서 있을 수 있어야 하며,
서 있지 못할 경우 물리 설정에 문제가 있는 것으로 판단한다.

---

## 배경
- V57.B1: stand-first bootstrap (걷기 전에 서기부터)
- 이전 세션에서 FK calibration + 대칭 init pose 완성
- init_z=0.194, stiffness=16, damping=2, effort_limit=15
- zero_stand_probe로 테스트한 결과 로봇이 서 있지 못하여, 본 디버깅 세션 개시

---

## 테스트 환경
- `scripts/utils/zero_stand_probe.py`: action=0을 매 step 전송하고 joint/torque/contact 기록
- headless 모드 (`cmd.exe /c` 통해 WSL→Windows 실행)
- 16 envs, Isaac Lab + PhysX, decimation=4 (50Hz), step_dt=0.02s
- DCMotor actuator: `target = raw_action * scale + offset`
  - scale=1.0, offset=default_joint_pos=init_pos (확인 완료)
  - action=0 → target = init_pos

---

## 시간순 테스트 기록

### Test 1: 기존 설정 확인 (init_z=0.194, Kp=16, Kd=2, effort=15)

**가설**: 이전 세션에서 실패했던 설정 재확인

**로그**: `logs/diagnostics/zero_probe_latest.log`

**결과**:
```
step=1:   height=0.2030 (init 0.194에서 상승), ang_xy=3.79, toe_fz=ALL 0.0
step=10:  rear_left_leg=-1.37 (init -0.70), rear_right_leg=-2.17 (폭주)
step=50:  terminated=6.25%, height=0.108
step=90:  terminated=50%, height=0.104
step=100: terminated=44%, height=0.108, mean_ep_len=15
```

**관찰**:
1. Step 1에서 height가 0.194→0.203으로 **상승** (9mm) — 상향 반발력 발생
2. 후방 다리 토크 step 1부터 포화:
   - rear_left_foot_torque=-15.0 (포화)
   - rear_right_foot_torque=-15.0 (포화)
   - rear_right_leg_torque=15.0 (포화)
3. 전방 다리는 상대적으로 안정, 후방이 먼저 붕괴
4. **모든 개별 toe_fz = 0.0** (하지만 toe_contact_mean=0.0476 > 0)
5. 비대칭: 후방 > 전방, 우측 > 좌측 순으로 불안정

**초기 분석**:
- height 상승 → 지면에서 밀어올림 → toe sphere가 지면에 관통된 것으로 추정
- toe_fz=0인데 toe_contact_mean>0 → 센서 인덱싱 문제 의심

---

### URDF 질량 분석

robot.py, URDF 확인:

**총 질량 5.30 kg**:
- base_link: 2.80 kg
- lidar_link: 0.50 kg (base 위, z+0.035)
- rear_link: 0.20 kg (base 뒤)
- front_link: 0.20 kg (base 앞)
- 다리 × 4: shoulder 0.10 + leg 0.15 + foot 0.10 + toe 0.05 = 0.40 kg/leg = 1.60 kg

**merge_fixed_joints 후 base 합성 질량**: 2.80 + 0.50 + 0.20 + 0.20 = 3.70 kg
**다리당 지지 하중**: 5.30/4 = 1.325 kg = ~13 N

**정적 torque 추정**:
- 다리당 13 N × lever arm (~0.05m max) = ~0.65 Nm
- effort_limit 15 Nm 대비 4.3% → **정적으로는 충분**

---

### 핵심 발견: toe sphere 지면 관통

**FK 계산**:
- toe link center: body_z - 0.1937m below
- init_z=0.194 → toe link center z = 0.194 - 0.1937 = 0.0003m (지면 위 0.3mm)

**URDF toe collision**: sphere radius = 0.02m
- sphere 바닥 = 0.0003 - 0.02 = **-0.0197m (지면 아래 20mm)**

**이것이 step 1 height 상승의 원인으로 확인됨.**
- PhysX가 관통 해소하며 로봇을 위로 밀어올림
- max_depenetration_velocity=1.0 제한이 있지만 impulse 발생

---

### Test 2: effort_limit=50 (토크 포화 가설 검증)

**가설**: 후방 다리 토크가 15 Nm에서 포화되어 position hold 실패. effort를 올리면 해결되는지 확인.

**변경**: saturation_effort=50, effort_limit=50 (나머지 동일)

**로그**: `logs/diagnostics/zero_probe_effort50.log`

**결과**:
```
step=1:  rear_left_foot_torque=-19.91 (이전 -15.0), rear_right_foot=-15.65
step=10: 다수 관절 20-25 Nm, rear_right_leg=25.96
step=50: terminated=37.5% (이전 6.25% 대비 6배 악화)
step=70: terminated=68.8%
```

**결론**: **토크 포화가 원인이 아닌 것으로 판명.** 높은 토크 → 높은 반발 에너지 → 심한 진동 → 조기 종료.

**원복**: effort=15로 복원

---

### Test 3: init_z=0.22 (toe sphere clearance 확보)

**가설**: 20mm 관통이 문제. init_z를 올려서 toe sphere가 지면 위에 있게 하면 해결되는지 확인.

**변경**: init_z=0.22 (sphere 바닥 = 0.22 - 0.194 - 0.02 = +0.006m, 6mm 여유)

**로그**: `logs/diagnostics/zero_probe_z022.log`

**결과**:
```
step=1:  height=0.203 (0.22에서 17mm 하락), ang_xy=?? (이전 로그에서 미기록)
step=50: terminated=0% (개선)
step=80: terminated=50%
step=100: terminated=31%
```

**관찰**:
- 50 step까지 생존 (이전 6.25% → 0%) — 관통 제거 효과 확인
- 그러나 이후 불안정해짐
- RL_toe만 간헐적 접촉 (fz=9.96 at step 30), FL/FR/RR = 0 지속

---

### Test 4: stiffness=40, damping=5, effort=25 (강한 PD)

**가설**: PD가 너무 약해서 position hold 실패. 더 강한 PD로 해결 가능한지 확인.

**변경**: Kp=40, Kd=5, effort=25, init_z=0.22

**로그**: `logs/diagnostics/zero_probe_strong_pd.log`

**결과**:
```
step=1:  height=0.203, 대부분 토크 포화 (±25)
step=20: many joints at ±25 Nm saturated, rear legs to -2.2
step=50: terminated=6.25% → step=90: 56%
```

**결론**: 강한 spring이 접촉 impulse를 증폭. 강한 PD가 안정성을 향상시키지 않는 것으로 확인됨.

---

### Test 5: fix_base=True (body 고정, 다리만 테스트)

**가설**: body 움직임을 제거하고 다리 PD만 고립 테스트

**변경**: fix_base=True, Kp=16, Kd=2, effort=15, init_z=0.22

**로그**: `logs/diagnostics/zero_probe_fixbase.log`

**결과 (200 steps, terminated=0% 전체)**:
```
step=1:
  FL_shoulder=-0.032, FL_leg=-0.734, FL_foot=1.381
  FL_shoulder_torque=1.05, FL_leg_torque=6.55, FL_foot_torque=6.48

step=10:
  FL_foot=1.510, FL_foot_torque=15.0 (포화)
  FL_leg=-0.829, FL_leg_torque=10.69

step=100:
  FL_foot=1.528, FL_foot_torque=15.0 (여전히 포화)
  FL_leg=-0.889, FL_leg_torque=12.11
  FL_shoulder=+0.046 (init -0.04에서 부호 반전)

step=160:
  FL_foot=1.528, FL_foot_torque=15.0
  FL_leg=-0.922, FL_leg_torque=12.56
```

**핵심 발견**:
1. **완벽 대칭**: 4다리 모두 동일한 joint angle/torque (L/R 부호만 반대)
2. **Foot torque = +15.0 (포화)** — 모든 4다리, step 10부터 끝까지
3. **Leg이 느리게 드리프트**: -0.70 → -0.92 (200 steps에 걸쳐)
4. **Foot도 드리프트**: 1.32 → 1.528 (step 10 이후 정체)
5. **Shoulder 부호 반전**: init FL=-0.04 → +0.046

**수치 검증 (핵심 미해결 사항)**:

Foot at step 100: current=1.528, target=1.32 (offset 확인됨)
- PD torque = 16 × (1.32 - 1.528) = 16 × (-0.208) = **-3.33 Nm**
- Velocity ≈ 0 (quasi-static) → damping ≈ 0
- 예상 total = **-3.33 Nm**
- **실제 reported = +15.0 Nm** ← 부호 반대, 크기 4.5배

Gravity torque on foot (no ground contact, free hanging):
- distal mass = foot(0.10) + toe(0.05) = 0.15 kg
- lever arm ≈ 0.038m (combined CoM)
- gravity torque = 0.15 × 9.81 × 0.038 = **0.056 Nm**
- **0.056 Nm vs reported 15 Nm → 268배 차이**

---

### Debug: action offset 확인

probe에 debug 출력 추가하여 실제 offset/scale 확인:

**로그**: `logs/diagnostics/zero_probe_debug.log`

```
[DEBUG] joint_names=['front_left_shoulder', 'front_right_shoulder', 'rear_left_shoulder', 'rear_right_shoulder', 'front_left_leg', 'front_right_leg', 'rear_left_leg', 'rear_right_leg', 'front_left_foot', 'front_right_foot', 'rear_left_foot', 'rear_right_foot']
[DEBUG] default_joint_pos=['-0.0400', '0.0400', '-0.0400', '0.0400', '-0.7000', '-0.7000', '-0.7000', '-0.7000', '1.3200', '1.3200', '1.3200', '1.3200']
[DEBUG] action_term=joint_pos offset=['-0.0400', '0.0400', '-0.0400', '0.0400', '-0.7000', '-0.7000', '-0.7000', '-0.7000', '1.3200', '1.3200', '1.3200', '1.3200']
[DEBUG] action_term=joint_pos scale=1.0
```

**확인 결과**: default_joint_pos = init_pos, offset = init_pos. action=0 → target = init_pos **정상 확인.**

그럼에도 foot torque가 +15.0 (target 방향과 반대)으로 보고됨.

---

### Test 6: damping=10, effort=15, init_z=0.22 (강한 감쇠)

**가설**: 높은 damping으로 진동 억제. 느리지만 안정적인지 확인.

**변경**: Kd=10 (나머지 동일, fix_base=False)

**로그**: `logs/diagnostics/zero_probe_highdamp.log`

**결과 (terminated=0% through 140 steps)**:
```
step=1:   height=0.227, FL_leg=-0.641 (init -0.70에서 +0.06 이동)
step=10:  rear_left_leg=-1.748, rear_right_leg=-1.695
step=50:  height=0.090, all legs deeply bent
step=100: height=0.076, legs at -2.5 (joint limit 근처)
step=140: height=0.073, terminated=0%
```

**관찰**:
1. **terminated = 0%** — 감쇠가 진동 억제에 효과적
2. 그러나 **서서히 주저앉음** (height 0.22 → 0.07)
3. 다리가 극단값으로 드리프트 (leg: -0.70 → -2.5)
4. **PD가 중력을 이기지 못함** — effort_limit 내에서도 position hold 실패

---

### Test 7: stiffness=50, damping=10, effort=50, init_z=0.214 (과잉 강화)

**가설**: 모든 파라미터를 극단적으로 올리면 물리적으로 서 있을 수 있는가.

**변경**: Kp=50, Kd=10, effort=50, init_z=0.214

**로그**: `logs/diagnostics/zero_probe_overpowered.log`

**결과**:
```
step=1:  FL_leg=-0.522 (init -0.70에서 +0.18), height=0.222 (상승)
         foot_torque=50.0 (ALL saturated), leg_torque=-34 to -37
step=10: height=0.252 (추가 상승), 거의 모든 관절 ±50 포화
step=20: terminated=75%
step=30: terminated=100%
```

**결론**: 강한 PD가 착지 impulse를 증폭하여 로봇이 튕겨나감. 전 테스트 중 최악의 결과.

---

### Test 8: init_z=0.214, Kp=16, Kd=5, effort=15 (최종 조합)

**가설**: 올바른 init_z + 튜닝된 PD 파라미터 조합

**변경**: init_z=0.214, Kp=16, Kd=5, effort=15

**로그**: `logs/diagnostics/zero_probe_final.log`

**결과 (테스트 시점 최고 성능)**:
```
step=1:   height=0.222, ang_xy=3.69, 토크 8-15 범위
step=10:  여러 관절 ±15 포화, rear legs 벌어짐
step=50:  terminated=0%, height=0.102
step=80:  terminated=6.25%, ep_len=71
step=100: terminated=6.25%, ep_len=79
step=150: terminated=37.5%
step=190: terminated=31%, ep_len=71
```

**비교표**:

| 설정 | Step 50 term | Step 100 term | Step 100 ep_len |
|------|-------------|--------------|-----------------|
| z=0.194, Kd=2 (원래) | 6.25% | 44% | 15 |
| z=0.22, Kd=2 | 0% | 31% | 24 |
| z=0.22, Kd=10 | 0% | 0% (collapse) | 100 |
| z=0.214, Kd=5 | **0%** | **6.25%** | **79** |
| effort=50 | 37.5% | - | - |
| Kp=40, Kd=5 | 6.25% | 56% | - |
| Kp=50, Kd=10, E=50 | 75%@s20 | - | - |

---

## 미해결 문제

### 1. fix_base torque 불일치 (최우선)

**현상**: body 고정, 다리만 자유, 지면 접촉 없음
- PD target = 1.32 (확인됨)
- foot current = 1.528
- 예상 PD torque = **-3.33 Nm**
- 실제 reported torque = **+15.0 Nm**
- 부호 반대 + 크기 4.5배

**가설**:
1. `robot.data.applied_torque`가 DCMotor output이 아닌 다른 값일 가능성
2. DCMotor 내부에서 예상과 다른 계산 수행 (joint_vel_target이 0이 아닐 수 있음)
3. PhysX joint drive가 stiffness=0에도 불구하고 자체 힘을 가할 가능성
4. 부호 convention: URDF joint axis 방향 vs torque 보고 방향 차이
5. `applied_torque`가 actuator effort가 아닌 PhysX net joint torque일 가능성

**검증 방법**:
- DCMotor의 `computed_effort` vs `applied_effort` 직접 읽기
- `robot.data.joint_pos_target` 확인
- 1-joint 단순 모델로 DCMotor 동작 검증
- Isaac Lab 소스의 applied_torque 할당 코드 추적

### 2. 비대칭 붕괴 패턴

**현상**: fix_base=False에서 항상 rear_right가 먼저 붕괴
- fix_base=True에서는 **완벽 대칭** → URDF/PD 자체는 대칭
- 초기 조건 차이 또는 수치 noise 가능성
- base_rotate (180deg yaw)의 영향 가능성

### 3. toe 접촉 센서 인덱싱

**현상**: `toe_contact_mean > 0`인데 개별 `FL/FR/RL/RR_toe_fz = 0.0`
- scene contact sensor: `prim_path="{ENV_REGEX_NS}/Robot/.*"` (모든 body 추적)
- merge_fixed_joints=True → toe_link가 foot_link에 병합
- probe가 `net_forces_w[:, :, 2]`의 index 0-3을 FL/FR/RL/RR로 가정
- 실제로는 다른 body일 가능성 (base_link=0, shoulder=1, ...)

**검증 방법**:
- contact sensor의 body_names 목록 출력
- 올바른 index로 toe force 읽기

---

## 추가 테스트 (torque 불일치 심층 조사)

### Test 9: PD internals 출력 + fix_base
probe에 computed_torque, joint_pos_target, joint_vel 등 내부 상태 출력 추가.

```
Step 1:  foot=1.378, vel=+0.32, computed=-11.77  (정상)
Step 10: foot=1.499, vel=+10.0(!), computed=+45.57  (bang-bang)
Step 50: foot=1.546, vel=+10.0,  computed=+9.12   (정체)
```
vel이 10.0 = PhysX maxJointVelocity에 고정. computed_torque 부호가 예상과 반대.

### Test 10: URDF velocity=100 + Kp=16 (PhysX 클램프 해제)
- velocity ±66 rad/s 폭주. 악화.

### Test 11: Kp=5 Kd=1 + URDF vel=100 + fix_base
- foot vel=2.7→0.92 (수렴), foot=1.297 (init 1.32 근처)
- torque 0.05~0.25 Nm. 100 steps terminated=0%
- **PhysX vel clamp 제거 + 낮은 Kp = PD 정상 작동**

### Test 12: Kp=5 Kd=1 + URDF vel=100 + free
- Kp=5는 body weight 지탱 불가 (gravity shift 0.31 rad)

### Test 13: URDF vel=20, DCMotor vel=20, Kp=16 Kd=5 + free (최종)

**가설**: URDF vel = DCMotor vel_limit = 10이 문제.
vel=10에서 DCMotor max_effort = 15×(1-10/10) = 0 → 양방향 토크 불가.
둘 다 20이면 vel=10에서 max_effort = 15×(1-10/20) = 7.5 → 양방향 가능.

```
step=100:  terminated=0%, height=0.104, ep_len=100
step=200:  terminated=0%, height=0.100, ep_len=176
step=300:  terminated=0%, height=0.102, ep_len=275
```
**300 steps terminated = 0%.**

---

## 추가 테스트 (standing equilibrium 개선 시도)

### Test 14: DCMotor effort_limit=25 (토크 증가)
**가설**: effort_limit이 부족해서 crouched equilibrium으로 내려감. 올리면 해결되는지 확인.
**결과**: 악화. step 300: 37.5% terminated (이전 0%)
- 높은 effort = 높은 반발 에너지 = 불안정 증가
- **결론: DCMotor에서 effort 증가는 해결책이 아님**

### Test 15: 기둥형 (columnar) pose — leg=-0.35, foot=0.63
**가설**: Z자 다리를 수직에 가깝게 펴면 moment arm 감소 → 적은 토크로 지지 가능
**FK 계산**: height=0.247m (+15%), toe x=0.000
**결과**: 대폭 악화. step 50에서 25% terminated
- leg=-0.35는 theta=0까지 0.35 rad밖에 없어서 착지 충격으로 쉽게 flip
- Z자형 (leg=-0.70)은 0까지 0.70 rad 버퍼 → 더 안정
- **결론: 이론적으로는 타당하나 실제로는 flip zone proximity가 더 위험**

### Test 16: init_z=0.185 + 관절별 차등 gain
**설정**: shoulder Kp=12/Kd=4, leg Kp=28/Kd=5, foot Kp=8/Kd=2
**가설**: 낮은 시작점 + leg gain 강화로 Phase 2→3 전환 지연
**결과 (vs 이전 best DCMotor)**:
```
         이전 (Kp=16 균일, z=0.210)  현재 (관절별, z=0.185)
step 100: height=0.104              height=0.118 (+13%)
step 200: height=0.100              height=0.119 (+19%)
step 300: height=0.102, term=0%     height=0.122, term=6.25%
```
- leg Kp=28이 하중 지지력 향상 → 높이 20% 개선
- 그러나 여전히 crouched 상태 유지 (height 0.12, 다리 크게 벌어짐)

### Test 17: foot/toe inertia 10배 증가 (URDF)
**설정**: foot Iyy 0.0005→0.005, toe Iyy 1e-5→1e-4
**가설**: 저관성이 PD 과잉반응의 원인. 서보 로터 관성 추가로 완화 시도.
**결과**: step 1이 훨씬 안정 (ang_xy=0.10 vs 1.74), 그러나 height 더 낮아짐 (0.073 vs 0.102)
- 높은 관성 = 느린 PD 응답 = body weight에 더 밀림
- **결론: 관성 증가는 초기 안정성 향상, 장기 지지력 하락. 원복 처리.**

---

## DCMotor → ImplicitActuator 전환

### 배경: DCMotor의 구조적 한계
위의 Test 14~17에서 DCMotor 환경 내에서 다양한 시도를 수행:
- effort 증가 → 불안정
- pose 변경 → flip 위험
- gain 분리 → 부분 개선
- inertia 변경 → 트레이드오프

모든 시도에서 height 0.10~0.12 이상 유지 불가. **DCMotor의 velocity-dependent saturation이 구조적 병목으로 확인됨.**

### Test 18: ImplicitActuator (effort_limit 없음)
**변경**: DCMotorCfg → ImplicitActuatorCfg, 같은 gain (12/28/8, 4/5/2)
**결과**:
```
step=50:  height=0.1440, vel_xy=0.0002, ang_xy=0.11
step=100: height=0.1441, vel_xy=0.0006, ang_xy=0.11
step=200: height=0.1441, vel_xy=0.0006, ang_xy=0.10
step=300: height=0.1441, vel_xy=0.0006, ang_xy=0.10
```
- **Step 50 이후 완전 정지.** height 소수점 4자리까지 동일
- **DCMotor와 완전히 다른 결과**: 같은 gain, 같은 pose에서 actuator만 교체

### Test 19: ImplicitActuator + effort_limit=15 (최종 결정)
**가설**: DCMotor와 동일한 토크 제한을 걸어도 standing이 유지되는지 확인.
**결과**: **Test 18과 소수점 4자리까지 동일.**
```
step=50:  height=0.1440
step=100: height=0.1441
step=300: height=0.1441
모든 토크 < 7 Nm (effort_limit 15 Nm 한참 아래)
```
- **정적 평형에서 필요한 최대 토크 = rear_foot -5.90 Nm** (15 Nm 한참 이내)
- **DCMotor의 문제는 effort_limit이 아니라 velocity-dependent saturation이었음** 확정

### Test 20: 600 steps 장기 안정성 + episode reset 확인
**결과**:
```
step=450: height=0.1441 (안정)
step=500: time_out_frac=1.0 → episode reset
step=510: height=0.1627 (새로 착지 중)
step=550: height=0.1441 (다시 안정)
```
- Episode reset 후에도 **동일한 0.1441 평형으로 복귀**
- **무한히 안정적**

### GUI 확인
"서 있다가 잠시 후 뒤로 살짝 내려앉은 상태에서 정지"
= Phase 1 (init height 0.185) → Phase 2 (loaded eq 0.144) → Phase 3 (영구 안정)
**이것이 정상 동작.** 중력 하에서 관절이 약간 압축되는 것은 자동차 서스펜션과 동일한 원리.

---

## 분석팀 토론

### 초기 의견: "DCMotor 유지, ImplicitActuator 전환 반대"
근거: 실험 연속성, 원인 분리 필요, DCMotor 설정 미세조정 여지

### 반론: "같은 gain/pose에서 actuator만 바꿨는데 결과가 다르다"
근거: Test 17(DCMotor)=height 0.12 vs Test 18(Implicit)=height 0.144, 동일 설정
→ 병목은 standing equilibrium이 아니라 **actuator realization**

### 의견 수정: "effort_limit=15 유지한 비교 실험은 타당"
Test 19에서 effort_limit=15에서도 동일 결과 → **DCMotor의 velocity saturation이 유일 원인** 확정

---

## 근본 원인 확정 (최종)

### 원인 1: init_z에 toe sphere radius 미포함 (해결)
- init_z=0.194 → toe 구 바닥 지면 아래 20mm → PhysX impulse
- **수정**: init_z=0.210 (4mm 관통 + 느린 depenetration)

### 원인 2: URDF velocity = DCMotor velocity_limit = 10 (해결)
- PhysX 하드 클램프 + DCMotor saturation → bang-bang 진동
- **수정**: 둘 다 20

### 원인 3: DCMotor velocity-dependent saturation (최종 원인)
- DCMotor의 `torque = saturation × (1 - vel/vel_limit)` curve가
  관절이 움직일 때 가용 토크를 줄여서, 정적 평형으로 수렴 불가
- **해결**: ImplicitActuator 전환 (PhysX 연속시간 PD, velocity saturation 없음)
- effort_limit=15 유지 → 같은 토크 제한, 현실성 보존

---

## 최종 적용 변경

| 파일 | 항목 | 이전 | 최종 | 이유 |
|------|------|------|------|------|
| URDF | velocity | 10.0 | **20.0** | PhysX vel clamp 여유 확보 |
| spot_micro.py | actuator | DCMotorCfg | **ImplicitActuatorCfg** | velocity saturation 제거 |
| spot_micro.py | effort_limit | 15.0 (DCMotor) | **15.0 (Implicit)** | 토크 제한 유지 |
| spot_micro.py | init_z | 0.194 | **0.185** | loaded eq 근처 시작 |
| spot_micro.py | stiffness | 16.0 균일 | **shoulder=12, leg=28, foot=8** | 관절별 역할 차등 |
| spot_micro.py | damping | 5.0 균일 | **shoulder=4, leg=5, foot=2** | 관절별 역할 차등 |
| spot_micro.py | max_depenetration | 1.0 | **0.2** | 부드러운 착지 |
| env_cfg.py | target_height | 0.22 | **0.18** | loaded eq (0.144) 위 목표 |
| zero_stand_probe.py | debug output | 없음 | PD internals 출력 | 진단용 유지 |

---

## 핵심 교훈

1. **init_z 계산에 collision geometry 반드시 포함**: FK는 link center만 계산, sphere radius 별도 고려
2. **effort_limit 증가 ≠ 안정성 증가**: 높은 토크 = 높은 반발 에너지
3. **stiffness 증가 ≠ 안정성 증가**: 강한 spring = 접촉 impulse 증폭
4. **기둥형 pose의 함정**: 이론적 moment arm 최소화 vs 실제 flip zone proximity 위험
5. **URDF velocity = DCMotor velocity_limit이면 bang-bang 필연**
6. **DCMotor의 velocity-dependent saturation이 standing의 구조적 병목**: 같은 gain/effort에서 ImplicitActuator만으로 해결
7. **ImplicitActuator + effort_limit = 두 가지 요건 동시 충족**: PhysX 안정성 + 토크 제한 현실성
8. **Isaac Lab 표준은 ImplicitActuator**: A1, ANYmal, Spot 모두 사용
9. **loaded equilibrium은 init height보다 낮음**: 이것은 정상 (중력 하 관절 압축)
