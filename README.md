# spot_micro_rl

SpotMicro 기반 4족보행 로봇의 **강화학습(RL) 보행 정책 연구 프로젝트**입니다.  
이 저장소는 단순 결과물 보관용이 아니라, **가설 → 구현 → 실험 → 분석 → 교훈**을 지속적으로 축적하는 **연구형/실험형 프로젝트**를 목표로 합니다.

---

## 1. 프로젝트 목적

이 프로젝트의 목적은 다음과 같습니다.

- SpotMicro 계열 4족보행 로봇에서 **실제로 배치 가능한(deployable)** RL 보행 정책을 만드는 것
- 단순히 “걷는다”가 아니라, 아래 조건을 만족하는 보행을 만드는 것
  - **안정적 부팅**
  - **자연스러운 보행**
  - **앞/뒤 다리 균형**
  - **과도한 nose-down, torsion, front-overload 억제**
  - **실기체 적용 가능성**
- 실험 과정에서 나온 **성공/실패 가설과 코드 변화, 결과 해석**을 문서화해 다음 구현자에게 재사용 가능한 자산으로 남기는 것

---

## 2. 이 저장소의 성격

이 저장소는 일반적인 “완성된 제품 코드 저장소”가 아닙니다.  
다음 두 가지가 함께 존재합니다.

1. **실제 학습/실험 코드**
2. **버전별 계획서, 분석 문서, 실패 기록, 교훈 정리**

즉 이 저장소는 아래 성격을 갖습니다.

- **운영 가능한 코드 저장소**
- **연구 로그 저장소**
- **의사결정 근거 저장소**

따라서 `plan/` 폴더는 부가 자료가 아니라, 프로젝트 이해에 핵심입니다.

---

## 3. 현재 프로젝트 운영 원칙

현재 프로젝트는 아래 원칙을 중심으로 진행합니다.

### 3.1 baseline-first
새 구조를 넣기 전에, 먼저 **부팅/기본 보행 baseline**이 살아 있어야 합니다.

### 3.2 mechanics-first
성공 기준을 단순 `stride`, `timeout`으로 두지 않고, 아래를 같이 봅니다.

- front/rear balance
- body posture stability
- deployability
- nose-down / torsion / front-overload 억제

### 3.3 standard-locomotion-first
복잡한 heuristic reward 누적 대신, 가능한 한 **Isaac Lab / ANYmal / Walk These Ways** 계열의
**표준 locomotion 구조**를 우선 참고합니다.

### 3.4 patch-loop 최소화
문제가 생길 때마다 reward를 계속 덧붙이는 방식은 지양합니다.  
가능하면:

- baseline 재정의
- success criteria 재정의
- 구조 전환

을 먼저 검토합니다.

---

## 4. 현재 상태 (V60)

**서기 성공 → From-Scratch 보행 학습 → 비대칭 Exploit 교정 중** (2026-04-06)

### V59: 서기 학습 성공

| 지표 | 결과 |
|------|------|
| 생존율 (timeout) | 100% |
| 4발 접지율 | 99.9% |
| 수평 유지율 | 99.8% |
| 목표 높이 달성 | 96% |

### V59.D: 서기→보행 전환 시도 (실패)
- 서기 정책이 너무 강해 보행으로 전환 불가
- curriculum 복원 버그 발견 (저장된 reward weight가 env_cfg를 덮어씀)

### V60: From-Scratch 보행 학습

| 버전 | 결과 | 문제 |
|------|------|------|
| V60.A | 생존 100%, tracking 96%, 약간 전진 | RR(오른뒤) 비대칭 exploit — 1발만 98% 공중 |
| V60.B | penalty -3.0 추가 | 효과 부족 (cr_RR 2%→3.3%) |
| V60.C | penalty -10.0 + rear balance -5.0 | **RR 교정 성공** (cr_RR 0.03→0.997) |
| V60.D | gait incentive 강화 + static bias 약화 | no-go: 앞다리만 swing, 뒷다리 고착 |
| V60.E | rear 전용 clearance + static bias 제거 | **진행 중** |

핵심 설정:
- **URDF 질량**: 1.41kg (원본 5.3kg에서 실물 기준 수정)
- **merge_fixed_joints=False** (True면 toe contact reporting 불가)
- **ImplicitActuator** stiffness=20, damping=0.5
- **서보 기준**: STS3215 (30kg·cm, 12V)

### 추천 읽기 순서

1. **이 README**
2. **`plan/V60_PLAN.md`** (현재 active 버전)
3. `plan/V59_PLAN.md` (서기 학습 상세)
4. `plan/README.md` (V1~V59 전체 히스토리)

---

## 5. 현재 유효한 접근 / 폐기된 접근

### 현재 유효한 접근
- **from-scratch 보행**: 서기 선행 없이 처음부터 동적 균형+보행을 동시에 학습
- **실물 기준 URDF**: 질량 1.41kg, STS3215 서보 스펙
- **merge_fixed_joints=False**: toe contact reporting 보장
- **per-leg exploit 교정**: 비대칭 사용을 직접 penalty (contact_min, excess_swing, rear_balance)
- **curriculum 복원 자동 skip**: 버전 변경 resume 시 env_cfg 우선
- standard locomotion reward 구조 우선
- success criteria에 deployability 포함

