# V27_ANALYSIS.md

## V27 시리즈 한 줄 정의

**V27은 "4다리를 기능적으로 모두 쓰지 않으면 살아남지 못하는 정책"을 목표로 한 버전이다.**
V27.1a/1b는 그 강도 조정 실험이다.

---

## 1. 배경 — V26.1까지의 실패

### 반복된 실패 패턴 (V24~V26.1)

| 버전 | 실패 원인 |
|------|----------|
| V24 | RL contact ≈ 0, propulsion ≈ 0. 3족 exploit 고착. penalty가 교정이 아닌 회피를 유도함. |
| V25 | RR collapse. iter 400에서 조기 종료. 비대칭 패널티의 한계. |
| V26 | Exploratory run. Symmetric floor 첫 시도. uncommitted 코드, 결과 기반으로 V26.1 설계. |
| V26.1 | Symmetric floor + load sharing 강화. 구조적 개선이었으나 single-limb collapse 완전 차단에 실패. |

### 핵심 실패 원인 (V26.1까지 공통)

1. 초기 penalty가 너무 약해 collapse가 먼저 고착됨
2. floor 기준이 너무 낮아 fake contact 허용
3. soft gate 우회 가능
4. reward 구조상 3족 해법이 경제적으로 여전히 유리

### V26.1 run 정보

| run | TRAIN_VERSION | 최종 iter | 결과 |
|-----|--------------|----------|------|
| 2026-03-15_07-08-50 | V26.1 | 1,800 | single-limb collapse 차단 실패 |

---

## 2. V27 원본 PLAN

### 핵심 목표

- 4개 다리가 실제로 contact + propulsion에 참여
- single-limb collapse 금지
- 좌우/전후 propulsion 편중 억제
- **"잘 걷는 것"이 아니라 "4발 안 쓰면 못 사는 것"**

### 설계 원칙

1. Contact만으로는 충분하지 않음 — propulsion + usage 동시 확인
2. Single-limb collapse = 즉시 실패 신호
3. Reward보다 validity가 상위 조건
4. 초기 200~300 iter 안에 승부

### V27-A 구성 (본선)

| 항목 | 역할 |
|------|------|
| `limb_usage_min_penalty` | 최소 다리 사용률 보장 |
| `per_leg_contact_floor_penalty` | 각 다리 최소 contact 비율 |
| `per_leg_propulsion_floor_penalty` | 각 다리 최소 propulsion |
| `rear_left_right_propulsion_diff_penalty` | 뒷다리 좌우 추진 편중 억제 |
| `front_left_right_propulsion_diff_penalty` | 앞다리 좌우 추진 편중 억제 |
| `diagonal_coupling_strong_soft_gate` | 3족 우회 차단 |
| `single_limb_validity_gate` | 최약 다리 contact+prop 복합 패널티 |

### 운영 기준 (원본 PLAN)

| iter | 기준 |
|------|------|
| 100 | early warning, limb-wise 확인 |
| 200 | contact/prop/swing/usage floor 미달 시 강한 경고 |
| 300 | V27-A 실패 판정, V27-B 전환 또는 중단 검토 |
| 400 | collapse 지속 시 즉시 중단 |

---

## 3. V27.1a — 구현 및 결과

### 주요 파라미터

| 항목 | 값 |
|------|-----|
| `single_limb_validity_penalty` weight | -20.0 (initial) → -60.0 (final) |
| validity_gate ramp | iter 0 → 100 |
| `per_leg_contact_floor` weight | -10.0 (initial) → -40.0 (final) |
| `per_leg_propulsion_floor` weight | -10.0 (initial) → -30.0 (final) |
| floor ramp | iter 0 → 50 |
| diagonal `min_contact` | 0.25 |
| diagonal `min_propulsion` | 0.10 |
| collapse restart | iter 100~300 (4발 전체 감시) |

### 실험 결과

#### iter 101 / 201

| 지표 | 관측값 |
|------|--------|
| FL/FR/RL/RR contact | 전부 0.005 ~ 0.020 |
| FL/FR/RL/RR propulsion | 전부 0.004 ~ 0.015 |
| usage_min | ≈ 0.000 ~ 0.001 |
| survival | 1 ~ 2% |
| fall | 100% |
| diagonal gated/raw ratio | 0.17 ~ 0.35 |

### 실패 분석

**원인: 초기 penalty/gate 과강도로 학습 자체를 눌러버린 상태**

