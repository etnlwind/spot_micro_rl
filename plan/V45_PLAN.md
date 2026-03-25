# V45 Plan: Shoulder-Leg 분리 + Pair Coupling + Leg Lift

> 작성: 2026-03-26
> 상태: **설계 완료, 구현 대기**

---

## 1. V42~V44 전체 여정 요약

| 버전 | 핵심 변경 | shoulder | stride | coupling | 교훈 |
|------|----------|:--------:|:------:|:--------:|------|
| V38.3 | 50개 reward (기준) | 0.46 | 6.94 | 0.52 | rich reward = 좋은 보행, but splay |
| V43-E | 15개 clean + boot gating | **0.40** | 0.39 | 0.0 | clean = splay 해결, but 보행 부족 |
| V44 | + coupling + pose -0.5 | 0.53 | **1.69↑** | 0.0 | pose↓ → stride↑ + splay↑ (trade-off) |

**핵심 발견**: 15개 clean reward는 splay를 해결했지만 보행 품질이 부족. 50개 reward는 보행은 좋지만 splay. 두 장점을 합쳐야 함.

---

## 2. V44에서 발견된 3가지 근본 문제

### 문제 1: joint_default_pose가 shoulder와 leg를 동시 제어

```
joint_default_pose는 12개 관절 전체에 동일한 벌칙:
  shoulder 4개: 벌어지면 penalty → splay 방지 (필요)
  leg+foot 8개: 움직이면 penalty → stride 차단 (해로움)
```

정량 증거:
```
V43-E: pose -2.0 → shoulder 0.40(좋음) + stride 0.39(나쁨)
V44:   pose -0.5 → shoulder 0.53(나쁨) + stride 1.69(개선)
```

pose penalty를 바꾸면 shoulder와 stride가 **항상 반대 방향**으로 움직임. 이 trade-off는 12개 관절을 동일하게 제어하기 때문에 발생. **shoulder와 leg를 분리해야 해소됨.**

### 문제 2: diagonal_coupling_reward의 sparse gradient

```
coupling reward: tanh(FL_vel * RR_vel / deadzone^2)
  → 로봇이 대각 교대를 시도해야 output > 0
  → 시도 안 하면 output = 0, gradient = 0
  → weight 10으로 1500+ iter 돌려도 coupling = 0.0
```

이것은 교훈 #1 "output=0 reward는 weight를 올려도 0"과 동일한 패턴. coupling reward 함수 자체를 바꿔야 함.

### 문제 3: 보행 품질을 가르치는 구체적 reward 부재

V38.3의 stride 6.94는 구체적 보행 reward 덕분:
```
V38.3 iter 3000 positive rewards (상위):
  leg_lift:          2.36  ← 발 들기 (보폭의 전제조건)
  rear_joint_vel:    1.72  ← 뒷발 움직임
  rear_alternation:  0.97  ← 뒷발 교대
  stance_propulsion: 0.77  ← 추진력
  fwd_vel_bootstrap: 0.48  ← 전진
  rear_swing:        0.43  ← 뒷발 스윙
```

V44의 15개 reward에는 이런 구체적 "어떻게 걸을지" 신호가 없음. `forward_velocity`와 `stride_length`만으로는 **방법을 가르치지 못함**.

---

## 3. V45 설계

### 변경 1: joint_default_pose 제거 → shoulder_neutral 추가

**기존**: `joint_default_pose` (12개 관절 전체, weight -0.5~-2.0)
**변경**: `shoulder_neutral_penalty` (shoulder 4개만, weight -3.0)

```python
# 기존 코드에 이미 있음 (rewards.py line 1636)
shoulder_neutral_penalty(
    shoulder_cfg=SceneEntityCfg("robot", joint_names=[
        "front_left_shoulder", "front_right_shoulder",
        "rear_left_shoulder", "rear_right_shoulder"
    ]),
    target_angles=[-0.04, -0.04, -0.04, -0.04],  # 약간 안쪽
)
```

효과:
- shoulder: -3.0으로 강하게 제어 → splay 방지 (V43-E의 0.40 수준 기대)
- leg+foot: penalty 없음 → 큰 보폭 자유 (V44의 stride↑ 유지)
- **trade-off 해소**: shoulder와 stride를 독립적으로 제어

weight -3.0 선택 이유:
```
V38.3에서 shoulder_neutral weight = -6.0, shoulder_dev = 0.46
V43-E에서 joint_default_pose -2.0 (12개), shoulder_dev = 0.40
V45에서 shoulder_neutral -3.0 (4개만) → 중간값, shoulder_dev ~0.40 기대
```

