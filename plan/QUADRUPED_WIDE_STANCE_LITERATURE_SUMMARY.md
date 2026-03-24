# QUADRUPED_WIDE_STANCE_LITERATURE_SUMMARY.md

# 사족보행 문헌 조사 요약
## 주제: wide stance, shoulder posture, 초기 gait 형성, 그리고 우리 프로젝트에 대한 시사점

작성: 2026-03-24

---

## 1. 핵심 결론 요약

문헌과 현재 프로젝트 실험 흐름(V33~V40)을 함께 보면, 다음 해석이 가장 설득력 있다.

1. **좋은 4족 보행은 자세와 분리되지 않는다.**  
   어깨-상완-몸통 정렬은 단순 미관 문제가 아니라 locomotion 기능과 연결된다.

2. **하지만 wide stance / sprawling이 무조건 나쁜 것은 아니다.**  
   특정 구조에서는 안정성과 효율을 함께 얻는 wide stance 보행도 가능하다.

3. **RL에서는 “조금 벌리고 덜 망하는 전략”이 초기에 매우 쉽게 학습된다.**  
   정책은 동물처럼 피로나 관절 부담을 직접 느끼지 못하고, reward에 드러난 것만 배운다.

4. **따라서 현재 프로젝트의 plateau는 후반 correction 부족뿐 아니라, 초기 gait가 wide-stance 의존 전략 위에 형성된 결과일 수 있다.**

5. **문헌적으로 가장 그럴듯한 다음 방향은 “초기 약한 anti-wide-stance bias + strong gait bootstrap” 조합이다.**

---

## 2. 문헌에서 확인된 주요 포인트

### 2.1 자세와 보행은 분리되지 않는다
Brocklehurst 계열 연구는 sprawling–parasagittal 전환에서 어깨 기능과 forelimb pose space가 달라지고, 보다 정렬된 parasagittal posture가 distinct pose space를 가진다고 본다.

즉 “좋은 보행은 단순히 발 타이밍만 맞으면 된다”가 아니라,
**어깨-상완-몸통 정렬 자체가 locomotion 기능의 일부**라는 뜻이다.

우리 프로젝트 시사점:
- `shoulder dev(어깨 벌어짐 정도)`는 단순 보조 지표가 아니라,
- 보행 품질의 핵심 축일 가능성이 높다.

---

### 2.2 wide stance / sprawling이 무조건 비효율적인 것은 아니다
TITAN-XIII 같은 sprawling-type quadruped 연구는, 설계와 제어에 따라 넓은 자세에서도 빠르고 에너지 효율적인 보행이 가능하다고 본다.

즉:
- “벌어지면 무조건 나쁨”은 과도한 일반화
- 핵심은 **우리 SpotMicro가 목표로 하는 보행 품질에 비해 wide stance가 너무 싸게 학습되는가**이다

우리 프로젝트 시사점:
- wide stance 자체를 절대악으로 보면 안 된다
- 하지만 current 목표가 “더 정렬된 고품질 4족 보행”이라면, 지금 wide stance가 너무 유리하게 학습될 가능성은 문제다

---

### 2.3 RL에서는 viability가 초기 gait를 지배한다
최근 quadruped RL 문헌은 초기 gait 형성에서 **viability(안 넘어지고 버티는 능력)** 가 매우 강한 목적 함수로 작동한다고 본다.

이 말은 곧:
- 초기에는 에너지 효율이나 자세 품질보다
- “덜 망하는 전략”이 먼저 학습되기 쉽다는 뜻이다.

우리 프로젝트 시사점:
- policy는 초기에 **wide stance + contact 안정성**을 먼저 배우고,
- 그 위에 stride와 gait를 쌓았을 가능성이 있다.
- 나중에 `shoulder dev(어깨 벌어짐 정도)`를 줄이려 하면 이미 형성된 gait 전체를 다시 갈아엎어야 하므로 plateau가 생길 수 있다.

---

### 2.4 초기 gait bootstrap은 문헌적으로 널리 쓰인다
quadruped RL 구현과 논문들에서는 초기 locomotion 형성을 위해 다음이 자주 쓰인다.

- `feet_air_time`
- `foot_clearance`
- contact-phase / gait-cycle shaping
- low-speed command
- curriculum

