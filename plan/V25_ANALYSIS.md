# V25 통합 분석 문서

> 작성: 2026-03-14~15
> 완료: 2026-03-15 (iter 400, 훈련 중단)
> 상태: **실패** — rear-right collapse (붕괴 위치 이동)
> 목적: V25 설계 과정, 구현 내용, 훈련 결과, 실패 분석 전체를 단일 문서로 정리

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
- 모든 다리에 동일 기준을 적용해야 collapse location shift를 방지
- 이것이 V26.1의 symmetric per-leg existence floor 설계 근거

→ **훈련 중단. V26 전환.**

---

## 1. 배경: V23/V24 실패 분석

### V23 실패

| 지표 | 수치 | 판정 |
|------|------|------|
| mean_reward | 높음 | — |
| episode_length | 높음 | — |
| survival | 높음 | — |
| contact_ratio_rl | ≈ 0.0 | **CRITICAL** |

- replay/영상 검증: **rear-left 미사용 3족 보행 exploit**
- 3족 보행으로 trot reward, survival reward를 동시에 획득하는 local minimum 수렴
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
| contact_ratio_rl | ≈ 0.00026 | **CRITICAL** |
| stance_time_rl | ≈ 0.00026 | 붕괴 |
| swing_time_rl | ≈ 0.992942 | 붕괴 |
| propulsion_rl | ≈ 0.000156 | 붕괴 |
| limb_usage_rl | ≈ 0.000052 | 붕괴 |
| contact_ratio_fl | ≈ 0.903 | 정상 |
| contact_ratio_fr | ≈ 0.588 | 정상 |
| contact_ratio_rr | ≈ 0.859 | 정상 |
| gate/diagnostics | 정상 작동 | — |

**V24 실패 원인 분석:**

1. **weight 부족**: `limb_usage_min_penalty -12.0` × gap 0.30 = **-3.6/step** ≈ 총 reward 544의 0.7%
   → collapse penalty가 3족 보행 이득을 상쇄하지 못함

2. **ramp 시작이 너무 늦음**: iter 200부터 ramp 시작
   → rear-left collapse는 iter 100~200 이전에 이미 고착됨. 패널티가 시작되기 전에 정책이 굳어버림

3. **diagonal_coupling exploit 경로 미차단**: RL이 접지하지 않아도 FR↔RL 관절 속도 상관이 일부 유지되어 diagonal_coupling 보상을 부분적으로 획득 가능

4. **usage proxy 신호 희석**: `limb_usage_min_penalty`는 4개 다리 min 기반
   → 나머지 3개 다리가 정상이면 RL 붕괴 신호가 희석됨

---

## 2. V25 설계 논의 과정

### 2.1 설계 방향 — G안 vs CS안

V25는 두 가지 설계 방향이 제시되었다.

**G안 (V25_PLAN-G.md) — Validity-First Structural Redesign:**
- V25를 "penalty 조금 더 세게"가 아니라 구조 재설계로 정의
- 3층 validity 구조: Layer A(Existence Floor) + Layer B(Symmetry Guard) + Layer C(Support Participation)
- V25-A(일반) → V25-B(직접 처방) → V25-C(posture) 분기 구조
- validity fast-ramp 0~300 구간 독립 운영

**CS안 (V25_PLAN-CS.md) — Per-Limb Direct Gating:**
- 단일 run, 분기 없음
- `rear_left_contact_floor_penalty` weight -60, iter 0부터 full weight
- diagonal_coupling pair_b soft gate
- restart-on-collapse heartbeat 자동화

### 2.2 G/CS 논의 핵심 쟁점

| # | 항목 | G 입장 | CS 입장 | 최종 결정 |
|---|------|--------|--------|---------|
| F1 | usage proxy | V24 구현 재사용 | V24 구현 재사용 | **재사용** |
| F2 | restart-on-collapse | V25-A에 포함 | iter 100 기준 포함 | **포함** |
| F3 | per_leg vs rear_left | per_leg 주력, rear_left는 B에서 | rear_left 직접 -60 | **CS 채택** |
| F4 | diagonal gate | soft gate 권장 | soft gate threshold 0.15 | **soft gate** |
| F5 | A→B 전환 트리거 | iter 200 기준 명시 | 분기 구조 자체 폐기 | **분기 폐기** |
| F6 | abort 자동화 | 수동 판단 우선 | heartbeat 자동화 | **수동 우선** |

