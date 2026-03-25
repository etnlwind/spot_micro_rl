# V43 Plan: Connected Trot — 전진·발들기·phase·접지추진의 연결

> 작성: 2026-03-25
> 상태: **훈련 완료 — boot 실패 (ep_len 8 고착)**

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

## 2. V43 Reward 구조 (15개)

### 생존/안정 (4개)
```
1. alive_bonus          (+10)
2. base_height_l2       (-15)
3. flat_orientation_l2  (-7)
4. undesired_contacts   (ramp -20→-100)
```

### 전진 추종 (2개)
```
5. track_lin_vel_xy     (+1)
6. track_ang_vel_z      (+0.5)
```

### 정규화 (4개)
```
7.  action_rate_l2       (-0.5)
8.  dof_acc_l2           (-0.001)
9.  dof_pos_limits       (-5)
10. joint_default_pose   (-2.0)  ← V42 -0.5에서 상향
```

### 연결된 보행 (5개) — V43 핵심
```
11. forward_velocity_gated  (+8)   — per-leg propulsion gating
12. feet_air_time           (+20)  — 발 들기
13. gait_phase_contact      (+15)  — phase + contact + push 연결
14. stance_propulsion       (+8)   — 접지 추진
15. stride_length           (+5)   — 보폭
```

### V42에서 제거
- `forward_velocity` (독립) → `forward_velocity_gated`로 교체
- `diagonal_coupling` → `gait_phase_contact`에 흡수
- `joint_vel_l2` → `dof_acc_l2`와 중복

---

## 3. 구현 핵심 함수

### `_per_leg_propulsion()` — V43 공통 helper
```python
# 각 발의 foot-body heading 상대 속도로 추진력 계산
# stance_mask (num_envs, 4) + push_magnitude (num_envs, 4) 반환
# forward_velocity_gated, gait_phase_contact_reward, stance_propulsion_reward에서 공유
```

### `forward_velocity_gated()` — per-leg propulsion gating
```python
# gate = mean(stance_mask * push) / threshold
# 다리로 안 밀면 gate ≈ 0 → 전진 보상 차단
```

### `gait_phase_contact_reward()` — phase + contact + push
```python
# stance phase: 접지 + 실제 추진력 있으면 +1, 없으면 -1
# swing phase: 미접지 +1, 접지 -1
# 기둥처럼 서있기만 해도 -1
```

---

## 4. 훈련 결과

- **Run**: `2026-03-25_16-11-35`
- **Envs**: 8192
- **결과**: **boot 실패**

### 핵심 지표 (iter 500)

| 지표 | 값 | 목표 | 판정 |
|------|-----|------|------|
| ep_len | **8.3** | > 230 | FAIL |
| forward_velocity | 0.015 | > 1.0 | FAIL |
| stride_length | 0.011 | > 6.0 | FAIL |
| gait_phase | 0.17 | > 0 | OK (유일) |
| stance_propulsion | 0.16 | > 0 | OK |

### 실패 분석

분석팀 피드백: "stance_propulsion은 올라가는데 forward_velocity가 안 붙으면 gait exploit, 둘 다 안 붙으면 threshold 빡빡"

**초기 진단**: propulsion_threshold=0.1이 boot phase에서 전진 신호를 차단 → V43-B로 gate ramp 시도

**최종 진단 (V43-C 이후)**: propulsion gating이 아닌 **walking reward가 boot phase에서 충돌**하는 것이 근본 원인. feet_air_time(+20)이 boot에서 "발을 들어라" 신호를 보내 alive_bonus(+10) "서있어라"와 충돌. → V43-D에서 해결.

---

## 5. 교훈

1. **per-leg propulsion gating 자체는 올바른 설계** — exploit 방지에 효과적
2. **boot failure는 gating 문제가 아니라 reward 충돌 문제** — 15개 reward가 boot에서 서로 싸움
3. **V42 clean restart 시 gait_gate 메커니즘을 함께 제거한 것이 근본 원인**
4. **reward 설계 시 phase별 상호작용 분석이 필수** (개별 reward만 보면 놓침)
