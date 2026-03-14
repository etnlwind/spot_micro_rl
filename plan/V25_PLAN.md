# V25 설계 및 구현 문서

> ⚠️ **SUPERSEDED**: 이 문서는 V25 설계 초안입니다.
> 훈련 결과 및 실패 분석은 **[V25_ANALYSIS.md](V25_ANALYSIS.md)** 를 참조하세요.

> 작성: Claude Sonnet 4.6 / 2026-03-14
> 상태: ~~구현 완료, 훈련 실행 중~~ → **실패 (iter 400, RR collapse)**
> 목적: V25에서 변경된 모든 설계 결정, 구현 내용, 운영 기준을 단일 문서로 정리

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
   → rear-left collapse는 iter 100~200 이전에 이미 고착됨. 패널티가 시작되기 전에 정책이 굳어버림

3. **diagonal_coupling exploit 경로 미차단**: RL이 접지하지 않아도 FR↔RL 관절 속도 상관이 일부 유지되어 diagonal_coupling 보상을 부분적으로 획득할 수 있었음
   → 3족 보행에서도 diagonal reward를 먹는 경로가 열려 있었음

4. **usage proxy 신호 희석**: `limb_usage_min_penalty`는 4개 다리 평균 또는 min 기반
   → 나머지 3개 다리가 정상이면 RL 붕괴 신호가 희석됨

---

## 2. V25 핵심 설계 원칙

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

G의 V25-A/B 분기 구조를 채택하지 않은 이유:
- A/B 전환 대기(iter 200~300)가 V24 패턴 재현
- per_leg_contact_floor와 rear_left_contact_floor는 RL 붕괴 상황에서 gradient 신호가 사실상 동일 → A/B 분리가 의미없음
- 가장 강한 직접 처방 하나를 iter 0부터 적용하는 것이 더 빠름

---

## 3. 구현된 reward 변경사항

### 3.1 제거된 항목 (V24 → V25)

| 항목 | 이유 |
|------|------|
| `limb_usage_min_penalty` | weight -12, proxy 희석으로 실패 확인. rear_left_contact_floor로 대체 |
| `rear_left_right_usage_diff_penalty` | usage proxy 기반으로 동일한 희석 문제. RL collapse 시 이미 rear_left_contact_floor가 작동 |

### 3.2 신규 항목

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
    rl_contact = _contact_ratio(contact_sensor, sensor_cfg.body_ids, contact_threshold)  # (N, 1)
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

동작 설명:
- `contact_ratio_rl < 0.30`이면 `gap = 0.30 - contact_ratio_rl` → 패널티 발생
- `contact_ratio_rl ≥ 0.30`이면 `gap = 0` → 패널티 없음
- 전진 속도 < `min_vel` (0.05 m/s)이면 gate=0 → 정지 상태에서는 패널티 없음
- ramp 없음 — iter 0부터 weight -60 전력 적용
- weight -60 × gap 최대(0.30) = **-18/step** ≈ 총 reward의 ~3.3%
  (gap이 더 클수록 패널티 증가, floor 미달 시 최대 -60 × 1.0 = -60/step)

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
self.rewards.diagonal_coupling = RewTerm(
    func=custom_mdp.diagonal_joint_coupling_reward,
    weight=25.0,
    params={
        ...
        # V25 추가 파라미터
        "rl_participation_sensor_cfg": SceneEntityCfg("contact_forces", body_names="rear_left_toe_link"),
        "rl_contact_threshold": 1.0,
        "rl_min_contact": 0.15,
    },
)
```

동작 설명:
- `rl_gate = clamp(contact_ratio_rl / 0.15, 0, 1)`
- `contact_ratio_rl = 0` → gate = 0 → pair_b(FR↔RL) 보상 완전 차단
- `contact_ratio_rl = 0.15` → gate = 1.0 → 정상 보상
- 0~0.15 구간 선형 증가 → gradient 연속 (binary gate 불사용)
- pair_a(FL↔RR)는 영향 없음 — RL 붕괴가 FL↔RR 보상을 막지 않음

**왜 binary가 아닌 soft gate인가:**
0.14↔0.16 경계에서 reward가 계단식으로 변하면 PPO gradient 추정이 불안정해짐.
soft gate는 0~0.15 전 구간에서 gradient를 유지.

### 3.4 curriculum validity ramp 무력화

V24의 validity_ramp가 iter 200 이전에는 패널티를 주지 않았던 문제를 해결.
V25에서 validity ramp를 사실상 비활성화:

```python
"validity_ramp_start": 0,   # V25: 해당 term 없음 — no-op
"validity_ramp_end": 1,
```

`initial_weight`와 `final_weight` 모두 0.0으로 유지 → ramp term이 있어도 아무 효과 없음.

---

## 4. restart-on-collapse 자동화 (heartbeat.py)

### 목적

collapse는 iter 100~200에 고착된다. iter 300이 되어서 사람이 판단하면 이미 늦다.
heartbeat가 자동으로 감지하여 fresh restart를 실행.

### 상수 설정

```python
_COLLAPSE_CHECK_ITER_MIN = 100   # iter 100 이전은 warming-up — 감지 안 함
_COLLAPSE_CHECK_ITER_MAX = 300   # iter 300 이후는 이미 늦음 — restart 대신 알림만
_COLLAPSE_CONTACT_THRESHOLD = 0.05
_COLLAPSE_SWING_THRESHOLD = 0.95
_COLLAPSE_CONSECUTIVE_REQUIRED = 3  # 연속 N회 감지 시 실제 collapse로 판정
```

### 감지 조건

iter 100~300 구간에서 매 poll 마다 아래를 체크:

```
contact_ratio_rl < 0.05  AND  swing_time_rl > 0.95
```

이 조건이 **연속 3회** 충족되면 collapse로 확정.

### 동작 흐름

```
조건 충족 (연속 1회) → collapse_consecutive_count = 1, 로그만
조건 충족 (연속 2회) → collapse_consecutive_count = 2, 로그만
조건 충족 (연속 3회) → collapse 확정
  → stop_training()
  → Telegram: 🚨 COLLAPSE RESTART — iter N
  → launch_training(fresh=True)  ← 반드시 fresh=True
  → collapse_restart_done = True  (한 run에서 1회만)
