# V46 Plan: 3-Run 실험 — V43-E Boot + V38.3 Gait 순차 통합

> 작성: 2026-03-26
> 상태: **Run A 구현 대기**

---

## 1. 전략

### 왜 3-Run 분해인가

V44에서 coupling + pose를 동시 변경했더니 **stride는 올랐지만 splay도 올라서, 어떤 변경이 무엇을 일으켰는지 분리 불가**. 이 프로젝트의 반복된 교훈: **동시에 많이 바꾸면 해석이 안 된다**.

V46의 3개 가설을 독립 실험으로 분해:

| Run | 가설 | 변경 | 판정 |
|-----|------|------|------|
| **A** | gait reward 부족이 종종걸음 원인 | V43-E + V38.3 gait 8개 추가 | stride > 2.0 |
| **B** | shoulder-leg 분리로 trade-off 해소 | Run A + shoulder_neutral 교체 | shoulder < 0.45 |
| **C** | coupling은 보조 gait reward로 진입 | Run B + coupling shaping | coupling > 0.2 |

### 왜 V43-E baseline인가

| baseline 후보 | 상태 | 적합성 |
|--------------|------|--------|
| V38.3 | stride 6.94, splay 0.46, boot gating 없음 | boot 퇴행 위험 |
| V44 | stride 1.69, splay 0.53 | trade-off에 오염 |
| **V43-E** | ep_len 248, shoulder 0.40, stride 0.39 | **문제가 단일 축(gait 부족)으로 정리** |

V43-E는 boot/posture가 해결된 상태에서 **gait만 부족**. 실험 설계에 가장 깔끔한 baseline.

---

## 2. Run A (V46-A): V43-E + V38.3 Gait Reward

### 목적

> "V43-E의 종종걸음은 gait-specific reward 부족 때문이다"

V43-E의 안정된 boot/posture 위에 V38.3의 검증된 gait reward를 추가하여, stride와 coupling이 살아나는지 확인.

### 유지 (V43-E 그대로)

```
[Boot]      boot_standing(+15↓), boot_foot_contact(+5↓), boot gating curriculum
[생존]      alive_bonus(+10), base_height_l2(-15), flat_orientation(-7), undesired_contacts(ramp)
[전진]      forward_velocity_gated(+8), track_lin(+1), track_ang(+0.5)
[보행]      gait_phase_contact(+15), stride_length(+5), feet_air_time(+20), stance_propulsion(+8)
[정규화]    action_rate(-0.5), dof_acc(-0.001), dof_pos_limits(-5)
[자세]      joint_default_pose(-0.3→-2.0 ramp) ← V43-E 그대로
[설정]      8192 envs, gate_alpha ramp, push_alpha ramp
```

### 추가 (V38.3에서 8개)

```
[보행 품질] — V38.3에서 stride 6.94를 만든 핵심
  leg_lift(+)              — 발 들기 (V38.3 최대 positive 7.15)
  rear_alternation(+)      — 뒷발 교대 (stride 핵심 4.38)
  rear_joint_velocity(+)   — 뒷발 움직임 (9.98)
  rear_swing(+)            — 뒷발 스윙 (1.08)
  swing_stride(+)          — 스윙 중 보폭 (1.27)
  foot_clearance(+)        — 발 높이 (0.52)
  trot_gait(+)             — trot 패턴 (0.67)
  diagonal_coupling(+10)   — 대각 커플링 (V38.3에서 0.52 작동)
```

모두 walk_ramp에 포함 (iter 800~2000): boot에서는 OFF.

### 건드리지 않는 것 (Run B/C 영역)

- joint_default_pose → shoulder_neutral 교체 (Run B)
- stance_width_penalty 제거 (Run B)
- coupling shaping 재설계 (Run C)

### 왜 pose -0.3→-2.0에서도 stride가 올라올 수 있는가

```
V38.3 pose-related penalties: -28.5 (V43-E의 2.4배 더 강함)
V38.3 stride: 6.94

→ V38.3은 더 강한 pose penalty에서도 stride 6.94 달성
→ 충분히 강한 gait positive reward가 있으면 pose penalty 극복 가능
→ Run A에서 gait reward 8개 추가 시 같은 메커니즘 기대
```

### 판정 기준

| iter | 성공 | 실패 |
|------|------|------|
| 300 | ep_len > 30 | < 15 → boot 퇴행, 중단 |
| 1000 | ep_len > 200 | < 100 → 중단 |
| **3000** | **stride > 2.0** | < 1.0 → gait reward 부족 가설 약함 |
| **3000** | **coupling > 0** | 0.0 → coupling은 Run C에서 별도 해결 |

