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

---

## 개발담당 피드백

> 작성: Claude Sonnet 4.6 / 2026-03-14
> 목적: 구현 착수 전 설계상 불명확하거나 문제가 될 부분을 명시. 앞부분 설계 원칙은 그대로 유지.

---

### F1. `usage proxy 재정의`는 V24에 이미 구현되어 있음

문서에 “contact/propulsion이 붕괴하면 usage도 함께 붕괴”라고 명시되어 있으나, 이는 V24 `_compute_limb_usage_proxy`에 이미 반영된 내용이다.

```python
support_gate = torch.maximum(contact_score, propulsion_score)
usage_scores[suffix] = usage_scores[suffix] * support_gate
```

contact와 propulsion이 둘 다 0이면 support_gate=0 → usage=0 → penalty gap 최대. V24 실패 원인은 proxy 정의가 잘못된 것이 아니라 **weight 크기**(총 reward 544 대비 gap 최대 시 ~0.7%)였다.

“usage proxy 재정의”를 신규 작업으로 진행할 경우 불필요한 공수가 발생한다. **기존 구현 재사용 여부를 결정해야 한다.**

---

### F2. V25-A weight 합산이 collapse를 막기에 충분한지 불명확

V24 실패 구조:
- `limb_usage_min_penalty` -12.0 × gap 0.30 = **-3.6/step** ≈ 총 reward의 0.7%

V25-G 제안 합산(gap 최대 가정):
- `limb_usage_min_penalty` -16.0 × 0.30 = -4.8
- `support_phase_min_participation_penalty` -14.0 × ~0.30 = -4.2
- `per_leg_propulsion_floor_penalty` -6.0 × ~0.25 = -1.5
- **합계 약 -10.5/step** ≈ 총 reward의 ~2%

V24보다 3배 강해졌으나, collapse가 iter 200 이전에 고착되면 동일한 결말이 반복될 가능성이 있다. V25-A에 `restart-on-collapse`가 포함되지 않으면 이 위험은 그대로 남는다.

**`restart-on-collapse`가 V25-A 본선에 포함되는지 명확히 해야 한다.**

---

### F3. `support_phase_min_participation_penalty`와 `per_leg_contact_floor_penalty` 역할 중복 위험

두 term 모두 contact/stance 참여를 요구하는 구조다. 정의가 다르지 않으면 동일한 신호에 중복 패널티가 부과되어 weight 설계가 복잡해지고 실패 원인 분석(attribution)이 어렵다.

추정되는 의도 차이:
- `support_phase_min_participation_penalty`: 특정 시점에 접지 중인 다리 수에 대한 제약 (multi-leg 관점)
- `per_leg_contact_floor_penalty`: 각 다리의 전체 구간 contact_ratio ≥ floor (per-leg 관점)

역할이 다르면 수식 수준에서 명확히 분리해야 한다. 역할이 같으면 하나만 구현하고 나머지는 제거하는 것이 낫다.

**구현 전에 두 term의 수식 의도를 확정해야 한다.**

---

### F4. `diagonal_coupling` gate — binary 차단은 gradient 불연속

CS 구현안:
```python
rl_gate = (metrics[“contact_ratio_rl”] > 0.15).float()  # binary 0 or 1
corr_b = corr_b * rl_gate
```

`contact_ratio_rl`이 0.14↔0.16 경계를 오갈 때 reward가 계단식으로 뛴다. PPO 학습에서 이 불연속은 gradient 추정을 불안정하게 만들 수 있다.

soft gate 대안:
```python
rl_gate = torch.clamp(metrics[“contact_ratio_rl”] / 0.20, 0.0, 1.0)
corr_b = corr_b * rl_gate
```

0~0.20 구간에서 선형으로 기여가 증가하므로 gradient가 연속적이다.

**binary vs soft gate 방식을 결정해야 한다. soft gate를 권장한다.**

---

### F5. V25-A 실패 시 V25-B로 전환하는 트리거 기준이 없음

문서 구조상 V25-A 먼저, 실패하면 V25-B로 진행하는 순서로 읽힌다. 그러나 V25-A를 언제 포기할지 기준이 없다. 이 기준이 없으면 V24에서 반복된 “조금 더 지켜보자” 운영이 재발한다.

제안 기준:
> iter 200 시점에서 `contact_ratio_rl < 0.05` AND `swing_time_rl > 0.95` 이면 V25-A 즉시 중단 → V25-B로 재시작

**V25-A → V25-B 전환 트리거를 명시해야 한다.**

---

### F6. abort 자동화 여부 불명확

문서에 “iter 600 collapse 지속 시 즉시 중단”이라고 명시되어 있으나, 이것이 heartbeat 자동 kill인지 사람이 판단하는 것인지 구분이 없다. 구현 범위가 달라진다.