- 특정 다리 collapse 이전에 4발 전체가 uniformly low
- iter 100 시점에 이미 validity_gate full-strength(-60) 도달
- 초기 랜덤 정책이 전부 "실패"로 보이면서 가치함수 bootstrapping 왜곡
- diagonal gate도 강하게 작동 → locomotion signal 자체가 형성되지 않음

**결론: 철학은 맞음. 구현 방향도 맞음. 하지만 초기 강도와 timing이 과했음.**

---

## 4. V27.1b PLAN

### 한 줄 정의

**V27.1a의 철학은 유지하되, 초기 제약 강도를 낮춰서 "4발 기능 참여를 강제하면서도 학습 자체는 살아나게" 만드는 조정판.**

### 핵심 목표

1. V27의 핵심 철학 유지 (4발 기능 참여, contact+propulsion 동시 확인, single-limb collapse = 실패)
2. **초기 학습이 죽지 않게 제약 강도 완화**
   - iter 0~200: 학습 가능성 확보
   - iter 200+: 본격 강제

### 유지할 것

- `per_leg_contact_floor_penalty`
- `per_leg_propulsion_floor_penalty`
- `limb_usage_min_penalty`
- `rear/front_left_right_usage_diff_penalty`
- `rear/front_left_right_propulsion_diff_penalty`
- collapse_restart의 4발 모니터링 구조
- heartbeat/report의 4발 전체 출력
- `diagonal_coupling_raw` vs `gated` 비교 출력

### 변경할 것

| 항목 | V27.1a | V27.1b |
|------|--------|--------|
| validity_gate initial | -20.0 | **-5.0** |
| validity_gate final | -60.0 | **-35.0** |
| validity_gate ramp | 0 → 100 | **0 → 200** |
| contact floor initial | -10.0 | **-2.0** |
| contact floor final | -40.0 | **-20.0** |
| contact floor ramp | 0 → 50 | **0 → 150** |
| propulsion floor initial | -10.0 | **-2.0** |
| propulsion floor final | -30.0 | **-15.0** |
| propulsion floor ramp | 0 → 50 (contact 공유) | **50 → 200 (별도 ramp)** |
| limb_usage_min ramp | 0 → 50 | **0 → 150** (의도적 완화) |
| diagonal `min_contact` | 0.25 | **0.15** |
| diagonal `min_propulsion` | 0.10 | **0.05** |
| collapse restart 최소 iter | 100 | **200** (100~200은 warning only) |

### 구현 변경사항 (코드)

- `rewards.py` `_curriculum_apply_weights`: `propulsion_floor_alpha` 파라미터 추가, propulsion floor를 contact floor에서 분리
- `rewards.py` `reward_weight_curriculum`: `propulsion_floor_ramp_start/end` 파라미터 추가, `env._crr_propulsion_floor_alpha` 독립 계산
- `env_cfg.py`: 전체 파라미터 업데이트
- `heartbeat.py`: iter 100~200 warning-only 블록 추가 (`_COLLAPSE_CHECK_ITER_MIN_WARN = 100`, `_COLLAPSE_CHECK_ITER_MIN = 200`)
- `common.py`: TRAIN_VERSION, TRAINING_CONFIG, format_report curriculum weight 예상값 업데이트

### Curriculum Stage 설계

| Stage | iter | 목표 | 설정 |
|-------|------|------|------|
| 1 | 0~100 | 기립/자세 유지, 기본 contact 형성 | validity gate 약하게, contact floor 약하게 |
| 2 | 100~200 | 4발 바닥 상호작용 시작, single-limb 완전 붕괴 방지 | gate 중간 강도, contact floor 강화 시작 |
| 3 | 200~400 | 기능적 4발 참여 형성, 비대칭 억제 본격화 | gate 최종 강도 근접, 전체 floor 강화 |

---

## 5. V27.1b — 실험 결과

### run 정보

| 항목 | 값 |
|------|-----|
| run_dir | `2026-03-15_15-49-37` |
| 시작 | 2026-03-15 15:49 (fresh start) |
| commit | `9c9b7f4` (V27.1b 구현), `4eb620e` (주석 보완) |

---

### iter 101

