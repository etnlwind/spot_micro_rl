# V41 Plan: Narrow-Stance Bootstrap Curriculum

작성: 2026-03-24  
상태: 설계 초안

---

## 1. 핵심 아이디어

V41는 **초기부터 wide stance(과한 어깨 벌림)에 너무 의존하지 않게 하면서**, 동시에 **좁은 자세에서도 걸을 수 있는 gait bootstrap**을 주는 실험이다.

한 줄로 요약하면:

> **초기 약한 anti-wide-stance bias + 저속 직진 gait bootstrap + 후반 일반 보행 전환**

즉, 기존처럼 “먼저 걷게 하고 나중에 `shoulder dev(어깨 벌어짐 정도)`를 줄이는” 방식이 아니라,  
**처음 gait가 형성될 때부터 과한 wide stance 위에 보행이 쌓이지 않게 만드는 것**이 목표다.

---

## 2. 배경

### 지금까지의 흐름 요약
- **V37**: posture를 강하게 누르다 보행 붕괴
- **V38**: Soft CaT로 `shoulder dev(어깨 벌어짐 정도)` `0.54 → 0.45`까지는 감소
- **V39**: 후반 gait 재구성(CPG) 시도했지만 늦었고 약했음
- **V40-A**: `CaT prob` 단일 변수로 `0.45 plateau` 원인 검증 중

### 새 가설
현재 `0.45 plateau`는 단순히 후반 correction이 약해서가 아니라,

> **초기 gait가 wide-stance 의존 전략 위에 형성되었기 때문**

일 수 있다.

즉 policy가 처음부터
- 넓게 벌리고
- contact를 안정적으로 확보하고
- 그 위에 gait를 형성했다면,

나중에 `shoulder dev(어깨 벌어짐 정도)`를 더 줄이려 하면  
이미 형성된 gait 전체를 다시 갈아엎어야 해서 plateau가 생길 수 있다.

---

## 3. V41의 핵심 가설

### 가설
초기 학습에서:

1. wide stance를 **완전 공짜 전략으로 두지 않고**
2. 동시에 narrow stance에서도 가능한 **기초 gait bootstrap**을 주면,

후반에 `shoulder dev(어깨 벌어짐 정도)`를 줄일 때 생기는
- contact 붕괴
- stride 악화
- `ep_len` 저하
가 줄어들 수 있다.

### 이 가설이 맞다면
- 후반 correction을 더 세게 하지 않아도
- 최종 plateau 자체가 더 낮아질 수 있다

---

## 4. 목표

### 1차 목표
- `shoulder dev(어깨 벌어짐 정도) < 0.42`

### 2차 목표
- `stride > 5.0`
- `ep_len > 200`

즉 성공 정의는:

> **좁은 자세 + 보행 유지**

를 동시에 달성하는 것이다.

---

## 5. 설계 철학

### 원칙 1. 초기부터 wide stance를 너무 싸게 두지 않는다
초기 학습에서 wide stance가 매우 안전하고 매우 싸면,
policy는 그 위에 gait를 쌓는다.

따라서 V41는
- stance 관련 bias를 **아주 약하게라도** 초기에 둔다.

### 원칙 2. 하지만 강하게도 누르지 않는다
처음부터 자세를 세게 누르면 V37류 붕괴가 재현될 수 있다.

따라서:
- 작은 bias
- 완만한 ramp
- low-speed bootstrap
이 중요하다.

### 원칙 3. 좁은 자세에서도 gait를 배우게 한다
wide stance를 비싸게만 만들면 policy는 막막해진다.

따라서 동시에:
- `feet_air_time`
- `foot_clearance`
- `contact-phase` / diagonal timing
- 저속 직진 추종

같은 **기초 보행 신호**를 준다.

---

## 6. V41 실험 구조

## Phase 1: 초기 형성기 (iter 0 ~ 1000)

### 목적
- wide stance에 깊게 고착되기 전에
- 좁은 자세에서도 저속 gait를 배우게 하기

### command
- `lin_vel_x`: `0.05 ~ 0.25`
- `lin_vel_y`: `0`
- `ang_vel_z`: `0`

