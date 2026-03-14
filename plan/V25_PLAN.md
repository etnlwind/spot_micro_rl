# V25 최종 설계 및 구현 요청

현재 SpotMicro RL 프로젝트의 V23, V24 실험 결과를 바탕으로 **V25는 단순 튜닝이 아니라 구조 재설계판**으로 진행해야 합니다.

## 현재까지 확정된 사실

1. **V23 실패**
   - reward, episode length, survival 수치는 높았음
   - replay/영상 검증 결과 실제로는 **rear-left 미사용 3족 exploit**였음

2. **contact KPI 문제는 해결됨**
   - 초기 “전 다리 contact 거의 0” 문제는 정책 문제가 아니라 raw export mapping 오류였음
   - 실제 접촉력은 `*_toe_link`에 들어가는데, raw export가 `*_foot_link`를 읽고 있었음
   - 수정 후 결과:
     - `FL / FR / RR` contact ratio는 정상 범위
     - `RL`만 `0.0`

3. **rear-left collapse는 실제 정책 문제**
   - iter 600 / 1000 / 2400 replay 결과에서 RL만 지속적으로 붕괴
   - 예:
     - iter 600: `RL contact_ratio ≈ 0.0013`
     - iter 1000: `RL = 0.0`
     - iter 2400: `RL = 0.0`
   - 따라서 rear-left collapse는 **적어도 iter 600 시점에는 이미 형성**되어 있었음

4. **V24 실패**
   - V24에서 limb-wise KPI, limb validity gate, usage proxy, fast-ramp penalty를 도입했음
   - diagnostics/gate는 성공했음
   - 그러나 **정책 행동 자체는 바뀌지 않았음**
   - iter 2000 기준:
     - `contact_ratio_rl ≈ 0`
     - `stance_time_rl ≈ 0`
     - `swing_time_rl ≈ 1`
     - `propulsion_rl ≈ 0`
     - `limb_usage_rl ≈ 0`
   - 결론:
     - **gate/diagnostics는 성공**
     - **학습 objective는 실패**

## 핵심 문제 정의

이제 문제는 sensor/export/gate가 아니라 **학습 objective가 실제 정책 행동을 못 바꾸는 것**입니다.

즉 V25는 아래 질문에 답해야 합니다.

> **어떻게 하면 rear-left collapse 같은 single-limb collapse를 초반부터 차단하고, 네 다리를 실제로 쓰게 만들 것인가?**

---

## V25 설계 원칙

### 1. validity-first
우선순위는 아래와 같아야 합니다.

1. **4개 다리가 실제로 접지/추진에 참여하는가**
2. **single-limb collapse가 없는가**
3. **좌우/전후 비대칭이 과도하지 않은가**
4. 그 다음 compact stance / shoulder style
5. 그 다음 distal jitter / aesthetic refinement

즉 V25에서는 **validity가 posture/style보다 항상 우선**입니다.

### 2. G를 뼈대로, CS를 도구로 사용
- **상위 설계 철학은 G 채택**
  - 구조 재설계
  - 3층 validity 구조
  - iter 100 / 200 / 300 / 600 단계 판정
  - Run A / B / C 구조
- **하위 구현 수단은 CS 채택**
  - diagonal coupling exploit 경로 차단
  - 직접 penalty 항목
  - 구체 코드 변경 단위

즉:
- **무엇을 바꿀 것인가** → G
- **어떻게 바로 구현할 것인가** → CS

---

## V25 목표 구조

### 3층 validity 구조

#### Layer 1. Existence Floor
특정 다리 하나라도 사실상 사라지지 않게 만드는 최소 사용 보장층

후보:
- `limb_usage_min_penalty`
- `per_leg_contact_floor_penalty`
- `per_leg_propulsion_floor_penalty`

#### Layer 2. Symmetry Guard
좌우/전후 비대칭 억제층

후보:
- `rear_left_right_usage_diff_penalty`
- `rear_left_right_propulsion_diff_penalty`
- 필요 시 `front_left_right_usage_diff_penalty`

#### Layer 3. Support Participation
공중에서만 흔드는 다리를 “사용 중”으로 인정하지 않게 하는 층

후보:
- `support_phase_min_participation_penalty`
- usage proxy에서 support gating 강제
- contact/propulsion이 붕괴하면 usage도 함께 붕괴

---

## V25 실험 구조

### V25-A (본선)
일반화 가능한 본선 구조

반드시 포함:
- `limb_usage_min_penalty`
- `rear_left_right_usage_diff_penalty`
- `per_leg_propulsion_floor_penalty`
- `support_phase_min_participation_penalty`
- **diagonal_coupling exploit 경로 차단**
- validity fast-ramp
- iter 100 / 200 / 300 / 600 운영 기준

### V25-B (직접 처방 실험)
V25-A에 추가:
- `rear_left_contact_floor_penalty`

중요:
- 이 항목은 **최종 일반 구조가 아니라 direct-fix 실험용**
- 현재 RL collapse를 직접 겨냥한 교정 실험