### 리스크

1. **V38.3 gait reward가 boot 충돌**: rear_* reward가 boot에서 noise → 완화: walk_ramp으로 OFF
2. **rear_* reward가 splay 유발**: 교훈 #9 "다리별 전용 보상은 역할 분리 유발" → 감시: shoulder_dev > 0.50
3. **pose -2.0이 여전히 stride 차단**: V38.3은 극복했지만 구조가 다름 → 감시: iter 2000에서 stride < 1.0이면 가설 재검토

---

## 3. Run B (V46-B): Run A + Shoulder-Leg 분리

### 목적

> "stride↔splay trade-off는 shoulder와 leg를 분리하면 해소된다"

### 변경 (Run A 대비)

```
제거: joint_default_pose
추가: shoulder_neutral(-3.0, shoulder 4 joints only)
제거: stance_width_penalty (있으면)
```

### 판정 기준

| iter | 성공 | 실패 |
|------|------|------|
| 3000 | stride 유지 + shoulder < 0.45 | shoulder > 0.50 (splay 제어 실패) |

---

## 4. Run C (V46-C): Run B + Coupling Shaping

### 목적

> "coupling 0.0은 sparse gradient 때문이며, 풍부한 gait reward 환경에서는 자연 해소 가능"

Run A/B에서 rear_alternation, trot_gait, swing_stride 등이 함께 작동하면 diagonal_coupling이 자연스럽게 올라올 수 있음. Run B까지 coupling이 여전히 0이면, Run C에서 추가 shaping.

### 판정 기준

| iter | 성공 | 실패 |
|------|------|------|
| 3000 | coupling > 0.2 | 0.0 → 구조적 접근 (CPG/trajectory) 필요 |

---

## 5. Run A 예상 Reward Budget

### V43-E (현재, 17개 reward)
```
Positive: gait_phase(12) + alive(10) + prop(7) + fwd(6) + stride(0.4) = ~36
Negative: pose(-12) + action(-4) + limits(-4) + acc(-3) + feet(-1) = ~-24
```

### V46-A (예상, 25개 reward)
```
Positive: gait_phase(12) + alive(10) + rear_joint_vel(~10) + prop(7) + leg_lift(~7)
          + fwd(6) + rear_alt(~4) + fwd_bootstrap(~4) + coupling(~2) + stride(~2)
          + others(~5) = ~69
Negative: pose(-12) + action(-4) + limits(-4) + acc(-3) + feet(-1) = ~-24
```

Positive가 36→69로 거의 2배 증가. net reward가 크게 개선되어 policy가 적극적으로 보행을 시도할 인센티브.

---

## 6. 전체 타임라인

```
Run A (V46-A): 3000 iter (~3시간)
  → stride > 2.0? → Yes → Run B
  → No → 분석, gait reward weight 조정 후 재시도

Run B (V46-B): 3000 iter (~3시간)
  → stride 유지 + shoulder < 0.45? → Yes → Run C
  → No → shoulder_neutral weight 조정

Run C (V46-C): 3000 iter (~3시간)
  → coupling > 0.2? → Yes → 성공! 15000 iter 완주
  → No → CPG/trajectory 접근 검토
```

총 예상: 9시간 (3 × 3000 iter). 15000 완주 대비 60% 시간 절약.

---

## 7. V42~V46 전체 여정

| 버전 | 전략 | shoulder | stride | coupling | 핵심 교훈 |
|------|------|:--------:|:------:|:--------:|----------|
| V38.3 | 50개 reward | 0.46 | **6.94** | **0.52** | rich reward = 좋은 보행 |
| V43-E | 15개 clean + boot | **0.40** | 0.39 | 0.0 | clean = splay 해결, 보행 부족 |
| V44 | + coupling + pose↓ | 0.53 | 1.69 | 0.0 | trade-off 미해결 |
| **V46-A** | **V43-E + gait 8개** | ~0.42? | **2~4?** | 0~0.3? | **gait reward 부족 가설 검증** |

---

## 8. 참고

- V43-E: Boot 성공 baseline (ep_len 248, shoulder 0.40)
- V38.3: Gait 품질 기준 (stride 6.94, coupling 0.52, 77개 reward)
- V44: Shoulder-leg trade-off 확인 (pose -0.5 → stride↑ splay↑)
- V45: Shoulder-leg 분리 개념 (Run B에 통합)
- 분석팀 피드백: 3-Run 분해, V43-E baseline, 3000 iter 중단, KPI 우선순위