즉 **직진 저속만 허용**한다.

### posture bias
- `shoulder_neutral`: 약한 penalty
- `stance_width_penalty`: 약한 penalty

중요:
- 강한 값 금지
- 목표는 “강제 교정”이 아니라 **초기 wide stance를 덜 싸게 만들기**

### gait bootstrap
이 phase에서는 아래 항목을 baseline보다 강화한다.

- `feet_air_time`
- `foot_clearance`
- `contact-phase` / diagonal timing
- 저속 직진 추종

즉 posture만 보지 않고,
**좁은 자세에서도 발을 들고 앞으로 가는 패턴**을 먼저 배우게 한다.

### CaT
- 끄거나 매우 약하게
- 권장: baseline보다 더 약하거나, 매우 낮은 probability만 허용

이유:
- 초기부터 CaT까지 세면 또 붕괴할 수 있음

---

## Phase 2: 전환기 (iter 1000 ~ 3000)

### 목적
초기 형성된 좁은 자세 기반 gait를 유지한 채 정상 locomotion으로 확장

### command 확장
- `lin_vel_x`: `0.0 ~ 0.4`
- `lin_vel_y`: `0`
- `ang_vel_z`: `0` 또는 아주 소량 허용

### posture bias
- `shoulder_neutral`, `stance_width_penalty`
  - Phase 1보다 약간 강화
  - 여전히 V37 수준은 금지

### gait bootstrap
- Phase 1보다 약간 줄이되 유지
- 아직 gait 형성 지원 필요

### CaT
- baseline 수준으로 ramp
- 예: V38.3 baseline 수준 또는 V40-A 결과 반영

---

## Phase 3: 일반화기 (iter 3000+)

### 목적
초기 형성된 좋은 자세/보행 패턴을 유지하면서 일반 command에서 검증

### command
- 현재 flat locomotion baseline 범위로 확장

### posture bias
- baseline 유지

### gait bootstrap
- baseline 수준으로 환원 또는 약하게 유지

### CaT
- baseline 또는 V40-A 결과 반영

이 phase에서 보는 것은:

> **초기 형성 방식을 바꾸면 최종 `shoulder dev(어깨 벌어짐 정도)` plateau도 낮아지는가**

이다.

---

## 7. 실제 변경점 요약

### 바뀌는 것
1. 초기 저속 직진 phase 추가
2. 초기 약한 `shoulder_neutral` / `stance_width` bias
3. 초기 gait bootstrap 강화
4. CaT는 초반 약하게, 중반 이후 baseline 복귀

### 바꾸지 않는 것
1. 로봇 구조 자체
2. joint limit
3. action space 구조
4. contact target 정의
5. reward 전체 철학의 전면 교체

즉 V41는 **구조 실험이 아니라 초기 형성 조건 실험**이다.

---

## 8. 파라미터 방향 (정성)

### posture 관련
- `shoulder_neutral`: 현재 강한 값의 **20~40% 수준**
- `stance_width_penalty`: 현재 강한 값의 **20~40% 수준**

즉 “느끼긴 느끼되, 무너지진 않게”

### gait bootstrap 관련
초기 phase에서만 강화:
- `feet_air_time`
- `foot_clearance`
- `contact-phase` / trot-like timing

### command
- 초기엔 **직진 저속**
- 측이동 / yaw는 뒤로 미룸

### CaT
- Phase 1: off 또는 매우 약함
- Phase 2 이후: baseline 복귀

---

## 9. 판정 기준

## 성과 지표
- `shoulder dev(어깨 벌어짐 정도) < 0.42`
- `stride > 5.0`
- `ep_len > 200`

## 보조 지표
- `splay%`
- `contact_band per-step`
- `late_phase_band_exit per-step`
- `policy entropy`
- `feet_air_time`
- `phase/contact following`

### 성공 해석
- `shoulder dev(어깨 벌어짐 정도)`가 0.45 아래에서 안정
- `stride`, `ep_len` 유지
- V40-A보다 더 좋은 자세-보행 균형

