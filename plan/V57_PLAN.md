# V57 Plan: Clean Phase-Centric Reboot

> 작성: 2026-04-02
> 상태: A1 설계/구현 완료, fresh start 검증 대기
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

### A1: Clean Flat-Trot Bootstrap

목표:

```text
flat terrain에서
clean phase-centric stack으로
자연스럽고 반복 가능한 trot bootstrap을 만든다
```

이름을 `A1`로 둔 이유:

```text
V57 안에서도
먼저 "clean baseline bootstrap"을 확인해야 하기 때문이다.
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

### B-track (필요 시)

`V57`에서는 `phase`가 이미 주연이므로,
`V55`식 B-track이 그대로 오지는 않는다.

필요하면:

```text
구조 파라미터(freq, duty, aggregation, stance width 등)
ablation track
```

으로 따로 분리한다.

---

## 6. Experiment V57.A1

### 6.1 질문

`V57.A1`이 답할 질문은 하나다.

```text
"77개 heuristic 없이,
 clean phase-centric reward stack만으로
 flat terrain에서 자연스럽고 내구성 있는 trot을 만들 수 있는가?"
```

### 6.2 reward 설계 원칙

`A1`은 아래 수준으로 제한한다.

#### primary

```text
1. track_lin_vel_xy_exp
2. track_ang_vel_z_exp
3. phase_contact
4. phase_clearance
```

#### stability / mechanics

```text
5. lin_vel_z_l2
6. ang_vel_xy_l2
7. flat_orientation_l2
8. base_height_l2
```

#### smoothness / safety

```text
9. action_rate_l2
10. dof_acc_l2 or joint_vel_l2
11. undesired_contacts or contact force/impact penalty
12. feet_air_time (phase-linked 또는 표준형)
```

즉:

```text
다리별 heuristic 군
- rear_alternation
- rear_joint_velocity
- stance_propulsion
- usage_diff 다수
- floor/band/cooperation ecology
```

은 `A1`에서 기본적으로 넣지 않는다.

### 6.3 최종 구현 inventory

`V57.A1`은 아래 13개로 고정한다.

```text
Primary
1. track_lin_vel_xy_exp      +1.0
2. track_ang_vel_z_exp       +0.5
3. phase_contact             +1.0
4. phase_clearance           +0.5

Stability / mechanics
5. lin_vel_z_l2              -2.0
6. ang_vel_xy_l2             -0.1
7. flat_orientation_l2       -1.0
8. base_height_l2            -1.0   (target_height=0.22)

Smoothness / safety
9. action_rate_l2            -0.01
10. dof_acc_l2               -2.5e-7
11. undesired_contacts       -1.0
12. joint_deviation          -0.1   (temporary weak bootstrap prior)
13. alive_bonus              +1.0   (die-fast 방지용 최소 survival prior)
```

설계 의도:

```text
- phase_contact / phase_clearance가 gait timing의 주연
- velocity / orientation / smoothness는 표준 quadruped RL 축만 유지
- joint_deviation은 SpotMicro boot viability를 위한 약한 safety prior로만 둔다
- alive_bonus는 clean stack 예외 1개로, die-fast 방지 목적의 최소 survival prior다
- feet_air_time는 A1 첫 버전에서 넣지 않는다
  (phase_clearance와 timing overlap을 피하기 위함)
```

### 6.4 legacy 처리

`A1`은 clean reboot이므로 아래를 명시적으로 끈다.

```text
- legacy gait_gate          OFF
- legacy phase_table        OFF
- reward_weight_curriculum  OFF
- only_positive_rewards     OFF
- alive_bonus              ON (+1.0)
```

즉 `A1`은:

```text
- iter 500 release shock를 전제로 하지 않는다
- staged handoff를 전제로 하지 않는다
- clean stack 자체로 부팅/학습 가능한지 본다
- 단, die-fast 방지를 위해 alive_bonus 1개는 허용한다
```

### 6.5 phase가 주연이라는 뜻

`A1`에서는:

```text
phase_contact / phase_clearance가 gait timing의 핵심 신호
```

이다.

이건 `V55`와 다르다.

```text
V55:
phase = probe

