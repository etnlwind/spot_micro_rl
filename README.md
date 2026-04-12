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

## 4. 현재 상태 (V68)

**Reference Trajectory Tracking — 대칭 trot 달성** (2026-04-12)

### 핵심 성과: V68

V63~V67까지 **10개 이상의 reward 구조를 반복 실험**하며 밝혀낸 결론:
- "RL이 좋은 gait를 발견하게 하자" 접근은 **exploit whack-a-mole**로 수렴
- **이상적 trot을 먼저 정의하고, RL이 따라가게 하는** 것이 정답

### V68 접근

1. **V63.I**(역대 최고 보행 품질)의 실제 policy rollout 녹화
2. 궤적 분석 → **좌우 대칭화** (비대칭 89.9% 감소)
3. 대칭화된 reference joint trajectory 생성 (`ideal_trot_reference.json`)
4. **Reference tracking reward**(주연 w=10) + phase randomization
5. RL이 대칭화된 V63.I 궤적을 추적하며 학습

### V68 결과 (iter 2500 기준, 최적 체크포인트)

| 지표 | V63.I (이전 최고) | **V68** | 개선 |
|------|------|------|------|
| 대각 대칭 diff | 12.6%p | **1.5%p** | **8배** |
| stride | 4.35 | **4.40** | 동등+ |
| timeout | 99.95% | **100%** | ✅ |
| reward | 386 | **475** | +23% |
| GUI 품질 | FR/RR 이상 | **"보행 좋아 보인다"** | ✅ |

### 버전 히스토리 요약 (V59~V68)

| 버전 | 핵심 시도 | 결과 |
|------|------|------|
| V59 | 서기 학습 | 성공 (100% 생존, 99.9% 접지) |
| V60~V61 | from-scratch 보행 | exploit 패치 한계 |
| V62 | phase-gated propulsion | drag 차단 성공 |
| V63 (B~J) | trot 유도 reward 반복 실험 | V63.I = 보행 품질 최고 (대칭 부족) |
| V64 | mirror symmetry augmentation | phase 충돌 실패 |
| V65 | curriculum (true_trot→alternation) | 부팅 문제 |
| V66 | phase randomization | 대칭 개선, 후반 재발 |
| V67 | balance-gated true_trot | 대칭 ✅ stride ❌ |
| **V68** | **reference trajectory tracking** | **대칭 ✅ stride ✅ GUI ✅** |

### 핵심 교훈 (V1~V68)

1. **Reward를 더 추가하는 것은 한계가 있다** — exploit은 항상 새 길을 찾는다
2. **true_trot_pattern은 frozen diagonal을 보상한다** — 시간축 교대를 측정하지 않음
3. **대칭은 reward가 아닌 구조로 해결해야 한다** — phase randomization + reference tracking
4. **이미 작동하는 policy에서 reference를 추출**하면 동역학적으로 유효한 궤적을 얻을 수 있다
5. **시뮬레이터를 적극 활용**하면 설계→검증→수정 사이클을 빠르게 돌릴 수 있다

### Best Checkpoint — `checkpoints/V68_model_2500_best.pt`

저장소에 정식으로 보존된 **유일한 "deployable" checkpoint**입니다.

| 항목 | 값 |
|------|------|
| 파일 경로 | `checkpoints/V68_model_2500_best.pt` |
| 파일 크기 | 4,682,677 B (≈4.47 MB) |
| 포맷 | rsl_rl PPO checkpoint (`model_state_dict` + `optimizer_state_dict` + `iter`) |
| 원본 run | `logs/rsl_rl/spot_micro_flat/2026-04-12_12-26-08_V68/model_2500.pt` |
| 훈련 iteration | 2500 / 5000 (전체 훈련의 50%) |
| 훈련 환경 | Isaac-Velocity-Flat-SpotMicro-v0 |
| num_envs | 4096 |
| 훈련 버전 | V68 (Reference Trajectory Tracking) |
| Reference 파일 | `logs/ideal_trot_reference.json` (V63.I rollout 대칭화, 7.1 KB, 25 steps × 12 joints × 2 series) |
| Observation | 48-dim (Isaac Lab flat locomotion 표준 + phase randomization) |
| Action | 12-dim (joint position target, shoulder/leg/foot × 4) |
| Actuator | ImplicitActuator (stiffness=20, damping=0.5) |
| URDF | 실물 기준 질량, `merge_fixed_joints=False` |
| Gait frequency | 2.00 Hz (cycle = 25 steps × 20ms dt) |

#### 왜 `model_2500`인가 (model_4999 아님)

V68 훈련은 5000 iteration을 완주했지만, 학습 추이를 보면 **중간 iter 2000~2500 구간이 가장 좋습니다**.

