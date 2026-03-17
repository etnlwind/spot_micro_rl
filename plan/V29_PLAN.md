# V29_PLAN.md

## 한 줄 정의
**V29는 V28.3에서 front contact cap이 앞발 고착 local optimum을 깨지 못한 근본 원인을 수정하는 버전이다.**
핵심 문제는 `contact_residency` 밴드에 상한이 없어 FL/FR contact 0.83도 최대 reward를 받는 구조이며,
밴드 상한 추가 + 보폭 직접 보상 + swing 조건부 속도 보상으로 "큰 보폭 trot"을 유도한다.

---

## V28.3 실측 결과 요약

### 실패
| iter | FL contact | FR contact | FL swing | FR swing | rear_usage_diff | diagonal |
|------|-----------|-----------|----------|----------|-----------------|----------|
| 700  | 0.799 | 0.808 | 0.172 | 0.164 | 0.033 | 0.522 |
| 1001 | 0.783 | 0.807 | 0.204 | 0.179 | 0.000 | 0.559 |
| 1701 | 0.830 | 0.874 | 0.168 | 0.124 | 0.000 | 0.538 |
| 2200 | 0.824 | 0.883 | 0.174 | 0.115 | 0.014 | 0.536 |

cap ramp 시작 후 FL/FR contact 거의 변화 없음. FR swing은 오히려 0.164 → 0.115로 감소.
iter 1000 full strength 이후에도 front-heavy 패턴 고착. **cap 효과 없음.**

### 성공
- rear_usage_diff: 0.000~0.033 (V28.2 달성 완전 유지)
- limb_validity_pass: 전 구간 유지

---

## 근본 원인 재진단

### 원인 1. contact_residency 밴드에 상한 없음 (핵심)

`per_leg_contact_band_residency_reward` 실제 구현:

```python
in_band = 1.0 if contact_ratio >= 0.20 else 0.0
ema = ema * 0.95 + in_band * 0.05
reward = ema * weight   # late_max = 4.0
```

**band_low=0.20만 존재, 상한 없음.**

```
FL contact 0.50 → in_band=1.0 → EMA≈1.0 → reward ≈ 4.0/step
FL contact 0.83 → in_band=1.0 → EMA≈1.0 → reward ≈ 4.0/step  (동일!)
```

FL/FR이 0.83이든 0.50이든 contact_residency는 동일하게 최대 reward를 지급.
cap(-10.0)이 이 local optimum을 외부에서 억제하려 했지만,
이미 굳어진 보행 패턴 + trot_gait(weight=180.0)의 관성을 깨지 못함.

### 원인 2. stride_length_reward 비활성

foot liftoff → touchdown 사이 XY 변위를 측정하는 함수가 이미 구현되어 있지만
**weight=0.0으로 한 번도 사용되지 않았음.**

앞발이 크게 들려야 → 큰 보폭 → reward 증가하는 직접 신호가 없음.

### 원인 3. 몸체 안정성 패널티 너무 약함

```python
lin_vel_z_l2  = -0.7    # 수직 진동 억제 (너무 약함)
ang_vel_xy_l2 = -0.2    # pitch/roll 억제 (사실상 무시됨)
```

trot_gait(180.0), forward_velocity(35.0)에 비해 안정성 패널티가 너무 작아
착지 충격과 자세 흔들림이 제대로 억제되지 않음.

---

## 설계 철학 — "보폭 효율"

### 핵심 통찰

> 기계의 수명은 접지 횟수에 비례한다. 같은 거리를 이동하려면 접지 횟수를 최소화하면서
> 한 번 발을 움직일 때 최대한 크게 벌려야 한다. 단, 과도한 보폭은 몸체 충격과
> 불필요한 동력 소비를 유발하므로, 몸체에 충격이 가지 않을 만큼 자연스러운 최적 보폭을
> 스스로 찾게 해야 한다.

**수식화**:
```
stride_efficiency = 이동 거리 / 접지 횟수
                  = forward_velocity × (1 - avg_contact_ratio)
최적화 목표: stride_efficiency 최대화, body_impact 최소화
```

이 목표를 직접 보상하면 trot 보행이 자연스럽게 출현한다:
- 접지 과다(앞발 고착) → contact_residency 감소 → 자연적 억제
- 보폭 증가 → stride_length_reward 증가 → 자연적 장려
- 충격 과다(과보폭) → lin_vel_z + ang_vel_xy 패널티 증가 → 자연적 조절
- 4발 불균형 → swing_gate_velocity 감소 → 자연적 균형 유도

