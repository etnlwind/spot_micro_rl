# V50 Plan: Boot Standing Extension + Height Maintenance

> 작성: 2026-03-28
> 상태: **완료 — 초반 높이 개선 확인, walking 활성화 후 하락 반복 → 구조 변경 필요**

---

## 실험 일지

### 출발점

`V49`에서 드러난 핵심 문제는:

```text
잘 걷기는 하지만
앞다리를 거의 안 쓰는 귀뚜라미 보행
```

첫 해석은 `boot가 너무 빨리 끝나고, 높이 유지 압력이 약하다`였다.

### 처음 계획

그래서 `V50`은:

```text
- boot_standing을 더 오래 유지
- standing/height 계열 reward를 더 강화
```

### 실제로 한 일

```text
V50   : boot 연장 + height 강화
V50.1 : height gradient 더 강화
V50.2 : boot standing floor 추가
```

### 결과

공통 패턴은 같았다.

```text
- 초반에는 높이와 front lift가 조금 좋아짐
- 하지만 walking이 본격 활성화되면 다시 낮아짐
- 장기적으로 귀뚜라미 보행이 재발
```

### 이 버전이 남긴 교훈

`V50`은 "standing reward를 세게 주는 것만으로는 부족하다"를 보여줬다.
즉 단순 가산 reward가 아니라, `walking reward 자체에 height 조건을 거는` 방향이 필요하다는 결론으로 이어진다.

## 1. 왜 Boot 연장이 필요한가

### V49 귀뚜라미 보행의 원인

V49에서 stride 6.9를 달성했지만 front_leg_lift = 0.08 (앞발 미사용).
직접 원인: **boot_standing ramp-down이 300 iter로 너무 빠름**.

```
V49 timeline:
  iter 0~300: boot_standing 15.0 → 0 (빠른 감소)
  iter 300~: walking reward만 남음 → 낮은 자세 최적화 → 귀뚜라미
```

해결 방향: ramp-down 연장 + 높이 유지 reward 강화.

---

## 2. V50 변경: A+B 결합

### 파라미터 변경

| 파라미터 | V49 | V50 | 변경 이유 |
|---------|:---:|:---:|----------|
| boot_standing_initial | 15.0 | **20.0** | 초기 "서기" 신호 강화 |
| boot_ramp_down_iters | 300 | **1500** | "서기" 습관 충분히 각인 (5배 연장) |
| standing_height.weight | 10.0 | **15.0** | walking phase 높이 유지 보조 |
| base_height_l2.weight | -15.0 | **-20.0** | 높이 penalty 강화 |

### 설계 근거

boot_standing ramp-down 300→1500:
```
V49: 300 iter = ~15분 → "서기" 미각인
V50: 1500 iter = ~75분 → walking 활성화(~iter 300) 이후에도 1200 iter 추가 유지
```

standing_height 10→15, base_height_l2 -15→-20:
```
Walking reward 총합: ~60+
Standing/Height reward: 10+15 = 25 → 여전히 walking의 40% 수준
목적: walking 활성화 후에도 "높이 유지" 압력 지속
```

---

## 3. 테스트 런 이력 (GUI 세션 문제)

| Run | 시각 | 내용 | 결과 |
|-----|------|------|------|
| 11-34-56 | 11:34 | headless (cli 직접 실행) | iter 0만, GUI 테스트 용도 |
| 11-38-07 | 11:38 | GUI 시도 (hidden window) | iter 0만, 창 안 보임 |
| 11-41-31 | 11:41 | GUI 시도 (CREATE_NEW_CONSOLE) | iter 0만, 세션 0 제한 |
| 11-44-19 | 11:44 | GUI 시도 (같은 문제) | iter 0만 |
| **11-48-45** | **11:48** | **GUI (listener Console 세션)** | **iter 200, GUI 성공** |
| 11-50-59 | 11:50 | headless (이전 resume용) | iter 200 |
| **13-06-47** | **13:06** | **resume from model_200** | **iter 1000+ 진행** |

**교훈 #24**: WSL에서 GUI 프로세스 실행 불가 (세션 0 제한). Listener의 Console 세션에서만 가능.

---

## 4. V50 결과: iter 1030

### 주요 지표

| 지표 | V49 (iter 1140) | V50 (iter 1030) | 변화 |
|------|-----------------|-----------------|------|
| ep_len | 234 | 243 | 유사 |
| stride | 6.9 | 5.83 | 소폭 하락 |
| coupling | 0.59 | 0.54 | 소폭 하락 |
| **front_leg_lift** | **0.08** | **0.137** | **70% 개선** |
| boot_standing | 2.05 | 3.23 | ramp-down 연장 효과 |
| shoulder_dev | - | 0.515 | 아직 높음 |