| 지표 | V27.1a | V27.1b | 변화 |
|------|--------|--------|------|
| FL contact/prop | 0.005~0.020 | 0.057 / 0.051 | ✅ 대폭 개선 |
| FR contact/prop | 0.005~0.020 | 0.059 / 0.053 | ✅ 대폭 개선 |
| RL contact/prop | 0.005~0.020 | 0.040 / 0.035 | ✅ 개선 (약함) |
| RR contact/prop | 0.005~0.020 | 0.050 / 0.041 | ✅ 개선 |
| survival | 1~2% | 6.4% | ✅ 3~6배 |
| diagonal ratio | 0.17~0.35 | **0.95** | ✅ gate 거의 투명 |
| reward | — | -13.4 | |
| usage_min | ≈ 0 | 0.014 | ✅ 탈출 |

**판정: ✅ PLAN iter 100 기준 통과**
- 4발 contact 전부 0 아님 ✅
- 전체 평균 contact > V27.1a ✅ (0.052 vs 0.005~0.020)
- survival 5% 이상 조짐 ✅ (6.4%)
- gated/raw ratio 양호 ✅ (0.95)

---

### iter 200

| 지표 | iter 101 | iter 200 | 변화 |
|------|----------|----------|------|
| FL contact/prop | 0.057 / 0.051 | 0.054 / 0.049 | ➡️ 유지 |
| FR contact/prop | 0.059 / 0.053 | 0.056 / 0.051 | ➡️ 유지 |
| RL contact/prop | 0.040 / 0.035 | **0.025 / 0.022** | ❌ 악화 |
| RR contact/prop | 0.050 / 0.041 | 0.050 / 0.038 | ➡️ 유지 |
| survival | 6.4% | 5.6% | ❌ 약간 악화 |
| diagonal ratio | 0.95 | 0.78 | 🟡 하락 |
| reward | -13.4 | -13.0 | ➡️ 정체 |
| usage_min | 0.014 | **0.007** | ❌ 역주행 |
| VF Loss | 13.2 | 8.5 | ✅ 개선 |
| noise std | 0.955 | 0.828 | ✅ 안정화 |

**판정: ⚠️ 강한 경고**
- validity_gate -35 full-strength 도달 시점에 RL이 눌리기 시작
- 학습 완전 정체 (보상 -13.4 → -13.0)
- usage_min 역주행 (0.014 → 0.007)
- PLAN 계속진행 4개 기준 중 2개 미달 (contact 평균 0.046 < 0.05, usage_min 0.007 < 0.03, survival 5.6% < 10%)
- PLAN 강한경고 기준: usage_min < 0.01 → 해당

---

### iter 302

| 지표 | iter 200 | iter 302 | 변화 |
|------|----------|----------|------|
| FL contact/prop | 0.054 / 0.049 | **0.099 / 0.088** | ✅ 급격히 개선 |
| FR contact/prop | 0.056 / 0.051 | **0.096 / 0.088** | ✅ 급격히 개선 |
| RL contact/prop | 0.025 / 0.022 | **0.040 / 0.034** | ✅ 회복 |
| RR contact/prop | 0.050 / 0.038 | **0.082 / 0.061** | ✅ 개선 |
| survival | 5.6% | 8.1% | ✅ 개선 |
| diagonal ratio | 0.78 | 0.92 | ✅ 개선 |
| reward | -13.0 | **-6.0** | ✅ +7.0 급반전 |
| usage_min | 0.007 | 0.016 | ✅ 회복 |

**신규 관찰:**
- ⚠️ **TAP Suspicion** — FL(c=0.10, p=0.09), FR(c=0.10, p=0.09)
  - contact+prop 0.08~0.18 구간에서 정체
  - floor penalty를 겨우 회피하는 최소 contact 전략 가능성
  - 진짜 보행 발전인지, penalty 회피 학습인지 iter 400에서 판별 필요
- `rear_left_right_propulsion_diff_penalty: -0.9764` TOP5 패널티 진입 — RL/RR 비대칭 신호
- RL contact 0.040: FL/FR(0.097~0.099) 대비 여전히 2.5배 차이

**판정: 계속 진행 — PLAN iter 300 실패 기준 미해당**
- all-limb suppression 없음 ✅
- gated/raw ratio 양호 (0.92) ✅
- FL/FR contact/prop floor 근처가 아님 ✅

**차이: heartbeat 자동 판정 "V27-A 실패"는 PLAN 기준과 다름. 실제 PLAN 기준으로는 중단 근거 없음.**

---

### V27.1b 전체 추이