---

## V29 핵심 수정 (5개)

### 수정 1. contact_residency 밴드 상한 추가

**목적**: FL/FR contact 0.65 초과 시 residency EMA 감소 → reward 내재적 억제.
외부 패널티 없이 reward 구조 자체가 앞발 고착을 막는 구조.

**변경**:
```python
# 현재 (V28.3)
in_band = 1.0 if contact_ratio >= 0.20 else 0.0

# V29
in_band = 1.0 if (0.25 <= contact_ratio <= 0.65) else 0.0
```

파라미터:
- `band_low`: 0.20 → **0.25** (완전 허공 방지 유지)
- `band_high`: 없음 → **0.65** (이상 시 EMA 하락 시작)

**수치 근거**:
```
FL contact 0.83 (V28.3 실측):
  V28.3: in_band=1.0 → EMA 유지 → reward 4.0/step
  V29:   in_band=0.0 → EMA 서서히 하락 → reward 감소

EMA alpha=0.05, episode=1000 step 가정:
  50 step 후: EMA = 0.95^50 ≈ 0.077 (reward 거의 0)
  → 앞발이 0.65 초과 유지하면 약 50 step 내에 residency reward 소멸
```

**propulsion_residency, usage_residency도 동일하게 적용**:
- `prop_band_high`: 없음 → **0.65**
- `usage_band_high`: 없음 → **0.65**

---

### 수정 2. stride_length_reward 활성화

**목적**: 발이 공중에서 멀리 이동할수록 직접 보상. 앞발 lift + 크게 내딛기 유도.

**설계**:
```python
# env_cfg.py
self.rewards.stride_length = RewTerm(
    func=custom_mdp.stride_length_reward,
    weight=0.0,  # curriculum ramp으로 제어
    params={
        "target_stride": 0.10,   # 0.06m → 0.10m (자연 trot 보폭)
        "min_vel": 0.05,
        ...
    },
)
```

**TRAINING_CONFIG 추가**:
```python
"stride_length_ramp_start": 400,
"stride_length_ramp_end": 700,
"stride_length_max": 12.0,
```

**수치 근거**:
```
trot 보폭 이론값: 0.08~0.12m (체장의 20~30%)
target_stride=0.10m → 자연스러운 중간값
max=12.0 → forward_velocity(35.0)의 34% — 보조 신호로 적절

현재 FL/FR swing 0.115~0.174:
  FL stride ≈ 0 (앞발 거의 안 들림)
  → stride_length_reward → 0 → 보상 박탈 → 자연적 압박
```

---

### 수정 3. swing_quality_gate_velocity 신규

**목적**: 4발 중 가장 swing이 적은 발이 병목. 모든 발이 균등히 스윙해야 전진 보상 지급.

**설계**:
```python
def swing_quality_gated_velocity(
    env, swing_target=0.30, min_vel=0.05, asset_cfg=...
):
    """V29: forward velocity × min_swing_quality gate.

    4발 중 최소 swing ratio로 forward velocity reward를 조건부 지급.
    앞발 swing 0.12 → gate ≈ 0.40 → velocity reward 40%만 지급.
    모든 발 swing ≥ 0.30 → gate 1.0 → full velocity reward.
    """
    metrics = compute_v23_raw_metrics(env)
    min_swing = torch.min(torch.stack([
        metrics["swing_time_fl"], metrics["swing_time_fr"],
        metrics["swing_time_rl"], metrics["swing_time_rr"]
    ], dim=-1), dim=-1).values
    gate = torch.clamp(min_swing / swing_target, 0.0, 1.0)
    fwd_vel = ... # heading velocity
    return fwd_vel * gate * _heading_velocity_gate(env, asset_cfg, min_vel)
```

**TRAINING_CONFIG 추가**:
```python
"swing_gate_ramp_start": 500,
"swing_gate_ramp_end": 800,
"swing_gate_max": 20.0,  # forward_velocity(35.0)의 일부를 이쪽으로 이전
```

**수치 근거**:
```
V28.3 실측 FL swing=0.174, FR swing=0.115:
  min_swing = 0.115
  gate = 0.115 / 0.30 = 0.383
  swing_gate_velocity ≈ fwd_vel × 0.383 → reward 62% 손실

FL/FR swing 0.30 달성 시:
  gate = 1.0 → full reward
  → 4발 균등 swing이 직접 이익
```

---

### 수정 4. 몸체 안정성 패널티 강화

