# V26_PLAN-G.md (원본 설계안 — G 작성)

> ⚠️ **SUPERSEDED**: 이 문서는 V26 설계 원본 초안(G 작성)입니다.
> 실제 채택된 설계 철학은 **[V26_ANALYSIS.md](V26_ANALYSIS.md)**, 구현 계획은 **[V26.1_PLAN.md](V26.1_PLAN.md)** 를 참조하세요.

## V26 한 줄 정의
**V26은 "예쁜 보행"이 아니라, "부하가 분산되고 파손 위험이 낮은 자연스러운 4족보행"을 목표로 하는 버전이다.**

즉 V23/V24/V25가
- exploit를 잡고
- validity를 세우고
- rear-left collapse를 읽고
- 직접 처방을 고민한 단계였다면,

V26은 목표 자체를 이렇게 바꾼다.

> **전진 성공보다, 건강한 보행을 먼저 학습시키는 구조**

---

## 1. V26에서 바뀌는 가장 중요한 관점

### 기존 관점
- 앞으로 잘 가는가
- 안 넘어지는가
- trot처럼 보이는가
- 보기 좋은가

### V26 관점
- **하중이 4다리에 적절히 분산되는가**
- **특정 다리에 지속 과부하가 없는가**
- **불필요한 고빈도 접촉/충돌이 없는가**
- **접촉 품질이 좋은가**
- **그 결과로 자연스럽고 안정적이고 예뻐 보이는가**

즉 "예쁜 보행"은 목표가 아니라 **좋은 하중 분산과 낮은 파손 위험의 결과**로 본다.

---

## 2. V26이 해결하려는 문제 정의

V23/V24/V25를 통해 확인된 핵심 실패는 다음과 같다.

1. **rear-left collapse**
   - 한 다리가 사실상 사라짐
   - 나머지 3다리에 하중 집중
   - 기계적으로 위험한 gait

2. **reward exploit**
   - 전진/리듬 보상이 살아 있으면
   - 실제로는 병적인 gait도 선택됨

3. **contact quantity와 contact quality 혼동**
   - 접촉이 많다고 좋은 것이 아님
   - 짧고 빠른 다리질 + 잦은 충돌은 파손 위험

4. **style을 너무 일찍 보려는 유혹**
   - compact stance
   - shoulder aesthetics
   - posture style
   이런 건 validity와 load distribution 뒤에 와야 함

따라서 V26의 문제 정의는 명확하다.

> **"자연스러운 4족보행"이란, 네 다리가 모두 실제 지지/추진에 참여하고, 하중이 과도하게 한쪽에 몰리지 않으며, 충격과 불필요한 고속 접촉이 억제된 보행이다.**

---

## 3. V26의 설계 철학

V26은 reward를 "행동 예쁘게 만들기"로 짜지 않는다.
**기계적으로 건강한 보행을 유도하는 reward**로 짠다.

### 철학 1. 4다리 존재 보장
한 다리라도 사실상 사라지면 실패다.

### 철학 2. 하중 분산 우선
특정 다리에 하중이 몰리면 실패다.

### 철학 3. 접촉 품질 우선
접촉 횟수가 많다고 좋은 게 아니라, **필요한 순간에 부드럽게 지지하는 접촉**이 좋아야 한다.

### 철학 4. 충격/고빈도 발질 억제
짧고 빠른 다리질, contact oscillation, 충격성 touchdown은 강하게 억제한다.

### 철학 5. 스타일은 마지막
validity → load sharing → stability가 먼저고, compact stance/style은 그 다음이다.

---

## 4. V26의 전체 구조

V26은 4층 구조로 간다.

### Layer A. Survival / Basic Stability
- 넘어지지 않기
- 자세 유지
- base height 유지
- orientation 안정

### Layer B. Limb Validity
- 4개 다리 모두 실제 참여
- single-limb collapse 금지
- contact / stance / propulsion 존재 보장

### Layer C. Load Sharing / Contact Quality
- 특정 다리 과부하 억제
- 좌우/전후 하중 편중 억제
- 불필요한 충격 억제
- 고빈도 발질 억제
- 안정적인 stance/swing 비율 유도

### Layer D. Efficient Gait / Style
- trot-like timing
- diagonal coordination
- posture/style
- compact stance
- aesthetic refinement

