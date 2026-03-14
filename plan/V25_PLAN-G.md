# V25_PLAN-G — Validity-First Structural Redesign for SpotMicro RL

> 작성일: 2026-03-14
> 작성 목적: V23/V24 실패 분석을 바탕으로, 다음 학습 버전(V25)을 **튜닝 강화판이 아니라 구조 재설계판**으로 정의하기 위함.
> 작성 원칙: 좋게 해석하지 않음. 시간 낭비를 막기 위해 **중단 / 유지 / 수정 / 폐기** 관점으로만 판단함.

---

## 0. Executive Summary

### 최종 결론

- **V23는 실패 정책이었음.** reward, survival, episode length는 높았지만 실제로는 rear-left 미사용 3족 exploit였음.
- **V24는 계측/진단 체계는 성공했지만, 학습 제어는 실패했음.** rear-left collapse를 숫자로 정확히 잡아냈으나, iter 2000에서도 행동을 바꾸지 못했음.
- 따라서 **V25는 “penalty 조금 더 세게” 수준이 아니라, validity-first 구조 재설계가 필요함.**
- V25의 1순위 목표는 posture/style이 아니라 **“네 다리를 실제로 다 쓰게 만드는 것”**임.

### 한 줄 정의

> **V25는 reward 증가형 locomotion 실험이 아니라, single-limb collapse를 초반부터 차단하는 validity-constrained quadruped learning 실험임.**

---

## 1. 현재까지의 실패 사실 정리

### 1.1 V23 / V24에서 이미 확인된 사실

1. `rear-left (RL)` limb collapse는 **적어도 iter 600 시점에는 이미 형성**되어 있었음.
2. RL collapse는 후반부 style 문제나 jitter 문제가 아니라, **초기부터 잘못된 해법으로 수렴한 exploit**임.
3. V24에서 validity-first 설계(새 KPI, gate, penalty)를 넣었지만, **iter 2000에서도 RL은 거의 사용되지 않았음.**
4. 따라서 병목은 센서, export, reason 출력이 아니라 **학습 objective가 실제 정책 행동을 못 바꾼 것**임.

### 1.2 중요 수치

#### V24 iter 2000 기준
- `contact_ratio_rl ≈ 0.00026`
- `stance_time_rl ≈ 0.00026`
- `swing_time_rl ≈ 0.992942`
- `propulsion_rl ≈ 0.000156`
- `limb_usage_rl ≈ 0.000052`

반면 같은 시점:
- `contact_ratio_fl ≈ 0.903`
- `contact_ratio_fr ≈ 0.588`
- `contact_ratio_rr ≈ 0.859`

즉, **RL만 사실상 공중 스윙 상태로 고정**되어 있으며, 나머지 세 다리로 보행하는 형태임.

### 1.3 이번 실패의 정확한 의미

- hard safety 관점에서는 살아남음
- locomotion core 관점에서는 전진/리듬/보상도 높음
- 그러나 **quadruped validity 관점에서는 실패**임

따라서 앞으로는 다음 원칙을 고정함.

> reward, episode length, survival이 높아도 **single-limb collapse가 있으면 실패 정책으로 간주**함.

---

## 2. V25의 목표 재정의

## 기존 목표(잘못된 우선순위)
1. reward 상승
2. ep_len 상승
3. trot/diagonal coupling
4. posture/style

## V25 목표(새 우선순위)
1. **네 다리 모두 실제 접지/추진에 참여할 것**
2. **single-limb collapse가 없을 것**
3. **좌우 / rear 비대칭이 과도하지 않을 것**
4. 그 다음 compact stance / shoulder style
5. 그 다음 distal jitter / aesthetic refinement

### V25 성공 기준
V25는 아래 조건을 모두 만족해야만 성공으로 간주함.

- `hard_safety_gate_pass = true`
- `limb_validity_gate_pass = true`
- 특정 다리의 `contact_ratio`, `propulsion`, `limb_usage`가 collapse되지 않음
- front/rear 좌우 대칭이 과도하게 무너지지 않음
- 그 이후에만 posture/style을 검토함

---

## 3. V25 설계 철학

### 3.1 튜닝 강화판이 아니라 구조 재설계판

V24는 본질적으로 “validity penalty를 추가한 튜닝 강화판”이었음. 그러나 결과적으로 행동을 바꾸지 못했음.

따라서 V25는 다음 둘 중 **B안**으로 설계함.

- **A안 (폐기)**: 기존 구조 유지 + penalty/ramp만 조금 더 강화
- **B안 (채택)**: reward 중심부에 **support participation / limb validity**를 더 직접적으로 반영하는 구조 재설계