```
Iter   | Reward  | EpLen | Survival | RL contact | TAP
     0 |   -26.5 |  21.2 |    —     |    —       | —
   101 |   -13.4 |  31.9 |   6.4%   |  0.040     | 없음
   200 |   -13.0 |  27.8 |   5.6%   |  0.025     | 없음
   302 |    -6.0 |  40.6 |   8.1%   |  0.040     | FL/FR 의심
```

---

## 6. 외부 분석 의견 (V28 방향 제안)

> V27.1b까지로 확인된 건, penalty를 세게 하면 전체가 죽고, 약하게 하면 특정 다리 약세 + TAP 최적화가 남는다는 점이다.

**제안 방향:**

1. **floor penalty → target-band reward/penalty 구조**
   - 최소치만 넘기면 끝이 아니라, 정상 범위까지 올라가야 이득
2. **4발 동시 기능 참여 직접 보상**
   - contact + propulsion + stance quality를 함께 봄
3. **TAP 최적화 직접 억제**
   - floor 근처 정체, 짧은 가짜 접촉, 낮은 추진의 조합을 명시적으로 불리하게

**운영 기준 변경 제안:**
- iter 100: all-limb suppression 여부
- iter 200: 특정 다리 약세 여부
- iter 300: target-band 진입 실패면 종료

---

## 7. 외부 의견에 대한 판단

### 동의

- "penalty 세게 → all-limb suppression, 약하게 → TAP + 단일 약세" — V27.1a/1b 데이터가 명확히 지지. 진단 정확.
- 구조 변경 필요하다는 결론 — 동의. V27 시리즈 전체가 증명.
- target-band 방향 — 타당. floor penalty의 근본 문제(threshold 회피 최적화)를 해결.
- 운영 기준 변경 — 타당. V28 구조에 논리적으로 일치.

### 동의 안 함

**3번(TAP 억제)은 1번(target-band)의 부산물이다.**
target-band가 제대로 설계되면 floor 근처 버티기는 자동으로 불리해진다. 별도 구조를 추가하면 복잡도만 올라간다.

**iter 302에서 V27.1b를 종료하고 V28로 가는 결론은 성급하다.**
- iter 200~300 구간에서 보상 -13 → -6 급반전
- TAP는 suspicion 단계, 확정 아님
- RL은 회복 방향
- iter 400에서 TAP가 굳는지/돌파하는지 확인 후 결정이 데이터 기반

---

## 8. 종합 평가

### V27 시리즈가 증명한 것

| 실험 | 결과 | 결론 |
|------|------|------|
| V27.1a (강도 강) | 4발 전체 0.005~0.020, survival 1~2% | 과강도 → all-limb suppression |
| V27.1b (강도 완화) | FL/FR 회복, RL 약세, TAP 발생 | 완화 → single-limb 약세 + TAP |

**penalty 기반 존재 강제 구조의 딜레마:**
- 세게 걸면: 학습 자체를 억제
- 약하게 걸면: threshold 회피 전략이 최적이 됨

### V28 전환 근거

V27 시리즈가 완전히 소진되면 다음을 확인할 수 있음:
- iter 400에서 FL/FR TAP가 굳는가 (0.10 정체 지속)
- RL이 FL/FR 수준으로 따라오는가
- 위 두 조건이 bad이면 V27.1b 실패 확정 → V28 전환

### V28 핵심 원칙

**"안 하면 벌점"이 아니라 "정상 4발 참여를 해야만 이득"인 구조**

- floor penalty → target-band reward
- cooperative 4발 동시 보상 (단, curriculum 필수)
- TAP는 target-band의 부산물로 자연히 해소

### V28의 진짜 난관

1. **target 수치 설정** — 너무 높으면 달성 불가, 너무 낮으면 TAP 재현
2. **초기 신호 희박 문제** — positive reward는 "맞는 것"을 해야 신호가 나옴. 초기 랜덤 정책에서 희박함. curriculum 설계가 V27보다 정교해야 함
3. **4발 cooperative reward** — staged curriculum 없이 걸면 V27.1a의 재현

---

## 9. 현재 상태 (V27.1b 진행 중)

| 항목 | 값 |
|------|-----|
| run_dir | `2026-03-15_15-49-37` |
| 현재 iter | 302 (진행 중) |
| 다음 판단 포인트 | **iter 400** — TAP 굳는지 여부 |
| 실패 조건 | FL/FR contact 0.10 정체 + RL 회복 정지 + usage_min 개선 없음 |
| 성공 조건 | FL/FR contact 0.15 이상 돌파 + RL 0.06 이상 + TAP 해소 |