**목적**: 자연스러운 보폭 상한 자동 조절. 과보폭 시 몸체 흔들림 → 패널티 증가 → 스스로 최적 보폭 탐색.

**변경**:
```python
# 현재 → V29
lin_vel_z_l2:  -0.7 → -2.0   # 착지 충격(수직 진동) 억제 강화
ang_vel_xy_l2: -0.2 → -1.0   # 과보폭 시 pitch/roll 흔들림 억제
```

**효과**:
```
보폭이 너무 작을 때: stride_length_reward 감소 → 더 크게 내딛도록 유도
보폭이 너무 클 때:  착지 충격 증가 → lin_vel_z 패널티 증가 → 조절
→ 자연스러운 최적 보폭이 reward 함수 내에서 스스로 결정됨
```

---

### 수정 5. front_contact_cap 제거, front_balance 제거

V28.3에서 추가한 두 항목을 제거:
- `front_pair_contact_cap_penalty`: 수정 1(residency 재설계)로 내재화됨, 중복
- `front_rear_support_balance_penalty`: 수정 3(swing_gate)으로 대체됨

외부 패널티 레이어를 줄이고 reward 구조 자체로 유도하는 방향.

---

## 타이밍 설계

```
iter 0~300:    Layer C 진입 (4발 기립 + 기본 움직임)
iter 300~600:  rear_contact_diff ramp (V28.2)
iter 400~700:  rear_symmetry → full strength (V28.2)
               stride_length ramp 시작 (V29 신규)
iter 500~800:  swing_gate_velocity ramp (V29 신규)
iter 600~800:  coop_min_leg ramp (V28.2)
iter 600~900:  exit_penalty ramp (V28.2)
iter 800+:     모든 제약 full strength
               contact_residency 쌍방향 밴드 + stride + swing_gate 동시 작동
```

**핵심 원칙**:
- rear symmetry(iter 400~700) 안정화 후 보폭 reward 개입
- swing_gate는 stride보다 100 iter 늦게 시작 (stride 학습 후 velocity와 연동)

---

## 파일별 변경 내역

### `rewards.py`

1. **`per_leg_contact_band_residency_reward` 수정**
   - `band_high` 파라미터 추가 (default=1.0, 하위 호환)
   - `in_band = 1.0 if band_low <= contact_ratio <= band_high else 0.0`
   - propulsion_residency, usage_residency 동일하게 적용

2. **`swing_quality_gated_velocity` 신규 추가**
   - 4발 min swing ratio × heading_velocity

3. **`reward_weight_curriculum` 파라미터 추가**
   - `stride_length_ramp_start/end/max`
   - `swing_gate_ramp_start/end/max`

4. **`_curriculum_apply_v281_weights` 확장**
   - stride_length term weight 관리
   - swing_gate_velocity term weight 관리
   - front_contact_cap, front_balance 항목 제거

### `env_cfg.py`

1. **TRAIN_VERSION**: `"V28.3"` → `"V29"`

2. **contact_residency 파라미터 변경**:
   ```python
   # per_leg_contact_band_residency
   "band_low": 0.20 → 0.25
   "band_high": (없음) → 0.65    # 신규

   # per_leg_propulsion_band_residency
   "band_high": (없음) → 0.65

   # per_leg_usage_band_residency
   "band_high": (없음) → 0.65
   ```

3. **안정성 패널티 weight 변경**:
   ```python
   lin_vel_z_l2:  -0.7 → -2.0
   ang_vel_xy_l2: -0.2 → -1.0
   ```

4. **신규 RewTerm**:
   ```python
   # stride_length: weight 0.0 → curriculum ramp (max 12.0)
   self.rewards.stride_length.weight = 0.0  # 기존 항목, 파라미터 조정
   self.rewards.stride_length.params["target_stride"] = 0.10

   # swing_quality_gated_velocity: 신규
   self.rewards.swing_gate_velocity = RewTerm(
       func=custom_mdp.swing_quality_gated_velocity,
       weight=0.0,  # curriculum ramp max 20.0
       params={"swing_target": 0.30, "min_vel": 0.05, ...},
   )
   ```

5. **제거할 RewTerm**:
   - `self.rewards.front_pair_contact_cap` 제거
   - `self.rewards.front_rear_support_balance_penalty` weight 0.0 유지 (파라미터 원복)