### 3.2 핵심 철학

- **contact/stance participation은 reward 주변부가 아니라 핵심 제약**이어야 함
- swing/lift/clearance는 support 없이 단독으로 usage로 인정하면 안 됨
- “발을 들고 있는 것”은 usage가 아니라, **실제 접지와 추진이 있을 때만 유효한 사용**으로 봄
- validity는 나중 correction이 아니라 **초기 탐색부터 제어되는 objective**여야 함

---

## 4. 유지 / 수정 / 폐기 판단

### 4.1 유지할 것

다음 항목은 V25에서도 유지함.

#### 운영/리포트 계층
- heartbeat / supervisor 운영 체계
- workbook / run log / checkpoint review 구조
- front / side / rear / top / overview clip 생성
- raw posture/style/jitter export
- limb-wise KPI export
- limb validity gate / reason 출력 구조

#### locomotion core
- trot reward
- diagonal coupling
- forward velocity reward
- leg lift
- foot clearance
- flat orientation
- 기본 smoothness penalties
- STAND → WALK → TROT 메인 curriculum 골격

이유: locomotion core 자체는 이미 형성 가능함. 지금 병목은 validity임.

### 4.2 수정할 것

#### validity 관련 objective
- `limb_usage_min_penalty`
- `rear_left_right_usage_diff_penalty`
- usage proxy 정의
- gate 운영 시점
- abort / restart 기준

#### 새로 추가할 가능성이 높은 항목
- `support_phase_min_participation_penalty`
- `per_leg_propulsion_floor_penalty`
- `single_limb_collapse_penalty`
- 필요 시 `rear_left_specific_emergency_penalty` (단, 일반화 가능성 훼손 여부 주의)

### 4.3 폐기할 것

아래 접근은 V25에서 폐기함.

- “reward 높으니 더 돌려보자”식 판단
- iter 1000+까지 validity fail인데도 계속 관찰만 하는 운영
- contact 없이 lift/clearance가 높으면 usage로 인정하는 proxy
- posture/style을 validity보다 앞세우는 해석

---

## 5. V25 핵심 구조 변경안

## 5.1 Validity objective를 3층 구조로 분해

### Layer A — Single-limb existence floor

목적:
- 어떤 한 다리라도 완전히 사라지는 해법을 원천 봉쇄

후보 항목:
- `limb_usage_min_penalty`
- `single_limb_collapse_penalty`

정의 원칙:
- 네 다리 중 최저 usage가 floor 미만이면 큰 penalty
- usage는 swing만으로 유지되지 않고, **contact/stance/propulsion이 같이 있어야 살아남음**

### Layer B — Left-right symmetry guard

목적:
- 특정 축(특히 rear pair)에서 비대칭 exploit 방지

후보 항목:
- `rear_left_right_usage_diff_penalty`
- `rear_left_right_propulsion_diff_penalty`

정의 원칙:
- RL vs RR 사용률 차이가 크면 강하게 벌점
- 단, 이 penalty는 `limb_usage_min_penalty`보다 항상 약하게 유지

### Layer C — Support participation constraint

목적:
- 실제 stance/support phase에 최소 참여를 강제

후보 항목:
- `support_phase_min_participation_penalty`
- `per_leg_contact_floor_penalty`
- `per_leg_propulsion_floor_penalty`

정의 원칙:
- stance/contact/propulsion이 실제로 없으면 usage가 자동 붕괴
- “공중에서 흔들기”는 사용으로 인정하지 않음

---

## 5.2 추천 Reward 구성

### A. 유지
- trot / diagonal / forward velocity / orientation / smoothness는 유지

### B. 강화
- `limb_usage_min_penalty` → **주력 penalty**
- `rear_left_right_usage_diff_penalty` → **보조 penalty**

### C. 신규 도입 권고

#### 1) `support_phase_min_participation_penalty`
목적:
- 다리마다 최소 stance/contact 참여를 요구

권장 이유:
- 현재 실패는 usage collapse보다 더 직접적으로 “support phase 부재”임
- RL은 `swing_time≈1`, `stance≈0`, `contact≈0`, `propulsion≈0`
- 이를 가장 잘 겨냥하는 제약이 필요함

#### 2) `per_leg_propulsion_floor_penalty`
목적:
- 접지만 하고 실제 추진이 없는 다리도 막음

권장 이유:
- 향후 contact는 살아도 propulsion이 0인 편법으로 바뀔 수 있음
- contact만으로는 부족할 수 있으므로 propulsion floor가 유효함

