# V47 Plan: V38.3 순정 + Boot 가속

> 작성: 2026-03-26
> 상태: **훈련 중 (iter 5860) — V38.3 재현 + shoulder 개선 + boot 가속 성공**

---

## 실험 일지

### 출발점

`V46-A/B`까지 해본 뒤 남은 결론은 명확했다.

```text
reward를 선별해서 깔끔하게 만들수록
boot/posture 일부는 좋아져도
stride 6+ 수준의 보행은 돌아오지 않았다
```

### 전략 전환

그래서 `V47`은 철학 자체를 바꿨다.

```text
작동하는 V38.3 rich reward ecology는 건드리지 않고
부족한 boot만 추가하자
```

### 실제로 한 변경

```text
- V38.3 reward/curriculum 거의 그대로 유지
- boot_standing 추가
- boot_foot_contact 추가
```

### 결과

`V47`은 이후 모든 버전의 기준점이 됐다.

```text
- stride 6+
- coupling 0.46 수준
- boot도 더 빠름
```

### 이 버전이 남긴 교훈

`V47`은 "rich reward가 무조건 나쁜 게 아니다"를 다시 확인한 버전이다.
이후 `V48~V54`는 모두 어떤 방식으로든 `V47`을 기준점으로 비교하게 된다.

## 1. 왜 V38.3으로 돌아가는가

### 한 달의 결론

| 버전 | reward 수 | stride | coupling | shoulder | 교훈 |
|------|:--------:|:------:|:--------:|:--------:|------|
| V38.3 | 77 | **6.79** | **0.49** | 0.45 | rich reward = 좋은 보행 |
| V43-E | 17 | 0.39 | 0.0 | **0.40** | clean = splay 해결, 보행 죽음 |
| V46-A | 25 | 1.45 | 0.0 | 0.46 | gait 추가만으론 부족 |
| V46-B | 25 | 1.29 | 0.0 | **0.44** | shoulder 분리 OK, stride 여전히 부족 |

V42~V46 실험에서 제거한 reward들 (+37.56 positive):
```
per_leg_contact_target_band:    +12.60  ← V38.3 positive 1위
per_leg_propulsion_target_band:  +9.10
limb_usage_target_band:          +7.56
forward_velocity_bootstrap:      +3.38
four_limb_cooperation:           +2.50
contact_residency:               +2.42
```

이것들을 "복잡한 상호작용으로 splay 유발"이라고 제거했지만, **동시에 stride 6.79의 핵심 동력일 가능성이 매우 높다**. V46-B에서 같은 gait reward(leg_lift, rear_alternation 등)를 추가해도 stride 1.29에 머문 것이 증거.

### V47 전략

> **작동하는 시스템(V38.3)을 고치지 말고, 부족한 것(boot)만 더하자.**

---

## 2. V47 변경: 최소한의 추가

### 유지 (V38.3 그대로)

```
[Reward]     77개 전부 유지 — band/residency/validity 포함
[Curriculum] 기존 reward_weight_curriculum (80+ params, gait_gate 포함)
[CaT]        Soft CaT (shoulder_splay, prob ramp)
[Shoulder]   shoulder_neutral -6.0 (V38.3 원래 값)
[Envs]       V38.3 설정 그대로
```

### 추가 (2개만)

```
boot_standing_reward (+15)
  - height_score(k=100) × orientation_score
  - 서있으면 ~1.0, 넘어지면 ~0.0
  - V43-E에서 검증: boot를 iter 200에서 ep_len 241로 가속
  - V38.3의 gait_gate가 walking reward를 pause할 때 positive gradient 제공
  - ramp-down: iter 500 이후 점진 감소 → 0

boot_foot_contact (+5)
  - 4발 접지율 (0~1)
  - boot phase에서 "발을 땅에 대라" 보조 신호
  - ramp-down: iter 600 이후 점진 감소 → 0
```

### 건드리지 않는 것

```
- shoulder_neutral -6.0 → -3.0 변경 (다음 단계)
- stance_width_penalty 제거/조정 (다음 단계)
- joint_default_pose 분리 (다음 단계)
- coupling shaping 재설계 (다음 단계)
- reward 제거/정리 (하지 않음)
```

---

## 3. Boot 가속의 기대 효과

### V38.3의 boot (기존)

```
gait_gate: ep_len < 200이면 walking reward pause
iter 50: ep_len 44.9 (느린 boot)
iter 100: ep_len 43.7
iter 300: ep_len 86.2
iter 500: ep_len 242.8
→ boot 완료까지 ~500 iter
```

### V47의 boot (boot_standing 추가)

```
gait_gate + boot_standing: 기존 gait_gate가 pause하는 동안 positive gradient 제공
V43-E에서 boot_standing 효과:
  iter 50: ep_len 134.9 (V38.3의 44.9 대비 3배)
  iter 100: ep_len 204.6 (V38.3의 43.7 대비 5배)
  iter 200: ep_len 239.5
→ boot 완료까지 ~200 iter (V38.3의 절반 이하)
```

boot_standing은 V38.3의 gait_gate를 **보완**:
- gait_gate: walking reward OFF (해로운 신호 차단)
- boot_standing: standing reward ON (유익한 신호 제공)
- 둘이 합쳐져서 boot 가속

---

## 4. 구현 방식

### 기능 플래그

```python
_CLEAN_REWARDS = False    # V38.3 원래 reward 구조 사용
_CONNECTED_TROT = False   # V43+ 구조 사용 안 함
```