→ **초기 형성 문제였을 가능성 강함**

### 부분 성공
- `shoulder dev(어깨 벌어짐 정도)`는 개선
- `stride`는 유지
- `ep_len` 약간 흔들림

→ bias 강도 / phase 길이 조정 필요

### 실패
- `shoulder dev(어깨 벌어짐 정도)` 그대로
- 또는 gait 붕괴

→ 초기 bias가 너무 약하거나 bootstrap 부족, 또는 가설 약함

---

## 10. V40-A와의 관계

### V40-A
질문:
> **CaT 압력만 더 주면 0.45 plateau를 뚫는가?**

즉 **후반 correction 검증 실험**이다.

### V41
질문:
> **애초에 초기 gait가 잘못된 wide-stance 기반 위에서 형성된 것 아닌가?**

즉 **초기 형성 조건 재설계 실험**이다.

### 권장 순서
1. V40-A 완료
2. 결과 해석
3. V40-A 실패 시 V41 착수

즉 V41는 V40-A를 대체하는 카드가 아니라,
**V40-A 이후의 다음 메인 카드**다.

---

## 11. 언제 V41를 실제로 써야 하나

다음 조건이 나타나면 V41를 실제 메인 실험 축으로 올릴 가치가 크다.

### 조건 1
V40-A에서 `CaT prob`를 올려도
- `shoulder dev(어깨 벌어짐 정도)`가 `0.45` 아래로 안 내려감

### 조건 2
`shoulder dev(어깨 벌어짐 정도)`가 내려가려 하면
- `stride`
- `ep_len`
- `contact_band`
가 함께 흔들림

### 조건 3
후반 correction 계열
- `positive posture reward`
- `target band 편향 점검`
- `threshold/margin 조정`
이 반복적으로 한계에 부딪힘

이 경우에는 이제
- 후반 correction 강화가 아니라
- **초기 형성 단계 재설계**
로 넘어가야 한다.

---

## 12. 기대 가치

V41가 맞는 방향이라면 다음을 설명할 수 있다.

- 왜 `shoulder dev(어깨 벌어짐 정도)`를 나중에 줄이려 하면 항상 gait가 흔들리는가?
- 왜 policy는 wide stance를 쉽게 못 버리는가?
- 왜 `0.45` 근처에서 반복적으로 멈추는가?

그 답을 단순히
- contact가 어려워서
- CaT가 약해서

가 아니라,

> **애초에 gait 자체가 잘못된 자세 기반 위에서 형성되었다**

로 설명할 수 있다.

---

## 13. 한계

물론 V41도 아직 가설이다.

### 한계 1
아직 실제 실험으로 검증되지 않았다

### 한계 2
초기 posture bias는 잘못 설계하면 또 부팅 붕괴를 부를 수 있다

### 한계 3
gait bootstrap과 posture bias를 동시에 설계해야 해서 실험 난도가 높다

따라서 V41는
- 큰 변화 한 번
보다
- 작은 bias
- 해석 가능한 구성
으로 가야 한다.

---

## 14. 최종 요약

V41는 다음 문장으로 요약할 수 있다.

- 지금까지는 “먼저 걷게 하고 나중에 `shoulder dev(어깨 벌어짐 정도)`를 줄이는” 흐름이 강했다
- 하지만 실제로는 좋은 4족 보행이 처음부터 과한 wide stance에 의존하지 않는 방향으로 형성되어야 할 수 있다
- 따라서 후반 correction만 강화하기보다, 초기 gait 형성 조건에서 wide stance를 너무 싸게 두지 않는 설계를 검토할 가치가 있다
- 다만 지금 당장 기존 실험을 버리고 갈아타기보다, **V40-A 결과 이후 다음 프레임으로 사용하는 것이 적절하다**

한 줄 결론:

> **현재 plateau의 진짜 원인은 후반 correction 부족이 아니라, 초기 gait가 wide-stance 의존 전략 위에 형성된 것일 수 있으며, V41는 이를 검증하기 위한 초기 형성 조건 재설계 실험이다.**
