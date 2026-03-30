# V53 Plan: Front Leg Lift Reward

> 작성: 2026-03-29
> 상태: **설계 완료 — from-scratch 훈련 예정**

---

## 실험 일지

### 출발점

`V52.1`에서 드디어 문제의 구조가 드러났다.

```text
leg_lift가 평균 구조라서
앞다리를 추가로 들면 점수가 오히려 떨어진다
```

즉 이제는 height나 gate가 아니라,
`앞다리 사용 자체를 직접 보상`해야 하는 단계라고 판단했다.

### 처음 계획

`V53`의 가설은 매우 직접적이었다.

```text
앞다리 전용 leg lift reward를 넣으면
귀뚜라미 보행의 경제학이 뒤집힐 것이다
```

### 이 버전의 의미

`V53`은 `V49~V52`가 누적해서 만든 결론을 반영한 설계 버전이다.

```text
- baseline restore만으론 부족
- boot/height 강화만으론 부족
- min_height termination만으론 부족
- 구조적으로 앞다리를 쓰지 않게 만드는 reward bias를 직접 깨야 함
```

### 이후로 이어진 이유

하지만 `V53` 계열까지 오면서도
`reward를 계속 패치하는 접근` 자체가 한계라는 문제의식이 커졌다.
이게 다음 `V54`의 `phase clock 기반 구조 전환`으로 바로 이어진다.

## 1. 왜 앞다리 전용 Reward가 필요한가

### V49~V52.1: 귀뚜라미 보행의 반복

| 버전 | 접근 | front_lift 결과 | 상태 |
|------|------|:---------------:|------|
| V49 | baseline | 0.08 | 귀뚜라미 |
| V50 | boot 연장 + height 강화 | 0.137 → 하락 | 귀뚜라미 |
| V51 | soft height gate | 0.257 → 0.035 | 초반 성공, 장기 실패 |
| V52 | + min height termination | 0.035 | 귀뚜라미 |
| V52.1 | data-driven weight | 0.091 → 하락 중 | 개선만, 해결 안 됨 |

5개 버전에 걸쳐 height 강화, gate, termination, weight 재설계를 모두 시도했지만 **근본 해결 실패**.

### 근본 원인: leg_lift_reward의 평균 구조

V52.1 데이터 분석에서 결정적 원인 발견:

```python
# leg_lift_reward 내부 구현
def leg_lift_reward(...):
    # 스윙 중인 다리들의 leg joint 변위 보상
    swing_reward = compute_per_leg_lift(...)
    return swing_reward.sum(dim=1) / num_swing  # ← 평균!
```

**실측 데이터 (V52.1 iter 1000)**:

```
Per-leg lift scores:
  FL (front left):  0.088
  FR (front right): 0.061
  RL (rear left):   0.716
  RR (rear right):  0.565
→ 뒷다리 vs 앞다리: 8배 차이
```

### 평균이 만드는 perverse incentive

```
Case A: 뒷다리만 스윙 (2다리)
  avg(0.72, 0.57) = 0.645
  reward = 0.645 × 20 = 12.9/step

Case B: 4발 모두 스윙 (4다리)
  avg(0.09, 0.06, 0.72, 0.57) = 0.36
  reward = 0.36 × 20 = 7.2/step

차이: 12.9 - 7.2 = 5.7/step
→ 앞다리를 추가하면 점수가 5.7 낮아짐
→ 앞다리 사용 = 사실상 -5.7/step penalty
```

정책은 합리적으로 **앞다리를 사용하지 않는 것**이 최적이라고 학습.

### 앞다리 포기의 전체 경제학 (V52 실측)

```
앞다리 포기 이득: +34.70/step (movement penalty 감소)
앞다리 포기 손실: -28.94/step (walking reward 감소)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
순이익: +5.76/step → 앞다리 포기가 합리적 전략

V52.1 weight 조정 후: -1.80/step (앞다리 유리, but 마진 부족)
```

weight 조정만으로는 마진이 -1.80 → 학습 noise에 취약. **구조적 추가 보상**이 필요.

---

## 2. V53 해결: front_leg_lift_reward 추가

### 설계 원칙

```
1. 기존 leg_lift(4발 평균, w=20) 유지 → 기존 reward 파괴 없음
2. front_leg_lift(앞다리만, w=15) 별도 추가 → additive
3. 앞다리 FL/FR만 대상 → 뒷다리에 영향 없음
```

### 구현

#### rewards.py — `front_leg_lift_reward` 함수

```python
def front_leg_lift_reward(
    env, asset_cfg, sensor_cfg, front_leg_joint_cfg,
    contact_threshold, target_angle
):
    """기존 leg_lift_reward와 동일 로직, 앞다리 FL/FR만 대상."""
    # front_leg_joint_cfg: joint_names=["front_left_leg", "front_right_leg"]
    # sensor_cfg: body_names=["front_left_toe_link", "front_right_toe_link"]

    # 1. contact 감지 (앞다리 toe만)
    front_contact = contact_forces > contact_threshold  # [N, 2]

    # 2. 스윙 판정 (contact 없는 다리)
    front_swing = ~front_contact  # [N, 2]

    # 3. leg joint 변위 보상 (스윙 중인 앞다리만)
    front_leg_pos = joint_pos[:, front_leg_indices]
    front_lift_score = compute_lift_score(front_leg_pos, target_angle)

    # 4. 스윙 다리만 보상 (2다리 평균)
    swing_reward = front_lift_score * front_swing
    return swing_reward.sum(dim=1) / front_swing.sum(dim=1).clamp(min=1)
```

