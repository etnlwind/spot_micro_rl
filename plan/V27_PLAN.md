# V27_PLAN.md

## V27 한 줄 정의
**V27은 “잘 걷는 정책”이 아니라, “4다리를 기능적으로 모두 쓰지 않으면 살아남지 못하는 정책”을 목표로 하는 버전이다.**

즉 이번 버전의 핵심은 reward, survival, gait 점수보다 **functional limb validity**를 상위에 두는 것이다.

---

## 1. 배경과 실패 원인 요약

V26/V26.1까지의 결과를 검토한 결론은 명확하다.

- reward / survival / gait 점수가 높아도
- 특정 다리(single-limb)가 사실상 사라지는 3족 exploit가 반복되면
- 그 run은 실패다.

특히 V26/V26.1에서 확인된 실패 패턴은 다음과 같았다.

- `contact_ratio_rl ≈ 0`
- `propulsion_rl ≈ 0`
- `swing_time_rl ≈ 1`
- `limb_usage_rl ≈ 0`

이것은 “왼쪽 뒷다리가 거의 허공에 떠 있고, 실제 지지/추진에 참여하지 않는다”는 뜻이다.

### 핵심 실패 원인
1. **초기 penalty가 너무 약했다**
2. **floor 기준이 너무 낮았다**
3. **soft gate가 우회 가능했다**
4. **reward 상으로 3족 해법이 여전히 경제적으로 유리했다**

즉 V27은 “잘 걷게 만들기”보다 먼저 **3족 exploit를 경제적으로 완전히 불리하게 만드는 구조**여야 한다.

---

## 2. V27 핵심 목표

V27의 우선순위는 아래와 같다.

1. **4개 다리가 실제로 contact + propulsion에 참여**
2. **single-limb collapse 금지**
3. **좌우 / 전후 propulsion 편중 억제**
4. 그 다음에야 gait quality / style을 해석

즉 V27에서는 “예쁜 보행”이 목표가 아니다.  
**4발 기능 참여를 먼저 강제하고, 그 결과로 좋은 보행이 따라오게 만드는 것**이 목표다.

---

## 3. 설계 원칙

### 원칙 1. Contact만으로는 충분하지 않다
다리가 바닥에 “살짝 닿는 것”만으로는 살아 있다고 보지 않는다.  
반드시 **propulsion과 usage까지 살아 있어야 한다.**

### 원칙 2. Single-limb collapse는 즉시 실패 신호다
특정 다리 하나라도
- contact가 거의 0
- propulsion이 거의 0
- swing이 거의 1
- usage가 거의 0

이면 그 run은 높은 reward와 관계없이 실패 방향으로 본다.

### 원칙 3. Reward보다 validity가 상위 조건이다
reward가 높아도 single-limb collapse면 채택 금지다.

### 원칙 4. 초기 200~300 iter 안에 승부를 본다
잘못된 해법은 초반에 굳는다.  
따라서 iter 200~300 안에 collapse 조짐이 보이면 빠르게 실패 판정을 내린다.

---

## 4. V27-A (본선)

### 목적
일반화 가능한 구조만으로 single-limb collapse를 막고, 4발 기능 참여를 만들 수 있는지 검증한다.

### 반드시 포함할 항목
1. `limb_usage_min_penalty`
2. `per_leg_contact_floor_penalty`
3. `per_leg_propulsion_floor_penalty`
4. `rear_left_right_propulsion_diff_penalty`
5. `front_left_right_propulsion_diff_penalty`
6. `diagonal_coupling_strong_soft_gate`
7. `single_limb_validity_gate`

### 구현 의도
- `contact`만 살아도 통과시키지 않는다
- `propulsion`이 거의 0이면 실패로 본다
- `usage`는 contact/propulsion 둘 다 낮으면 거의 0으로 붕괴해야 한다
- 특정 다리를 희생하고 나머지로 버티는 해법을 차단한다

---

## 5. V27-B (direct-fix 실험)

### 목적
V27-A 본선이 실패할 경우, rear-left collapse를 직접적으로 교정하는 항목이 실제로 필요한지 검증한다.

### 추가 항목
1. `rear_left_contact_floor_penalty`
2. `rear_left_propulsion_floor_penalty`

### 주의
- V27-B는 **일반 해법이 아니라 direct-fix 실험**이다
- 본선 구조 성공과 동일하게 해석하면 안 된다

---

## 6. Ramp / Curriculum

V26/V26.1은 초반 penalty가 약해서 collapse가 먼저 고착되었다.  
V27은 초반부터 더 강하게 개입한다.