```

**왜 fresh=True인가:**
collapsed 모델 checkpoint로 resume하면 동일한 collapse로 즉시 복귀.
iter 0부터 다시 학습해야 의미 있는 재시작.

### iter 300 이후

`_COLLAPSE_CHECK_ITER_MAX = 300` 이후에는 restart를 실행하지 않음.
이유: iter 300에서도 collapse가 남아있으면 설계 자체를 재검토해야 할 상황.
자동 restart가 아니라 수동 판단 + V26 설계 검토가 올바른 대응.

### collapse_restart_done 플래그

한 run 안에서 restart는 1회만 실행.
restart 후 새 run에서는 플래그가 초기화되어 다시 감지 시작.

---

## 5. 운영 기준 (heartbeat / KPI 기반)

### 단계별 기준

| iter 구간 | 동작 |
|-----------|------|
| 0~99 | warming-up — collapse 감지 안 함, 기록만 |
| 100~299 | collapse 감지 구간 — 연속 3회 확인 시 automatic fresh restart |
| 300+ | restart 없음 — KPI 확인 후 수동 판단 |

### iter 300 기준 KPI 판정

| 지표 | 통과 기준 | 판정 |
|------|-----------|------|
| contact_ratio_rl | ≥ 0.10 | 최소 접지 형성 |
| swing_time_rl | ≤ 0.85 | 공중 지속 개선 |
| contact_ratio_rl | ≥ 0.05 | 신호라도 있으면 관찰 유지 |
| contact_ratio_rl | < 0.05 | **설계 검토 권고** |

### 중단 기준

| 상황 | 대응 |
|------|------|
| iter 300, contact_ratio_rl < 0.05 지속 | 수동 중단, V25 설계 재검토 |
| iter 300, contact_ratio_rl 0.05~0.10 + 상승 추세 | 100 iter 추가 관찰 |
| iter 600, contact_ratio_rl < 0.05 | 즉시 중단, V26 설계 |

**원칙**: reward/survival이 좋아도 RL collapse가 남아있으면 실패.

---

## 6. `/start` vs `/resume` 명령 분리

V25 훈련 시작 전 state.json에 V24 checkpoint가 남아있는 문제 해결을 위해 구현.

### 흐름

```
Telegram: /start
  → checkpoint 존재 여부 확인 (state.json 기록 기준, 파일 존재 무관)
  → 없으면: 즉시 fresh start → 메시지1
  → 있으면: 메시지2 표시 (현재 iter 표기) → 사용자 응답 대기

사용자 Y 입력:
  → launch_training(fresh=True) → 메시지1

Y 외 모든 입력:
  → "취소되었습니다." → 중단
  (60초 무응답도 자동 취소)
```

### 메시지1 (fresh start 완료)

```
🚀 TRAINING START (FRESH)
run: 2026-03-14_22-23-04
iter 0부터 시작합니다.
```

### 메시지2 (기존 checkpoint 있을 때)

```
⚠️ 확인 필요 — FRESH START
현재 진행: iter 2,000 (model_2000.pt)

이 진행상황을 초기화하고 iter 0부터 새로 시작합니다.
계속하려면 Y를 입력하세요. (60초 내, 다른 입력은 취소)
```

### `launch_training(fresh=True)` 구현 핵심

```python
if fresh:
    update_state(active_run="", active_checkpoint="", last_command="start-fresh")
    command = build_train_command()  # checkpoint 인수 없음 — iter 0부터
    ...
    # 5초 대기 후 state 업데이트 시 구 checkpoint 참조 금지
    active_checkpoint = None  # fresh start는 checkpoint 없음