핵심은 **B, C가 D보다 앞**이라는 점이다.

---

## 5. V26 reward 구조 제안

### A. 유지할 기존 core reward
- forward velocity tracking
- body orientation / upright
- base height
- smoothness penalties
- 기본 trot/diagonal 관련 reward
- foot clearance
- joint velocity / acceleration regularization

다만 이 항목들은 **주력 목표가 아니라 기반**이다.

### B. 존재 보장 계열 (Existence Floor)

#### 1) `limb_usage_min_penalty`
역할:
- 네 다리 중 하나라도 usage가 낮으면 강하게 감점

usage는 아래가 모두 있어야 살아 있다고 본다.
- contact participation
- stance participation
- propulsion contribution

즉 lift/clearance만 높고 contact가 거의 없으면 usage는 **0에 가깝게 붕괴**해야 한다.

#### 2) `per_leg_contact_floor_penalty`
역할:
- 각 다리의 최소 contact participation 보장

중요:
이건 "contact가 많아라"가 아니라 **"완전히 사라지지는 마라"**는 floor다.

#### 3) `per_leg_propulsion_floor_penalty`
역할:
- 각 다리가 최소한의 추진 기여를 하게 함

이건 "바닥에 살짝 닿기만" 하는 fake recovery를 막기 위해 중요하다.

### C. 하중 분산 / 대칭 계열 (Load Sharing)

#### 4) `rear_left_right_usage_diff_penalty`
#### 5) `front_left_right_usage_diff_penalty`
#### 6) `rear_left_right_propulsion_diff_penalty`

#### 7) `front_rear_support_balance_penalty`
역할:
- 앞/뒤 전체가 너무 한쪽으로만 지지/추진을 몰아먹지 않게 함

완전 균등을 강요하는 게 아니라 **병적인 편중**만 막는 soft constraint로 둔다.

### D. 접촉 품질 / 파손 억제 계열

#### 8) `contact_oscillation_penalty`
역할:
- 짧은 시간 내 contact on/off가 과도하게 반복되면 감점

#### 9) `touchdown_impact_penalty`
역할:
- 발이 바닥에 닿을 때 충격이 크면 감점

#### 10) `foot_slap_or_stomp_penalty`
역할:
- 과한 발끝 속도/충격으로 바닥을 치는 패턴 억제

#### 11) `micro_step_penalty`
역할:
- 너무 짧고 빠른 contact 반복을 억제

#### 12) `stance_quality_reward`
역할:
- contact가 존재할 때, 너무 짧고 불안정한 stance가 아니라
  **실제 지지 역할을 하는 stance**를 보상

### E. gait exploit 차단 계열

#### 13) `diagonal_coupling_soft_gate`
원칙:
- 특정 다리가 collapse 상태면 그 다리를 포함한 diagonal reward는 soft attenuation
- binary 금지
- soft gate 유지

### F. direct-fix 실험용 항목

#### 14) `rear_left_contact_floor_penalty`
유지할 수는 있다.
하지만 **본선이 아니라 실험용**이다.

즉:
- V26-A: 일반 구조
- V26-B: RL direct-fix 추가

이렇게 나눠야 한다.

---

## 6. V26의 핵심: "contact quantity"가 아니라 "contact quality"

우리가 막아야 하는 건:
- 발을 빠르게 흔들어 자주 닿는 gait
- contact count만 많은 gait
- 실제 하중 분산 없이 툭툭 치는 gait

### contact quantity를 직접 보상하지 않음
"닿아라"는 floor만 둔다.

### contact quality를 보상
좋은 contact는:
- stance에 실제 참여
- 추진에 실제 기여
- 충격이 과하지 않음
- contact oscillation이 과하지 않음

즉 **필요할 때, 제대로 닿는 다리**를 만들고 싶은 것이다.

---

## 7. V26 ramp / curriculum

잘못된 해법은 초반에 굳는다. 그래서 penalty를 늦게 걸면 안 된다.

### 추천 구간

#### iter 0~80
- survival / upright / base height 중심
- validity floor 아주 약하게 on

#### iter 80~200
- limb validity floor 빠르게 강화
- single-limb collapse early warning 구간

#### iter 200~350
- load sharing / contact quality penalty ramp-up
- exploit 경로를 실질적으로 차단해야 하는 구간

