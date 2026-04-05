# SpotMicro RL 실험 흐름 요약 (V1 ~ V59)

이 문서는 `plan` 폴더의 V1~V59 흐름을 바탕으로,
각 버전이 **무엇을 해결하려던 실험이었는지**를 짧고 쉽게 정리하면서도,
전체 맥락이 보이도록 해설을 덧붙인 요약 문서이다.

> 최신 active family는 `V59`.
> **서기 학습 성공** (timeout 98%, 4발 접지 98%). 다음은 보행 전환.

---

# 전체 흐름 한눈에 보기

이 프로젝트의 큰 흐름은 아래와 같이 요약할 수 있다.

1. **걷게 만들기**
2. **제대로 움직이게 만들기**
3. **학습 순서와 판정 체계를 만들기**
4. **로봇의 꼼수와 local optimum을 막기**
5. **어색한 보행을 넘어서 정상 trot 구조를 가르치기**
6. **작동하는 시스템 위에 부족한 것만 더하기**
7. **데이터로 reward 구조의 숨겨진 문제를 발견하고 해결하기**
8. **Isaac Lab 표준 구조로 전환하여 단순하고 견고한 학습 기반을 확보하기**

단순히 reward 몇 개 조정하는 프로젝트가 아니라,
점점 더 **보행 구조 자체를 설계하고, 데이터로 검증하는 방향**으로 발전해 온 흐름이다.

---

# 1기 — 일단 걷게 만들기 시대 (V1 ~ V8)

## 이 시기의 핵심

초기 버전들의 목표는 단순했다.

> **서고, 발을 들고, 트로트 비슷하게라도 걷게 만들자.**

이때는 아직 로봇이
- 몸을 낮게 깔고 기거나
- 발을 거의 들지 않거나
- 트로트 판정이 너무 엄격해서 학습이 막히는
문제가 많았다.

그래서 주로 `feet_air_time`, `standing_height`, trot 보상, same-side 패널티 같은 기초 보상들을 조정하며,
**벌레처럼 기는 상태에서 "그래도 걷는 모양"으로 끌어올리는 실험**을 반복한 시기이다.

## 버전별 한 줄 요약

- **V1** — 서기에서 겨우 걸음으로 넘어왔지만, 진동과 발 끌기가 심한 상태를 높이/보상 튜닝으로 조금 더 걷는 형태로 밀어보려는 실험.
- **V2** — `feet_air_time`을 완화해서 발 들기 reward가 너무 빡빡해 학습이 막히는 문제를 줄이려는 실험.
- **V3** — 몸을 낮게 깔고 기는 대신, 더 세운 자세로 걷게 하려고 `standing_height`를 더 강하게 준 실험.
- **V4** — 트로트 판정을 매우 엄격하게 해서 "정확한 대각 trot만" 보상해보려던 실험.
- **V5** — 너무 엄격한 trot 판정을 완화해서, 학습이 아예 멈추지 않으면서 트로트 방향으로 가게 하려는 조정.
- **V6** — same-side 패널티와 trot 가중치를 손봐 바운드/페이스를 줄이고 대각 보행을 더 강하게 유도하려는 실험.
- **V7** — 작은 보폭, 제자리 트로트, 벌레형 보행 같은 초기 부작용을 덜어내려는 마지막 기초 미세 조정.
- **V8** — Flat 지형에서 쓸 만한 최종 기초 모델을 만들고, 이를 Rough 지형 전이의 출발점으로 삼으려는 실험.

---

# 2기 — 러프 지형과 뒷다리 문제 시대 (V9 ~ V17)

## 이 시기의 핵심

Flat에서 겨우 걷는 것과, 실제로 의미 있게 움직이는 것은 다르다는 점이 드러난 시기이다.

> **진짜 앞으로 내딛게 만들자. 특히 뒷다리가 제대로 움직이게 하자.**

Rough 지형으로 넘어가자,
- 뒷다리가 안 움직이거나
- 뒤를 거의 안 쓰고 앞발만 버티거나
- 셔플링만 하는 문제가 심하게 드러났다.