- **자동화**: heartbeat.py에 collapse 감지 → `common.stop_training()` 호출 → Telegram 알림 추가 필요
- **수동**: Telegram 알림만 보내고 사람이 `/stop` 실행

**구현 방식을 결정해야 한다.**

---

### 피드백 요약

| # | 항목 | 결정 필요 사항 |
|---|------|--------------|
| F1 | usage proxy | V24 기존 구현 재사용 vs 신규 작성 |
| F2 | V25-A weight + restart | restart-on-collapse의 V25-A 포함 여부 |
| F3 | term 중복 | `support_phase_min_participation` vs `per_leg_contact_floor` 역할 분리 또는 폐기 |
| F4 | diagonal gate | binary vs soft gate |
| F5 | A→B 전환 트리거 | iter 200 기준 명시 또는 다른 기준 |
| F6 | abort 방식 | heartbeat 자동화 vs 수동 판단 |




- - -
Feedback from G V2
좋습니다.
개발담당 의견이 반영된 V25_PLAN.md는 방향이 맞고, 이전 G/CS 비교 결과를 꽤 잘 흡수한 통합안입니다.

냉정한 총평

채택 가능합니다.
다만 그대로 바로 구현에 들어가기 전에 딱 3가지는 더 못 박아야 합니다.

현재 문서는 이미 다음을 분명히 하고 있습니다.
	•	V25를 단순 튜닝이 아니라 구조 재설계판으로 정의함.  ￼
	•	문제를 sensor/export가 아니라 학습 objective failure로 규정함.  ￼
	•	validity-first 우선순위와 G를 뼈대로, CS를 도구로 쓰는 구조를 명시함.  ￼
	•	3층 validity 구조, V25-A/B/C 분기, fast-ramp, iter 100/200/300/600 운영 기준까지 포함함.  ￼

이 정도면 문서 수준은 충분합니다.

⸻

잘된 점

1. 문제 정의가 정확합니다

문서가 가장 중요한 걸 정확히 잡았습니다.
	•	V23은 rear-left 미사용 3족 exploit
	•	V24는 diagnostics/gate는 성공했지만 행동 제어는 실패
	•	따라서 V25는 objective를 바꾸는 구조 재설계여야 한다는 점

이건 맞습니다. 이 부분이 흔들리면 또 시간 낭비합니다.  ￼

2. G/CS 통합 방식이 적절합니다

문서가 명시적으로
	•	무엇을 바꿀 것인가 → G
	•	어떻게 바로 구현할 것인가 → CS

로 정리한 건 좋습니다. 이건 설계 철학과 구현 실행력을 동시에 잡는 방식입니다.  ￼

3. V25-A / B / C 분리가 실무적으로 좋습니다

특히
	•	V25-A = 본선 일반 구조
	•	V25-B = direct-fix 실험
	•	V25-C = validity 성공 후 posture/style

이 구조는 매우 좋습니다.
이렇게 안 나누면 RL 특화 처방이 본선 구조를 오염시킬 수 있는데, 문서는 그걸 막고 있습니다.  ￼

4. diagonal exploit path 차단을 본선에 넣은 점이 좋습니다

이건 CS의 가장 강한 부분이었고, 문서가 V25-A 본선에 넣은 건 잘한 결정입니다.
이번 실패는 “벌점이 약했다”뿐 아니라 잘못된 보상 경로가 열려 있었다는 문제도 있었기 때문입니다.  ￼

⸻

아직 보완이 필요한 3가지

1. per_leg_contact_floor_penalty와 rear_left_contact_floor_penalty의 역할 충돌을 정리해야 합니다

현재 문서는 Layer 1 후보로 per_leg_contact_floor_penalty를 두고, V25-B에서 rear_left_contact_floor_penalty를 추가합니다.  ￼

이 구조 자체는 괜찮지만, 구현 들어가면 이런 문제가 생길 수 있습니다.
	•	본선 일반 penalty와 RL 특화 penalty가 같은 현상을 이중 처벌
	•	결과적으로 어떤 항목이 실제로 행동을 바꿨는지 attribution이 흐려짐

권장

구현 지시서에는 이렇게 못 박는 게 좋습니다.
	•	V25-A: per_leg_contact_floor_penalty 또는 per_leg_propulsion_floor_penalty 중 하나를 주된 existence floor로 사용
	•	V25-B: 그 위에 rear_left_contact_floor_penalty를 direct-fix ablation으로 추가
	•	둘 다 동시에 full-weight로 켜지 않음

즉 A는 일반 구조, B는 RL 직접 처방 비교 실험으로 명확히 분리해야 합니다.

⸻

2. iter 300399와 400600의 차이를 더 명확히 해야 합니다

문서는 현재:
	•	300~399: strong fail
	•	400~600: abort 후보
	•	600+: 즉시 중단

으로 되어 있습니다.  ￼