### 현재 주의 깊게 다루는 접근
- ImplicitActuator → DCMotor 전환 (Sim2Real)
- penalty weight는 reward budget 대비 수치 검증 필수
- 서기→보행 전환 vs from-scratch (from-scratch가 더 효과적으로 확인됨)

### 현재 폐기 또는 경계하는 접근
- merge_fixed_joints=True (contact reporting 불가)
- URDF 원본 질량 그대로 사용 (5.3kg, 실물의 3.2배)
- action_scale과 zero-action stability 미검증 상태로 학습 시작
- reward patch 무한 누적
- stride/timeout만으로 성공 판정
- **서기→보행 resume 전환** (정적 균형이 동적 균형으로 전이 안 됨)

---

## 6. 성공 기준

이 프로젝트에서 “성공”은 단순히 걷는 것이 아닙니다.
최소한 아래를 함께 만족해야 합니다.

### 서기 (V59 달성)
- 4발 접지 유지 (98%+)
- 몸체 수평 유지 (pitch < 5°)
- 목표 높이 유지 (205mm 근처)
- 발을 떼지 않고 관절 미세 조정으로 균형 유지

### 보행 (다음 목표)
- 서기에서 자연스럽게 보행 전환
- front/rear 사용이 한쪽으로 심하게 무너지지 않음
- 실기체 적용 관점에서 과도한 front-overload / torsion / nose-down이 없음
- STS3215 서보 (3Nm) 한계 내에서 동작

즉,
**”움직인다”보다 “실제로 쓸 수 있는 gait인가”를 더 중요하게 봅니다.**

---

## 7. 문서 해석 시 주의

버전 문서가 많기 때문에, 아래를 항상 구분해야 합니다.

- **현재 유효한 기준**
- **과거에 시도했지만 폐기된 접근**
- **특정 버전에서만 유효했던 로직**

과거 문서는 매우 중요하지만, 자동으로 현재 정답이 되지는 않습니다.  
항상 최신 기준 문서와 함께 해석해야 합니다.

---

## 8. 디렉토리 안내

### `plan/`
버전별 계획, 분석, 연구 메모, 히스토리 문서가 모여 있습니다.  
이 프로젝트를 이해하려면 가장 중요한 폴더입니다.

### 학습/환경 코드
실제 RL 실험 환경, reward, curriculum, locomotion 관련 구현이 포함됩니다.

### 기타 운영/보조 코드
로그 수집, 분석, 실험 보조 스크립트 등이 포함될 수 있습니다.

---

## 9. 이 프로젝트를 보는 가장 좋은 관점

이 프로젝트를 “왜 이렇게 문서가 많지?”라는 관점보다,  
다음처럼 보는 것이 맞습니다.

> 이 프로젝트는 SpotMicro RL 보행 문제를 두고  
> **어떤 가설을 세웠고, 어떻게 구현했고, 왜 실패했고, 무엇을 교훈으로 남겼는지**를 함께 보존하는 연구형 저장소다.

즉 코드만 보는 것보다,
**코드 + plan 문서 + 분석 결과**를 같이 읽어야 전체가 보입니다.

---

## 10. 앞으로 문서를 추가할 때 권장 사항

새 문서를 추가할 때는 가능하면 아래를 명확히 남깁니다.

- 가설
- 변경 코드/파라미터
- 기대 효과
- 실패 기준
- 성공 기준
- 결과
- 다음 버전으로 넘어가는 이유

이 7개가 남으면, 이후 AI 협업이나 사람 협업 모두에서 해석 비용이 크게 줄어듭니다.

---

## 11. V59~V60 핵심 교훈

### V59 교훈
1. **URDF 질량은 반드시 실물 기준 검증** — 원본 5.3kg은 실물 1.7kg의 3배
2. **merge_fixed_joints=True는 contact reporting을 깨뜨림** — SpotMicro에서는 반드시 False
3. **contact termination은 consecutive 판정 필수** — 1 step 판정은 진동으로 즉사
4. **curriculum 복원 버그** — resume 시 저장된 reward weight가 env_cfg를 덮어씀

### V60 교훈
5. **서기→보행 resume 전환은 비효율** — 정적 균형(서기)과 동적 균형(보행)은 완전히 다른 스킬
6. **from-scratch가 resume보다 나음** — V60.A가 V59.D보다 훨씬 좋은 결과
7. **1발 exploit** — feet_air_time이 1발만 들어도 보상 → 최소 비용 exploit 발생
8. **penalty는 reward budget 대비 수치 검증 필수** — -3.0은 양수 15에 비해 부족, -10 이상 필요
9. **exploit 교정은 간접(penalty)보다 직접(표적 타격)이 효과적** — rear pair balance가 전체 std보다 정확

---

## 12. 한 줄 요약

**spot_micro_rl은 SpotMicro 기반 4족보행 RL 연구 프로젝트이며, 실물 기반 물리 설정 위에서 from-scratch 보행 학습과 exploit 교정을 통해 실기체 배치 가능한 4족 보행 policy를 만드는 것을 목표로 합니다.**
