# V24 Plan — Limb Validity Gating

> 작성: 2026-03-14
> 상태: **종료 — 목표 미달성** (2026-03-14)
> 최종 run: `2026-03-14_18-29-12`, iter 1800 → 2002

---

## 1. V24 도입 배경

V23 실험에서 posture-first refinement는 gait/posture 지표를 개선했으나, 다음 문제가 해결되지 않았다.

- **특정 사지 미사용 exploit**: rear-left가 거의 접지하지 않는 비대칭 보행 패턴 발현
- **좌우 사지 비대칭**: rear-left/right 사용량 차이 0.9 이상 (허용 기준 0.18)
- **Limb collapse**: 특정 사지가 swing을 유지하면서 접지/추진이 0에 수렴
- **Soft reward 한계**: 간접 유도만으로는 이 패턴을 억제할 수 없었음

V24는 이를 **명시적 gate(차단) 메커니즘**으로 전환한다.

---

## 2. V24 핵심 변경

### 2.1 새로운 Reward Term 2개

#### `limb_usage_min_penalty` (weight: -12.0)

4개 사지 중 가장 덜 사용된 사지의 usage proxy가 `min_usage=0.30` 미달 시 패널티.

```
usage_score = 0.55 * contact_score
            + 0.35 * propulsion_score
            + 0.10 * swing_activity
            (각 점수는 target 기준 clamp(0,1) 정규화)

support_gate = max(contact_score, propulsion_score)
usage_score  = usage_score * support_gate  # 접지/추진 없으면 0으로

penalty = max(0, 0.30 - min(usage_scores))
```

#### `rear_left_right_usage_diff_penalty` (weight: -8.0)

rear-left / rear-right 사용량 차이가 `max_diff=0.18` 초과 시 패널티.

```
diff    = |usage_rl - usage_rr|
penalty = max(0, diff - 0.18)
```

두 패널티 모두 `_heading_velocity_gate(min_vel=0.05)`로 정지 시 비활성화.

---

### 2.2 Validity Ramp (점진적 강화 커리큘럼)

| iter 구간 | alpha | limb_usage weight | rear_diff weight | stage |
|-----------|-------|-------------------|------------------|-------|
| 0–199     | —     | (미적용)          | (미적용)         | observe |
| 200       | 0.0   | -3.0              | -2.0             | early_warning |
| 400       | 0.5   | -7.5              | -5.0             | lock_warning |
| 600+      | 1.0   | -12.0             | -8.0             | enforce |

```python
alpha = clamp((iter - 200) / (600 - 200), 0.0, 1.0)
weight = initial + (final - initial) * alpha
```

---

### 2.3 Ops 레이어 추가

| 파일 | 추가 내용 |
|------|-----------|
| `scripts/common.py` | `LIMB_VALIDITY_THRESHOLDS`, `compute_limb_validity_metrics()`, `_validity_stage_key()`, `_summarize_validity_operation()` |
| `scripts/utils/evaluate_limb_gate_checkpoint.py` | 특정 checkpoint limb validity 수동 평가 전용 스크립트 |
| `scripts/utils/analyze_training.py` | limb validity 열 추출, collapse detection, V24 operation status workbook 기록 |

#### Limb Validity 4단계 판정

| stage | iter | operation_status |
|-------|------|-----------------|
| observe | 0–199 | observing |
| early_warning | 200–399 | provisional_exclusion (collapse 시) |
| lock_warning | 400–599 | warning_active |
| enforce | 600+ | enforced_pass / enforced_fail |

#### Collapse 감지 조건
```
contact_ratio < 0.05
AND swing_time > 0.95
AND propulsion < 0.02
→ 해당 사지 "collapse" 분류
```

---

## 3. 전체 Run 진행 기록

### Run 1: `2026-03-13_18-53-26` (초기 run)

| iter | reward | ep_len | survival | gait | posture | limb_usage_min | rear_diff | limb_validity |
|------|--------|--------|----------|------|---------|---------------|-----------|---------------|
| 381 | 271 | 235 | 47% | B | C | 0.1040 | >0.18 | provisional_fail |
| 400 | — | — | — | — | — | 0.0853 | >0.18 | provisional_fail |
| 500 | — | — | — | — | — | 0.0451 | >0.18 | provisional_fail |
| 600 | 323 | 250 | 100% | A | C | 0.00379 | 0.93 | enforced_fail |
| 700 | — | — | — | — | — | 0.00078 | — | enforced_fail |
| 800 | 410 | 243 | 100% | A | B | 0.000362 | — | enforced_fail |
| 1803 | 489 | 246 | 100% | A | B | 0.000079 | 0.93 | enforced_fail |

### Run 2 (최종): `2026-03-14_18-29-12` (model_1800.pt에서 재개)

heartbeat 수치:

| iter | reward | survival | gait | posture | limb_usage_min | rear_diff | limb_validity |
|------|--------|----------|------|---------|---------------|-----------|---------------|
| 1800 | 99 | 9.6% | F | A | 0.000026 | 0.033 | enforced_fail |
| 1900 | 544 | 100% | A | B | 0.000065 | 0.925 | enforced_fail |