front_leg_lift 0.08 → 0.137로 개선되었으나, **walking 활성화 후 하락 추세** 관찰.

---

## 5. V50.1: Height Gradient 강화 (실패)

### 변경

```python
# boot_standing의 height_k 강화
height_k = 500  # was 100
```

### Height Score 계산 (height_k별 비교)

```
height_k=100 (V49/V50):
  h=0.23 → score=1.00  (목표)
  h=0.22 → score=0.90
  h=0.21 → score=0.82
  h=0.20 → score=0.73
  h=0.19 → score=0.50
  h=0.18 → score=0.37

height_k=500 (V50.1):
  h=0.23 → score=1.00  (목표)
  h=0.22 → score=0.61
  h=0.21 → score=0.37
  h=0.20 → score=0.22
  h=0.19 → score=0.007
  h=0.18 → score=0.000
```

k=500에서는 0.23 근처만 높은 점수, gradient 극대화.

### 결과: standing_height trajectory

| 시점 | standing_height | 비고 |
|------|:---------------:|------|
| iter 271 (초반) | **0.228** | 목표 근접! boot phase 효과 |
| walking 활성화 후 | **0.197** | 하락 — walking(60+)이 height gradient 압도 |

초반에 0.228까지 올라갔으나, walking reward 활성화 후 다시 하락.
**height reward gradient만으로는 walking(60+)을 이기지 못함.**

---

## 6. V50.2: Boot Standing Floor (실패)

### 변경

```python
# boot_standing ramp-down 시 최소값 유지
boot_standing_floor = 10  # was 0
# ramp-down 후에도 10.0의 높이 압력 유지
```

### 결과: boot_standing floor 분석

| 시점 | standing_height | boot_standing | walking 총합 |
|------|:---------------:|:-------------:|:------------:|
| iter 1074 | **0.196** | 10.0 (floor) | ~60+ |

boot_standing이 floor=10으로 유지되어도 **walking(60+) 대비 무력** (6:1 비율).
walking reward가 10배 이상 크므로 "낮아도 앞으로 가면 보상" 구조가 지배적.

---

## 7. V50 시리즈 전체 결론

### 패턴: 초반 성공 → walking 활성화 후 하락

```
모든 V50 변형에서 동일한 패턴:
  Phase 1 (boot): standing_height 0.22~0.23 (목표 달성)
  Phase 2 (walking): standing_height 0.19~0.20 (하락)

walking reward 총합: +60.8
height reward 총합: +3.9 (standing_height + base_height_l2)
비율: 15:1 → walking이 압도적
```

### Reward Weight 조정의 한계

```
가능한 조정:
  standing_height: 15 → 30? → 부팅 불안정 우려
  base_height_l2: -20 → -40? → penalty > alive_bonus 위험
  boot_standing: floor=10 → 20? → walking 대비 여전히 소수

근본 문제: reward weight 비율 조정으로는 15:1 구조를 깰 수 없음
→ 구조적 변경 필요 (V51 soft height gate)
```

---

## 8. 핵심 교훈

| # | 교훈 | 출처 |
|---|------|------|
| 21 | 앞/뒷다리 비대칭은 boot phase에서 높이 습관이 안 잡혀서 발생 | V49→V50 |
| 24 | WSL에서 GUI 프로세스 실행 불가 (세션 0 제한) | V50 GUI 시도 |
| - | reward weight 조정만으로는 15:1 비율 구조를 깰 수 없음 | V50/50.1/50.2 전체 |
| - | 초반 성공 지표에 속지 말 것 — walking 활성화 후 추세 확인 필수 | V50.1 iter 271 |

---

## 9. 다음 단계

reward weight 조정의 한계 확인 → **구조적 접근 필요**:
- Soft height gate: walking reward에 높이 조건부 스케일링
- 분석팀 협업으로 V51 설계

---

## 10. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | boot_standing_initial 15→20, boot_ramp_down 300→1500 |
| `env_cfg.py` | standing_height.weight 10→15, base_height_l2.weight -15→-20 |
| `env_cfg.py` | V50.1: height_k 100→500 |
| `env_cfg.py` | V50.2: boot_standing_floor=10 |
| `listener.py` | GUI 세션 실행 지원 (Console 세션 경유) |