### D. 비권장
- posture/style weight를 지금 더 올리는 것
- distal jitter penalty를 지금 강하게 넣는 것

이유: 현재 병목은 validity이고, posture/jitter는 후순위임.

---

## 6. V25 penalty weight 제안

### 6.1 기본 원칙

- `min_usage` 계열 > `rear_diff` 계열 > style penalty
- validity penalty는 시작부터 ON
- 단, 완전 full-strength 즉시 적용은 locomotion bootstrap을 과하게 망칠 수 있으므로 **초기 약적용 + 매우 빠른 ramp** 사용

### 6.2 제안 값 (초안)

#### 1) `limb_usage_min_penalty`
- iter 0~100: **-6.0**
- iter 100~300: 선형 ramp to **-16.0**
- iter 300+: **-16.0** 유지

#### 2) `rear_left_right_usage_diff_penalty`
- iter 0~100: **-3.0**
- iter 100~300: 선형 ramp to **-10.0**
- iter 300+: **-10.0** 유지

#### 3) `support_phase_min_participation_penalty` (신규 추천)
- iter 0~100: **-4.0**
- iter 100~300: 선형 ramp to **-14.0**
- iter 300+: **-14.0** 유지

#### 4) `per_leg_propulsion_floor_penalty` (신규 보조)
- iter 0~100: **-2.0**
- iter 100~300: 선형 ramp to **-6.0**
- iter 300+: **-6.0** 유지

### 6.3 왜 기존보다 더 세게 가나

V24는:
- `limb_usage_min_penalty`: -3 → -12
- `rear_diff_penalty`: -2 → -8
- 0~200 고정, 200~600 ramp

이었음.

그러나 RL collapse는 **600 이전에 이미 굳었고**, V24는 이를 못 막았음. 따라서 V25는:
- 더 이른 시점
- 더 강한 초기 압력
- support 참여 직접 제약
이 필요함.

---

## 7. Curriculum / Ramp 운영안

## 결론
**기존 메인 gait curriculum과 별도로, validity 전용 fast-ramp를 독립 운용**함.

### 7.1 메인 gait curriculum
- 기존 STAND → WALK → TROT 구조 유지
- 다만 validity가 먼저 망가지면 이 curriculum 성공은 무의미함

### 7.2 validity fast-ramp

#### 제안
- iter 0~100: 약적용
- iter 100~300: 빠른 ramp
- iter 300+: full-strength 유지

### 이유
- collapse는 iter 600 이전에 이미 형성됨
- 200~600도 늦었음
- 따라서 V25는 **0~300 사이에 exploit를 꺾는 것**이 목표여야 함

---

## 8. Gate / Shortlist 운영안

## 8.1 hard_safety_gate

### 운영
- iter 0부터 계산/로그
- iter 200부터 후보 평가에 반영

### 의미
- 넘어짐/critic 불안정/ep_len 붕괴를 잡는 기본 gate

## 8.2 limb_validity_gate

### 운영
- iter 0부터 계산/로그
- iter 100부터 early warning
- iter 200부터 provisional exclusion
- iter 300~400부터 strong exclusion
- iter 600까지 fail 지속이면 **abort**

### reason 문구 우선순위
Generic한 문구보다 아래를 우선 출력함.

1. `rear_left_contact_collapse(c=...,s=...,p=...)`
2. `single_limb_usage_collapse(leg=RL,usage=...)`
3. `rear_left_right_usage_diff_excess(...)`
4. `rear_left_right_propulsion_diff_excess(...)`
5. 그 다음에야 generic contact/usage fail 문구

## 8.3 shortlist

### iter < 100
- 기록만 함
- candidate 판단 안 함

### iter 100~199
- early warning만
- provisional candidate 없음

### iter 200~399
- provisional shortlist 허용
- 조건: `hard_safety_gate_pass = true` AND `single-limb collapse reason 없음`

### iter 400~599
- validity fail 지속 시 candidate 제외
- “exploit 고착 중” 경고

### iter 600+
- 정식 shortlist 조건:
  - `hard_safety_gate_pass = true`
  - `limb_validity_gate_pass = true`

---

## 9. Abort / Restart 기준

## 운영 원칙
이번에는 애매하게 보지 않음. **시간 낭비 가능성이 보이면 중단**함.

### iter 100
- RL collapse reason 등장 시 **early warning**
- 단, 즉시 abort는 하지 않음

### iter 200
- single-limb collapse reason 지속 시 **provisional fail**
- shortlist 제외
- penalty/ramp 상태 점검 플래그 발생