### 구현 후 즉시 검증

- boot_contact의 `body_names=".*toe_link"`가 현재 로봇 URDF의 contact sensor와 일치하는지 확인 (이 프로젝트에서 toe/foot contact 해석 차이로 진단이 뒤틀린 이력 있음)

### 코드 변경

```python
TRAIN_VERSION = "V47"

# V47 블록: boot reward만 추가
if TRAIN_VERSION.startswith("V47"):
    # boot_standing_reward 추가
    self.rewards.boot_standing = RewTerm(
        func=custom_mdp.boot_standing_reward,
        weight=15.0,
        params={"asset_cfg": SceneEntityCfg("robot"),
                "target_height": 0.23, "height_k": 100.0},
    )
    # boot_foot_contact 추가
    self.rewards.boot_contact = RewTerm(
        func=custom_mdp.boot_foot_contact,
        weight=5.0,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*toe_link"),
                "contact_threshold": 1.0},
    )
```

### Boot reward ramp-down

기존 `reward_weight_curriculum`에 boot ramp 로직 추가 (간단):
```python
# iter 500 이후 boot_standing 점진 감소
# iter 600 이후 boot_contact 점진 감소
# iter 800에서 둘 다 0
```

**확정: V38.3의 gait_gate와 연동** (iteration 기반이 아닌 ep_len 기반):
- gait_gate가 풀릴 때 (ep_len > 200) boot reward도 감소 시작
- walking reward가 살아나면서 boot reward가 자연스럽게 교체
- V38.3의 기존 curriculum 구조를 최대한 보존하는 방식

---

## 5. 판정 기준

### iter 300: Boot 가속 확인

| 지표 | V38.3 (기존) | V47 기대 | 성공 기준 |
|------|:----------:|:--------:|:---------:|
| ep_len | 86 | > 200 | > 150 (V38.3 대비 가속) |

### iter 1000: Boot 안정화

| 지표 | 성공 | 실패 |
|------|------|------|
| ep_len | > 230 | < 200 |
| shoulder | < 0.50 | > 0.50 (CaT 무력화 경고) |

### iter 3000: 보행 품질

| 지표 | 성공 | 실패 |
|------|------|------|
| stride | > 5.0 | < 3.0 |
| coupling | > 0.3 | 0.0 |
| shoulder | < 0.47 | > 0.50 |

### iter 5000: 최종 (V38.3 대비)

| 지표 | V38.3 (6527) | V47 목표 |
|------|:----------:|:--------:|
| stride | 6.79 | > 6.0 |
| coupling | 0.49 | > 0.4 |
| shoulder | 0.451 | < 0.46 |
| ep_len | 207 | > 230 (boot 효과로 개선 기대) |

---

## 6. 리스크

### 1. boot_standing이 V38.3 reward 생태계에서 충돌

- boot_standing은 항상 positive (~1.0 when standing)
- V38.3의 다른 reward와 간섭 가능
- 완화: ramp-down으로 boot phase 이후 0으로 줄임
- 감지: iter 1000에서 reward 분포가 V38.3과 크게 다르면 → boot ramp 조기 종료

### 2. boot이 가속되어도 stride/coupling은 V38.3과 동일

- 이 경우 V47의 가치: boot 시간 절약 (500→200 iter)
- stride/coupling은 V38.3 수준 유지가 최선
- V38.3보다 나빠지면: boot_standing의 부작용 → weight 조정

### 3. CaT + boot_standing 충돌

- V38.3에는 Soft CaT가 있음 (shoulder splay 확률적 종료)
- boot_standing이 CaT의 종료 효과를 상쇄할 수 있음 (longer episodes = less CaT pressure)
- 감지: shoulder_dev > 0.50 with ep_len > 230 → CaT가 무력화됨
- 대비: boot_standing ramp-down을 더 일찍 (iter 300)

---

## 7. V38.3 → V47 → 이후 경로

```
V47 (현재):  V38.3 + boot 가속
  → stride ~6.0, coupling ~0.4, shoulder ~0.45, boot 가속

V47.1 (다음): shoulder 개선 전용 실험 — 동급 후보 3개:
  → shoulder_neutral weight 조정 (-6→-3 등)
  → stance_width_penalty 조정/제거
  → joint_default_pose 부분 분리 (shoulder만 유지)
  → V47 결과에서 가장 유력한 축을 선택

V47.2 (필요 시): coupling 추가 개선
  → coupling이 V38.3 수준(0.49) 이하면 shaping 추가
```

---

## 8. 핵심 교훈 (V42~V46 전체)

1. **reward 수를 줄이는 것 ≠ 정답** — 15개 clean은 splay 해결, stride 죽음
2. **제거한 reward가 동력이었음** — band/residency +37.56이 stride의 핵심
3. **작동하는 시스템을 고치지 말 것** — V38.3은 작동함, 부족한 것만 더하기
4. **한 번에 하나만** — boot만 추가, shoulder는 다음 단계
5. **shoulder 0.45와 0.44의 차이(0.01)보다 stride 6.79와 1.29의 차이(5.5)가 중요**

---

## 9. 참고

- V38.3: stride 6.79, coupling 0.49 (77개 reward, 기존 curriculum)
- V43-E: boot_standing 검증 (ep_len 248, boot 가속)
- V46-A/B: gait reward 추가 + shoulder 분리 실험 (stride 1.29 한계)
- 분석팀 피드백: "작동하는 시스템 + boot만" 권고