> iter 1800의 수치 이상은 warm-up 구간으로 체크포인트 로딩 직후 상태. iter 1900부터 정상.

per-iter 수치 (training_launch.log, iter 1801~2002 전 구간):

| 지표 | 관측 범위 | 추세 |
|------|----------|------|
| contact_ratio_rl | 0.0002 ~ 0.0004 | **완전 평탄, 변화 없음** |
| propulsion_rl | 0.0001 ~ 0.0002 | **완전 평탄, 변화 없음** |
| stance_time_rl | 0.0002 ~ 0.0004 | contact_ratio_rl과 동일 |
| swing_time_rl | 0.97 ~ 0.99 | 거의 항상 공중 — 접지 없음 |
| contact_ratio_rr | 0.81 ~ 0.89 | 정상 수준, 안정 |
| propulsion_rr | 0.61 ~ 0.65 | 정상 수준, 소폭 감소세 |

**주요 관찰:**

- iter 381에서 limb_usage_min=0.104이었던 것이 iter 1900에서 0.000065으로 단조 감소 — 패널티 적용 이후 개선이 아니라 **악화** 지속
- 200 consecutive iter(1801~2002)에서 c_rl이 단 한 번도 0.001을 넘지 않음 → **self-correction 없음**
- reward 544 달성에도 limb_validity 전 구간 fail → **3다리 보행으로 고보상 경로 완전 고착화**

---

## 4. 원인 분석 (최종)

### 4.1 패널티 방식의 구조적 한계

V24 penalty가 감지 자체는 정상 작동했다. 실패한 것은 **이미 고착된 collapse를 패널티로 되돌리는 것**이다.

- iter 200~600 ramp 시작 시점에 이미 rear-left collapse가 deep local minimum에 진입
- 모델이 rear-left 없이도 trot-like pattern으로 reward를 충분히 획득하는 경로를 학습
- penalty가 그 경로의 총 보상(544)보다 유의미하게 낮음 — weight -12.0은 총 reward 대비 ~2% 수준

### 4.2 ramp 타이밍 문제

| 구간 | 실제 상황 |
|------|----------|
| iter 0~200 | collapse 시작 (observe 구간 — 패널티 없음) |
| iter 200~600 | collapse 이미 고착, ramp 시작했으나 역부족 |
| iter 600+ | enforce 적용, 그러나 limb_usage_min은 계속 하락 |

collapse가 **패널티 적용 이전에** 이미 안정화됐다. 패널티를 더 일찍(iter 0부터) 강하게 걸었어야 했다.

### 4.3 reward 구조 문제

- `diagonal_coupling`이 rear-right + front-left 조합만으로도 충분히 충족됨
- rear-left 전용으로 패널티를 받는 reward term이 없음 (min_usage는 4개 중 최소값이라 rear-left만 선택적으로 차단하지 못함)
- 즉 rear-left collapse를 **직접 차단하는 term 부재**

---

## 5. 최종 결론

| 평가 항목 | 결과 |
|----------|------|
| limb_validity_gate 통과 checkpoint | **0개 (전 구간 fail)** |
| rear-left self-correction | **없음** |
| V24 패널티 효과 | **없음 — limb_usage_min 단조 감소** |
| gait/posture 품질 | A/B 달성 (V24 이전 수준과 동일) |
| V24 목표 달성 여부 | **실패** |

**결론**: 패널티 방식만으로는 이미 고착된 collapse를 되돌리는 것이 불가능하다는 것이 실험적으로 증명됐다.

---

## 6. V25 설계 방향 (제언)

V24 실패에서 도출된 교훈:

1. **collapse가 형성되기 전에 차단**: validity 패널티를 iter 0부터 적용하거나, 초기 커리큘럼 자체를 4발 균등 사용으로 강제
2. **per-limb 직접 패널티**: min_usage 대신 rear-left contact_ratio에 직접 lower-bound penalty
3. **reward 경로 차단**: 3다리 보행으로 높은 diagonal_coupling/propulsion을 얻지 못하도록 reward 구조 수정
4. **restart-on-collapse**: collapse 감지 시 해당 run을 즉시 종료하고 새 run으로 재시작하는 hard reset 전략

---

## 7. 평가 기준 (사후)

V24 성공 기준이었던 항목들과 실제 결과:

| 기준 | 목표 | 실제 결과 |
|------|------|----------|
| Hard Safety Gate | survival ≥ 90% | ✅ iter 600+ 이후 100% |
| Limb Validity Gate | enforced_pass 1회 이상 | ❌ 전 구간 enforced_fail |
| limb_usage_min | ≥ 0.30 | ❌ 최종 0.000065 |
| rear_usage_diff | ≤ 0.18 | ❌ 0.925 (5배 초과) |
| collapse_detected | False | ❌ iter 600부터 지속 |
| Gait score | ≥ A | ✅ A 달성 |
| Posture score | ≥ B | ✅ B 달성 |

---

## 8. 참고 문서

- `plan/V23_ANALYSIS.md` — posture-first refinement 배경
- `plan/CURRENT_STATE_2026-03-15.md` — 최종 세션 상태
- `plan/MEMORY.md` — active handoff
