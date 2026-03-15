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

---

---

## 트레이너 의견 — 2026-03-15 17:23

> 이하는 Claude Sonnet 4.6 (트레이너)의 검토 의견이다. 원문 설계와 구분된다.

---

### 전체 방향 평가

방향은 맞다. “안 하면 벌점” 중심의 한계는 V23~V27 8개 런이 증명했고, target-band 전환은 RL 설계 원칙상 올바른 수렴이다.

3층 구조(Survival → Floor → Target-Band)와 cooperative reward를 후반 강화형으로 분리한 것은 V27.1a의 all-limb suppression 교훈을 잘 반영했다.

---

### 핵심 우려 5가지

#### 우려 1. target band 수치의 근거 부재 (가장 중요)

`contact_target_low = 0.12`, `propulsion_target_low = 0.10`을 제안하는데, V26~V27 런에서 이 수치를 안정적으로 넘은 다리가 몇 개나 있었는지 먼저 확인해야 한다.

- 달성 불가능한 band → reward signal이 아예 안 들어오는 **phantom incentive** 문제
- “floor보다 분명히 위”라는 말만으로는 근거가 없음

**제안:** V26 iter 200 (4발 통과 시점)의 실측 contact/propulsion 수치를 기준으로 band low를 설정한다. 그것이 달성 가능성이 확인된 유일한 참조점이다.

---

#### 우려 2. tap_suspicion 억제가 구조적으로 불완전

“band 안에 있어야 이득이므로 tap이 자연히 줄어든다”는 논리는 band_low(0.12)가 tap threshold(~0.05~0.10)보다 충분히 높을 때만 성립한다.

floor~band_low 구간에서는 벌점도 없고 band 보상도 없는 **중간 회색 지대**가 생긴다. policy가 이 구간에 안착할 가능성이 있다.

**제안:** floor~band_low 구간에 약한 penalty를 유지하거나, band reward를 inverted-U shape으로 설계해서 중간 정체가 이득이 없게 만든다.

---

#### 우려 3. cooperative reward의 트리거가 불명확

“Stage 2에서 매우 약하게 시작 가능”이라고 했는데, 어떤 조건에서 켜는지 명확한 트리거가 없다.

4발이 band에 들어오기 전에 켜지면 signal이 거의 0인데 작은 noise가 되고, 너무 늦게 켜면 후기 gait 안정화에 기여를 못한다.

**제안:** `target_band_hit_count >= 2` 같은 명확한 조건을 트리거로 설정한다.

---

#### 우려 4. V27 대비 실질적 차이가 Layer C뿐

Layer B는 V27.1b와 사실상 동일하다. Layer C의 target-band reward가 충분히 강하지 않으면 policy 입장에서는 V27.1b와 동일한 gradient 환경이 된다.

“floor 근처에 있어도 벌점 없고 이득도 없다” vs “floor 근처에 있으면 벌점” — policy 관점에서 결과가 예상 외로 비슷할 수 있다.

**제안:** Layer C 가중치 합산이 Layer B 벌점 합산의 1.5~2배 이상이어야 구조가 실질적으로 작동한다. target-band에 들어왔을 때의 이득이 floor 근처 유지 시의 “벌점 회피 이득”보다 커야만 의미가 있다.

---

#### 우려 5. iter 100~250 취약구간이 V26/V27과 동일

V26.1 collapse 구간(200~350), V27.1b RL 약세 고착 구간이 Stage 2(100~250)와 겹친다. V28이 이 구간에서 무엇을 다르게 하는지 Plan에서 명확하지 않다.

**제안:** collapse_restart 로직 유지(이미 반영)에 더해, 이 구간에서 단일 다리 약세가 감지되면 해당 다리의 target-band reward를 일시적으로 강화하는 **per-leg adaptive incentive** 도입을 고려한다.

---

### 구현 전 체크리스트

| 항목 | 현재 상태 | 권장 |
|---|---|---|
| band low 수치 근거 | 경험적 제안만 있음 | V26 iter 200 실측치 기준으로 보정 |
| floor~band_low 회색 지대 처리 | 미정 | 약한 penalty 또는 inverted-U |
| cooperative reward 트리거 조건 | “Stage 2쯤에” 수준 | `band_hit_count >= N` 명시 |
| Layer C 가중치 크기 | 미정 | Layer B 합산의 1.5~2배 이상 |
| tap_suspicion 구조적 억제 | 모니터링만 | reward 구조에서도 명시 |

---

### 트레이너 종합 판정

V28은 V23~V27의 실패를 가장 잘 소화한 설계다.

다만 **실제 성패는 target band 수치와 curriculum 타이밍이 결정한다.** 구조가 맞아도 수치가 달성 불가능한 범위이거나 cooperative reward 타이밍이 틀리면 다시 실패한다. 이 두 가지가 맞으면 V28이 처음으로 “4발이 동시에 의미있는 기능을 하는” 상태에 도달할 수 있다.