### 기본 구간
- iter `0~50`: 중간 이상 강도
- iter `50~150`: 빠르게 full-strength 도달
- iter `150+`: full-strength 유지

### 해석 원칙
- iter 150이 넘어도 특정 다리 collapse가 뚜렷하면 매우 위험하다
- iter 200~300에서 개선이 없으면 빠르게 실패로 본다

---

## 7. Threshold 기본값 초안

아래는 V27의 초기 구현 기본값이다.  
더 나은 값이 있으면 이유와 함께 수정 가능하다.

- `contact_ratio_floor = 0.10`
- `propulsion_floor = 0.10`
- `limb_usage_min_floor = 0.10`
- `rear_left_right_propulsion_diff_max = 0.25`
- `front_left_right_propulsion_diff_max = 0.25`

### 중요 원칙
- `0.000x` 수준은 절대 “살아 있음”으로 인정하지 않는다
- “바닥에 닿기만 하는” fake recovery는 통과시키지 않는다

---

## 8. diagonal strong soft gate

### 목적
특정 다리가 collapse 상태일 때도 diagonal/rear-driven reward를 계속 먹는 우회 경로를 줄인다.

### 원칙
- binary gate는 금지
- 반드시 **soft gate**로 구현한다
- 특정 다리의 contact/propulsion/usage가 floor 아래로 내려갈수록 관련 gait reward를 강하게 감쇠한다

### 구현 기대
- 관련 diagonal / rear-driven reward term에 연속적인 감쇠 계수를 곱한다
- PPO 불안정성을 만들 정도의 급격한 cliff는 피한다

---

## 9. 운영 / 중단 기준

### iter 100
- early warning
- limb-wise 값 확인 시작

### iter 200
다음이면 **강한 실패 경고**
- 특정 다리 `contact_ratio < floor`
- 특정 다리 `propulsion < floor`
- 특정 다리 `swing_time > 0.95`
- 특정 다리 `usage < floor`

### iter 300
위 상태가 지속되면:
- **V27-A 실패**
- V27-B 전환 또는 중단 검토

### iter 400
여전히 collapse면:
- **즉시 중단 기본값**

---

## 10. 리포트에 반드시 포함할 값

모든 heartbeat / checkpoint report에 아래 값을 넣는다.

- `contact_ratio_fl/fr/rl/rr`
- `propulsion_fl/fr/rl/rr`
- `swing_time_fl/fr/rl/rr`
- `limb_usage_fl/fr/rl/rr`
- `limb_validity_reason`
- `rear_left_right_propulsion_diff`
- `front_left_right_propulsion_diff`
- `front_rear_propulsion_balance`

### 추가 요구
- `run_dir`
- `metrics_source_run`

도 항상 같이 출력한다.  
과거처럼 run/report 혼선을 다시 허용하지 않는다.

---

## 11. 성공 기준

V27 성공은 다음을 모두 만족해야 한다.

1. 4개 다리가 실제로 contact + propulsion에 참여
2. single-limb collapse reason 없음
3. 특정 다리 usage/propulsion이 바닥에 머무르지 않음
4. 좌우/전후 propulsion 편중 완화
5. 그 이후에만 gait/style 해석 가능

---

## 12. 실패 기준

다음 중 하나라도 지속되면 실패다.

- 특정 다리 `contact_ratio ≈ 0`
- 특정 다리 `propulsion ≈ 0`
- 특정 다리 `swing_time ≈ 1`
- 특정 다리 `usage ≈ 0`
- `limb_validity_reason`이 single-limb collapse를 직접 지목

즉:
**높은 reward / survival / gait 점수도 single-limb collapse를 덮지 못한다.**

---

## 13. 구현 담당 AI에게 요구하는 출력 형식

다음 형식으로 답하도록 한다.

1. **V27-A 구현 계획**
2. **수정할 파일 목록**
3. **각 파일에서 추가/수정할 함수**
4. **초기 weight / threshold / ramp 값**
5. **iter 100/200/300/400 판정 규칙**
6. **V27-B 전환 조건**
7. **예상되는 리스크**
8. **최종 구현 순서**

---

## 14. 최종 요약

- V27은 reward 중심 버전이 아니다
- V27은 **4발 기능 참여 강제 버전**이다
- 특정 다리 collapse가 보이면 높은 점수와 무관하게 실패로 본다
- iter 200~300 안에 조짐을 보고 빠르게 판정한다
- V27-A는 일반 구조 본선
- V27-B는 rear-left direct-fix 실험
- 이번 목표는 “잘 걷는 것”이 아니라 **“4다리를 안 쓰면 아예 못 살게 하는 것”**이다