### iter 300~400
- collapse reason 지속 + `usage_rl ≈ 0`이면 **strong fail**
- 계속 학습해도 exploit가 굳을 가능성 높음

### iter 600
아래 조건이면 **즉시 abort / restart**
- `rear_left_contact_collapse(...)` 지속
- `limb_usage_rl < 0.10`
- `contact_ratio_rl < 0.05`
- `propulsion_rl < floor`

### iter 600+ 이후
- 위 상태가 유지되는데도 계속 학습하는 것은 **원칙적으로 금지**

---

## 10. KPI / Diagnostics 운영안

## 10.1 최우선 KPI

### per-leg contact / support
- `contact_ratio_fl/fr/rl/rr`
- `stance_time_fl/fr/rl/rr`
- `swing_time_fl/fr/rl/rr`
- `propulsion_fl/fr/rl/rr`
- `limb_usage_fl/fr/rl/rr`

### derived
- `limb_usage_min`
- `rear_left_right_usage_diff`
- `rear_left_right_propulsion_diff`

## 10.2 운영 관점에서 가장 먼저 볼 수치
매 iter checkpoint clip/report에서 가장 먼저 보는 값은 아래로 고정.

1. `contact_ratio_rl`
2. `propulsion_rl`
3. `limb_usage_rl`
4. `swing_time_rl`
5. `rear_left_right_usage_diff`
6. `limb_validity_reason`

## 10.3 posture/style는 후순위
- stance width
- shoulder deviation
- posture_style_score

이 값들은 validity 통과 후에만 의미 있게 봄.

---

## 11. V25 실험 설계

## Run A — Validity Core

### 목적
- single-limb collapse 제거가 가능한지 확인

### 포함
- 강화된 `limb_usage_min_penalty`
- 강화된 `rear_left_right_usage_diff_penalty`
- 신규 `support_phase_min_participation_penalty`
- 신규 `per_leg_propulsion_floor_penalty`
- validity fast-ramp

### 제외
- posture/style weight 상향
- distal jitter 강화

### 성공 조건
- iter 200~400에서 RL collapse reason 사라짐
- iter 600까지 limb_validity_gate_pass = true

## Run B — Validity + Posture

Run A 성공 시에만 진행.

### 목적
- compact stance / shoulder style refinement

### 포함
- Run A 유지
- stance width / shoulder style 미세조정

## Run C — Validity + Posture + Jitter

Run B 성공 시에만 진행.

### 목적
- aesthetic refinement

---

## 12. 실무 판단 기준

### 유지
- 4발 사용이 성립하고 있으며, collapse reason이 없음

### 수정
- validity는 대체로 성립하나, 비대칭이 경계선 수준으로 남아 있음

### 중단
- iter 300~600 구간에서 single-limb collapse가 지속됨

### 폐기
- reward는 높지만 4발 validity가 무너진 정책

---

## 13. 최종 권고안

## 최종 결론: **구조 재설계 + 새 런 시작**

V25는 아래처럼 진행해야 함.

1. **현재 V24 current run은 폐기**
2. **V25는 validity-first 구조 재설계판으로 새로 시작**
3. penalty는 더 세게, 더 빠르게, 더 직접적으로 적용
4. single-limb collapse는 600 이전에 반드시 차단
5. posture/style은 validity 성공 이후에만 다룸

### 명확한 판정
- **유지:** 아니오
- **수정:** 부분 수정 수준 아님
- **폐기:** V24 current run은 폐기
- **구조 재설계:** 예, V25는 구조 재설계가 필요

---

## 14. 즉시 실행 항목

### 개발/훈련 담당 AI에게 전달할 핵심
1. V25는 tuning 강화판이 아니라 구조 재설계판임
2. validity fast-ramp를 0~300 중심으로 재설계할 것
3. support participation과 propulsion floor를 직접 penalty에 포함할 것
4. iter 600 validity fail이면 무조건 abort
5. reward, ep_len, survival보다 single-limb collapse 여부를 최우선 판단 기준으로 둘 것

---

## 15. 부록 — V25에서 절대 하지 말 것

- reward가 높으니 더 돌려보기
- iter 1000+까지 validity fail인데 계속 관찰하기
- posture/style를 validity보다 먼저 논의하기
- contact 없이 lift/clearance만으로 usage를 인정하기
- generic failure reason만 출력하기

---

## 최종 한 줄

> **V25는 “더 잘 걷게 하자”가 아니라, “rear-left를 버리는 해법이 초반부터 절대 살아남지 못하게 하자”는 설계여야 함.**