그래서 rear alternation, rear contact 패널티, rear stride 같은 **뒷다리 전용 보상**이 등장했고,
이 과정에서 "걷는 것"과 "잘 걷는 것"이 전혀 다른 문제라는 점이 분명해졌다.

## 버전별 한 줄 요약

- **V9** — Flat에서 만든 보행을 Rough로 옮기기 위해, 더 멀리/더 어려운 지형으로 가면 이득이 되게 한 진행형 보상 실험.
- **V10** — 뒷다리가 거의 안 움직이니, rear alternation으로 뒷다리 교대 스윙을 직접 강제해보려는 실험.
- **V11** — 뒷다리 두 발이 동시에 계속 붙는 걸 강하게 벌줘서, 최소한 한 발씩은 들게 만들려는 실험.
- **V12** — 뒷다리가 실제로 앞으로 내딛게 하려고, 발 높이와 전진을 결합한 rear stride 보상을 넣은 실험.
- **V13** — 큰 보상 구조 변경을 resume로 이어붙이면 critic이 쉽게 깨진다는 걸 확인한 전환기 실험.
- **V14** — Rough 쪽 reward 구조를 크게 바꾸며, 기존 critic을 그대로 믿고 가면 더 꼬일 수 있다는 점을 확인한 실험.
- **V15** — Rough에서 꼬인 흐름을 끊고, Flat에서 from-scratch로 다시 시작해 기반을 재정비하려는 실험.
- **V16** — 접촉보다 관절 속도 중심으로 옮기며, 더 키네마틱한 trot를 만들려는 실험.
- **V17** — 키네마틱 trot를 유지하려 했지만, 정지/서기 함정이 다시 강하게 나타난 실험.

---

# 3기 — 커리큘럼과 학습 운영 체계 시대 (V18 ~ V23)

## 이 시기의 핵심

이 시기부터는 reward만 보는 게 아니라,
**언제 무엇을 배우게 할지, 그리고 어떻게 읽을지**를 설계하기 시작했다.

> **보상만 바꾸지 말고, 학습 순서와 판정 체계를 설계하자.**

이때 등장한 키워드는:
- 서기 -> 걷기 -> 트로트 커리큘럼
- hard switch vs soft ramp
- critic shock
- heartbeat / KPI / 영상 / workbook
- posture/style refinement

이 시기는 "reward 몇 개 바꿨다"보다,
**학습 방법론과 분석 체계를 함께 만든 시기**라고 할 수 있다.

## 버전별 한 줄 요약

- **V18** — 서기, 걷기, 트로트를 3단계로 나눠 가르치면 데드락을 풀 수 있는지 본 커리큘럼 실험.
- **V19** — phase 전환을 hard switch로 하면 critic shock가 얼마나 큰지 확인한 실험.
- **V20** — critic shock를 줄이기 위해 phase 전환을 soft-ramp로 천천히 섞는 실험.
- **V21** — gait-quality-first KPI, heartbeat, 판정 체계를 도입해 훈련을 더 정밀하게 읽으려는 운영 실험.
- **V22** — 영상, workbook, 분석 아티팩트를 체계화해 나중에 판정을 재검토 가능하게 만드는 실험.
- **V23** — locomotion core를 유지하면서 posture/style refinement를 시도한 실험.

---

# 4기 — 4발 참여와 local optimum과의 전쟁 시대 (V24 ~ V35)

## 이 시기의 핵심

이 시기의 핵심은 분명하다.

> **로봇이 4발로 걷는 척하지만, 실제로는 일부 다리만 쓰는 꼼수를 계속 찾는다.**

여기서 본격적으로 나타난 문제는:
- 3족 exploit
- 특정 다리 collapse
- 앞발 과고정
- rear bias
- validity gate
- target band
- front swing 부족
- 부팅 불안정

이 시기는 **"진짜 4발 참여를 만들기 위해 loophole을 하나씩 막아가는 시기"**였다.