즉 초기에는
“완벽하게 잘 걷게 하라”보다
**“걷기 비슷한 패턴부터 쉽게 배우게 하라”**
는 방향이 일반적이다.

우리 프로젝트 시사점:
- narrow stance에서도 걸을 수 있게 하려면
- posture penalty만 세게 걸 게 아니라
- **그 자세에서도 걸을 수 있는 gait bootstrap**이 같이 있어야 한다

---

## 3. 현재 프로젝트(V33~V40)와 연결한 해석

### V33
- 구조 재설계를 급하게 밀다가 부팅 붕괴
- 교훈: 부팅 이전에 철학을 너무 많이 바꾸면 안 된다

### V34
- standing curriculum 시도
- 교훈: 학습 순서는 중요하지만, bootstrap 자체가 약하면 부족하다

### V35
- alive bonus, penalty 완화, 저속 command로 초기 생존 회복
- 교훈: 초기 viability가 핵심이다

### V36
- gait는 개선되었지만 `shoulder dev(어깨 벌어짐 정도)`는 거의 안 줄어듦
- 교훈: gait 개선과 posture 개선은 같은 문제가 아니다

### V37
- posture를 강하게 누르자 gait 붕괴
- 교훈: 자세를 세게 때리기만 하면 안 된다

### V38
- Soft CaT로 `0.54 → 0.45`까지는 감소
- 교훈: 후반 correction도 어느 정도는 먹히지만 한계가 있다

### V39
- CPG/phase로 후반 gait 재구성 시도
- 교훈: 이미 형성된 wide-stance gait를 후반에 뜯어고치기는 어렵다

### V40-A
- 현재 `CaT prob` 단일 변수로 “압력 부족이었는지”를 검증 중

이 흐름 전체를 보면,
현재 프로젝트는 이미 “초기 bootstrap 중요성”도 봤고, “후반 correction 한계”도 많이 경험했다.

따라서 다음 점프는 다음 질문일 가능성이 크다.

> **후반에 더 세게 줄일까?**
보다
> **애초에 처음 gait를 wide-stance 위에서 배우지 않게 할 수 있을까?**

---

## 4. 현재 가장 설득력 있는 의견

문헌 + 실험 흐름을 합쳐 보면, 제 의견은 다음과 같다.

### 4.1 지금 당장은 V40-A를 끝까지 본다
이건 현재 가장 해석 가능한 단일 변수 실험이다.

확인해야 하는 것:
- 정말 `CaT prob` 부족이었는가?
- 아니면 `0.45` 아래는 contact/gait 병목이 남는가?

### 4.2 V40-A가 실패하면 다음은 “후반 correction 강화”보다 “초기 형성 재설계”
즉 다음 단계는:
- 더 강한 CaT
- 더 복잡한 후반 correction
보다

**초기부터 wide stance를 너무 싸게 두지 않으면서, 좁은 자세에서도 걸을 수 있는 bootstrap을 설계하는 방향**
이 더 유망하다.

### 4.3 가장 유망한 방향은 “초기 약한 anti-wide-stance bias + strong gait bootstrap”
이 조합은 다음 장점을 가진다.

- V37처럼 posture를 세게 눌러 붕괴시키지 않음
- V36처럼 wide stance 위에서 gait가 형성되는 것도 줄일 수 있음
- 문헌상 초기 locomotion 형성 철학과도 잘 맞음

---

## 5. 실험 방향으로 번역하면

### 지금 당장
- V40-A 끝까지 진행
- 최소 3000 iter, 가능하면 5000 iter까지

### V40-A 실패 후
다음 메인 실험은 V41 계열이 적절하다.

핵심:
- 초기 직진 저속 phase
- 초기 약한 `shoulder dev(어깨 벌어짐 정도)` / stance bias
- 동시에 `feet_air_time`, `foot_clearance`, phase bootstrap 강화
- 후반 normal locomotion으로 자연스럽게 확장

---

## 6. 한 줄 최종 정리

> **문헌과 현재 실험 흐름을 함께 보면, 현재 plateau의 진짜 원인은 후반 correction 부족만이 아니라, 초기 gait가 wide-stance 의존 전략 위에서 형성된 것일 수 있으며, 다음 단계에서는 초기부터 과한 어깨 벌림에 덜 의존하는 gait 형성 조건을 설계하는 방향이 가장 유망하다.**