### 2.3 최종 설계 결정 (CS 단일 설계 채택)

**G 권고를 따르지 않은 이유:**

1. **V25-A/B 분기 구조**: A를 iter 200까지 지켜보다 B로 넘어가면 V24 패턴 반복. collapse는 200 이전에 고착됨.

2. **F3의 모호함**: "per_leg 또는 per_leg_propulsion 중 하나" — contact가 없으면 propulsion도 0이므로 contact 직접 타겟이 근본적. propulsion_floor는 불필요.

3. **weight 기준 부재**: G 권고 어디에도 수치가 없음. V24 실패의 직접 원인이 weight -12(2%)였으므로 "충분히 강한 weight"를 명시해야 함.

**채택된 단일 설계:**

| 항목 | 결정 | 이유 |
|------|------|------|
| 분기 구조 | **없음 — 단일 run** | A/B 전환 대기가 V24 패턴 반복 유발 |
| penalty target | `rear_left_contact_floor_penalty` 직접 | min_usage proxy는 다른 다리가 희석 |
| weight | **-60** | 총 reward의 최소 10% 이상 |
| ramp | **없음 — iter 0부터 full** | collapse보다 패널티가 먼저여야 함 |
| restart-on-collapse | **iter 100** 기준 | iter 300은 너무 늦음 |
| diagonal coupling | soft gate, threshold 0.15 | binary는 gradient 차단 |

> **설계 원칙: 패널티가 작동하려면 collapse보다 먼저, collapse보다 강해야 한다.**

---

## 3. V25 핵심 설계 원칙 (최종)

### 원칙 1: 패널티가 collapse보다 먼저, collapse보다 강해야 한다

V24의 두 가지 실패:
- **늦게 시작**: iter 200 ramp → collapse 이전에 패널티 없음
- **너무 약함**: -3.6/step ≈ 총 reward의 0.7%

V25 대응:
- **iter 0부터 full weight**: ramp 없음
- **weight -60**: 총 reward의 최소 10% 이상

### 원칙 2: 직접 타겟 — RL에만, contact에만

V24 proxy의 문제: 4개 다리 min 또는 avg → RL 신호 희석
V25: `rear_left_contact_floor_penalty` — RL만, contact_ratio만 직접 타겟

### 원칙 3: exploit 경로 차단

diagonal_coupling에서 RL 미접지 시 pair_b 보상을 soft gate로 차단
→ 3족 보행이 diagonal reward까지 얻는 경로를 닫음

### 원칙 4: 단일 run, 분기 없음

G의 V25-A/B 분기 구조를 채택하지 않음. 가장 강한 직접 처방 하나를 iter 0부터 적용.

**사후 평가**: 원칙 자체는 타당했으나 비대칭성이 치명적 결함이었다.
"강하게 직접 타겟" ✅, "한 다리만 지목" ❌.

---

## 4. 구현된 reward 변경사항

### 4.1 제거된 항목 (V24 → V25)

| 항목 | 이유 |
|------|------|
| `limb_usage_min_penalty` | weight -12, proxy 희석으로 실패 확인. rear_left_contact_floor로 대체 |
| `rear_left_right_usage_diff_penalty` | usage proxy 기반으로 동일한 희석 문제 |

### 4.2 신규 항목

#### `rear_left_contact_floor_penalty`

```python
def rear_left_contact_floor_penalty(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg = SceneEntityCfg("contact_forces"),
    contact_threshold: float = 1.0,
    floor: float = 0.30,
    min_vel: float = 0.05,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
) -> torch.Tensor:
    contact_sensor = env.scene.sensors[sensor_cfg.name]
    rl_contact = _contact_ratio(contact_sensor, sensor_cfg.body_ids, contact_threshold)
    gap = torch.clamp(float(floor) - rl_contact[:, 0], min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)
```