## 버전별 한 줄 요약

- **V24** — 특정 다리를 거의 안 쓰는 3족 exploit를 막기 위해 limb validity gate를 도입한 실험.
- **V25** — 특정 다리 collapse를 직접 막아보려 했지만, 문제가 다른 다리로 이동하는지만 확인한 실험.
- **V26** — collapse가 이동하지 못하게 모든 다리에 같은 existence floor를 주는 대칭 floor 실험.
- **V27** — 4다리를 기능적으로 모두 쓰지 않으면 reward를 못 받게 만드는 per-limb validity 구조 실험.
- **V28** — 단순 floor를 넘는 수준이 아니라, 정상적인 4발 참여 범위(target band)에 들어오면 이득이 되게 만든 실험.
- **V29** — 앞발이 너무 오래 붙어 있어도 보상받던 loophole를 막고, 더 큰 보폭 trot를 만들려 한 실험.
- **V30** — 보상보다 초기 자세 비대칭이 문제일 수 있다고 보고, 초기 자세를 더 대칭적으로 바로잡으려 한 실험.
- **V31** — rear에 쓰던 swing 강제를 front에도 대칭 적용해 앞발을 직접 들어보려 한 실험.
- **V32** — front swing 보상을 걷어내고 `feet_air_time` 하나를 크게 키워 앞발 체공을 끌어내보려 한 실험.
- **V33** — 미세조정만으로는 안 된다고 보고, reward 구조 자체를 대폭 줄여 근본 재설계를 시도한 실험.
- **V34** — 서기도 못 하는데 걷기까지 동시에 요구한 게 문제라 보고, standing curriculum으로 서기->걷기를 분리하려 한 실험.
- **V35** — 급진적 개편보다 먼저, reproducible한 부팅 안정성을 확보하기 위한 기반 정비 실험.

---

# 5기 — anti-splay와 구조적 gait 유도 시대 (V36 ~ V39)

## 이 시기의 핵심

이 시기부터는 문제가 더 선명해졌다.

- 셔플은 어느 정도 잡았다
- 그런데 자세가 이상하다
- 특히 어깨가 옆으로 퍼진다(splay)
- 앞발은 과하게 붙어 있다

그래서 질문이 바뀌었다.

> **나쁜 자세를 직접 누를 것인가, 아니면 좋은 gait를 구조적으로 가르칠 것인가?**

이 시기는 그 전환의 시기이다.

- **V36~V38**: 퍼지면 혼낸다
- **V39**: 처음부터 올바른 박자로 걷게 시킨다

## 버전별 한 줄 요약

- **V36** — 벌레걸음, 셔플, 어깨 퍼짐을 동시에 줄여보려는 anti-splay/anti-shuffle 실험.
- **V37** — anti-shuffle은 어느 정도 됐지만 splay가 남아 있어, 어깨 벌어짐을 더 직접 벌주는 강화 실험.
- **V38** — 로봇의 어깨가 옆으로 퍼지는(splay) 나쁜 자세를, 점수 깎기 대신 '훈련 강제 종료'로 막아보려는 CaT 실험.
- **V39** — splay를 직접 때리기보다, CPG/phase clock으로 정상 trot 리듬을 구조적으로 지시해서 splay와 앞발 과고정을 함께 풀어보려는 실험.

---

# 6기 — Clean Reward + Boot 해결 시대 (V42 ~ V44)

## 이 시기의 핵심

50개 reward의 복잡한 상호작용이 splay를 유지시킨다는 가설로, reward를 15개로 줄이는 "Clean Restart" 시도. Boot 실패(서지도 못함)를 거쳐 근본 원인을 발견하고 해결.

> **"reward 수를 줄이는 것이 정답이 아니라, 어떤 reward가 있는가가 핵심"**

## 버전별 한 줄 요약

