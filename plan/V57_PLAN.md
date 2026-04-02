# V57 Plan: Clean Phase-Centric Reboot

> 작성: 2026-04-02
> 상태: B1.1 설계/구현 완료, planted-stand 행동 제약 추가
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
12. dof_acc_l2        -2.5e-7
13. undesired_contacts -1.0
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

### 7.3.2 각 reward의 역할 구분

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

### 7.3.3 기대되는 로그 변화

`B1.1`이 맞다면 TensorBoard에서 먼저 보여야 하는 건 다음이다.

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
```

즉 `B1.1`의 첫 성공 신호는
`standing_height`가 아니라
`발 재배치와 접지 중 foot motion이 줄어드는 것`
이어야 한다.

### 7.3.4 기대되는 영상 변화

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

현재 구현 상태:

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
alive_bonus                = ON (+1.0)
standing_height            = ON (+5.0)
feet_on_ground             = ON (+2.0)
stationary_reward          = ON (+1.0)
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

---

## 12. 최종 추천

바로 실행할 다음 1순위는 `V57.B1` fresh start 검증이다.

한 줄 요약:

`V57의 다음 단계는 걷기보다 먼저 서기다. V57.B1은 symmetric reset과 stand-only command 위에서, 발을 붙인 채 높고 수평하게 버티는 planted stand control을 먼저 학습시키는 단계다.`