V57.A1:
phase = primary gait driver
```

추가 결정:

```text
phase aggregation = mean
```

이유:

```text
- 첫 실험의 질문은 "phase 구조를 policy가 배우는가?"다
- mean_min은 weakest leg에 과도하게 끌려가므로 A1엔 보수적이다
- 4발 균등화는 A2 이후 필요 시 다시 검토한다
```

### 6.6 우리가 일부러 버릴 것

`A1`에서 일부러 안 넣는 것:

```text
- 77개 legacy ecology 대부분
- iter 500 gait-gate release
- handoff / bridge / staged shock
- direct RL-only patch history
- barrier / CaT style reward 통합
```

즉 `A1`은 “기존 것을 고친 버전”이 아니라
“새 clean stack”이다.

---

## 7. 성공 기준

`A1`의 첫 성공 기준은 두 단계다.

### 7.1 Boot viability

iter 200~400:

```text
- die-fast 아님
- ep_len > 80
- bad_orientation 1.0 고착 아님
- phase_contact 0 고착 아님
```

즉 첫 질문은:

```text
SpotMicro에서 clean stack만으로
서는가 / 움직이는가 / 학습 신호가 생기는가
```

이다.

### 7.2 Gait quality

iter 400:

```text
- ep_len > 150
- time_out > 0.60
- diagonal_raw > 0.35
- stride > 2.5
```

iter 1000:

```text
- time_out > 0.80
- diagonal_raw > 0.45
- stride > 4.0
- front/rear contact gap 과도하지 않음
```

### 영상 기준

필수:

```text
- 매 스텝 nose-down 과도하지 않음
- 앞발/뒷발이 서로 비틀린 torsion gait 아님
- 앞다리가 충격 흡수용 버팀목처럼 과사용되지 않음
- 보행이 "기괴한 타협해"로 보이지 않음
```

기각:

```text
수치가 좋아도
영상상 front-heavy / torsion / nose-down이 심하면 실패
```

---

## 8. 실패 해석

`A1` 실패의 의미:

```text
clean phase-centric stack만으로는
현재 SpotMicro morphologies / controls에서
flat trot bootstrap이 충분하지 않았다.
```

하지만 그 실패도 가치가 있다.

왜냐하면:

```text
그때 비로소
어떤 최소 heuristic / safety prior가 필요한지
깨끗하게 추가할 수 있기 때문이다.
```

즉 실패해도:

```text
V55/V56처럼 77개 ecology 안에서 길을 잃지 않는다.
```

---

## 9. 구현 상태

현재 구현 상태:

```text
TRAIN_VERSION            = V57.A1
legacy gait_gate         = OFF
legacy phase_table       = OFF
reward curriculum        = OFF
phase observation        = ON
phase aggregation        = mean
only_positive_rewards    = OFF
alive_bonus              = ON (+1.0)
```

따라서 다음 검증은:

```text
1. curriculum_0.pt가 아니라 reward snapshot/runtime이 clean stack 기준인지 확인
2. boot viability (iter 200~400) 먼저 확인
3. 그 다음 수치 + 영상 mechanics로 A1 성공/실패 판정
```

## 10. 바로 다음 작업

`V57.A1` 구현 후 바로 해야 할 것:

```text
1. fresh start
2. boot viability 검증
3. episode scalar + 영상 mechanics 함께 확인
4. die-fast 징후가 있으면 only_positive_rewards A1b 검토
```

---

## 11. 최종 추천

바로 실행할 다음 1순위는 `V57.A1` fresh start 검증이다.

한 줄 요약:

`V55/V56은 문제 지도를 만드는 데는 성공했지만, 최종 해법은 아니었다. V57.A1은 phase가 주연이고 reward가 13개뿐인 clean quadruped RL stack으로 다시 시작하는 메이저 전환이다.`
