# V28_ANALYSIS.md

## V28 종합 분석

### 한 줄 결론
**V28은 지금까지의 버전 중 처음으로 “4발 모두를 유효하게 참여시키는 구조”를 실제로 만들어냈지만, 후반(대략 iter 1000 이후) rear-left 유지 실패로 인해 최종적으로는 실패한 버전이다.**

즉 V28은 완전 실패 버전이 아니라,
- **초반/중반 구조 성공**
- **후반 유지 실패**

로 정의하는 것이 가장 정확하다.

---

## 1. 왜 V28이 중요했는가

V23~V27 계열은 크게 두 가지 문제를 반복했다.

1. **single-limb collapse**
   - 대표적으로 rear-left 또는 rear-right가 사실상 사라짐
   - 3족 exploit로 전진/생존 reward를 먹는 구조

2. **penalty 중심 구조의 한계**
   - penalty를 약하게 주면 특정 다리 희생 local optimum이 살아남음
   - penalty를 강하게 주면 all-limb suppression(전체 학습 억제)이 생김

V28은 이 문제를 해결하기 위해,
기존의 “안 하면 벌점” 중심 구조에서 벗어나
**“target band 안에 들어오면 이득” 중심 구조**로 전환한 첫 버전이었다.

즉 V28의 설계 철학은 다음과 같았다.

- floor penalty는 하한선 역할만 한다
- contact / propulsion / usage가 target band 안에 들어와야 보상이 커진다
- 4발 cooperation reward를 후반 강화형으로 켠다
- tap optimization은 floor만 넘기는 구조 대신 target-band 구조로 자연스럽게 억제한다

이 철학 자체는 타당했고, 실제 학습 결과도 상당 부분 이를 지지했다.

---

## 2. V28의 성공 구간

V28에서 가장 중요한 사실은,
**좋은 상태가 실제로 한 번 만들어졌고, 일정 구간 유지되었다는 점**이다.

### 2.1 iter 600
iter 600 리포트는 V28의 첫 확실한 성공 구간이다.

핵심 특징:
- 4발 validity pass
- RL도 충분히 살아 있음
- target-band reward 실제 작동
- cooperation reward 실제 작동
- usage_min 매우 높음
- collapse reason 없음

이 시점은 다음을 의미한다.

> V28은 “좋은 4족보행 상태”를 실제로 만들 수 있었다.

즉 실패 원인을 “애초에 구조가 틀렸다”로 볼 수 없게 만든 기준점이 바로 iter 600이다.

### 2.2 iter 800
iter 800은 가장 중요한 기준 checkpoint다.

왜냐하면:
- 좋은 상태가 “우연히 한 번 나온 것”이 아니라
- **일정 시간 유지된 상태**였기 때문이다.

따라서 iter 800은 다음 의미를 가진다.

- **best reference checkpoint**
- 이후 버전이 목표로 삼아야 할 기준 정책
- V28이 실제로 도달할 수 있었던 최선의 상태

이 구간의 공통점은 다음과 같다.

- 4발 모두 contact / propulsion이 충분히 살아 있음
- usage_min이 높음
- validity pass
- target-band reward가 top reward contributor로 작동
- cooperation reward가 실제로 보상 구조에 기여

정리하면,
**V28의 600~800 구간은 “성공 방향”이 아니라 사실상 “성공 상태”에 가까운 구간**이었다.

---

## 3. V28의 붕괴 구간

문제는 이 좋은 상태가 후반까지 유지되지 못했다는 점이다.

### 3.1 iter 1000
iter 1000은 붕괴 시작점으로 보는 것이 맞다.

이 시점에서:
- RL contact / propulsion / usage가 다른 다리보다 눈에 띄게 낮아짐
- 아직 완전 collapse는 아니지만,
- **rear-left 약세가 구조적으로 형성되기 시작**

즉 iter 1000은 다음처럼 정의할 수 있다.

> **collapse onset reference**

### 3.2 iter 1200
iter 1200부터는 사실상 실패 진입이다.

이 시점에는:
- RL이 target band 밖으로 밀려나고
- floor 근처 또는 floor 아래로 가라앉으며
- usage도 사실상 붕괴에 가까워짐

즉 iter 1200은:

> **failure entry reference**

### 3.3 iter 1400 이후
이후 구간은 회복 없는 고착 단계다.

특징:
- RL contact ≈ 0
- RL propulsion ≈ 0
- RL usage ≈ 0
- swing ≈ 1
- rear_left_contact_collapse reason 명시

즉 iter 1400 이후는 전형적인
**rear-left 3족 exploit 고착 구간**이다.

---

## 4. V28 실패의 본질

V28 실패를 정확히 정의하면 다음과 같다.

### 잘못된 정의
- V28은 초반부터 실패했다
- target-band 구조 자체가 틀렸다
- V28은 V27과 다를 바 없다

### 올바른 정의
- V28은 **초반/중반에는 분명히 성공했다**
- 하지만 후반에 특정 다리(RL)가 band 안에 계속 머물도록 만드는 장치가 부족했다
- 그 결과, policy가 후반 학습 과정에서 **rear-left를 버리는 local optimum**으로 이동했다

즉 V28의 실패는

> **entry 실패가 아니라 residency 실패**

라고 보는 것이 정확하다.

---

## 5. V28이 실제로 잘한 것

V28은 실패한 런이지만, 동시에 매우 중요한 성공도 만들었다.

### 5.1 4발 validity를 실제로 확보했다
이전 버전들과 달리,
V28은 적어도 600~800 구간에서
**네 다리 모두가 실제 contact + propulsion 참여를 하는 상태**를 만들었다.