- **V42** — 50개->16개 clean reward. 구현 완료했지만 독립 reward의 exploit 가능성 발견 -> V43으로 연결 전환.
- **V43** — 15개 connected reward (per-leg propulsion gating). Boot 실패 (ep_len=8). walking reward가 boot에서 충돌하는 것이 원인.
- **V43-B** — propulsion gate를 boot에서 OFF. Boot 여전히 실패. gating이 원인이 아님을 확인.
- **V43-C** — joint_default_pose -2.0->-0.3 완화. Boot 여전히 실패. pose가 원인이 아님을 확인.
- **V43-D** — Walking reward boot gating (5-Phase). ep_len 10 (V43 대비 +20%), fwd_vel 7배 향상. 방향은 맞지만 positive signal 부족.
- **V43-E** — boot_standing + boot_foot_contact 추가 (V41 bootstrap 철학). **Boot 성공 (ep_len 248, shoulder 0.40)**. 하지만 stride 0.39, coupling 0.0 (종종걸음).
- **V44** — diagonal_coupling 복원 + pose -0.5 완화. stride 1.3~2.4 (개선), 하지만 shoulder 0.53 (악화), coupling 0.0 (변화 없음). shoulder-leg trade-off 확인.

## 핵심 교훈

- walking reward가 boot에서 충돌 -> boot gating 필수 (V43-D)
- boot에 positive signal 필요 -> boot_standing reward (V43-E)
- joint_default_pose가 shoulder와 leg를 동시 제어 -> 분리 필요 (V44)
- coupling reward의 sparse gradient -> output=0이면 weight 올려도 0 (V44)
- 15개 reward는 splay 해결(0.40)하지만 보행 품질 부족(stride 0.39)

---

# 7기 — 통합 시대 (V45 ~ V46)

## 이 시기의 핵심

15개 clean reward와 50개 rich reward 각각의 장점을 합치는 방향. "reward 수가 아니라 어떤 reward가 있는가"가 핵심.

> **V38.3의 검증된 보행 품질 + V42~V44에서 발견한 boot/splay 개선을 통합**

## 버전별 한 줄 요약

- **V45** — shoulder-leg 분리 + pair coupling + leg_lift. 설계만 완료 (미구현). V46으로 전략 전환.
- **V46-A** — V43-E + V38.3 gait reward 8개 추가. stride 1.45 (pose penalty 한계).
- **V46-B** — V46-A + shoulder-leg 분리. stride 1.29, shoulder 0.44 (제거한 reward가 stride 동력이었음 발견).
- **V47** — **V38.3 순정 + boot_standing + boot_contact.** stride 6.29, coupling 0.46, shoulder 0.43. **V38.3 재현 + shoulder 개선 + boot 2배 가속. 성공.**

---

# 8기 — 서서 4발로 걷게 만들기 시대 (V47 ~ V53)

## 이 시기의 핵심

V47에서 V38.3 순정 + boot_standing이라는 성공 공식을 찾았지만,
비디오를 자세히 보니 로봇이 **앞다리를 거의 안 들고** 뒷다리만으로 기어가는 "귀뚜라미 보행"을 하고 있었다.

> **로봇이 걷긴 걷는데, 앞다리를 안 든다. 어떻게 4발 모두 쓰게 만들 것인가?**

이 시기는 그 질문에 답을 찾아가는 과정이다.
reward weight를 올려보고, height gate를 걸어보고, termination을 추가해보고,
결국 **reward 구조 자체(4발 평균)가 앞다리 사용을 penalty화한다**는 근본 원인을 찾아
**앞다리 전용 reward**로 해결하는 흐름이다.

- **V47**: 성공했는데 영상 보니 귀뚜라미
- **V48**: 자세 보정 + 현실적 질량/토크 시도 -> 시기상조
- **V49**: 기반 복원, 귀뚜라미 원인 추적 시작, 인프라 정비
- **V50**: "높이를 유지하면 앞다리가 들릴 것" -> 실패 (walking이 높이를 압도)
- **V51**: "walking reward에 높이 조건을 걸자" -> 절반 성공 (높이는 유지, 귀뚜라미는 재발)
- **V52**: "데이터로 보자" -> reward delta 분석 -> 4발 평균 leg_lift가 범인
- **V53**: "앞다리만 따로 보상하자" -> from-scratch

