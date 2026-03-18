# V31 구현 계획: Front Swing 강제 — 구조적 접근

**기반**: V30 분석 결과 (iter 644), V28.2~V30 실패 패턴 종합
**목표**: FL/FR contact lock-in 해결 (0.82+ → 0.55~0.65 목표)

---

## V30 실패 요약

| 항목 | V30 실적 (iter 644) | 판정 |
|------|---------------------|------|
| 전체 reward | 322.8 (V29 max 303) | ✅ 학습 품질 향상 |
| FL/FR contact | 0.822 (V29: 0.845) | ❌ lock-in 방향 동일 |
| F-R gap | 0.348 (V29: 0.358) | ❌ 거의 불변 |
| front_rear_balance_penalty | -0.77 (w=-4.0) | ❌ 미미한 효과 |
| RL/RR 비대칭 | 0.085 (RL<RR) | ❌ 재발 |

**V30 결론**: 초기 자세 대칭은 학습 효율을 개선했으나, front contact lock-in의 근본 원인은 **reward 구조의 front swing 공백**임이 확정.

---

## 근본 원인 분석

### 왜 앞다리를 안 들까?

현재 reward 시스템에서 **뒷다리 swing을 유도하는 보상 5개**가 존재:

| reward | weight | 역할 |
|--------|--------|------|
| rear_swing_bonus | +15 | 뒷발 높이 들기 |
| rear_joint_velocity | +20 | 뒷다리 관절 속도 |
| rear_joint_frozen | -60 | 뒷다리 동결 처벌 |
| rear_alternation | +30 | 뒷다리 교대 |
| rear_both_ground | -80 | 뒷다리 동시 접지 처벌 |
| **합계** | **~205** | |

**앞다리 swing 유도 보상: 0개**

PPO는 합리적으로 행동: 뒷다리는 움직여야 reward → 움직임. 앞다리는 움직이면 안정성 하락만 → 접지 유지.

### front_rear_balance_penalty(-4.0)가 실패하는 이유

F-R gap 0.35에 대한 penalty는 최대 ~-1.0/step. 반면 앞다리 접지로 얻는 안정성 보상은:
- standing_height(10) + base_height(-15 회피) + flat_orientation(-7 회피) ≈ +5~10/step

**패널티 < 안정성 이득** → PPO는 합리적으로 접지 유지 선택.

---

## V31 설계

### 핵심 원칙

> **"뒷다리에 적용한 것과 동일한 swing 강제 메커니즘을 앞다리에도 적용"**

뒷다리 활성화(V15~V16)에서 검증된 구조를 앞다리에 대칭 적용.

### 변경 1: 신규 reward 함수 (rewards.py)

#### 1a. `front_swing_bonus` (NEW)

rear_swing_bonus의 앞다리 미러. 앞발이 swing 중 target_clearance 이상 들리면 보상.

```python
def front_swing_bonus(env, sensor_cfg, foot_cfg, asset_cfg, target_clearance, min_vel):
    # rear_swing_bonus와 동일 로직, body_names만 front_*_toe_link으로 변경
```

| 파라미터 | 값 | 근거 |
|----------|-----|------|
| weight | +12.0 | rear(15)의 80% — 앞다리는 조향 역할이 있어 약간 보수적 |
| target_clearance | 0.05 | rear(0.08)보다 낮음 — 앞다리는 높이 들 필요 없음 |

#### 1b. `front_both_ground_penalty` (NEW)

rear_both_ground_penalty의 앞다리 미러. FL+FR 동시 접지 시 패널티.

```python
def front_both_ground_penalty(env, sensor_cfg, asset_cfg, contact_threshold, min_vel):
    # rear_both_ground_penalty와 동일 로직, body_names만 front_*으로 변경
```

| 파라미터 | 값 | 근거 |
|----------|-----|------|
| weight | -40.0 | rear(-80)의 50% — 완전 대칭은 과도, 점진적 접근 |
| contact_threshold | 1.0 | rear와 동일 |

#### 1c. `front_alternation_reward` (NEW)

rear_alternation_reward의 앞다리 미러. FL/FR 교대 접지 시 보상.

```python
def front_alternation_reward(env, sensor_cfg, asset_cfg, contact_threshold, min_vel):
    # rear_alternation_reward와 동일 로직, body_names만 front_*으로 변경
```

| 파라미터 | 값 | 근거 |
|----------|-----|------|
| weight | +20.0 | rear(30)의 67% |
| contact_threshold | 1.0 | rear와 동일 |

#### 1d. `min_swing_ratio_penalty` (NEW)