이건 괜찮지만, 실무에서는 누가 언제 stop 버튼을 누르는지가 더 분명해야 합니다.

권장

운영 문구를 이렇게 바꾸는 것이 좋습니다.
	•	iter 300~399: collapse reason 지속 시 “기본 중단 권고”
	•	iter 400~599: collapse reason 지속 시 “중단 기본값, 특별 사유 없으면 계속 금지”
	•	iter 600+: 자동 중단 또는 즉시 수동 중단

지금 문구는 아직 “조금 더 볼까?”의 여지를 남깁니다.
이번 프로젝트는 그 여지를 줄여야 합니다.

⸻

3. 최상위 리포트 경고 우선순위를 코드에도 강제해야 합니다

문서는 analysis report 최상위 경고가 생존률이 아니라 limb validity fail이어야 한다고 했습니다. 이건 매우 맞습니다.  ￼

하지만 이건 문구 수준이 아니라 리포트 생성 우선순위 로직으로 강제해야 합니다.

권장

개발 지시서에 아래를 추가하세요.
	•	rear_left_contact_collapse(...) 또는 single-limb collapse가 있으면
다른 모든 요약보다 먼저 최상단 CRITICAL로 출력
	•	survival/fall/reward는 그 아래 secondary summary로 내림

이걸 안 하면 또 보고서가 “reward 좋음 / survival 좋음”을 먼저 보여줘서 사람 판단을 흐립니다.

⸻

최종 판정

판정

수정 후 채택입니다.

즉 지금 문서는 폐기할 수준이 아니라,
이제 바로 구현 가능한 수준까지 왔습니다.
다만 아래 3가지를 추가로 못 박고 들어가야 합니다.
	1.	A와 B의 penalty 역할 분리
	2.	300/400/600 운영 의사결정 문구 강화
	3.	report 최상위 경고를 limb collapse 우선으로 코드 강제

⸻

개발/훈련 AI에게 바로 줄 보완 지시문

아래처럼 보내면 됩니다.

⸻

현재 V25_PLAN.md 방향에는 동의합니다.
다만 구현 전에 아래 3가지를 더 명확히 고정하고 싶습니다.
	1.	V25-A / V25-B penalty 역할 분리
	•	V25-A는 일반 구조 검증이 목적이므로 existence floor는 일반화된 항목(per_leg_contact_floor_penalty 또는 per_leg_propulsion_floor_penalty) 중심으로 갑니다.
	•	V25-B는 direct-fix 실험이므로 rear_left_contact_floor_penalty를 추가합니다.
	•	A와 B에서 일반 penalty와 RL 특화 penalty가 동시에 full-strength로 중첩되지 않도록 분리해주세요.
	2.	운영 중단 기준 문구 강화
	•	iter 300~399: collapse reason 지속 시 기본 중단 권고
	•	iter 400~599: 중단 기본값, 특별 사유 없으면 계속 금지
	•	iter 600+: 즉시 중단
현재 문서의 strong fail / abort 후보를 실제 stop decision 기준으로 더 명확히 반영해주세요.
	3.	리포트 최상위 경고 우선순위 강제
	•	rear_left_contact_collapse(...) 또는 single-limb collapse가 있으면 report 최상단 CRITICAL로 항상 먼저 출력
	•	reward / survival / ep_len은 그 아래 secondary summary로 내려주세요

이 3가지를 반영하면 V25_PLAN.md는 바로 구현 기준 문서로 채택하겠습니다.

⸻

한 줄로 정리하면,
이번 개발담당 의견 반영본은 방향이 맞고 채택 가능하지만, A/B penalty 역할 분리와 중단 기준, 리포트 경고 우선순위를 더 강하게 못 박아야 합니다.

- - -

## 개발담당 재검토 의견 — G V2 피드백에 대한 반론

> 작성: Claude Sonnet 4.6 / 2026-03-14
> 목적: G V2 피드백 3가지에 동의하는 부분과 반론을 명시. 구현 전 최종 조율 근거로 사용.

---

### R1. G2-F2 반론 — iter 400+ 자동 stop은 조건 없이 적용하면 너무 이름

G V2는 iter 400~599를 "중단 기본값, 특별 사유 없으면 계속 금지"로 강화하고 자동 stop을 권장했다.

**반론**: V25는 V24와 달리 패널티를 iter 0부터 적용한다. 이 경우 iter 300~400 구간에서 `contact_ratio_rl`이 0.03 → 0.08로 **상승 중인** run도 존재할 수 있다. 이 상태에서 정적 threshold만으로 자동 stop하면 회복 가능했던 run을 자르는 결과가 된다.

V24에서 400 이후 회복 가능성이 0에 가까웠던 것은 패널티 시작이 너무 늦었기 때문이다. V25는 전제가 다르므로 자동 stop 조건에 **추세 체크**가 반드시 포함되어야 한다.

