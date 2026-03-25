# V43 Plan: Connected Trot — 전진·발들기·phase·접지추진의 연결

> 작성: 2026-03-25
> 상태: 설계 중

---

## 1. V42 교훈

V42는 reward를 16개로 줄여 깨끗한 구조를 만들었지만, **4가지 축이 분리되어 exploit 가능**:

| 축 | V42 reward | exploit |
|---|---|---|
| 전진 | forward_velocity | 다리 안 쓰고 미끄러짐 |
| 발 들기 | feet_air_time | 제자리에서 발만 들기 |
| phase | gait_phase | 공중에서 타이밍만 맞추기 |
| 접지 추진 | **없음** | 다리로 땅을 밀 동기 없음 |

### V43 핵심 철학

**자연스러운 trot는 "전진", "발 들기", "phase", "접지 추진"이 연결된 운동이다.**
reward도 이 네 축을 분리하지 말고 연결해야 한다.

---

## 2. V43 Reward 구조

### V42 유지 (변경 없음): 10개

```
[생존/안정] 4개 — 그대로
  1. alive_bonus          (+10)
  2. base_height_l2       (-15)
  3. flat_orientation_l2  (-7)
  4. undesired_contacts   (ramp)

[전진 추종] 2개 — 그대로
  5. track_lin_vel_xy     (+1)
  6. track_ang_vel_z      (+0.5)

[정규화] 4개 — 그대로
  7. action_rate_l2       (-0.5)
  8. dof_acc_l2           (-0.001)
  9. dof_pos_limits       (-5)
  10. joint_default_pose  (-2.0)  ← V42 -0.5에서 상향
```

### V42에서 수정: 4개 → 5개 (연결 강화)

```
[연결된 보행] 5개

  11. forward_velocity_gated  (+8)
      → 전진 보상 + stride > 0 gating
      → 실제 보폭 없이 미끄러지면 보상 없음

  12. feet_air_time_gated     (+20)
      → V42와 동일하되, command velocity > threshold일 때만 보상
      → 제자리 발 들기 방지
      → (Isaac Lab feet_air_time에 이미 command gating 있는지 확인 필요)

  13. gait_phase_contact      (+15)
      → stance phase: 접지 + 추진력 있으면 보상
      → swing phase: 발이 떠있으면 보상
      → 공중에서 phase만 맞추는 exploit 방지

  14. stance_propulsion        (+8)
      → 발이 땅에 닿은 상태에서 전진 방향으로 미는 힘 보상
      → "다리로 걷기"의 핵심 연결 고리

  15. stride_length            (+5)
      → 보폭 (V42 그대로)
```

### V42에서 제거: 2개

```
  - forward_velocity (독립) → forward_velocity_gated로 교체
  - diagonal_coupling → gait_phase_contact에 흡수 (phase가 대각 동기화 포함)
  - joint_vel_l2 → dof_acc_l2와 중복, 제거
```

### 총 15개 reward

---

## 3. 연결 설계 상세

### 11. forward_velocity_gated

```python
def forward_velocity_gated(env, asset_cfg, min_stride=0.5):
    """전진 보상 + stride gating. 보폭 없이 미끄러지면 보상 없음."""
    forward_vel = ...  # 전진 속도
    current_stride = ...  # 현재 stride_length
    gate = (current_stride > min_stride).float()
    return forward_vel * gate
```

### 12. feet_air_time_gated

Isaac Lab의 `velocity_mdp.feet_air_time`이 이미 `command_name` 파라미터로 velocity gating을 할 수 있는지 확인 필요.
- 있으면: command velocity > threshold일 때만 보상하도록 설정
- 없으면: 커스텀 wrapper 작성

### 13. gait_phase_contact

```python
def gait_phase_contact(env, sensor_cfg, frequency, duty_factor):
    """Phase + 실제 접지/추진 연결.
    - stance phase: 접지(contact force > threshold) 시 +1, 미접지 시 -1
    - swing phase: 미접지 시 +1, 접지 시 -1
    V42 gait_phase와 다른 점: stance에서 단순 접지가 아닌 추진력 확인 가능"""
    # V42의 +1/-1 shape 유지
    # 추가: stance phase에서 contact force 확인
```

