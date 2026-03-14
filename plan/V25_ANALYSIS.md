# V25 분석 문서 (FAILED)

> 작성: Claude Sonnet 4.6 / 2026-03-14
> 완료: 2026-03-15 (iter 400, 훈련 중단)
> 상태: **실패** — rear-right collapse (붕괴 위치 이동)
> 목적: V25 설계 결정, 구현 내용, 훈련 결과 및 실패 원인 분석

---

## 0. 최종 판정 (iter 400)

**판정: V25 실패 — 붕괴 위치가 이동했을 뿐, 문제 해결 아님**

| 다리 | contact_ratio | propulsion | limb_usage | 판정 |
|------|--------------|------------|------------|------|
| FL | 정상 | 정상 | 정상 | ✅ |
| FR | 정상 | 정상 | 정상 | ✅ |
| RL | **0.930** | **0.516** | **0.930** | ✅ 회복됨 |
| RR | **0.011** | **0.009** | **0.003** | ❌ **COLLAPSE** |

**핵심 분석**:
- RL(rear-left)은 `rear_left_contact_floor_penalty -60` 덕분에 회복됨
- RR(rear-right)은 방어 없음 → 정책이 RL 대신 RR을 포기함
- **붕괴 위치가 RL → RR로 이동했을 뿐, 3족 보행은 그대로**
- 비대칭 패널티의 근본 한계: 특정 다리만 지목하면 collapse는 다른 다리로 이동

**V25 교훈 (V26 설계에 반영)**:
- 특정 다리 지목 패널티는 collapse 이동만 유발함
- 모든 다리에 동일 기준을 적용해야 collapse location shift를 방지할 수 있음
- 이것이 V26.1의 symmetric per-leg existence floor 설계 근거

→ **훈련 중단. V26 (V26.1_PLAN.md) 전환.**

---

## 1. 실험 이력 및 실패 원인 분석

### V23 실패

| 지표 | 수치 | 판정 |
|------|------|------|
| mean_reward | 높음 | — |
| episode_length | 높음 | — |
| survival | 높음 | — |
| contact_ratio_rl | ≈ 0.0 | **CRITICAL** |

- replay/영상 검증: **rear-left 미사용 3족 보행 exploit**
- 3족 보행으로 trot reward, survival reward를 동시에 획득하는 local minimum에 수렴
- contact KPI 문제는 당시 `*_foot_link` 매핑 오류였음 (추후 `*_toe_link`로 수정)

### V24 실패

V24 투입 항목:
- `limb_usage_min_penalty` (weight -12.0)
- `rear_left_right_usage_diff_penalty`
- limb validity gate / diagnostics
- usage proxy (`contact_score * propulsion_score`)
- fast-ramp (iter 200~600 구간 적용)

V24 iter 2000 기준 결과:

| 지표 | 수치 | 판정 |
|------|------|------|
| contact_ratio_rl | ≈ 0.0 | **CRITICAL** |
| stance_time_rl | ≈ 0.0 | 붕괴 |
| swing_time_rl | ≈ 1.0 | 붕괴 |
| propulsion_rl | ≈ 0.0 | 붕괴 |
| limb_usage_rl | ≈ 0.0 | 붕괴 |
| gate/diagnostics | 정상 작동 | — |

**V24 실패 원인 분석:**

1. **weight 부족**: `limb_usage_min_penalty -12.0` × gap 0.30 = **-3.6/step** ≈ 총 reward 544의 0.7%
   → collapse penalty가 3족 보행 이득을 상쇄하지 못함

2. **ramp 시작이 너무 늦음**: iter 200부터 ramp 시작
   → rear-left collapse는 iter 100~200 이전에 이미 고착됨

3. **diagonal_coupling exploit 경로 미차단**: RL 미접지 시에도 diagonal reward 부분 획득 가능

4. **usage proxy 신호 희석**: 4개 다리 min 기반 → 나머지 3개 정상 시 RL 붕괴 신호 희석

---

## 2. V25 핵심 설계 원칙

### 원칙 1: 패널티가 collapse보다 먼저, collapse보다 강해야 한다

- **iter 0부터 full weight**: ramp 없음
- **weight -60**: 총 reward의 최소 10% 이상

### 원칙 2: 직접 타겟 — RL에만, contact에만