6. **TRAINING_CONFIG 변경**:
   ```python
   # 제거
   "front_contact_cap_ramp_start": ...,
   "front_contact_cap_ramp_end": ...,
   "front_contact_cap_max": ...,
   "front_balance_ramp_start": ...,
   "front_balance_ramp_end": ...,
   "front_balance_max": ...,

   # 추가
   "stride_length_ramp_start": 400,
   "stride_length_ramp_end": 700,
   "stride_length_max": 12.0,
   "swing_gate_ramp_start": 500,
   "swing_gate_ramp_end": 800,
   "swing_gate_max": 20.0,
   ```

---

## 수치 근거 요약

| 수정 | 수치 | 근거 |
|------|------|------|
| contact band_high=0.65 | trot 허용 최대 contact | EMA alpha=0.05 → 50 step 내 reward 소멸 |
| stride target=0.10m | trot 보폭 이론값 0.08~0.12m | 자연스러운 중간값 |
| stride max=12.0 | fwd_vel(35.0)의 34% | 보조 신호, 주 신호 초과 금지 |
| swing_gate max=20.0 | fwd_vel(35.0)의 57% | 4발 균등 swing 강력 유도 |
| lin_vel_z -0.7→-2.0 | 충격 억제 2.9배 | trot_gait(180) 대비 여전히 약하지만 의미있는 신호 |
| ang_vel_xy -0.2→-1.0 | 흔들림 억제 5배 | 과보폭 자동 조절 역할 |

---

## 판정 기준

### iter 500 — 초기 판정
- FL/FR contact < 0.75 (residency 밴드 압박 시작 확인)
- rear_usage_diff < 0.10 (V28.2 성과 유지)
- stride_length reward 발동 확인 (rear부터라도)

### iter 800 — 핵심 판정
- FL/FR contact < 0.70 ✅
- FL/FR swing > 0.20 ✅ (V28.3 iter 700 수준 0.17에서 개선)
- diagonal_coupling_raw > 0.55 ✅
- 4발 validity pass 유지

### iter 1000 — 목표 판정
- FL/FR contact 0.40~0.65 ✅
- FL/FR swing > 0.30 ✅
- front-rear diff < 0.20 ✅
- diagonal_coupling_raw > 0.65 ✅

### iter 1500 — 최종 판정
- 4발 contact 0.40~0.55 (균등 trot) ✅
- FL/FR swing ≈ RL/RR swing (4발 대칭) ✅
- diagonal_coupling_raw > 0.70 ✅
- rear_usage_diff < 0.10 유지 ✅

### 중단 조건
| 조건 | 기준 iter | 판정 |
|------|-----------|------|
| FL/FR contact 증가 (0.90+) | iter 600+ | residency 밴드 재검토 |
| rear_usage_diff > 0.20 재발 | iter 500+ | 즉시 중단 — rear 우선 |
| 4발 validity fail 지속 | iter 500+ | 즉시 중단 |
| stride_length reward = 0 지속 | iter 800+ | band_high 재검토 |

---

## 리스크

### 리스크 1. contact_residency 밴드 상한이 초반 학습을 불안정하게 만들 가능성
초반(iter 0~400)에는 contact가 0.10~0.40 수준이어서 band_high 영향 없음.
**대응**: band_high는 고착 억제 목적 — 초반 낮은 contact 구간에서는 in_band=1.0으로 정상 학습.

### 리스크 2. swing_gate_velocity가 너무 강해 early collapse 유발
iter 500에서 FL swing=0.17이면 gate=0.57 → velocity reward 43% 손실.
**대응**: ramp_start=500, max=20.0은 점진적. iter 500에서 weight≈0으로 시작해 iter 800에서 full.
iter 800 이전에는 forward_velocity(35.0)이 주 신호로 유지됨.

### 리스크 3. 보폭 목표(0.10m)가 Spot Micro 체형에 비해 과도할 가능성
Spot Micro 다리 길이 대비 0.10m가 실제로 달성 가능한 보폭인지 불확실.
**대응**: stride_length_reward는 target 도달 시 reward이지 페널티가 없음.
0.10m 미달 시 reward가 줄어들 뿐 — 자연스러운 최대 보폭 탐색.

### 리스크 4. rear symmetry 재붕괴
V29에서 reward 구조가 바뀌어 rear가 다시 불안정해질 가능성.
**대응**: rear_symmetry_max -28.0, rear_contact_diff -15.0 완전 유지.
heartbeat의 rear_pair_residency_gap > 0.15 경보 유지.

---

## 유지할 것 (V28.2에서 그대로)