### 14. stance_propulsion

```python
def stance_propulsion(env, sensor_cfg, asset_cfg, min_vel):
    """발이 땅에 닿은 상태에서 전진 방향 추진력 보상.
    기존 프로젝트의 stance_propulsion 함수 재사용 가능."""
    # 이미 rewards.py에 구현되어 있음 (기존 50개 중 하나)
```

---

## 4. Exploit 방지 검증

### iter 300~500 조기 판정

| 지표 | 정상 | exploit 의심 |
|------|------|------------|
| forward_velocity > 0 **AND** stride > 0 | 함께 올라감 | velocity만 올라가고 stride = 0 |
| feet_air_time > 0 **AND** forward_velocity > 0 | 함께 | air_time만 높고 velocity = 0 |
| gait_phase > 0 **AND** contact_ratio > 0.2 | 함께 | phase만 높고 contact = 0 |
| stance_propulsion > 0 | 존재 | 0이면 다리로 안 밀고 있음 |

### 6개 동시 확인

```
forward_velocity, stride_length, stance_propulsion,
feet_air_time, FL/FR contact ratio, shoulder_dev
→ 6개가 같이 올라가야 정상 보행
```

---

## 5. 설계 원칙

1. **15개 유지** — V42의 깨끗함 유지
2. **연결이 핵심** — 독립 reward 금지, 축 간 gating/coupling
3. **exploit 조기 감지** — iter 300에서 6개 지표 동시 확인
4. **기존 함수 재사용** — stance_propulsion은 이미 구현됨
5. **8192 envs 유지**

---

## 6. 판정 기준

**진짜 목표: 자연스러운 trot으로 잘 걷는 로봇**

주 지표 (6개 동시 달성):
1. stride > 6.0
2. ep_len > 230
3. forward_velocity > 1.0
4. stance_propulsion > 0
5. feet_air_time > 0 (velocity gated)
6. gait_phase_contact > 0

관찰:
7. shoulder dev — 직접 공격 없이 자연 감소 관찰
8. FL/FR contact ratio
9. diagonal_coupling_raw

---

## 7. V42 → V43 변경 요약

| V42 | V43 | 이유 |
|-----|-----|------|
| forward_velocity (독립) | **forward_velocity_gated** (stride gating) | 미끄러짐 방지 |
| feet_air_time (독립) | **feet_air_time_gated** (velocity gating) | 제자리 발들기 방지 |
| gait_phase (+1/-1) | **gait_phase_contact** (contact 연결) | 공중 흔들기 방지 |
| 없음 | **stance_propulsion** (+8) | 접지 추진 핵심 |
| diagonal_coupling | 제거 (phase에 흡수) | |
| joint_vel_l2 | 제거 (dof_acc와 중복) | |
| joint_default_pose (-0.5) | **(-2.0)** | exploit 억제 강화 |

---

## 8. 리스크

1. **gating이 너무 엄격하면 초기 학습 신호 부족**
   - 완화: gate threshold를 낮게 시작 (stride > 0.5, velocity > 0.05)
   - boot 구간에서는 gating 완화

2. **stance_propulsion이 splay를 간접 유도할 수 있음**
   - 감시: shoulder_dev 추이
   - joint_default_pose -2.0이 어느 정도 억제

3. **15개로 줄였는데 여전히 학습 신호 부족**
   - V42 iter 100에서 ep_len 10이었음
   - V43은 stance_propulsion 추가로 "다리 밀기" 신호가 더 있어 부팅 개선 기대

---

## 9. 참고

- V42: 깨끗한 16개 구조 (exploit 발견)
- V35.5: 부팅 3결합 (유지)
- 기존 rewards.py: stance_propulsion 함수 이미 구현됨