V24 proxy의 문제: 4개 다리 min 또는 avg → RL 신호 희석
V25: `rear_left_contact_floor_penalty` — RL만, contact_ratio만 직접 타겟

### 원칙 3: exploit 경로 차단

diagonal_coupling에서 RL 미접지 시 pair_b 보상을 soft gate로 차단

### 원칙 4: 단일 run, 분기 없음

G의 V25-A/B 분기 구조를 채택하지 않음.
가장 강한 직접 처방 하나를 iter 0부터 적용.

**평가**: 원칙 자체는 타당했으나 비대칭성이 치명적 결함이었다.
"강하게 직접 타겟" ✅, "한 다리만 지목" ❌.

---

## 3. 구현된 reward 변경사항

### 3.1 제거된 항목 (V24 → V25)

| 항목 | 이유 |
|------|------|
| `limb_usage_min_penalty` | weight -12, proxy 희석으로 실패 확인. rear_left_contact_floor로 대체 |
| `rear_left_right_usage_diff_penalty` | usage proxy 기반으로 동일한 희석 문제 |

### 3.2 신규 항목

#### `rear_left_contact_floor_penalty`

```python
def rear_left_contact_floor_penalty(
    env, sensor_cfg, contact_threshold=1.0, floor=0.30,
    min_vel=0.05, asset_cfg,
) -> torch.Tensor:
    rl_contact = _contact_ratio(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    gap = torch.clamp(float(floor) - rl_contact[:, 0], min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)
```

설정: `weight=-60.0`, `floor=0.30`, ramp 없음 (iter 0부터 full weight)

**V24 대비**:

| 항목 | V24 | V25 |
|------|-----|-----|
| 방식 | usage proxy (간접) | contact_ratio 직접 |
| target | 4개 다리 min | RL만 |
| weight | -12.0 | -60.0 |
| ramp | iter 200~600 | 없음 (iter 0부터) |
| 최대 패널티/step | -3.6 | -18 ~ -60 |

### 3.3 수정된 항목

#### `diagonal_joint_coupling_reward` — RL participation soft gate 추가

- `rl_gate = clamp(contact_ratio_rl / 0.15, 0, 1)`
- RL 미접지 시 pair_b(FR↔RL) 보상 감소
- pair_a(FL↔RR)는 영향 없음 ← **이것이 RR collapse 방어 부재의 원인**

---

## 4. restart-on-collapse 자동화 (heartbeat.py)

iter 100~300 구간에서 `contact_ratio_rl < 0.05 AND swing_time_rl > 0.95` 조건이
연속 3회 충족되면 자동 fresh restart.

```python
_COLLAPSE_CHECK_ITER_MIN = 100
_COLLAPSE_CHECK_ITER_MAX = 300
_COLLAPSE_CONTACT_THRESHOLD = 0.05
_COLLAPSE_SWING_THRESHOLD = 0.95
_COLLAPSE_CONSECUTIVE_REQUIRED = 3
```

---

## 5. 훈련 경과 기록

### iter ~300 중간 판정 (2026-03-14)

| 지표 | 값 |
|------|----|
| reward | 196 |
| ep_len | 189.6 |
| survival rate | 37.9% |
| timeout rate | 73% |
| stability | F 지속 |

위험 신호: `rear_alternation` / `rear_joint_velocity` TOP → rear-driven 쏠림 가능성.

### iter ~500 중간 판정 (2026-03-15)

| 지표 | iter ~300 | iter ~500 |
|------|-----------|-----------|
| reward | 196 | **312** |
| ep_len | 189.6 | **233** |
| survival rate | 37.9% | **46.6%** |
| timeout rate | 73% | **86%** |
| stability | F | F (지속) |

기초 안정화는 진행 중이었으나 rear-driven 쏠림 의심 강화.

### iter 400 최종 판정 (2026-03-15)

위 "0. 최종 판정" 참조. 훈련 중단.

---

## 6. `/start` vs `/resume` 명령 분리 (인프라)

- `/start`: 기존 checkpoint 있으면 확인 후 fresh start
- `/resume`: 기존 checkpoint에서 재개
- `launch_training(fresh=True)` 시 `active_checkpoint = None` 고정 (구 checkpoint 재참조 버그 수정)