**수정 제안**:

| iter | 조건 | 동작 |
|------|------|------|
| 300~399 | collapse reason 지속 | Telegram 중단 권고 알림 — 사람 판단 |
| 400~599 | `contact_ratio_rl < 0.05` AND 최근 5 heartbeat 상승 추세 없음 | heartbeat 자동 stop |
| 400~599 | `contact_ratio_rl < 0.05` AND 상승 추세 있음 | 중단 보류, 100 iter 후 재판정 |
| 600+ | collapse 지속 | 무조건 즉시 stop |

---

### R2. G2-F1 반론 — `per_leg_contact_floor_penalty`와 `rear_left_contact_floor_penalty`의 기능 차이가 실제로 거의 없음

G V2는 V25-A를 "일반 existence floor", V25-B를 "RL 특화 direct-fix"로 역할 분리했다.

**반론**: `per_leg_contact_floor_penalty`를 per-leg으로 구현하면, RL만 붕괴된 상황에서 다른 세 다리는 contact_ratio가 정상이라 gap≈0이다. 결국 패널티는 RL에만 집중되며, `rear_left_contact_floor_penalty`와 **RL에 주는 gradient 신호가 사실상 동일**하다.

즉 A/B를 "일반 vs 특화"로 나눠도 학습 관점에서 실질적 차이가 없을 수 있다. 이렇게 되면 A가 실패한 후 B를 돌리는 것은 시간 낭비다.

**수정 제안**: V25-B의 역할을 재정의한다.

- **V25-A**: `per_leg_contact_floor_penalty` (일반) + diagonal coupling soft gate + validity fast-ramp. 충분히 강한 weight로 시작.
- **V25-B**: A와의 실질적 구조 차이가 있는 변형으로 재정의. 예:
  - diagonal coupling gate threshold 변경 (0.20 → 0.10으로 강화)
  - validity ramp 완전 제거 (iter 0부터 full-weight)
  - `restart-on-collapse` 기준 완화 (iter 300 → iter 200)

A와 B의 차이가 "같은 penalty를 일반 vs 특화로 나눈 것"이 아니라 **설계 가설이 다른 비교 실험**이 되어야 한다.

---

### R3. G2-F3 부분 동의 및 보완 — CRITICAL 알림의 observe 구간 오발 가능성

G V2의 "limb collapse 시 report 최상단 CRITICAL 강제" 방향은 맞다.

**단 한 가지 문제**: iter 0~99 observe 구간에서는 패널티도 없고 contact가 형성되기 전이다. 이 구간에서도 `contact_ratio_rl < threshold`이면 CRITICAL이 발생하여 false alarm이 반복된다.

**수정 제안**: CRITICAL 출력을 iter/stage로 gating한다.

| iter | collapse 감지 시 출력 |
|------|---------------------|
| 0~99 (observe) | 기록만, 알림 없음 |
| 100~199 (early_warning) | `[WARNING] limb collapse 감지` — heartbeat 상단 |
| 200~299 (provisional_fail) | `[CRITICAL] single-limb collapse` — 최상단, 굵게 |
| 300+ (strong_fail / enforce) | `[CRITICAL] collapse 지속 — 중단 검토` + 자동 판정 로직 연동 |

이 gating 없이 무조건 CRITICAL을 출력하면 초반 warming-up 구간에서 노이즈가 쌓여 실제 중요한 경고가 묻힌다.

---

### R4. 미해결 항목 — V25-A 실패 시 V25-B 전환 트리거 (G V2 미답변)

G V2 피드백에서 이 항목은 다루어지지 않았다. 하지만 구현에서 반드시 결정이 필요한 사항이다.

V25-A를 먼저 실행하고 실패하면 V25-B로 전환하는 구조라면, **언제 A를 포기하는지 기준**이 없으면 또 "조금 더 지켜보자"가 반복된다.

**제안 기준**:

> iter 200 시점에서 `contact_ratio_rl < 0.05` AND `swing_time_rl > 0.95` → V25-A 즉시 중단 → V25-B로 재시작

이 기준을 heartbeat 자동 판정에 포함시켜야 한다.

---

### 재검토 요약

| # | G V2 제안 | 동의 여부 | 수정 내용 |
|---|----------|----------|----------|
| G2-F1 | A/B penalty 역할 분리 | 부분 동의 | per-leg 구현 시 기능 차이 없음 → B를 구조적 차이 실험으로 재정의 |
| G2-F2 | 400+ 자동 stop | 부분 동의 | 추세 체크 조건 추가 필요 |
| G2-F3 | CRITICAL 최상단 강제 | 동의 | iter 100+ 이후부터만 적용, stage별 gating |
| R4 | (미답변) | — | A→B 전환 트리거 iter 200 기준 명시 필요 |