**구현 착수 전 V26 iter 200의 실측 수치 확인을 강력히 권장한다.**



---

---

## PLANNER 의견 — 2026-03-15 17:23

> 이하는 PLANNER의 검토 의견이다. 원문 설계 및 트레이너 의견과 구분된다.

---

### 결론

트레이너 의견은 대부분 맞고, V28 구현 전 반드시 반영해야 한다.

---

### 각 우려에 대한 입장

**우려 1 (band 수치 근거 부재) — 최우선**

동의한다. target band 수치는 감으로 정하면 안 되고, V26/V27에서 실제로 한 번이라도 도달한 값을 기준으로 잡아야 한다.

따라서 바로 구현하지 말고, 먼저 **V26 iter 200 기준 4발 contact/propulsion 실측치를 기준점으로 추출**하는 것이 선행돼야 한다.

---

**우려 2 (floor ~ band_low 회색지대) — 중요**

동의한다. 완전 무벌점 구간을 두면 tap/floor 정체가 다시 생긴다.

권고: **약한 penalty + band reward 동시 적용**. 회색지대에 penalty를 유지해 중간 정체를 이득 없는 구간으로 만든다.

---

**우려 3 (cooperative reward 트리거 불명확)**

동의한다. 조건 없이 켜면 안 된다.

권고:
- `target_band_hit_count >= 2` → 약하게 on
- `target_band_hit_count >= 3` → 강화

---

**우려 4 (Layer C vs Layer B 실질 차이)**

동의한다. Layer C가 약하면 V27.1b와 실질 차이가 없다.

**target-band 보상 총합 > Layer B 벌점 총합** 을 명시적 설계 조건으로 넣어야 한다.

---

**우려 5 (취약구간 100~250 반복 위험)**

동의한다. 다만 per-leg adaptive incentive는 1차 V28부터 넣기보다 **V28.1 후보로 미루는 것이 안전**하다. 1차에서는 collapse_restart 유지로 충분하다.

---

### PLANNER 최종 수정 방향

1. 실측치 기반 band 설정 (V26 iter 200 참조)
2. 회색지대 약한 penalty 유지
3. cooperative reward trigger 명시 (`band_hit_count >= 2/3`)
4. Layer C 가중치 합산 > Layer B 벌점 합산

**한 줄 결론: V28 방향은 맞지만, 지금 상태로 바로 구현하면 위험하다. band 수치와 trigger를 먼저 확정해야 한다.**



---

---

## 트레이너 재검토 의견 — 2026-03-15 17:23

> PLANNER 의견에 대한 트레이너(Claude Sonnet 4.6)의 추가 검토. 위 PLANNER 의견을 읽은 후 작성.

---

### 전반 평가

PLANNER가 5개 우려를 모두 수용하고 구체적인 threshold 숫자까지 제시한 것은 좋다.

---

### 동의하는 부분

**우려 1~4 수용 방식** — 모두 올바르다. 특히 "V26 iter 200 실측치 선추출" 원칙을 명시한 것은 이후 구현자가 임의 수치를 넣는 것을 막는 효과가 있다.

**우려 5의 V28.1 후보 판단** — 가장 현명한 결정이다. per-leg adaptive incentive는 구현 복잡도가 높고 디버깅이 어렵다. V28 1차에서 실패 원인을 명확히 격리하려면 변수를 최소화해야 한다.

---

### 추가 의견

**우려 3 트리거 수치 (`>= 2` / `>= 3`) 에 대해**

방향은 맞는데, 이 트리거가 **절대 count 기준**이라는 점이 약점이다. 4발 중 2개가 band에 들어왔다고 해도, 들어온 2개가 FL+FR이면 front 편중이고, FL+RL이면 diagonal이다. 단순 count보다 **어느 조합이 충족됐는지**가 더 중요할 수 있다.

실용적 권고: 1차 V28에서는 단순 count(`>= 2`)로 시작하되, 조합 편향이 관측되면 V28.1에서 diagonal 조건으로 강화한다.

---

**"Layer C 합산 > Layer B 합산" 조건에 대해**

원칙은 맞다. 다만 이것을 **정적 비율로 고정**하면 curriculum 진행 중 문제가 생긴다. Layer B는 ramp로 강해지고, Layer C도 ramp가 있다면 두 ramp가 교차하는 시점에 따라 초반에 Layer C가 오히려 더 약한 구간이 생긴다.

실용적 권고: "Layer C > Layer B"를 **최종 상태(iter 250+)** 기준으로 잡고, 초반(iter 0~100)에는 Layer B가 더 강해도 허용한다는 것을 명시한다.

---

### 종합 — 구현 전 선행 작업 순서

