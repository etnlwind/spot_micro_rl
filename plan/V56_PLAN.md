# V56 Plan: Durability-Friendly Mechanics First

> 작성: 2026-04-02
> 상태: M1 pitch / nose-down 직접 억제 설계/구현 완료
> 목적: `V55`에서 확보한 baseline recovery와 phase coexistence를 유지하되, 앞다리 과부하와 step-by-step nose-down이 큰 비자연 보행을 직접 교정한다.

---

## 1. 왜 V56인가

`V55`의 핵심 성과:

```text
1. iter 500 gait-gate release collapse를 상당히 완화했다
2. RL 바닥 고착을 줄여 phase probe가 가능한 baseline을 만들었다
3. phase가 실제로 읽히는 것까지는 확인했다
```

하지만 `V55`의 끝에서 남은 핵심 문제:

```text
- step마다 머리가 앞으로 고꾸라지는 nose-down oscillation
- 뒤에서 밀고 앞에서 받아내는 front-heavy mechanics
- 자연스럽지 않고 내구성에 부담이 큰 gait
```

즉 이제 목표는:

```text
"걷는다"가 아니라
"하드웨어에 올릴 수 있는 자연스럽고 내구성 있는 gait를 만든다"
```

---

## 2. V55에서 배운 것

### 2.1 A-track

```text
A5 ~ A5.4
- iter 500 gait-gate release에서 반복 붕괴
- reward 조정만으로는 release shock를 못 넘겼다

A5.5 ~ A5.6
- min_height는 근본 원인보다 collapse amplifier였다
- threshold 완화로 release shock는 상당히 줄었다

A6
- RL contact 바닥과 shoulder_splay를 줄여
  B-track 해석 가능한 baseline을 만들었다
```

### 2.2 B-track

```text
B1 / B1.1
- weak phase probe는 baseline과 공존 가능

B2 / B1.2
- phase를 너무 공격적으로 올리면 baseline 품질이 깨진다

B1.1A / B1.1B
- phase 2.0 / 0.75는 공존 가능
- 다만 후반 shoulder_splay drift와
  front-heavy / nose-down mechanics는 남는다
```

핵심 결론:

```text
phase clock은 도움이 되는 도구다.
하지만 자연 보행 / 내구성 문제를 단독으로 해결하지는 못한다.
```

---

## 3. 새 성공 기준

`V56`부터는 아래가 공식 성공 기준이다.

기존:

```text
- time_out
- stride
- diagonal_raw
- RL contact
```

추가:

```text
- step당 nose-down 정도
- front/rear contact gap
- front_lift vs rear_lift gap
- shoulder_splay drift
- 영상상 앞다리 과부하 여부
```

즉:

```text
수치가 좋아도
영상 mechanics가 나쁘면 실패로 본다.
```

---

## 4. V56 전체 흐름

### M1

목표:

```text
B1.1B baseline을 유지한 채
pitch / nose-down motion을 직접 억제한다.
```

핵심 가설:

```text
A6 -> B1.1 -> B1.1B까지
front_rear_support_balance / base_height / shoulder/stance gate를
여러 번 만졌지만 nose-down은 남았다.

즉 간접 posture gate만으로는 부족하고,
pitch motion 자체를 직접 벌해야 한다.
```

### M2

전제:

```text
M1이 부분 성공 이상
```

목표:

```text
앞다리 과사용과 landing impact를 더 직접 억제한다.
```

### P1

전제:

```text
M-track으로 mechanics가 어느 정도 정리됨
```

목표:

```text
그 다음에 다시 phase 구조 활용을 늘린다.
```

즉 `V56`은:

```text
M1 (pitch 직접 교정)
-> M2 (front overload 완화)
-> P1 (필요 시 phase 구조 재강화)
```

---

## 5. Experiment M1

### 5.1 해석

`M1`은:

```text
B1.1B + pitch 직접 억제 1개
```

즉 여러 변수를 한 번에 바꾸지 않는다.

질문은 하나다:

```text
"validated B1.1B baseline 위에
 pitch angular velocity penalty만 추가하면
 nose-down / front-heavy mechanics가 줄어드는가?"
```

### 5.2 설정

유지:

```text
base                        = B1.1B baseline 계승
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

posture gate 유지:
- shoulder_neutral post     = -10.0
- stance_width post         = -5.0
- front_rear_support        = -11.5
- base_height_l2            = -23.0
```

추가:

```text
pitch_ang_vel_l2            = -2.0
```

정의:

```text
body-frame pitch angular velocity의 제곱을
forward-velocity gate 위에서 직접 벌한다.
```

### 5.3 왜 pitch 직접 억제인가

```text
간접 제약:
- front_rear_support_balance
- base_height_l2
- shoulder_neutral
- stance_width_penalty

이들은 도움은 되지만,
policy는 여전히 "조금 숙였다가 앞다리로 받는" 해를 찾을 수 있었다.

M1은 그 회피 여지를 줄이기 위해
"pitch motion 자체"를 직접 벌하는 첫 실험이다.
```

---

## 6. 성공 기준

### checkpoint 기준

iter 400:

```text
- time_out > 0.75
- diagonal_raw > 0.45
- stride > 4.0
- RL contact > 0.20
- shoulder_splay < 0.20
```

iter 900:

```text
- time_out >= B1.1B 수준 유지
- diagonal_raw >= B1.1B 수준 유지
- RL contact >= B1.1B 수준 유지
- shoulder_splay <= B1.1B 수준 유지
```

### 영상 기준

필수:

```text
- step마다 nose-down oscillation 감소
- 앞다리가 충격 흡수용 버팀목처럼 과사용되지 않음
- front-heavy 착지 경향 완화
```

기각:

```text
수치가 유지되어도
영상상 앞다리 과부하 / nose-down이 그대로면 실패
```

---

## 7. 실패 해석

M1 실패의 의미:

```text
pitch angular velocity 직접 억제 1개만으로는
front-heavy mechanics를 고치기 충분하지 않았다.
```

이 경우 다음 단계:

```text
M2에서
- front overload 직접 억제
- landing impact / pitch recovery 관련 항목 추가
```

하지만 지금은 아직:

```text
frequency / duty_factor / aggregation
```

을 바꾸지 않는다.

이유:

```text
현재 더 직접적인 병목은
phase 파라미터보다 mechanics 쪽이기 때문이다.
```

---

## 8. 구현 상태

현재 코드 기준:

```text
기본 실행 버전
- TRAIN_VERSION = V56.M1

구현 완료
- V56.M1 분기 추가
- B1.1B baseline 계승
- pitch_ang_vel_l2 reward term 추가
- V56에서도 V55 release-ramp / soft-ramp 경로 재사용
```

---

## 9. 최종 추천

바로 실행할 다음 1순위는 `V56.M1`이다.

한 줄 요약:

`V55는 release collapse와 phase coexistence까지는 확인했다. V56의 첫 목표는 phase를 더 세게 하는 것이 아니라, 앞다리 과부하를 만드는 nose-down mechanics를 pitch 직접 억제로 줄이는 것이다.`