```
iter  550: 대칭 1.7%p, stride 3.58  (부팅 완료)
iter  962: 대칭 2.3%p, stride 4.39  (V63.I 초과!)
iter 1412: 대칭 2.0%p, stride 4.42  (안정)
iter 2236: 대칭 1.2%p, stride 4.38  (역대 최저 diff)
iter 2500: 대칭 1.5%p, stride 4.40  ← best checkpoint
iter 3372: 대칭 9.8%p, stride 4.41  (미세 상승)
iter 4014: 대칭 12.7%p, stride 1.55 (후반 편향 재발 + stride 하락)
```

후반(iter 3500+)에는 편향이 다시 나타나면서 stride도 떨어집니다. 즉 **완주 체크포인트(model_4999)가 최적이 아니기 때문에**, V68 훈련에서는 **중간 체크포인트 보존이 필수**입니다. `model_2500.pt`만 `checkpoints/` 폴더에 복사·커밋해 두었습니다.

#### 재생 방법 (Windows)

```cmd
:: 원본 run 경로로 재생
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt

:: 또는 저장소 보존본을 원본 위치로 복사 후 재생
copy checkpoints\V68_model_2500_best.pt logs\rsl_rl\spot_micro_flat\2026-04-12_12-26-08_V68\model_2500.pt
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt
```

내부적으로는 `scripts/rsl_rl/play.py`가 실행되며, 16 envs 기본으로 GUI에서 재생됩니다.

#### Resume 방법 (추가 훈련)

이 checkpoint에서 도메인 랜덤화·rough terrain 등 후속 실험을 이어가려면:

```cmd
resume.cmd 2026-04-12_12-26-08_V68 model_2500.pt 5000 V69.A
```

단, V68 훈련 자체가 iter 3500+에서 편향이 재발했기 때문에, 단순 resume만으로는 같은 문제가 반복될 수 있습니다. Domain randomization 같은 구조 변경과 함께 resume하는 것을 권장합니다.

#### Reference trajectory 파일

V68 reward가 참조하는 외부 데이터:

- **경로**: `logs/ideal_trot_reference.json`
- **원본**: V63.I model_4999에서 16 envs × 1000 steps rollout 녹화 (`scripts/record_v63i_trajectory.py`)
- **처리**: `scripts/analyze_trajectory.py`로 2.01 Hz 주기 탐지 → 25-step cycle 추출 → FL/RR ↔ FR/RL pair 대칭화 → **비대칭 89.9% 감소** (1.83 → 0.18)
- **내용**: 12개 joint(shoulder × 4, leg × 4, foot × 4)의 phase-normalized 25-step 궤적 + 원본 궤적
- **사용**: `reference_trot_tracking_reward`가 lazy load 후 매 step마다 linear interpolation해서 현재 phase의 목표 joint pose 계산

이 파일이 없으면 V68 훈련/재생이 불가능하므로, `logs/ideal_trot_reference.json`도 repo에 커밋된 상태입니다.

### 핵심 설정
- **URDF**: 실물 기준 질량, merge_fixed_joints=False
- **ImplicitActuator**: stiffness=20, damping=0.5
- **Phase randomization**: 연속 0~2π offset per env
- **Reference**: V63.I 대칭화 궤적 (25 steps/cycle, 2Hz)
- **서보 기준**: STS3215 (30kg·cm, 12V)

### 추천 읽기 순서

1. **이 README**
2. **`plan/V68_PLAN.md`** (최종 성공 버전 — reference tracking)
3. **`plan/V63_PLAN.md`** (V63 시리즈 + V64~V67 교훈 포함)
4. `plan/V59_PLAN.md` (서기 학습)
5. `plan/README.md` (V1~V68 전체 히스토리)

---

## 5. 현재 유효한 접근 / 폐기된 접근

### 현재 유효한 접근
- **Reference trajectory tracking**: 검증된 policy에서 궤적 추출 → 대칭화 → RL 학습 목표 (V68)
- **Phase randomization**: per-env random phase offset으로 대각 편향 초기 차단 (V66+)
- **from-scratch 보행**: 서기 선행 없이 처음부터 동적 균형+보행을 동시에 학습
- **실물 기준 URDF**: 실물 기반 질량, STS3215 서보 스펙
- **merge_fixed_joints=False**: toe contact reporting 보장
- success criteria에 대칭성 + GUI 품질 포함

### 현재 주의 깊게 다루는 접근
- **true_trot_pattern**: frozen diagonal exploit 보상 위험 → 주연으로 쓰면 안 됨 (V63~V67 교훈)
- reward 추가 전 반드시 **수치 검증** (reward budget 계산)
- **contact ratio만으로 대칭 판정 금지** — propulsion, foot placement, GUI도 동시 확인 (V67 교훈)

### 현재 폐기 또는 경계하는 접근
- **Reward patch 무한 누적** — exploit whack-a-mole로 수렴 (V63~V67에서 확인)
- **Mirror data augmentation** — phase clock과 충돌 (V64 실패)
- **Curriculum reward ramp** — 부팅 전 개입하면 서기 실패 (V65 실패)
- **Balance gate (balance_factor × true_trot)** — 대칭은 잡지만 stride 파괴 (V67 실패)
- merge_fixed_joints=True (contact reporting 불가)
- stride/timeout만으로 성공 판정
- 서기→보행 resume 전환 (정적→동적 전이 안 됨)