## 버전별 한 줄 요약

- **V47** — V38.3 순정 77개 reward + boot_standing(+15) + boot_contact(+5). stride 6.29, coupling 0.46 달성. "작동하는 시스템을 고치지 말 것"의 실증. 성공.

- **V48** — 비디오에서 몸이 너무 낮고 다리 과접힘 발견. leg=-0.97로 standing pose 보정. V48-C(6.54kg 질량)와 V48-D(현실 토크)는 보행 불안정 -> "보행 baseline 없이 realism 추가는 시기상조"라는 결론. Two-track 전략(보행 먼저, realism 나중) 결정.

- **V49** — V48-B 설정으로 baseline 복귀. curriculum state save/restore, `_USE_BOOT_STANDING` feature flag, CLI->Telegram 경유 routing 등 인프라 대폭 정비. iter 1140에서 stride 6.9 달성, 그런데 front_leg_lift가 0.08 — **귀뚜라미 보행** 최초 인식. boot_standing ramp-down(300 iter)이 너무 빨라 "낮게 기기" 습관이 고착된 것이 원인.

- **V50** — boot ramp-down을 300->1500으로 연장, standing_height 10->15, base_height_l2 -15->-20으로 높이 강화. iter 1030에서 front_lift 0.137 (V49 대비 70% 개선). 하지만 walking reward가 활성화되면 높이가 다시 하락. **reward weight 비율(15:1)로는 local optimum을 깰 수 없다**는 구조적 한계 확인.

- **V51** — "reward weight가 안 되면 구조를 바꾸자." Walking reward에 height 조건부 penalty를 거는 soft height gate 설계. 3번의 시행착오: w=40(즉사) -> w=15(수갑 효과) -> boot-gated(성공). boot-gated 버전에서 front_lift **0.257** 역대 최고 달성. 하지만 iter 3300에서 0.035로 재하락. **anti-crouch는 성공했지만, 적당히 낮은 자세에서의 귀뚜라미는 못 막았다.**

- **V52** — min_height_termination(0.15m, boot-gated) + front_rear_symmetry(w=8) 추가. height 0.19로 안정, 하지만 front_lift는 여전히 하락. **실측 reward delta 분석** 수행: 앞다리를 포기하면 순이익 +5.76/step — stance_width_penalty(+7.23) 하나가 순이익보다 컸다. V52.1에서 data-driven weight 재설계(stance_width -3->-1.5, flc 8->16, leg_lift 15->20). 그리고 **핵심 발견**: leg_lift의 4발 평균 구조가 뒷다리(다수파, 3발)에 의해 앞다리(소수파) 사용을 -5.7/step으로 penalty화. **평균 reward에서 다수파가 소수파를 억제하는 perverse incentive.**

- **V53** — V52.1의 발견에 기반한 해결책. 기존 leg_lift(4발, w=20) 유지 + **front_leg_lift(FL/FR only, w=15)** additive 추가. 수치 근거: 앞다리 사용의 net benefit이 -9.70/step(V52.1 조정 + front_lift)으로 크게 유리하도록 설계. from-scratch 훈련 시작.

## 핵심 교훈

- boot_standing ramp-down이 너무 빠르면 "낮게 기기" 습관 고착 (V49)
- reward weight 비율 조정으로는 local optimum을 깰 수 없다 -> 구조 변경 필요 (V50)
- height gate는 boot OFF, walking만 적용 — boot에서 height penalty 주면 서기 학습 자체 불가 (V51)
- penalty > alive_bonus이면 "죽는 게 이득"이 된다 (V51 w=40)
- reward 변경 시 per-step net reward 부호 검증이 핵심 — net negative면 ep_len 감소가 최적해 (V51)
- 실측 reward delta 분석이 직관보다 정확 — "이 reward가 학습을 방해한다"는 데이터로 증명 (V52)
- **4발 평균 reward에서 다수파(뒷다리)가 소수파(앞다리) 사용을 penalty화** — 평균 함수의 숨겨진 perverse incentive (V52.1)
- feature flag(`_USE_BOOT_STANDING`)로 버전 분기 없이 기능 제어 (V49)
- CLI 명령은 Telegram->Listener 경유로 통일, 직접 프로세스 실행 금지 (V50)