| 항목 | 유지 이유 |
|------|----------|
| rear_symmetry_max -28.0, ramp 400~700 | 달성된 rear 대칭 보호 |
| rear_pair_contact_diff -15.0 | EMA 사각지대 즉각 반응 |
| exit_penalty_max -15.0 | 밴드 이탈 억제 |
| coop_min_leg_factor 0.05 | RR 약세 시 cooperation 차단 |
| residency relay (early/late) | 구조 유효, band 파라미터만 수정 |
| heartbeat residency 경보 | rear_pair_residency_gap > 0.15 유지 |

---

## V28.2 / V28.3 / V29 비교표

| 항목 | V28.2 | V28.3 | V29 |
|------|-------|-------|-----|
| rear_symmetry_max | -28.0 | -28.0 (유지) | -28.0 (유지) |
| rear_contact_diff | -15.0 | -15.0 (유지) | -15.0 (유지) |
| contact_residency band | low=0.20 only | low=0.20 only | **low=0.25, high=0.65** |
| front_contact_cap | 없음 | -10.0 | **제거** |
| front_balance | 비활성 | -8.0 | **제거** |
| stride_length_reward | 비활성 | 비활성 | **max=12.0 활성화** |
| swing_gate_velocity | 없음 | 없음 | **max=20.0 신규** |
| lin_vel_z_l2 | -0.7 | -0.7 | **-2.0** |
| ang_vel_xy_l2 | -0.2 | -0.2 | **-1.0** |
| 앞발 고착 해결 | ❌ | ❌ | ✅ (목표) |
| 큰 보폭 trot | ❌ | ❌ | ✅ (목표) |

---

## 구현 우선순위

| 순위 | 항목 | 파일 | 중요도 |
|------|------|------|--------|
| 1 | contact/prop/usage residency band_high=0.65 추가 | rewards.py | 🔴 Critical |
| 2 | swing_quality_gated_velocity 신규 함수 | rewards.py | 🔴 Critical |
| 3 | stride_length target=0.10, weight ramp 활성화 | env_cfg.py | 🔴 Critical |
| 4 | lin_vel_z_l2 -2.0, ang_vel_xy_l2 -1.0 | env_cfg.py | 🟡 Important |
| 5 | front_contact_cap / front_balance 제거 | env_cfg.py | 🟡 Important |
| 6 | TRAIN_VERSION "V29" | env_cfg.py | 🟢 Minor |

---

## 구현 주의사항

1. **band_high는 하위 호환 파라미터로 추가**
   기존 `per_leg_contact_band_residency_reward` 시그니처에 `band_high=1.0` 기본값으로 추가.
   V28.x 이전 config는 기본값(1.0=상한 없음)으로 자동 호환.

2. **swing_gate_velocity는 forward_velocity를 대체하지 않음**
   두 reward 항목이 공존. forward_velocity(35.0)은 기본 이동 학습용으로 유지.
   swing_gate_velocity(20.0)는 추가 보상으로 4발 균등성 유도.

3. **stride_length_reward 기존 구현 확인 필수**
   weight=0.0이었던 이유가 있을 수 있음 — 활성화 전 함수 동작 검증.
   특히 foot liftoff/touchdown 감지 로직이 현재 물리 설정에서 올바르게 작동하는지 확인.

4. **residency EMA는 episode 리셋 시 초기화됨**
   run 재기동 후 EMA=0에서 시작 → 약 20 episode 후 수렴.
   band_high 효과는 EMA 수렴 후 발현 — 재기동 직후 FL 일시적 하락 후 band_high에 막힘.

5. **heartbeat 모니터링 항목 추가**
   V29에서 반드시 확인할 신규 지표:
   - `stride_length_fl/fr/rl/rr` (보폭 달성 여부)
   - `swing_gate_alpha` (gate 작동 강도)

---

## 최종 판단

V28.3 실패의 핵심은 **외부에서 패널티를 추가하는 방식의 한계**였다.
contact_residency 구조 자체가 앞발 고착을 지원하는 한, 아무리 강한 cap을 추가해도
이미 형성된 보행 패턴을 깨기 어렵다.

V29는 reward 구조 안에서 앞발 고착이 자연스럽게 손해가 되고,
큰 보폭 trot이 자연스럽게 이익이 되도록 재설계한다.
**억제가 아닌 유도, 패널티가 아닌 구조 교정이 V29의 방향이다.**

---

마지막 업데이트: 2026-03-17
기준 데이터: V28.3 Run3 (2026-03-17_15-28-19) iter 2200