per-leg swing ratio(= 1-contact_ratio)가 최소 기준 미달 시 패널티. 특정 다리가 아닌 **모든 다리에 공평하게** 적용.

```python
def min_swing_ratio_penalty(env, min_swing, min_vel, asset_cfg):
    # 각 다리의 episode swing ratio 계산
    # swing_ratio < min_swing인 다리마다 (min_swing - swing_ratio) * penalty
```

| 파라미터 | 값 | 근거 |
|----------|-----|------|
| weight | -20.0 | 강한 패널티 |
| min_swing | 0.20 | 최소 20% 시간은 swing 필요 (trot 이론값 50%) |

### 변경 2: 기존 reward 파라미터 조정 (env_cfg.py)

#### 2a. contact_residency band 축소

```
band_high: 0.85 → 0.70
```

**이유**: V29.2에서 FL/FR(0.84)을 band 안에 넣기 위해 0.85로 올렸지만, 이것이 오히려 FL/FR의 높은 contact를 **보상**하는 역효과. 0.70으로 낮추면 FL/FR(0.82)이 band 밖 → residency reward 감소 → 접지 줄이는 인센티브.

V29 문제(band 밖이면 gradient 0)는 V31의 새로운 swing 보상이 대체 gradient를 제공하므로 해결됨.

#### 2b. front_rear_support_balance_penalty 강화

```
weight: -4.0 → -8.0
max_diff: 0.25 → 0.15
```

**이유**: V30에서 -4.0/0.25가 -0.77에 불과. max_diff를 0.15로 줄이고 weight를 2배로 → 더 강한 gradient. V31의 front swing 보상이 안정성 손실을 보상하므로 안전.

#### 2c. per_leg_contact_target_band 조정

```
band_high: 0.75 → 0.65
```

**이유**: 현재 FL/FR(0.82)이 band 밖이어서 0 reward. 그러나 band를 좁히면 FL/FR이 내려와야 reward 진입 가능 → 더 명확한 유인.

### 변경 3: Curriculum 조정 (env_cfg.py)

Front swing 보상은 **iter 100부터** 서서히 활성화. 너무 이른 시점에 앞다리 swing을 강제하면 서기도 못 하는 상태에서 넘어짐.

```python
# V31: front swing ramp (iter 100~400)
"front_swing_ramp_start": 100,
"front_swing_ramp_end": 400,
"front_swing_bonus_max": 12.0,
"front_both_ground_max": -40.0,
"front_alternation_max": 20.0,
"min_swing_ratio_max": -20.0,
```

| iter 구간 | 기대 동작 |
|-----------|----------|
| 0~100 | 서기 + 안정화 (V30과 동일) |
| 100~400 | front swing 보상 점진 활성화 → 앞다리 들기 시작 |
| 400~800 | 4발 trot 학습 안정화 |
| 800~1200 | residency enforce → contact 분포 정밀 조정 |

---

## 예상 reward 균형 (iter 400+)

| 카테고리 | 앞다리 | 뒷다리 | 비고 |
|----------|--------|--------|------|
| swing bonus | +12 | +15 | 대칭 |
| both_ground penalty | -40 | -80 | 앞다리 보수적 |
| alternation | +20 | +30 | 대칭 |
| frozen/velocity | 0 | +20/-60 | 뒷다리 전용 유지 |
| **swing 계 합계** | **~72** | **~205** | 앞다리는 뒷다리의 35% — 점진적 도입 |

+ min_swing_ratio_penalty(-20): 4발 공통 — 어떤 다리든 swing < 20%이면 패널티

---

## 작업 목록

### Phase A: 코드 (rewards.py)
1. `front_swing_bonus` 함수 추가
2. `front_both_ground_penalty` 함수 추가
3. `front_alternation_reward` 함수 추가
4. `min_swing_ratio_penalty` 함수 추가

### Phase B: 설정 (env_cfg.py)
5. TRAIN_VERSION → "V31"
6. 4개 신규 reward term 등록
7. contact_residency band_high: 0.85 → 0.70
8. front_rear_balance_penalty: w -4→-8, max_diff 0.25→0.15
9. per_leg_contact_target_band band_high: 0.75 → 0.65

### Phase C: Curriculum (env_cfg.py)
10. front swing ramp 파라미터 추가 (iter 100~400)
11. reward_weight_curriculum 함수에 front swing ramp 로직 추가

### Phase D: 검증
12. supervisor 재시작 → V31 fresh start
13. iter 200: 앞다리 swing 시작 확인
14. iter 500: F-R gap < 0.25 확인
15. iter 1000: FL/FR contact < 0.70, F-R gap < 0.15