#### env_cfg.py — reward 등록

```python
# 앞다리 전용 SceneEntityCfg
toe_cfg_front = SceneEntityCfg(
    "contact_forces",
    body_names=["front_left_toe_link", "front_right_toe_link"]
)
front_leg_joint_cfg = SceneEntityCfg(
    "robot",
    joint_names=["front_left_leg", "front_right_leg"]
)

# front_leg_lift reward 등록
self.rewards.front_leg_lift = RewTerm(
    func=custom_mdp.front_leg_lift_reward,
    weight=15.0,
    params={
        "asset_cfg": SceneEntityCfg("robot"),
        "sensor_cfg": toe_cfg_front,
        "front_leg_joint_cfg": front_leg_joint_cfg,
        "contact_threshold": 1.0,
        "target_angle": 0.6,
    },
)
```

#### TRAIN_VERSION = "V53" (from-scratch)

새 reward 함수 추가 → from-scratch 훈련 필요 (checkpoint resume 불가).

---

## 3. 수치 근거: 예상 효과

### front_leg_lift 기대 이득

```
현재 (앞다리 미사용):
  front_leg_lift: 0.075 × 15 = 1.1/step

목표 (앞다리 = 뒷다리 수준 0.6):
  front_leg_lift: 0.6 × 15 = 9.0/step

이득: +7.9/step
```

### V52.1 변경과 합산한 전체 net

```
V52 기준 순이익:              +5.76/step (앞다리 포기 유리)
V52.1 weight 조정:           -7.56
V53 front_leg_lift:          -7.90
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총 net:                      -9.70/step (앞다리 사용이 크게 유리)
```

마진: 9.70/step → weight noise에 충분히 강건.

---

## 4. 기존 V52.1 변경 전부 유지

V53은 V52.1의 모든 변경을 포함하고 front_leg_lift만 추가:

```python
# V52.1에서 변경된 값 (유지)
stance_width_penalty = -1.5       # was -3.0
four_limb_cooperation = 16.0      # was 8.0 (V52에서 0→8, V52.1에서 16)
leg_lift = 20.0                   # was 15.0

# V51에서 도입된 값 (유지)
height_walking_gate = 40.0        # boot-gated
min_height_termination = 0.15     # boot-gated

# V50에서 도입된 값 (유지)
boot_standing_initial = 20.0
boot_standing_floor = 10.0
height_k = 500

# V48에서 도입된 값 (유지)
leg_default = -0.97
init_height = 0.22

# V53 추가
front_leg_lift = 15.0             # NEW
front_rear_symmetry = 8.0         # V52에서 도입
```

---

## 5. 체크포인트 기준

| iter | 확인 항목 | 성공 | 실패 |
|:----:|----------|------|------|
| 300 | ep_len > 200 | 부팅 성공 | 중단, boot 점검 |
| 800 | front_lift > 0.15, stride > 4.0 | 개선 시작 | weight 조정 (w=20~25) |
| 1200 | front_lift > 0.10, stride > 6.0 | 유지 확인 | V52 패턴 재발 → 구조 변경 |
| 2000 | front_lift > 0.10 안정 | **V53 성공** | 구조 변경 필요 |

핵심 판정: **iter 1200 이후 front_lift 하락 없이 0.10 이상 유지 여부**.
V51/V52에서는 모두 이 시점에서 하락 시작.

---

## 6. 리스크

### 1. front_leg_lift w=15가 부족

앞다리 비용(penalty)이 이득보다 클 수 있음.

```
front_leg_lift 예상 이득: +7.9/step
만약 앞다리 penalty가 +10 이상이면 여전히 포기가 유리
```

- 감지: iter 800에서 front_lift < 0.10
- 대응: w=20~25로 증가

### 2. 앞다리를 과도하게 들기

target_angle=0.6 이상으로 비자연스럽게 높이 들 수 있음.

- 감지: front_lift > 0.8 (비정상적으로 높음)
- 대응: target_angle 조정 또는 w 감소

### 3. stride 감소

앞다리 사용에 에너지 분배 → stride 하락 가능.

```
V49 (귀뚜라미): stride 6.9
V51 (front_lift 0.257): stride 2.03 (초반)
→ 4족 보행 시 stride가 낮아질 수 있음
```

- 감지: iter 1200에서 stride < 4.0
- 대응: stride > 4.0이면 허용 범위 (품질 우선)

---

## 7. 핵심 교훈 (V49~V53 전체)

| # | 교훈 | 출처 |
|---|------|------|
| 20 | boot_standing ramp-down이 너무 빠르면 "낮게 기기" 습관 고착 | V49 귀뚜라미 |
| 25 | penalty weight는 alive_bonus 초과 금지 | V51 w=40 즉사 |
| 26 | height gate는 boot phase에서 비활성 | V51 수갑 자세 |
| 29 | 파라미터 설계 시 실측 데이터 먼저 분석 | V52.1 |
| **30** | **reward의 평균 기반 함수는 다수파가 점수를 지배** | **V52.1 leg_lift** |
| 28 | "잘 가라" > "앞으로 가라" — 보행 품질 우선 | V49~V53 전체 |

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `rewards.py` | `front_leg_lift_reward` 함수 추가 (FL/FR 전용) |
| `env_cfg.py` | front_leg_lift reward 등록 (w=15), toe_cfg_front, front_leg_joint_cfg |
| `env_cfg.py` | TRAIN_VERSION = "V53" |
| `env_cfg.py` | V52.1 변경 전부 포함 (stance_width, flc, leg_lift) |