설정값:
```python
self.rewards.rear_left_contact_floor = RewTerm(
    func=custom_mdp.rear_left_contact_floor_penalty,
    weight=-60.0,
    params={
        "sensor_cfg": SceneEntityCfg("contact_forces", body_names="rear_left_toe_link"),
        "contact_threshold": 1.0,
        "floor": 0.30,
        "min_vel": 0.05,
        "asset_cfg": SceneEntityCfg("robot"),
    },
)
```

- `contact_ratio_rl < 0.30`이면 `gap = 0.30 - contact_ratio_rl` → 패널티 발생
- `contact_ratio_rl ≥ 0.30`이면 `gap = 0` → 패널티 없음
- 전진 속도 < `min_vel` (0.05 m/s)이면 gate=0 → 정지 상태에서는 패널티 없음
- ramp 없음 — iter 0부터 weight -60 전력 적용

**V24 대비**:

| 항목 | V24 | V25 |
|------|-----|-----|
| 방식 | usage proxy (간접) | contact_ratio 직접 |
| target | 4개 다리 min | RL만 |
| weight | -12.0 | -60.0 |
| ramp | iter 200~600 | 없음 (iter 0부터) |
| 최대 패널티/step | -3.6 | -18 ~ -60 |

### 4.3 수정된 항목

#### `diagonal_joint_coupling_reward` — RL participation soft gate 추가

```python
# V25: RL 참여 soft gate
if rl_participation_sensor_cfg is not None:
    contact_sensor = env.scene.sensors[rl_participation_sensor_cfg.name]
    rl_contact = _contact_ratio(contact_sensor, rl_participation_sensor_cfg.body_ids, rl_contact_threshold)[:, 0]
    rl_gate = torch.clamp(rl_contact / max(float(rl_min_contact), 1e-6), 0.0, 1.0)
    pair_b_reward = pair_b_reward * rl_gate
```

설정값:
```python
"rl_participation_sensor_cfg": SceneEntityCfg("contact_forces", body_names="rear_left_toe_link"),
"rl_contact_threshold": 1.0,
"rl_min_contact": 0.15,
```

- `rl_gate = clamp(contact_ratio_rl / 0.15, 0, 1)` — 0~0.15 선형 증가
- RL 완전 미접지 시 pair_b(FR↔RL) 보상 완전 차단
- pair_a(FL↔RR)는 영향 없음 ← **이것이 RR collapse 방어 부재의 원인**

### 4.4 curriculum validity ramp 무력화

V24의 validity_ramp를 사실상 비활성화:
```python
"validity_ramp_start": 0,   # no-op
"validity_ramp_end": 1,
```
`initial_weight`와 `final_weight` 모두 0.0 → ramp term 아무 효과 없음.

---

## 5. restart-on-collapse 자동화 (heartbeat.py)

### 상수 설정

```python
_COLLAPSE_CHECK_ITER_MIN = 100   # iter 100 이전은 warming-up — 감지 안 함
_COLLAPSE_CHECK_ITER_MAX = 300   # iter 300 이후는 이미 늦음
_COLLAPSE_CONTACT_THRESHOLD = 0.05
_COLLAPSE_SWING_THRESHOLD = 0.95
_COLLAPSE_CONSECUTIVE_REQUIRED = 3
```

### 감지 조건

iter 100~300 구간에서 매 poll:
```
contact_ratio_rl < 0.05  AND  swing_time_rl > 0.95
```
이 조건이 **연속 3회** 충족되면 collapse 확정.

### 동작 흐름

```
조건 충족 3회 연속 → collapse 확정
  → stop_training()
  → Telegram: 🚨 COLLAPSE RESTART — iter N
  → launch_training(fresh=True)  ← 반드시 fresh=True
  → collapse_restart_done = True  (한 run에서 1회만)
```

iter 300 이후: restart 없음 — 설계 자체 재검토 필요.

---

## 6. 인프라: `/start` vs `/resume` 명령 분리

V25 훈련 시작 전 state.json에 V24 checkpoint가 남아있는 문제 해결.

```
Telegram: /start
  → checkpoint 없으면: 즉시 fresh start
  → 있으면: 확인 메시지 (현재 iter 표기) → Y 입력 시 fresh start, 그 외 취소 (60초 타임아웃)
```