---

## 성공 기준

| 지표 | V30 실적 | V31 목표 |
|------|----------|----------|
| FL/FR contact | 0.822 | **< 0.65** |
| RL/RR contact | 0.474 | **> 0.50** |
| F-R gap | 0.348 | **< 0.15** |
| FL/FR swing ratio | ~0.18 | **> 0.35** |
| mean reward | 322 | **> 280** (4발 swing 비용 허용) |
| gait at iter 1000 | ⭐ B | **⭐ B 유지** |
| episode length | 247/250 | **> 230** |

reward 하락(322→280)은 예상됨 — 앞다리 swing은 안정성 비용을 수반. 280 이상이면 성공.

---

## 리스크

| 리스크 | 확률 | 대응 |
|--------|------|------|
| front swing 강제로 조기 넘어짐 증가 | 중 | ramp 시작 iter 100, weight는 rear의 35% 수준 |
| 4발 모두 swing → 지지점 부족 | 저 | trot_gait(w=40) + same_side_penalty(-30)가 대각선 패턴 유지 |
| reward 급락으로 학습 불안정 | 중 | iter 200에서 reward > 100 미달 시 front weight 50% 감소 |
| 뒷다리 활성도 하락 (front에 관심 분산) | 저 | rear 보상 유지 (변경 없음) |
| min_swing_ratio가 standing phase에서 오작동 | 저 | min_vel=0.05 gate 유지 |

---

## 설계 근거: 왜 reward 조정이 아닌 구조적 추가인가

V28.2~V30 (6개 버전) 실험 결과:

1. **패널티 강화** (front_rear_balance -4.0) → 효과 미미 (-0.77)
2. **band 축소** (V29 band_high=0.65) → gradient 소멸
3. **band 확장** (V29.2 band_high=0.85) → lock-in 보상
4. **물리 대칭** (V30 init pose) → lock-in 속도 감소만
5. **contact cap** (V28.3) → 고착 해결 불가

> **교훈 #6**: 특정 행동의 부재는 패널티로 해결할 수 없다 — 해당 행동에 대한 **명시적 보상**이 필요하다.

뒷다리 활성화가 V15~V16에서 성공한 이유: 5개의 전용 보상 함수로 "뒷다리를 움직이면 이득"이라는 명확한 신호를 제공. V31은 이 검증된 패턴을 앞다리에 적용.

---

## V31 실험 결과 및 V31.1 수정

### V31 결과 (iter 421, 조기 종료)

| 다리 | contact | propulsion | 상태 |
|------|---------|------------|------|
| FL | **0.815** | 0.611 | ❌ 고접지 유지 |
| FR | **0.031** | 0.035 | ❌ **완전 붕괴** |
| RL | **0.150** | 0.152 | ❌ **거의 붕괴** |
| RR | **0.805** | 0.622 | ❌ 고접지 유지 |

**실패 원인**: `front_alternation`(+16.6)이 "FL 항상 접지 + FR 항상 swing"이라는 **고정 역할**을 보상.
`abs(FL_contact - FR_contact)` 차이가 클수록 높은 reward → 한쪽만 영구적으로 드는 게 최적 전략.

> **교훈 #7**: step-level alternation check(`abs(a-b)`)는 temporal alternation을 강제하지 못한다 — "역할 분리"를 보상할 뿐이다.

### V31.1 수정

| 항목 | V31 | V31.1 | 이유 |
|------|-----|-------|------|
| front_alternation_max | 20.0 | **0.0** | 고정역할 보상 역효과 → 비활성화 |
| front_both_ground_max | -40.0 | **-15.0** | 너무 공격적 → 한 다리 포기 유발 |
| front_swing_bonus_max | 12.0 | 12.0 유지 | 앞발 들기 인센티브 |
| min_swing_ratio_max | -20.0 | -20.0 유지 | 4발 접지 고착 패널티 |

**V31.1 핵심**: front_swing_bonus(양의 인센티브) + min_swing_ratio(고착 패널티) 2개만으로 단순화.
front_both_ground는 보조적 역할(-15)로 완화.

### V31.1 결과 (iter 1001, 실패)

| 다리 | contact | swing_time | propulsion | 상태 |
|------|---------|------------|------------|------|
| FL | **0.874** | 0.103 | 0.726 | ❌ lock-in 재발 |
| FR | 0.593 | 0.383 | 0.546 | 🟡 부분 개선 |
| RL | **0.027** | **0.950** | 0.027 | ❌ **완전 붕괴** |
| RR | 0.758 | 0.219 | 0.493 | ❌ 고접지 |

