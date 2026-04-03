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