---

# 9기 — Baseline Recovery First, Phase Probe Second 시대 (V54 ~ V55)

## 이 시기의 핵심

V53까지는 "앞다리를 더 쓰게 만들자"가 중심이었지만,
V54부터는 질문이 달라졌다.

> **baseline locomotion이 없는 상태에서 phase를 먼저 얹으면 어떻게 되는가?**

V54는 이 질문에 대해 분명한 실패를 보여주었다.
phase_contact/phase_clearance를 주연으로 올리고 handoff까지 걸자,
로봇은 phase를 받아낼 locomotion 기반이 없는 상태에서 반복적으로 collapse했다.

그래서 V55에서는 전략 자체를 다시 세웠다.

> **phase를 먼저 강제하지 말고, baseline을 먼저 다시 살린 뒤 probe로 얹자.**

V54~V55는 reward 미세조정보다,
실험 방법론과 검증 방법 자체를 재정의한 시기이다.

## 버전별 한 줄 요약

- **V54** — clean phase-centric 전환. reward를 대폭 줄이고 phase_contact/phase_clearance를 주연으로 올린 handoff 실험. 하지만 baseline locomotion이 없는 상태에서 phase handoff를 걸자 반복적으로 collapse. 결론: **phase 수식보다 locomotion 기반이 먼저 필요하다.**

- **V55** — baseline recovery first, phase probe second 재설계. A-track에서 baseline을 되살리고(`A5.x`), `iter 500` gait-gate release collapse를 forward, release shock, min_height 증폭기 관점으로 분해 분석. `A6`에서 posture/usage gate를 보강해 baseline quality를 확보했고, `B1`에서 A6 baseline 위에 weak phase probe를 얹었을 때 baseline을 유지하는지 검증.

## 핵심 교훈

- **phase를 먼저 주연으로 올리면 안 된다** — baseline 없이 handoff를 걸면 collapse한다 (V54)
- **코드값이 아니라 실제 적용값으로 판정해야 한다** — env_cfg, checkpoint snapshot, runtime weight, TensorBoard scalar를 분리해 봐야 한다 (V55)
- **한 실험 = 한 가설** — shock 완화, conservative forward, min_height 완화 같은 실험을 따로 분리해야 원인 분리가 가능하다 (V55)
- **min_height는 근본 원인보다 증폭기일 수 있다** — threshold를 낮추자 iter 500 collapse가 즉사에서 회복 가능한 흔들림으로 바뀌었다 (V55 A5.5~A5.6)
- **A-track과 B-track의 목적을 분리해야 한다** — A는 baseline quality gate, B는 phase probe여야 해석 가능성이 생긴다 (V55)

---

# 10기 — Isaac Lab 표준 복귀 시대 (V56 ~ V58)

## 이 시기의 핵심

V55까지의 77개 heuristic 체계를 폐기하고, Isaac Lab 표준 locomotion 구조로 전환했다.
"표준을 신뢰하고, SpotMicro 크기만 보정한다."

## 버전별 한 줄 요약

- **V56** — pitch-first mechanics correction 시도. twist exploit 발견.

- **V57** — clean phase-centric reboot + zero-action stand 물리 디버깅.
  - bang-bang 진동 원인 규명 (URDF velocity = DCMotor velocity_limit)
  - ImplicitActuator 전환으로 zero-action standing 달성
  - stand-first RL 학습은 die-fast로 실패 (penalty 10~50배 과다)