### V25-C
전제:
- V25-A 또는 V25-B에서 single-limb collapse 해결 후에만 진행
- validity 성공 전에는 posture/style로 넘어가지 않음

---

## Validity Fast-Ramp 요구

V24의 0~200 / 200~600 fast-ramp도 늦었습니다.  
rear-left collapse는 600 이전에 이미 고정됩니다.

따라서 V25는 다음 원칙을 따르십시오.

- iter 0~100: 약하게 on
- iter 100~300: 빠르게 ramp-up
- iter 300+: full-strength
- 기존 gait curriculum과 **분리된 validity 전용 alpha/ramp** 사용

---

## Gate / 운영 정책

### hard_safety_gate
유지하되 단독 기준이 아닙니다.

### limb_validity_gate
더 중요한 gate로 승격합니다.

반드시 아래를 반영해야 합니다.
- limb_usage_min
- per-leg contact floor
- per-leg propulsion floor
- symmetry diff
- single-limb collapse reason

### 운영 판정 시점
- iter 0~99: 기록만
- iter 100~199: early warning
- iter 200~299: provisional fail
- iter 300~399: strong fail
- iter 400~600: abort 후보
- iter 600+: single-limb collapse 지속 시 즉시 중단

### 실패/중단 기준
iter 600 시점까지 아래가 유지되면 실패 설정으로 분류합니다.
- `contact_ratio_rl ≈ 0`
- `propulsion_rl ≈ 0`
- `swing_time_rl ≈ 1`
- `limb_usage_rl ≈ 0`
- `limb_validity_reason = rear_left_contact_collapse(...)`

원칙:
- **reward/survival이 좋아도 single-limb collapse가 남아 있으면 실패**
- 애매하면 중단

---

## 특별 구현 요구사항

### 1. diagonal_coupling exploit 경로 차단
이건 반드시 포함해야 합니다.

현재 exploit는 rear-left를 안 써도 diagonal/trot reward 일부를 계속 먹는 경로가 있었을 가능성이 큽니다.

따라서:
- RL collapse 상태면
  - RL이 포함된 pair 기여를 차단하거나
  - diagonal reward 전체를 강하게 감쇠하는 방식을 제안/구현해주십시오.

이 항목은 **V25-A 본선에 포함**합니다.

### 2. usage proxy 재정의
usage 정의는 아래를 반드시 만족해야 합니다.

- contact/stance participation이 무너지면 usage도 자동 붕괴
- propulsion이 0이면 usage가 유지되면 안 됨
- leg_lift / clearance는 보조 정보일 뿐, usage를 단독으로 살리면 안 됨

즉:

> **공중에서 계속 흔드는 것만으로는 사용으로 인정하지 않는다**

### 3. failure reason 직접화
generic한 reason보다 아래와 같은 직접 reason을 우선합니다.

예:
- `rear_left_contact_collapse(c=...,s=...,p=...)`
- `single_limb_usage_collapse`
- `rear_left_propulsion_floor_fail`

---

## 이번 요청에서 답해야 할 항목

아래 형식으로 답변해주십시오.

### 1. V24 실패 원인 분석
- diagnostics는 성공했는데 왜 정책 행동은 안 바뀌었는가
- current objective의 어떤 부분이 exploit를 허용했는가

### 2. V25 핵심 설계 원칙
- 무엇을 유지 / 수정 / 폐기할 것인가

### 3. 구체 reward 변경안
V25-A와 V25-B를 나눠서 제시해주십시오.
각 항목의 목적, 수식 개요, 권장 weight를 포함하십시오.
특히 아래 항목은 반드시 검토하십시오.
- `limb_usage_min_penalty`
- `rear_left_right_usage_diff_penalty`
- `per_leg_propulsion_floor_penalty`
- `support_phase_min_participation_penalty`
- `rear_left_contact_floor_penalty` (B용)
- `diagonal_coupling` 경로 차단

### 4. 구체 ramp / curriculum 변경안
- validity fast-ramp를 어떻게 구현할 것인지
- 0~100 / 100~300 / 300+ 구간별 제안
- 기존 gait curriculum과 어떻게 분리할 것인지

### 5. gate / shortlist 운영안
- iter 100 / 200 / 300 / 600 기준
- 계속 진행 / 경고 / provisional fail / strong fail / abort 기준

### 6. abort / restart 기준
- 어떤 조건에서 즉시 중단할 것인지
- checkpoint 채택 금지 기준은 무엇인지

### 7. 구현 우선순위
- 무엇을 1차 커밋에 넣고
- 무엇을 2차 실험 항목으로 미룰지

### 8. 최종 권고안
아래 중 하나로 결론을 명확히 내려주십시오.
- 유지
- 수정
- 폐기
- 구조 재설계

---

## 중요 지시
- 좋게 말하지 말 것
- “조금 더 지켜보자” 같은 표현 최소화
- 시간 낭비를 막는 실무 기준으로 판단할 것
- reward보다 **4발 사용 validity**를 우선할 것
- rear-left collapse를 막지 못하는 안은 채택하지 말 것
- RL 특화 penalty는 **본선 구조가 아니라 보조/direct-fix 실험용**으로 위치시킬 것