#### iter 350+
- full-strength validity + load sharing + contact quality
- 이 시점까지도 collapse면 해당 run 실패 가능성 큼

즉 V26은
**초반 안정화 → 빠른 validity 개입 → contact quality 개입**
순서로 간다.

---

## 8. V26 gate / 중단 기준

### iter 100
- early warning만
- 아직 중단은 아님

### iter 200
아래면 **강한 경고**
- `contact_ratio_rl < 0.05`
- `swing_time_rl > 0.95`
- `propulsion_rl ≈ 0`

### iter 250~300
위 패턴이 지속되면
- **A안 실패**
- direct-fix B안 전환 검토

### iter 400
single-limb collapse 지속 시
- **중단 기본값**

### iter 600
여전히 collapse면
- **즉시 중단**
- reward/survival과 무관하게 실패 처리

---

## 9. V26 실험 구조

### V26-A (본선)
목표:
- 일반 구조만으로 문제 해결 가능한지 검증

포함:
- limb_usage_min
- per_leg_contact_floor
- per_leg_propulsion_floor
- left/right usage diff
- left/right propulsion diff
- diagonal soft gate
- contact oscillation penalty
- touchdown impact penalty
- micro_step penalty
- stance quality reward

제외:
- RL 특화 penalty

### V26-B (직접 처방)
목표:
- 본선이 실패할 때 direct-fix가 실제로 필요한지 검증

추가:
- rear_left_contact_floor_penalty

주의:
- 성공해도 "일반 구조 성공"으로 해석하면 안 됨

### V26-C (style refinement)
전제:
- 4발 validity 확보
- 하중 분산 확보
- contact quality 확보

그 다음에만:
- compact stance
- shoulder style
- aesthetic posture

---

## 10. V26에서 반드시 새로 봐야 할 지표

### limb-wise
- `contact_ratio_*`
- `stance_time_*`
- `swing_time_*`
- `propulsion_*`
- `limb_usage_*`

### new load/contact quality
- `contact_oscillation_score_*`
- `touchdown_impact_*`
- `micro_step_score_*`
- `stance_quality_*`
- `front_rear_support_balance`
- `left_right_load_balance`

특히
- RL만 사라지는지
- contact는 살아도 impact가 큰지
- contact는 많아도 quality가 나쁜지

를 봐야 한다.

---

## 11. V26의 성공 기준

### 성공
- 4다리 모두 실제 contact/stance/propulsion 참여
- 특정 다리 collapse 없음
- 하중 편중이 완화됨
- 충격성/high-frequency contact가 낮아짐
- 그 결과 gait가 자연스럽게 보임

### 실패
- reward 높음
- survival 높음
- 그런데 특정 다리 usage collapse
- 또는 contact는 살아도 propulsion이 죽어 있음
- 또는 고빈도 발질/충격성 접촉이 심함

즉 "닿았다"만으로 성공 아님.
**건강하게 썼는가**가 성공 기준이다.

---

## 12. V26의 본질

우리는 "개처럼 보여라"를 직접 학습시키는 게 아니다.
대신 개나 말이 왜 그렇게 걷는지를 반영한다.

- 네 다리로 하중을 나눈다
- 무리하게 한 다리에 의존하지 않는다
- 필요할 때 부드럽게 접지한다
- 쓸데없이 빠르게 발을 치지 않는다
- 덜 다치고, 오래 버티는 방식으로 걷는다

즉 V26은

> **"예쁜 보행을 만들자"가 아니라, "덜 망가지고 덜 무리한 보행을 만들자"**

이다.

그리고 그렇게 되면 결과적으로
**자연스럽고 예쁜 4족보행**이 나올 가능성이 높다.

---

## 13. 최종 요약

### V26의 핵심
- validity-first를 유지한다
- 여기에 **load sharing / contact quality / impact suppression**을 본격적으로 넣는다
- "자주 닿는 gait"가 아니라 "좋게 닿는 gait"를 만든다
- RL collapse 같은 single-limb failure를 초반부터 차단한다
- style은 validity와 load quality 이후에 본다

### 가장 중요한 새 포인트
V26은 처음으로 **파손 위험과 부하 분산**을 reward 설계 중심으로 끌어온다.
