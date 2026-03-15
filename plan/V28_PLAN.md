# V28_PLAN.md

## V28 한 줄 정의
**V28은 “floor만 넘기면 살아남는 구조”를 버리고, “정상적인 4발 기능 참여 범위(target band)에 들어와야 이득이 되는 구조”로 전환하는 버전이다.**

즉 V27/V27.1 계열의 핵심 한계였던:
- 과강한 penalty → 전체 학습 억제
- 약한 penalty → 특정 다리 약세 고착
- floor 근처 정체 → tap optimization

를 구조적으로 끊는 것이 목표다.

---

## 1. V27 계열에서 배운 것

### V27.1a 실패
- penalty/gate가 너무 강해 **4발 전체가 죽는 all-limb suppression**
- contact / propulsion이 모두 바닥 수준
- locomotion bootstrap 자체가 죽음

### V27.1b 실패
- 전체 억제는 완화됐지만
- **RL 약세가 다시 고정**
- FL/FR는 floor 근처에서 버티는 **tap suspicion**
- 즉 “최소 기준만 넘기고 버티는” 해법이 다시 등장

### 결론
V27 계열은 이렇게 정리된다.

1. **penalty만으로 존재를 강제하면**
2. policy는
   - 전체를 죽이거나
   - 특정 다리를 희생하거나
   - floor 근처에서 정체하는
3. 우회 해법을 찾는다

따라서 V28은 **최소 기준(min floor)** 중심이 아니라  
**목표 범위(target band)** 중심이어야 한다.

---

## 2. V28 핵심 목표

V28의 목표는 아래 순서다.

1. **4다리 모두 실제 contact + propulsion에 참여**
2. **특정 다리 약세(single-limb weakness) 금지**
3. **floor 근처 정체(tap optimization) 금지**
4. **좌우/전후 하중 편중 완화**
5. 그 다음에야 gait / style 해석

즉 V28에서는
- “안 하면 벌점”보다
- **“정상 범위에 들어와야 이득”**이 더 중요하다.

---

## 3. V28 핵심 철학

### 철학 1. floor는 필요하지만 주인공이 아니다
floor는 완전 붕괴를 막는 **하한선**일 뿐이다.  
정책이 floor 바로 위에만 머물러도 되는 구조는 실패다.

### 철학 2. 보상은 target band 안에서 최대
각 다리는
- contact
- propulsion
- usage

가 어느 정도 **정상 범위 안에 들어왔을 때 최대 보상**을 받는다.

### 철학 3. 4발 동시 참여는 단계적으로 유도
초기 랜덤 정책에서 바로 “4발 완벽 동시 참여”를 요구하면 학습이 죽는다.  
따라서 cooperative reward는 **staged curriculum**으로 간다.

### 철학 4. TAP 억제는 별도 패널티보다 구조로 해결
contact 0.10 근처에서만 버티는 것이 이득이 없게 만들면, tap optimization은 자연히 줄어든다.

---

## 4. V28 reward 구조 개요

V28은 3층 구조로 간다.

### Layer A. Survival / Bootstrap
- upright / base height
- basic stability
- minimal forward progress
- smoothness regularization

역할:
- 초기에 아예 학습이 죽지 않게 하는 기반

### Layer B. Validity Floor
- per_leg_contact_floor_penalty
- per_leg_propulsion_floor_penalty
- limb_usage_min_penalty
- single_limb_validity_penalty
- usage / propulsion diff penalties

역할:
- 완전 붕괴 방지
- 특정 다리 희생 금지

### Layer C. Target-Band Incentive
- per_leg_contact_target_band_reward
- per_leg_propulsion_target_band_reward
- limb_usage_target_band_reward
- four_limb_cooperation_reward

역할:
- “floor만 넘기는” 해법이 아니라
- **정상적인 기능 참여 범위까지 올라오는 것**을 유도

핵심은 **Layer C가 V28의 주인공**이라는 점이다.

---

## 5. Target-Band 구조

### 5.1 기본 개념
각 다리에 대해 contact / propulsion / usage가
- 너무 낮아도 안 되고
- 너무 높아도 안 되며
- **적절한 범위 안에 들어왔을 때 최대 보상**을 받는다

즉 단순 floor가 아니라 **band reward**다.

---

### 5.2 contact target band
예시 초기 band:
- `contact_target_low = 0.12`
- `contact_target_high = 0.30`