**reward 추이**: 168(iter 600 peak) → -5(iter 900) → 65(iter 1001)

**V31.1 신규 보상 효과 (iter 1001)**:
| reward | 값 | 판정 |
|--------|-----|------|
| front_swing | +1.56 | 🟡 FR에만 효과, FL 변화 없음 |
| front_both_ground | -9.43 | ❌ 큰 패널티만 누적, 행동 변화 없음 |
| min_swing_ratio | -9.93 | ❌ 큰 패널티만 누적, 행동 변화 없음 |

**실패 원인**: `front_both_ground`(-15)와 `min_swing_ratio`(-20)도 `front_alternation`과 본질적으로 동일한 문제.
- `front_both_ground`: FL+FR 동시접지 패널티 → "둘 중 하나만 들면 OK" → FL 고정접지 + FR swing 고정
- `min_swing_ratio`: 4발 중 swing 부족한 다리에 패널티 → RL을 영구 swing으로 보내면 패널티 회피
- FL(0.874) + RR(0.758) 대각선 고접지, FR(0.593) + RL(0.027) 반대 대각선 — V31과 **방향만 바뀐 동일 패턴**

> **교훈 #8**: contact-level 패널티(`both_ground`, `min_swing_ratio`)는 모두 "어떤 다리를 희생할까" 최적화를 유발 — joint-level 접근이 필요.

---

## V31.2 수정: Joint-Level 접근 (현재 훈련 중)

### 근본 원인 재분석

V31~V31.1에서 시도한 모든 contact-level 보상/패널티가 대각 역할 분리를 유발:
- `front_alternation`(V31): abs(FL-FR) → 한쪽만 영구 swing이 최적
- `front_both_ground`(V31.1): FL*FR → 한쪽만 떼면 OK → 역할 고정
- `min_swing_ratio`(V31.1): swing 부족 다리에 패널티 → 특정 다리를 영구 swing에 배정

**공통점**: step-level contact 상태 기반 → PPO가 "어떤 다리를 희생할지" 선택하면 패널티 회피 가능.

### 왜 뒷다리는 성공했나?

뒷다리 활성화(V15~V16)는 contact-level 보상만이 아니라 **joint-level** 보상을 함께 사용:
- `rear_joint_velocity`(+20): 뒷다리 6개 관절의 절대 속도 합 → 관절이 움직여야 보상
- `rear_joint_frozen`(-60): 관절 속도 합 < threshold → 동결 페널티

**joint-level이 역할 분리를 방지하는 이유**: 관절 속도는 개별 측정 → FL 관절이 안 움직이면 FL에 직접 패널티. "FR이 대신 움직여서 회피" 불가.

### V31.2 설계

| reward | V31.1 | V31.2 | 이유 |
|--------|-------|-------|------|
| front_swing_bonus | +12 ramp | +12 ramp (유지) | 앞발 들기 양의 인센티브 |
| front_both_ground | -15 ramp | **0 (비활성화)** | 대각 역할 분리 유발 |
| min_swing_ratio | -20 ramp | **0 (비활성화)** | 대각 역할 분리 유발 |
| front_alternation | 0 | 0 (유지) | V31에서 이미 비활성화 |
| **front_joint_velocity** | 없음 | **+15 ramp (신규)** | rear_joint_velocity(+20)의 75% 미러 |
| **front_joint_frozen** | 없음 | **-40 ramp (신규)** | rear_joint_frozen(-60)의 67% 미러 |

Curriculum ramp: iter 100~400 (기존과 동일).

### V31.2 예상 앞다리 보상 균형

| 카테고리 | 앞다리 (V31.2) | 뒷다리 (기존) |
|----------|---------------|--------------|
| swing bonus | +12 | +15 |
| joint velocity | +15 | +20 |
| joint frozen | -40 | -60 |
| **합계** | **~67** | **~95** (+ alternation 30, both_ground -80) |

### 성공 기준

| 지표 | V31.1 실적 | V31.2 목표 |
|------|-----------|-----------|
| FL/FR contact | 0.874 / 0.593 | **< 0.70 / < 0.70** |
| RL/RR contact | 0.027 / 0.758 | **> 0.35 / > 0.35** |
| FL/FR 대칭 | 0.281 차이 | **< 0.10** |
| RL 붕괴 | ❌ 0.027 | **> 0.35** |
| F-R gap | 0.341 | **< 0.20** |
| mean reward | 65 (하락 중) | **> 200** |