`launch_training(fresh=True)` 핵심:
- `active_checkpoint = None` 고정 (구 checkpoint 재참조 버그 수정)

---

## 7. 훈련 경과 기록

### iter ~300 중간 판정 (2026-03-14)

**판정: 유지 가능하지만, 아직 성공 아님**

| 지표 | 값 |
|------|----|
| reward | 196 |
| ep_len | 189.6 |
| survival rate | 37.9% |
| timeout rate | 73% |
| stability | F 지속 |

위험 신호:
- `rear_alternation` / `rear_joint_velocity` TOP → rear-driven 쏠림 가능성
- RL limb-wise 핵심값이 리포트에 누락

### iter ~500 중간 판정 (2026-03-15)

**판정: 유지. 그러나 핵심 문제는 아직 미확인**

| 지표 | iter ~300 | iter ~500 |
|------|-----------|-----------|
| reward | 196 | **312** |
| ep_len | 189.6 | **233** |
| survival rate | 37.9% | **46.6%** |
| timeout rate | 73% | **86%** |
| stability | F | F (지속) |

기초 안정화는 진행 중이었으나 rear-driven 쏠림 의심 강화. RL 핵심 지표 여전히 리포트 없음.

### iter 400 최종 판정 (2026-03-15)

섹션 0 참조. 훈련 중단.

---

## 8. 실패 원인 분석

### 근본 원인: 비대칭 패널티의 구조적 한계

V25는 RL collapse를 막는 데는 성공했다. `rear_left_contact_floor_penalty -60`은 설계 의도대로 작동했다. 그러나 정책은 단순히 다른 출구(RR)를 찾았다.

```
V24: RL collapse (FL/FR/RR 정상)
V25: RR collapse (FL/FR/RL 정상 — RL은 강제로 회복됨)
```

**정책의 합리성**: 3족 보행이 4족 보행보다 특정 보상(trot, survival)을 더 잘 획득할 수 있다면, 정책은 어떤 다리라도 포기하는 방향을 택한다. 어떤 다리를 포기할지만 달라질 뿐.

### 설계 결함 목록

| 결함 | 설명 |
|------|------|
| 비대칭 타겟 | RL만 보호 → RR이 새 탈출구 |
| pair_a 차단 없음 | diagonal gate가 pair_b(FR↔RL)만 차단 → RR collapse 시 pair_a(FL↔RR)는 여전히 보상 |
| 3족 보행 이득 존재 | trot/survival 보상 구조가 3족 보행에서도 작동 |

### V26 설계 방향

- **Symmetric per-leg existence floor**: 모든 다리에 동일한 contact floor penalty 적용 → collapse 이동 불가
- `per_leg_contact_floor_penalty` (FL/FR/RL/RR 전체) + `per_leg_propulsion_floor_penalty`
- diagonal gate도 특정 다리가 아닌 모든 다리 기준으로 일반화

---

## 9. 변경 요약 (V24 → V25)

### reward 변경

| 항목 | V24 | V25 |
|------|-----|-----|
| `limb_usage_min_penalty` | weight -12.0 | **제거** |
| `rear_left_right_usage_diff_penalty` | weight -8.0 | **제거** |
| `rear_left_contact_floor_penalty` | 없음 | **신규** weight -60.0, iter 0부터 |
| `diagonal_coupling` — RL gate | 없음 | **추가** soft gate threshold 0.15 |
| validity_ramp | iter 200~600 | **무력화** (initial/final=0) |
| `TRAIN_VERSION` | "V24" | "V25" |

### 인프라 변경

| 항목 | 변경 내용 |
|------|----------|
| heartbeat.py | restart-on-collapse 추가 (iter 100~300, 연속 3회) |
| supervisor.py | `/start` fresh start 확인 흐름 (Y만 확인, 나머지 취소) |
| supervisor.py | `/resume` 명령 신규 분리 |
| common.py | `launch_training(fresh=True/False)` 파라미터 추가 |
| common.py | `fresh=True` 시 구 checkpoint 재참조 버그 수정 |