의미:
- 0.00~0.05는 붕괴
- 0.05~0.10은 barely alive
- 0.12~0.30은 유효한 접촉 범위
- 그 이상은 필요 시 평탄 또는 약한 감소

중요:
정확한 수치는 실험으로 보정해야 한다.  
초기값은 **floor보다 분명히 위**에 둬야 한다.

---

### 5.3 propulsion target band
예시 초기 band:
- `propulsion_target_low = 0.10`
- `propulsion_target_high = 0.25`

의미:
- “닿기만 하는 다리”는 부족
- 실제로 조금이라도 미는 다리여야 보상이 커짐

이 항목이 V28의 핵심이다.  
**가짜 회복(contact만 있고 propulsion 거의 없음)**을 구조적으로 불리하게 만든다.

---

### 5.4 usage target band
예시 초기 band:
- `usage_target_low = 0.12`
- `usage_target_high = 0.35`

의미:
- usage도 floor 근처에서 정체하면 보상이 약함
- 적절한 기능 참여 범위까지 올라와야 이득

---

## 6. four-limb cooperation reward

### 목적
각 다리가 개별적으로만 살아 있는 것이 아니라,
**4개 다리가 동시에 일정 수준 이상 기능 참여할 때** 추가 보상을 준다.

### 중요한 점
이 reward는 초기부터 강하게 넣으면 안 된다.  
초기 랜덤 정책에서는 4발 동시 충족이 거의 불가능하기 때문이다.

### 적용 방식
- 초기: 거의 0 또는 매우 약함
- 중기: 점진적으로 증가
- 후기: target band에 4발이 들어오면 의미 있는 보상

즉 cooperative reward는 **후반 강화형**이다.

---

## 7. V28에서 유지할 항목

다음은 유지한다.

1. `per_leg_contact_floor_penalty`
2. `per_leg_propulsion_floor_penalty`
3. `limb_usage_min_penalty`
4. `rear_left_right_usage_diff_penalty`
5. `front_left_right_usage_diff_penalty`
6. `rear_left_right_propulsion_diff_penalty`
7. `front_left_right_propulsion_diff_penalty`
8. `collapse_restart` 4발 감시 구조
9. heartbeat/report의 4발 전체 출력
10. `diagonal_coupling_raw` vs `gated`
11. `diagonal_coupling_soft_gate` (단, 초기에는 더 투명)

즉 V28은 완전 새로 짜는 게 아니라,  
**V27 바닥 구조 위에 target-band 층을 얹는 형태**다.

---

## 8. V28에서 수정할 것

### 8.1 single_limb_validity_penalty
권장:
- initial = `-5`
- final = `-25`
- ramp = `0 → 250`

의미:
- 완전 붕괴는 막되
- 초반 학습을 과하게 누르지 않음

---

### 8.2 per_leg_contact_floor_penalty
권장:
- initial = `-1`
- final = `-12`
- ramp = `0 → 200`

역할:
- 완전 붕괴 방지용
- target band 보상의 하한선 역할

---

### 8.3 per_leg_propulsion_floor_penalty
권장:
- initial = `-1`
- final = `-10`
- ramp = `50 → 250`

역할:
- contact보다 늦게 강화
- “닿기만 하는 가짜 회복” 억제

---

### 8.4 diagonal soft gate
권장:
- `min_contact = 0.10`
- `min_propulsion = 0.04`
- 초기 200 iter 동안 gate factor 하한선 유지  
  예: `gate_factor >= 0.5`

이유:
- V27.1a처럼 locomotion signal을 죽이면 안 된다

---

## 9. V28 신규 항목

### 9.1 per_leg_contact_target_band_reward
목적:
- contact를 floor 바로 위가 아니라 목표 범위로 유도

### 9.2 per_leg_propulsion_target_band_reward
목적:
- 추진이 실제로 살아 있는 다리를 만들기

### 9.3 limb_usage_target_band_reward
목적:
- usage도 floor 근처 정체가 아니라 정상 구간으로 유도

### 9.4 four_limb_cooperation_reward
목적:
- 4발이 동시에 target band 근처일 때 추가 보상

---

## 10. Curriculum 설계

V28의 성패는 항목보다 **curriculum**이 결정한다.