### 변경 2: diagonal_coupling 제거 → gait_phase pair coupling 강화

현재 `gait_phase_contact_reward`는 각 다리를 **독립적으로** phase 체크:
```python
# 현재: 다리별 독립 판정
FL이 phase 맞으면 +1, 안 맞으면 -1  (독립)
FR이 phase 맞으면 +1, 안 맞으면 -1  (독립)
→ 4다리 평균
```

이러면 FL만 phase 맞추고 나머지는 아무렇게나 해도 평균 > 0 가능.

**V45 수정**: 대각 **쌍 기반** 판정
```python
# V45: 쌍 단위 판정
pair_A(FL+RR) 둘 다 맞으면 +1, 하나라도 틀리면 -1
pair_B(FR+RL) 둘 다 맞으면 +1, 하나라도 틀리면 -1
→ 2쌍 평균
```

효과:
- FL과 RR이 **동시에** 맞아야 보상 → 자연스러운 대각 coupling
- sparse gradient 문제 없음 (phase는 이미 제공, 쌍 매칭만 추가)
- 별도 coupling reward 불필요

### 변경 3: leg_lift reward 복원

V38.3에서 가장 큰 positive reward (2.36). 발을 들어야 보폭이 늘어남.

```python
# 기존 코드에 이미 있음 — V42 공통 블록 또는 기존 50개 reward 중
leg_lift_reward: 발이 지면에서 떨어진 높이에 비례한 보상
weight: +2.0 (V38.3에서 검증된 수준)
```

walk_ramp에 포함 (iter 800~2000): boot에서는 OFF, walking에서 활성화.

### 변경하지 않는 것

- boot_standing + boot_contact: 유지 (boot 성공 보호)
- walking reward gating (5-Phase): 유지
- forward_velocity_gated: 유지
- gate_alpha ramp: 유지
- 8192 envs: 유지
- adaptive safety: shoulder_neutral로 전환하면 불필요할 수 있으나, 안전장치로 유지

---

## 4. Reward 구조 비교

### V44 (현재, 18개)
```
[Boot]     boot_standing(15↓), boot_contact(5↓)
[생존]     alive_bonus(+10), base_height_l2(-15), flat_orientation(-7), undesired_contacts(ramp)
[전진]     forward_velocity_gated(+8), track_lin(+1), track_ang(+0.5)
[보행]     gait_phase_contact(+15), diagonal_coupling(+10), stride(+5), feet_air_time(+20)
           stance_propulsion(+8)
[정규화]   action_rate(-0.5), dof_acc(-0.001), dof_pos_limits(-5), joint_default_pose(-0.5/-1.0)
```

### V45 (제안, 18개 — 수 동일)
```
[Boot]     boot_standing(15↓), boot_contact(5↓)
[생존]     alive_bonus(+10), base_height_l2(-15), flat_orientation(-7), undesired_contacts(ramp)
[전진]     forward_velocity_gated(+8), track_lin(+1), track_ang(+0.5)
[보행]     gait_phase_pair(+15), leg_lift(+2), stride(+5), feet_air_time(+20)
           stance_propulsion(+8)
[정규화]   action_rate(-0.5), dof_acc(-0.001), dof_pos_limits(-5), shoulder_neutral(-3.0)

변경:  joint_default_pose → shoulder_neutral (shoulder만)
       diagonal_coupling → 제거 (gait_phase에 pair 로직 흡수)
       없음 → leg_lift 추가 (V38.3에서 복원)
```

---

## 5. Phase별 Reward 충돌 분석

| Reward | Weight | Boot(서기) | Walk(걷기) | Splay 영향 |
|--------|--------|:----------:|:----------:|:----------:|
| boot_standing | +15↓ | **HELPFUL** | ramp down | 없음 |
| alive_bonus | +10 | HELPFUL | HELPFUL | 없음 |
| shoulder_neutral | -3.0 | 약간 제한 | 약간 제한 | **직접 억제** |
| forward_velocity | 0→+8 | OFF | HELPFUL | 없음 |
| gait_phase_pair | 0→+15 | OFF | **trot 강제** | 없음 |
| leg_lift | 0→+2 | OFF | **stride 유도** | 없음 |
| stride_length | 0→+5 | OFF | HELPFUL | 없음 |
| feet_air_time | 0→+20 | OFF | HELPFUL | 없음 |

**Boot에서 충돌 없음** (walking reward 전부 OFF, shoulder_neutral은 약한 제한).
**Walk에서 충돌 없음** (shoulder는 shoulder_neutral이 제어, leg는 자유).