```

**버그 수정 이력**:
- 최초 구현에서 `fresh=True`임에도 5초 대기 후 구 run의 checkpoint를 조회하여 state에 다시 쓰는 버그 있었음
- 수정: `fresh=True` 시 `active_checkpoint = None` 고정, 구 run 조회 없음

---

## 7. 요약: V24 → V25 변경 전체 목록

### reward 변경

| 항목 | V24 | V25 |
|------|-----|-----|
| `limb_usage_min_penalty` | weight -12.0 | **제거** |
| `rear_left_right_usage_diff_penalty` | weight -8.0 | **제거** |
| `rear_left_contact_floor_penalty` | 없음 | **신규** weight -60.0 |
| `diagonal_coupling` — RL gate | 없음 | **추가** soft gate threshold 0.15 |
| validity_ramp | iter 200~600 | **무력화** (0~1, initial/final=0) |
| `TRAIN_VERSION` | "V24" | "V25" |

### 인프라 변경

| 항목 | 변경 내용 |
|------|----------|
| heartbeat.py | restart-on-collapse 추가 (iter 100~300, 연속 3회) |
| supervisor.py | `/start` fresh start 확인 흐름 (Y만 확인, 나머지 취소) |
| supervisor.py | `/resume` 명령 신규 분리 |
| common.py | `launch_training(fresh=True/False)` 파라미터 추가 |
| common.py | `fresh=True` 시 구 checkpoint 재참조 버그 수정 |

---

## 9. 훈련 경과 기록

### iter ~300 중간 판정 (2026-03-14)

**판정: 유지 가능하지만, 아직 성공 아님**

iter 200 대비 명확한 개선:

| 지표 | 값 |
|------|----|
| reward | 196 |
| ep_len | 189.6 |
| survival rate | 37.9% |
| timeout rate | 73% |
| stability | **F 지속** |

**관찰된 위험 신호**:
- `rear_alternation` / `rear_joint_velocity` 리워드가 TOP 순위 → rear-driven 쏠림 가능성
- RL limb-wise 핵심값(`contact_ratio_rl`, `propulsion_rl`, `swing_time_rl`, `limb_usage_rl`, `limb_validity_reason`)이 리포트에 누락 → iter 400 전까지 수동 확인 필요

**iter 400 필수 확인 항목**:

| 항목 | 기준 | 비고 |
|------|------|------|
| `contact_ratio_rl` | ≥ 0.05 | rear_left 발바닥 접촉 여부 |
| `propulsion_rl` | ≥ 0.05 | rear_left 추진 기여 여부 |
| `swing_time_rl` | ≥ 0.05 | rear_left swing 동작 여부 |
| `limb_usage_rl` | ≥ 0.05 | rear_left 전반적 참여 |
| `limb_validity_reason` | 모든 limb 비율 ≥ 0.1 | 특정 limb 고사 여부 |
| `rear_alternation` 비율 | TOP에서 하락 | rear-쏠림 완화 추세 확인 |
| survival rate | ≥ 50% | 최소 생존 기준 |

**즉시 중단 조건** (iter 400 기준):
- `contact_ratio_rl` < 0.02 지속 → rear_left 완전 사망, V25 실패
- survival rate < 25% → 오히려 V24보다 퇴보
- reward < 150 → 명백한 회귀

### iter ~500 중간 판정 (2026-03-15)

**판정: 유지. 그러나 핵심 문제는 아직 미확인**

수치 지속 개선:

| 지표 | iter ~300 | iter ~500 |
|------|-----------|-----------|
| reward | 196 | **312** |
| ep_len | 189.6 | **233** |
| survival rate | 37.9% | **46.6%** |
| timeout rate | 73% | **86%** |
| stability | F | **F (지속)** |

**판단 근거**:
- 기초 안정화와 전진 형성은 살아 있음 → 유지 유효
- stability = F 지속, TOP 보상이 여전히 `rear_alternation` / `rear_joint_velocity` → rear-driven 쏠림 의심 강화
- RL 핵심 지표(contact_ratio_rl 등) 여전히 리포트 없음 → "문제 없음" 판단 불가

**iter 600 필수 확인 항목** (이전과 동일, 절대 생략 불가):

| 항목 | 판단 기준 |
|------|----------|
| `contact_ratio_rl` | RL 참여 여부 |
| `propulsion_rl` | 추진 기여 여부 |
| `swing_time_rl` | swing 동작 여부 |
| `limb_usage_rl` | 전반적 참여 여부 |
| `limb_validity_reason` | limb별 고사 여부 |

**즉시 중단 조건** (iter 600 기준):
- `contact_ratio_rl` ≈ 0, `propulsion_rl` ≈ 0, `swing_time_rl` ≈ 1 → rear_left 완전 미참여, V25 실패

> 한 줄 요약: 전체 학습은 올라가고 있지만, 우리가 해결하려는 핵심 문제(rear-left collapse)는 아직 확인조차 안 된 상태.

---

## 8. 미결 항목 (V25 결과 확인 후)

| 항목 | 조건 |
|------|------|
| V25 실패 시 V26 설계 | iter 300 contact_ratio_rl < 0.05 지속 시 |
| CRITICAL 알림 stage gating | iter 100+ 이후만 CRITICAL 출력 (false alarm 방지) — 미구현 |
| 400+ 자동 stop with 추세 체크 | V25 결과 확인 후 필요 시 구현 |
| report 최상단 limb collapse CRITICAL | V25 결과 확인 후 구현 여부 결정 |