---

## 6. 성공 기준

이 프로젝트에서 “성공”은 단순히 걷는 것이 아닙니다.
최소한 아래를 함께 만족해야 합니다.

### 서기 (V59 달성)
- 4발 접지 유지 (98%+)
- 몸체 수평 유지 (pitch < 5°)
- 목표 높이 유지 (205mm 근처)
- 발을 떼지 않고 관절 미세 조정으로 균형 유지

### 대칭 Trot 보행 (V68 달성, iter 2500)
- 대각 대칭 diff **1.5%p** (V63.I 12.6%p → 8배 개선)
- stride **4.40** (V63.I 4.35 동등+)
- timeout **100%** (2000 steps 완주)
- gait frequency **2.00 Hz** 설계값 일치
- forward speed 0.308 m/s, lateral drift 0.003 m/s (1%)
- body height 0.240m ±0.005 안정, GUI "보행 좋아 보인다" 판정
- front/rear 사용 균형, nose-down/torsion 억제
- STS3215 서보 (3Nm) 한계 내 동작

### 다음 목표 (V68 이후)
- **Domain randomization** — push recovery, mass/friction 변동 적응
- **Rough terrain** — 경사/계단/요철 지형 일반화
- **Height scanner** — 장애물 인식 observation 추가
- **Sim-to-real** — 실기체 배치 검증

즉,
**"움직인다"보다 "실제로 쓸 수 있는 gait인가"를 더 중요하게 봅니다.**
V68에서 시뮬레이션 기준으로 이 조건들을 처음으로 동시에 만족했고, 이후 단계는 randomization/terrain/실기체로 확장하는 것입니다.

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

## 11. 한 줄 요약

**spot_micro_rl은 SpotMicro 기반 4족보행 RL 연구 프로젝트이며, 실물 기반 물리 설정 위에서 from-scratch 보행 학습과 exploit 교정을 통해 실기체 배치 가능한 4족 보행 policy를 만드는 것을 목표로 합니다.**

---

## 12. 라이선스

이 저장소는 **Apache License 2.0** 하에 공개됩니다.

- 전체 라이선스 원문: [`LICENSE`](LICENSE)
- 서드파티 고지 및 저작권: [`NOTICE`](NOTICE)
- 훈련 checkpoint 라이선스: [`checkpoints/README.md`](checkpoints/README.md)

```
Copyright 2026 Sangjin RYU
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
```

### 서드파티 고지 요약

- **NVIDIA Isaac Lab** (BSD-3-Clause) — `source/spot_micro_rl/` 디렉토리는 Isaac Lab extension template에서 파생. 원 저작권 헤더 유지.
- **rsl_rl** (BSD-3-Clause) — PPO 훈련 백엔드
- **NVIDIA Isaac Sim / Omniverse** (proprietary) — 시뮬레이터 자체는 재배포되지 않음. 사용자가 별도 설치 필요.
- **SpotMicroAI 커뮤니티** — URDF/STL 원본 출처. 이 repo는 질량·관성·joint limit만 수정.

자세한 내용은 [`NOTICE`](NOTICE) 파일을 참조하세요.

### 훈련 weights

`checkpoints/V68_model_2500_best.pt`와 `logs/ideal_trot_reference.json`은
본 저장소에서 훈련·생성된 원저작물로, 코드와 동일하게 **Apache-2.0**으로 공개됩니다.

---

## 13. 인용 (Citation)

연구/논문에서 이 저장소나 weights를 인용하실 경우 아래 정보를 사용해 주세요.
더 자세한 메타데이터는 [`CITATION.cff`](CITATION.cff)를 참조하세요.

**BibTeX**:

```bibtex
@software{ryu2026spotmicrorl,
  author  = {RYU, Sangjin},
  title   = {spot\_micro\_rl V68: Reference Trajectory Tracking for Symmetric Trot},
  year    = {2026},
  version = {V68},
  url     = {https://github.com/etnlwind/spot_micro_rl},
  license = {Apache-2.0}
}
```

**Plain text**:

> RYU, Sangjin. *spot_micro_rl V68: Reference Trajectory Tracking for Symmetric Trot* (Version V68). 2026. https://github.com/etnlwind/spot_micro_rl

---

## 14. 기여 (Contributing)

버그 리포트, 재현 실험, 새 버전 plan 제안 등 모든 기여를 환영합니다.
시작하시기 전에 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 읽어주세요.

기여를 제출하면, 해당 기여가 Apache-2.0 라이선스로 배포되는 것에 동의하는 것으로 간주됩니다.

---

## 15. 문의

- **Author**: Sangjin RYU (`etnlwind`)
- **Email**: etnlwind@gmail.com
- **Repository**: https://github.com/etnlwind/spot_micro_rl