### 5.2 target-band 구조가 실제 보상으로 작동했다
리포트에서 `per_leg_contact_target_band`, `per_leg_propulsion_target_band`, `limb_usage_target_band`가 상위 reward contributor로 올라왔다.

이는 문서 설계가 아니라,
**실제로 학습을 이끈 reward 구조**였다는 뜻이다.

### 5.3 cooperation reward도 실제로 작동했다
4발이 동시에 band 안에 들어왔을 때 의미 있는 보상이 들어갔고,
이는 V28이 단순 floor 통과형이 아니라
**동시 기능 참여형 구조**로 작동했음을 보여준다.

### 5.4 all-limb suppression을 피했다
V27.1a의 핵심 실패는 “너무 세게 눌러서 학습이 죽는 것”이었다.  
V28은 그 함정을 피하면서도,
4발을 band 안으로 올리는 데 성공했다.

---

## 6. V28의 구조적 약점

그렇다면 왜 후반에 무너졌는가.  
핵심 약점은 4가지다.

### 6.1 band entry는 있지만 band residency가 약했다
V28은 “band에 들어오게 하는” 구조는 있었다.
하지만 **band 안에 계속 머물게 하는 구조**는 부족했다.

즉 policy가 한동안 좋은 상태에 있었다가,
후반에 한 다리를 천천히 빼는 것을 막지 못했다.

### 6.2 rear pair 내부 유지 대칭성이 약했다
V28은 front-rear balance는 보았지만,
실패 패턴을 보면 실제 핵심은 **rear 내부에서 RL이 RR보다 약해지는 것**이었다.

즉,
- 앞/뒤 전체 차이보다
- **rear-left vs rear-right의 장기 비대칭**
이 더 중요했는데,
이를 유지 차원에서 강하게 보지 못했다.

### 6.3 cooperation reward가 평균에 속을 수 있었다
cooperation reward가 평균 기반이면
- 3개 다리가 매우 좋고
- 1개 다리가 점점 죽어도
어느 정도 보상이 유지될 수 있다.

즉 최약 다리(min-leg)에 대한 감쇠가 약했다.

### 6.4 후반 이탈에 대한 late-phase penalty가 없었다
초반에는 band 진입이 중요하지만,
후반에는 **band 이탈**이 더 중요하다.

V28은 후반에 RL이 band 밖으로 나가는 현상에 대해
충분히 강하게 반응하지 못했다.

---

## 7. 시간축 요약

### 정리
- **iter 600:** 아주 좋음
- **iter 800:** 가장 좋은 기준점
- **iter 1000:** 이상 징후 시작
- **iter 1200:** 실패 진입
- **iter 1400+:** 실패 고착

즉 V28의 핵심 문제는 명확하다.

> **좋은 상태를 못 만든 것이 아니라, 만든 상태를 오래 유지하지 못했다.**

---

## 8. V28 평가: 실패인가, 부분 성공인가

엄격히 말하면 **최종 정책 관점에서는 실패**다.

왜냐하면:
- 후반에 RL collapse가 다시 발생했고
- 최종적으로는 4발 기능 참여를 유지하지 못했기 때문이다.

그러나 설계 검증 관점에서는 **명백한 부분 성공**이다.

왜냐하면:
- 4발 target-band 진입이 실제 가능하다는 걸 보여줬고
- cooperation reward가 작동함을 증명했고
- V27 계열보다 한 단계 높은 수준의 구조가 실제로 먹힌다는 걸 보여줬기 때문이다.

따라서 V28의 정확한 평가 문장은 다음과 같다.

> **V28은 최종 정책으로는 실패했지만, 4발 target-band entry와 cooperation 구조의 유효성을 입증한 중요한 부분 성공 버전이다.**

---

## 9. V28이 V28.1에 남긴 과제

V28이 남긴 가장 큰 교훈은 다음이다.

### 핵심 전환
- V28: **band entry**
- V28.1: **band residency**

즉 다음 버전은 새 구조를 만들기보다,
V28이 이미 만든 좋은 상태를 유지시키는 방향이어야 한다.

### 구체 과제
1. **Per-leg band residency**
   - contact / propulsion / usage가 최근 구간에서 얼마나 band 안에 머무는지 측정

2. **Rear pair residency symmetry**
   - RL vs RR의 장기 band residency 차이를 패널티

3. **Min-leg weighted cooperation**
   - 최약 다리가 낮으면 cooperation reward 감쇠

4. **Late-phase band exit penalty**
   - 후반에 band 밖으로 빠지는 다리를 조기 억제

즉 V28.1은
**새로운 target-band entry 구조를 만드는 것이 아니라, 좋은 target-band 상태를 유지시키는 유지 강화판**이어야 한다.

---

## 10. 최종 정리

### V28의 성공
- 4발 validity pass 달성
- target-band reward 실제 작동
- cooperation reward 실제 작동
- 600~800 구간에서 건강한 4족보행 상태 형성

### V28의 실패
- RL이 1000 이후부터 점점 band 밖으로 빠짐
- 1200 이후 실패 진입
- 1400 이후 rear-left collapse 고착

### V28의 본질
- entry 성공
- residency 실패

### 최종 판정
**V28은 최종 정책으로는 실패지만, “4발 target-band 구조가 실제로 가능한가”에 대한 검증에서는 가장 중요한 성공을 남긴 버전이다.**

---

## 한 줄 결론
**V28은 처음으로 “정상 4족 기능 참여”를 실제로 만들어낸 버전이었지만, 그 상태를 후반까지 유지하지 못해 RL collapse로 무너졌다. 따라서 V28의 실패 본질은 구조 실패가 아니라 유지 실패다.**