- **V58** — Isaac Lab 표준 locomotion 복귀.
  - 77개 -> 11개 reward
  - ImplicitActuator + velocity tracking
  - B1: locomotion bootstrap 성공 (ep_len 968, timeout 99%)
  - B1 한계: drag propulsion (feet_air_time=0 근사, diagonal_coupling=0)
  - B2: feet_air_time 강화 (weight 0.05->0.20, threshold 0.5->0.2)

## 핵심 교훈

- 77개 heuristic보다 표준 10개 reward가 낫다
- stand-first보다 velocity tracking이 더 자연스러운 학습 경로
- per-step reward 음수 = die-fast
- 한 문제씩, 데이터 기반으로

---

# 전체 흐름을 가장 짧게 다시 요약하면

- **V1~V8**: 일단 걷게 만들기
- **V9~V17**: 진짜로 내딛게 만들기, 특히 뒷다리 문제 해결
- **V18~V23**: 커리큘럼과 판정 체계 만들기
- **V24~V35**: 4발 참여를 속이는 꼼수와 loophole 막기
- **V36~V39**: splay를 직접 누르다가, 결국 정상 gait 구조를 가르치는 단계로 전환
- **V42~V44**: reward를 줄였더니 splay는 해결, 보행은 부족 -> boot gating, shoulder 분리 발견
- **V46**: 선별 복원 시도, stride 여전히 부족 -> 제거한 reward가 stride 동력이었음 발견
- **V47**: V38.3 순정 + boot만 추가 -> stride 6.29, shoulder 0.43 **성공**
- **V48~V52**: 귀뚜라미 보행(앞다리 미사용) 원인 추적 -> 4발 평균 reward의 perverse incentive 발견
- **V53**: 앞다리 전용 reward로 구조적 해결 시도
- **V54**: phase를 주연으로 올렸더니 baseline 없는 handoff collapse 확인
- **V55**: baseline을 다시 살린 뒤 phase를 probe로 얹는 전략으로 재설계
- **V56~V58**: 77개 heuristic 폐기, Isaac Lab 표준 locomotion 구조로 전환. 표준 11개 reward + ImplicitActuator로 locomotion bootstrap 성공, drag propulsion 해결 진행 중
- **V59**: URDF 질량 실물 기준 수정(5.3→1.41kg), merge_fixed_joints=False(contact 정상화), STS3215 서보 스펙 반영, **서기 학습 성공** (timeout 98%, 4발 접지 98%, 수평 유지 98%)

---

# 11기 — 실물 기반 서기 학습 시대 (V59)

## 이 시기의 핵심

V58까지의 locomotion 시도에서 반복된 실패(주저앉음, 넘어짐, 발 들기)의 근본 원인을 찾아낸 시기이다.

> **URDF 질량이 실물의 3배, merge_fixed_joints=True가 contact를 깨뜨림, 서기를 먼저 배워야 함**

## 핵심 발견

- **URDF 질량**: 원본 5.3kg은 실물 ~1.7kg의 3배. base 링크 inertial 누락으로 PhysX 1kg 기본값 추가
- **merge_fixed_joints=True**: toe_link contact reporting 완전 불가. False로 전환해야 4발 접촉 감지
- **서기 먼저**: 표준 locomotion으로 바로 가면 주저앉기가 최적해. 서기를 먼저 학습해야 함
- **consecutive termination**: 1 step 판정은 미세 진동으로 즉사. 연속 8 step 판정이 핵심

## 서기 학습 결과

- timeout 98%, 4발 접지 98%, 수평 유지 98%, 목표 높이 91%
- 다음 단계: 서기 체크포인트에서 보행 학습으로 전환

---

# 최종 한 문장

이 프로젝트의 흐름은,

> **"걷게 만들기"에서 시작해, 꼼수를 막고, reward를 줄이고, 표준으로 전환하고, URDF 질량과 contact 센서의 근본 문제를 해결한 뒤, "서기를 먼저 배우자"는 원칙 아래 4발 접지 + 수평 유지 서기 학습에 성공한 상태에서, 보행 전환을 준비하는 단계에 와 있다.**