| 순서 | 작업 | 비고 |
|---|---|---|
| 1 | V26 iter 200 실측치 추출 | band low 기준점 |
| 2 | 회색지대 penalty 강도 결정 | floor ~ band_low 구간 |
| 3 | cooperative trigger 조건 확정 | count >= 2/3, 조합 편향 모니터링 |
| 4 | Layer C/B 비율을 iter 단계별로 명시 | 초반/후반 구분 |
| 5 | 위 4개 확정 후 구현 착수 | — |

---

---

## 미해결 이슈 — 2026-03-15 17:23

> 트레이너/PLANNER 논의 후 도출된 미해결 이슈 목록.

---

### 이슈 1. V26 iter 200 실측치 미추출 — 블로커

트레이너/PLANNER 모두 "band low는 V26 iter 200 실측치 기준으로 설정하라"고 합의했지만, 실제로 그 수치를 아직 추출하지 않았다. V28_PLAN.md의 `contact_target_low = 0.12`, `propulsion_target_low = 0.10`은 여전히 근거 없는 경험치 상태다.

→ V28 구현 착수 전 선행 필수.

---

### 이슈 2. V27.1b 판정 미완 — 블로커

iter 400 heartbeat 관찰 후 V27.1b 판정이 남아 있다. 현재 훈련이 어디까지 갔는지, RL 약세가 지속되는지, collapse가 다시 발생했는지 확인이 안 된 상태다.

→ V27.1b를 공식 종료/실패 판정하고 V28으로 넘어가는 시점이 아직 정해지지 않았다.

---

### 이슈 3. V28 원문 수치 미반영

트레이너+PLANNER 의견이 수정을 권고하는 항목들이 원문(섹션 5~9)에 그대로 남아 있다. 의견 섹션과 원문이 충돌하는 상태다.

- 섹션 5.2: `contact_target_low = 0.12` → 실측치로 교체 필요
- 섹션 6: cooperative reward 트리거 조건 미명시
- Layer C/B ramp 교차 구간 명시 없음

→ 구현 착수 전 반드시 반영.

---

### 이슈 4. Layer C/B ramp 비율 미정

"iter 250+ 기준으로 Layer C > Layer B"는 합의됐지만, 각 ramp의 구체적인 initial/final/iter 범위가 아직 결정되지 않았다. 이것 없이 구현하면 교차 구간이 어디인지 모른 채 학습이 시작된다.

→ 구현 착수 전 반드시 반영.

---

### 이슈 5. cooperative trigger 조합 편향 모니터링 방법 미정

트레이너가 "FL+FR만 충족되는 경우 front 편중"을 우려했고 모니터링을 권고했지만, heartbeat에 이를 감지하는 지표가 없다. 1차 V28에서 단순 count로 가는 것은 합의됐지만, 관찰 방법이 없으면 편향이 생겨도 모른다.

→ V28 시작 후 조기 확인 필요.

---

### 이슈 요약

| # | 이슈 | 블로커 여부 |
|---|---|---|
| 1 | V26 iter 200 실측치 미추출 | **블로커** |
| 2 | V27.1b 판정 미완 | **블로커** |
| 3 | V28 원문 수치 미반영 | 구현 전 반드시 |
| 4 | Layer C/B ramp 비율 미정 | 구현 전 반드시 |
| 5 | cooperative 조합 편향 모니터링 방법 미정 | V28 시작 후 조기 확인 |

---

## PLANNER 최종 판단 — 2026-03-15 17:23

> 미해결 이슈에 대한 PLANNER의 최종 입장.

---

### 결론

개발AI(트레이너) 피드백이 맞다. 지금은 V28 구현 착수 전이다.

---

**블로커 1: V26 iter 200 실측치 미추출**

반드시 먼저 해야 한다. `contact_target_low`, `propulsion_target_low`를 감으로 정하면 V28도 실패한다.

**블로커 2: V27.1b 공식 판정 미완**

지금까지 대화상 실패 쪽으로 기울지만, iter 400까지 확인하고 종료를 공식화해야 다음 설계 기준점이 명확해진다.

**이슈 3: V28_PLAN 원문 수정 필요**

지금 문서는 의견과 본문 수치가 충돌한다. 구현 전에 본문 수치/트리거를 확정 반영해야 한다.

**이슈 4: Layer C/B ramp 비율 미정**

필수다. 최소한 아래 두 가지를 숫자로 확정해야 한다.
- 언제 Layer C를 켤지
- 언제 Layer C 총합이 Layer B보다 커질지

**이슈 5: cooperative 조합 편향 모니터링**

블로커까진 아니지만, V28 시작 전 heartbeat에 pair/side hit 요약을 넣는 것이 좋다.

---

### 우선순위

**1 → 2 → 3 → 4 → 5**

**한 줄 결론: 지금은 V28 코딩을 시작할 단계가 아니라, V26 실측치 추출과 V27.1b 종료 판정부터 끝내야 하는 단계다.**