### Stage 1: iter 0~100
목표:
- 학습이 죽지 않기
- 4발이 모두 “아예 0은 아닌 상태” 형성

구성:
- survival reward 중심
- floor penalty 약하게
- target-band reward 거의 약하거나 off
- cooperation reward off

### Stage 2: iter 100~250
목표:
- 각 다리가 floor 위로 올라오기
- RL/RR/FL/FR 중 약한 다리 식별
- target-band reward 서서히 on

구성:
- floor penalty 중간 강도
- target-band reward 약하게 켜기
- cooperation reward 매우 약하게 시작 가능

### Stage 3: iter 250~500
목표:
- floor 근처 정체 해소
- 각 다리가 target band 쪽으로 이동
- 편중 줄이기

구성:
- floor penalty 유지
- target-band reward 본격 강화
- cooperation reward 중간 강도

### Stage 4: iter 500+
목표:
- 4발 기능 참여 안정화
- 이후 gait/style 해석 가능

구성:
- cooperative reward 의미 있는 수준
- target-band가 주 보상 구조

---

## 11. Heartbeat에서 반드시 볼 것

### 기존 지표
- `contact_ratio_fl/fr/rl/rr`
- `propulsion_fl/fr/rl/rr`
- `swing_time_fl/fr/rl/rr`
- `limb_usage_fl/fr/rl/rr`
- `limb_validity_reason`

### 요약 지표
- `limb_usage_min`
- `rear_left_right_usage_diff`
- `front_left_right_usage_diff`
- `rear_left_right_propulsion_diff`
- `front_left_right_propulsion_diff`
- `front_rear_balance`

### 신규 V28 지표
- 각 다리의 target band 진입 여부
- `target_band_hit_count` (4발 중 몇 개가 band 안인지)
- `four_limb_cooperation_score`
- `tap_suspicion`

---

## 12. V28 iter 판정 기준

### iter 100
정상:
- 4발 평균 contact > `0.03`
- 4발 평균 propulsion > `0.02`
- `usage_min > 0.01`
- all-limb suppression 없음

실패 경고:
- 4발 전체가 여전히 `0.01` 수준
- gait raw/gated가 지나치게 낮음

### iter 200
정상:
- 4발 평균 contact > `0.05`
- 4발 평균 propulsion > `0.03`
- `usage_min > 0.03`

경고:
- 특정 다리 하나가 계속 뒤처짐
- floor 근처 정체가 뚜렷함

### iter 300
핵심 판정:
- 4발 중 최소 2~3개는 target band 하한에 접근해야 함
- `tap_suspicion`이 강하면 경고
- single-limb 약세 지속이면 실패 방향

### iter 500
실패 기준:
- target band 진입이 거의 없음
- floor 근처 정체
- 특정 다리 약세 고정

이 경우:
- **V28 실패**
- 구조 재검토

---

## 13. 예상되는 리스크

1. **target 값이 너무 높으면**
   - 달성 불가능한 reward가 된다

2. **target 값이 너무 낮으면**
   - V27과 다를 바 없이 floor 근처 정체가 생긴다

3. **cooperation reward를 너무 빨리 켜면**
   - 초기 신호가 희박해져 학습이 죽는다

4. **soft gate가 여전히 너무 세면**
   - locomotion bootstrap이 죽는다

즉 V28의 핵심 리스크는  
**“구조가 맞아도 target 수치와 curriculum이 틀리면 다시 실패한다”**는 점이다.

---

## 14. 구현 담당 AI에게 요구할 출력

다음 형식으로 답변하도록 한다.

1. V28 적용 파일 목록
2. 기존 항목 유지 / 수정 / 신규 추가 표
3. 각 penalty/reward의 초기값 / 최종값 / ramp
4. target band 초기값 제안 근거
5. cooperative reward ramp 계획
6. iter 100 / 200 / 300 / 500 판정 기준 적용 방식
7. 예상되는 실패 패턴
8. 바로 학습 시작 가능한지 여부

---

## 15. 최종 요약

V28은
- penalty만으로 존재를 강제하는 버전이 아니다
- floor만 넘기면 되는 버전도 아니다
- **정상적인 4발 기능 참여 범위에 들어와야 이득이 되는 버전**이다

한 줄로 다시 말하면:

> **V28은 “안 하면 벌점” 중심에서 “제대로 하면 이득” 중심으로 전환하는 첫 버전이다.**