---

## 6. 예상 결과

| 지표 | V43-E | V44 | V45 예상 | 근거 |
|------|:-----:|:---:|:--------:|------|
| ep_len | 248 | 250 | > 230 | boot 구조 유지 |
| shoulder_dev | **0.40** | 0.53 | **~0.40** | shoulder_neutral -3.0 직접 제어 |
| stride | 0.39 | 1.69 | **3.0~5.0** | leg 자유 + leg_lift 유도 |
| coupling | 0.0 | 0.0 | **> 0.2** | pair-based gait_phase |
| forward_vel | 5.88 | 7.07 | 4.0~6.0 | stride 전환으로 약간 하락 가능 |

---

## 7. 판정 기준

### iter 500: Boot 유지
| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 200 | < 100 |
| shoulder_dev | < 0.45 | > 0.50 |

### iter 1500: Trot 형성
| 지표 | 성공 | 부분 | 실패 |
|------|------|------|------|
| stride | > 2.0 | 1.0~2.0 | < 0.5 |
| coupling | > 0.1 | > 0 | 0.0 |
| shoulder_dev | < 0.43 | < 0.46 | > 0.50 |

### iter 3000: 최종
| 지표 | 목표 |
|------|------|
| ep_len | > 230 |
| stride | > 3.0 |
| coupling | > 0.2 |
| shoulder_dev | < 0.45 |

---

## 8. 리스크

### 1. shoulder_neutral -3.0이 boot를 방해
- 감지: iter 300에서 ep_len < 30
- 대비: boot phase에서 shoulder_neutral도 ramp (0→-3.0)

### 2. pair-based gait_phase가 너무 strict
- 감지: gait_phase reward가 V44 대비 크게 하락
- 대비: pair AND 대신 pair AVERAGE로 완화

### 3. leg_lift가 불필요한 높은 들기 유발
- 감지: 발은 높이 드는데 stride 안 늘어남
- 대비: weight 2.0→1.0 하향

### 4. stride 여전히 정체
- 감지: iter 2000에서 stride < 1.5
- 대비: stride weight 5→15 상향, 또는 V38.3의 rear_alternation 추가 복원

---

## 9. 구현 상세

### 코드 변경

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | TRAIN_VERSION="V45", joint_default_pose → shoulder_neutral 교체 |
| `rewards.py` | gait_phase_contact_reward에 pair coupling 로직 추가 |
| `env_cfg.py` | leg_lift reward 추가 (walk_ramp에 포함) |
| `env_cfg.py` | diagonal_coupling → 제거 또는 weight=0 (monitoring raw만 유지) |

### walk_ramp_config (V45)
```python
"walk_ramp_config": {
    "forward_velocity":  {"target": 8.0,  "start": 300,  "end": 800},
    "stance_propulsion": {"target": 8.0,  "start": 300,  "end": 800},
    "gait_phase":        {"target": 15.0, "start": 800,  "end": 2000},
    "leg_lift":          {"target": 2.0,  "start": 800,  "end": 2000},
    "stride_length":     {"target": 5.0,  "start": 800,  "end": 2000},
    "feet_air_time":     {"target": 20.0, "start": 1000, "end": 2500},
}
```

---

## 10. V42~V45 핵심 교훈 누적

1. reward 충돌 분석이 설계 전에 필수 (V43 boot 실패)
2. reward를 끄는 것 ≠ 대체하는 것 (V43-D positive 부족)
3. net reward 부호가 학습 방향 결정 (V43-D net negative)
4. positive/negative ratio가 boot 예측 변수 (V38.3: 0.82)
5. **reward 수를 줄이는 것 ≠ 정답. 핵심은 "어떤 reward"** (V43-E 종종걸음)
6. **종종걸음은 reward 불균형의 수학적 최적해** (forward >> stride)
7. **joint_default_pose는 shoulder와 leg를 분리해야 함** (V44 trade-off)
8. **output=0 reward는 weight를 올려도 0** (V44 coupling 실패)
9. **구체적 보행 신호(leg_lift 등)가 없으면 RL은 가장 쉬운 방법을 찾음**

---

## 11. 참고

- V44: coupling + pose 완화 (stride↑ splay↑ trade-off 확인)
- V43-E: boot 성공, 종종걸음 (clean reward의 한계)
- V38.3: 보행 품질 기준 (stride 6.94, coupling 0.52, leg_lift 2.36)
- V41: 초기 형성 조건 재설계 철학
- 기존 코드: shoulder_neutral_penalty (line 1636), leg_lift reward 함수 확인 필요
