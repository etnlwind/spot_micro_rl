# V24 Plan — Limb Validity Gating

> 작성: 2026-03-14
> 상태: 구현 완료, 첫 run 진행 중

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

## 3. 현재 Run 진행 상황 (`2026-03-13_18-53-26`)

| iter | reward | ep_len | survival | gait | stability | posture | limb_validity |
|------|--------|--------|----------|------|-----------|---------|---------------|
| 381 | 271 | 235 | 47% | B | F | C | 실패 (provisional) |
| 600 | 323 | 250 | 100% | A | D | C | 실패 (enforced_fail) |
| 800 | 410 | 243 | 100% | A | C | B | 실패 (enforced_fail) |
| 1803 | 489 | 246 | 100% | A | B | B | 실패 (enforced_fail) |

**주요 관찰:**

- iter 600 전후 생존율 50% → 100%, reward 급상승 — locomotion core 정착
- gait/posture는 A/B로 지속 개선 중
- 모든 checkpoint에서 rear-left collapse 지속
  - `rear_left_contact_collapse(c=0.00, s=0.99, p=0.00)` 반복
  - `limb_usage_min: 0.00008`, `rear_diff: 0.93` (기준 0.18 대비 5배 초과)
- V24 penalty가 작동하고 있으나 현재 reward 구조가 이를 극복하지 못하는 상태

---

## 4. 해석

V24 penalty가 감지하고 차단하는 것은 정상 작동이다. 문제는 현재 reward 구조가 rear-left collapse를 충분히 억제하지 못한다는 점이다.

가능한 원인:
- trot-gait / diagonal_coupling reward가 rear-right + front-left 조합만으로도 충분한 보상을 받음
- rear-specific reward의 구조상 rear-left를 사용하지 않아도 다른 항목으로 보상 충당 가능
- validity penalty weight(-12.0)가 총 reward(~490)에 비해 여전히 작은 상대적 비중

---

## 5. 다음 단계

### 5.1 현재 run 계속 관찰 (우선)

- iter 2000–5000 구간에서 rear-left가 자연적으로 회복되는지 확인
- limb_usage_min 추이가 점차 0.30에 접근하면 self-correction 가능성 있음

### 5.2 threshold 재검토 (필요 시)

- `limb_usage_min`: 0.30 → 0.15~0.20으로 낮추는 것 검토
- `rear_usage_diff_max`: 0.18 → 0.30으로 완화 검토
- 단, threshold 완화는 "문제 감지 포기"가 아니라 "달성 가능한 목표"로 재설정하는 것

### 5.3 Rear reward 구조 분석

- `rear_joint_velocity`, `rear_alternation` 등 rear-specific reward 항목 재검토
- diagonal_coupling이 rear-left를 실질적으로 사용하게 강제하는지 확인

### 5.4 Validity penalty 강화 (최후 수단)

- weight를 -12.0 이상으로 올리거나
- per-limb collapse penalty를 별도로 추가
- 단, 과도한 penalty는 locomotion 자체를 불안정하게 만들 수 있으므로 마지막 선택

---

## 6. 평가 기준

V24 성공 기준:

1. **Hard Safety Gate 유지**: survival ≥ 90%, fall ≤ 5%
2. **Limb Validity Gate 통과**: enforced_pass (iter 600+)
   - limb_usage_min ≥ 0.30 (4개 사지 모두)
   - rear_usage_diff ≤ 0.18
   - collapse_detected = False
3. **Gait/Posture 유지**: gait_score ≥ A, posture_score ≥ B

V24 1차 성공은 "style 완성"이 아니라 **limb validity gate를 통과한 checkpoint 1개 확보**다.

---

## 7. 참고 문서

- `plan/V23_PLAN.md` — posture-first refinement 배경
- `plan/CURRENT_STATE_2026-03-14.md` — 현재 운영 상태
- `plan/MEMORY.md` — active handoff
