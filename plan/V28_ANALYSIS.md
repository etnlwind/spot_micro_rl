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

---

## 11. 실측 데이터 기록 (2026-03-15~16)

### 11.1 Run 구조

V28 훈련은 총 3개의 run으로 진행됐다.

| run 디렉토리 | 기간 | checkpoint 범위 | 비고 |
| --- | --- | --- | --- |
| `2026-03-15_19-00-08` | 2026-03-15 19:00 ~ | iter 0~1000 (model_0, 200, 400, 600, 800, 1000) | supervisor 기동 당시 common.py 버전 표기가 V27.1b였으나 실제 env_cfg는 V28. train_version.txt 수동 교정 완료 |
| `2026-03-16_00-40-48` | 2026-03-16 00:40 ~ | iter 1000~2000 (model_1000, 1200, 1400, 1600, 1800, 2000) | 자동 resume run |
| `2026-03-16_03-45-40` | 2026-03-16 03:45 ~ | iter 2000~2400+ | 자동 resume run. iter 2001에서 RL collapse 확인 |

### 11.2 iter 100 실측 (run: `19-00-08`)

| 항목 | 값 |
| --- | --- |
| reward | -5.148 (avg10: -5.984) |
| survival | 11.4% |
| termination | timeout 2% / fall 98% |
| FL contact / prop | 0.115 / 0.100 |
| FR contact / prop | 0.120 / 0.105 |
| RL contact / prop | 0.090 / 0.076 |
| RR contact / prop | 0.092 / 0.075 |
| usage_min | 0.061 |
| TAP suspicion | FL, FR (contact+prop 0.08~0.18 정체) |
| V28 판정 | 🟡 조짐 관찰 |

초반 탐색 구간. 4발 모두 band_low(0.20) 아래이므로 Layer C 인센티브 거의 없음. Layer B floor만 겨우 회피 중.

### 11.3 iter 201 실측 (run: `19-00-08`)

| 항목 | 값 |
| --- | --- |
| reward | 66.109 (avg10: 57.399) |
| survival | 34.9% |
| termination | timeout 50% / fall 50% |
| FL contact / prop | 0.432 / 0.370 |
| FR contact / prop | 0.434 / 0.378 |
| RL contact / prop | 0.253 / 0.205 |
| RR contact / prop | 0.280 / 0.212 |
| usage_min | 0.417 |
| front_rear_balance | 0.3121 🔴 |
| TAP suspicion | 없음 ✅ |
| per_leg_contact_target_band TOP5 순위 | 4위 (+4.1067) |
| V28 판정 | 🟢 양호 |

**핵심 관찰**: iter 100→201 단 100 iter 만에 reward -5.1 → 66.1 (+71pts) 급등. Layer C가 즉시 작동했고 4발 모두 band 진입 확인. 단, FL/FR(0.43) vs RL/RR(0.25~0.28) 앞/뒤 불균형이 이미 형성되어 있음.

### 11.4 iter 2001 실측 (run: `03-45-40`)

| 항목 | 값 |
| --- | --- |
| reward | 209.034 |
| survival | 19.2% |
| termination | timeout 99% / fall 1% |
| FL contact / prop | 0.259 / 0.202 |
| FR contact / prop | 0.215 / 0.183 |
| **RL contact / prop** | **0.012 / 0.012 ← 붕괴** |
| RR contact / prop | 0.260 / 0.181 |
| usage_min | 0.005 🔴 |
| rear_usage_diff | 0.298 🔴 |
| V28 판정 | 🔴 즉시 중단 권고 |

**핵심 관찰**: RL이 사실상 완전 붕괴. contact=0.012로 이 다리는 기능 참여를 거의 안 함. FL/FR/RR은 band 안에 있지만 RL 없이 3발 구조로 고착. per_leg_contact_target_band가 TOP5에서 사라짐 — RL이 band 밖으로 밀려나 Layer C의 RL 기여분이 소실됨.

### 11.5 타임라인 요약

| iter | 상태 | 핵심 지표 |
| --- | --- | --- |
| 100 | 초기 탐색 | 4발 contact 0.09~0.12, TAP 징후 |
| 201 | **Layer C 즉시 작동** | 4발 모두 band 진입, reward +71pts |
| 600 | **성공 구간 (실측 확인)** | 4발 validity pass, RL 살아있음 |
| 800 | **best reference** | 가장 좋은 상태 유지 |
| 1000 | collapse onset | RL 약세 시작 |
| 2001 | **RL 완전 붕괴 확인** | RL contact=0.012, usage_min=0.005 |

### 11.6 Layer C 조기 작동 확인

iter 201 시점에서 `per_leg_contact_target_band`가 TOP5 4위에 진입한 것은 설계 의도 정확히 작동한 증거다.
V28 band ramp start가 iter 100이고, iter 201에서 이미 4발이 band에 들어오면서 Layer C가 강력하게 끌어당겼다.
이후 붕괴가 발생한 것은 Layer C가 틀린 것이 아니라, **RL이 band 밖으로 나갔을 때 다시 당겨오는 장치가 부족했기 때문**이다.

---

## 12. V28 최종 판정 (2026-03-16)

- **판정**: FAIL (최종 정책 기준)
- **공식 붕괴 확인 시점**: iter 2001 (RL contact=0.012)
- **훈련 종료**: mode=idle, 대기 상태
- **V28.1로 이행**: V28.1_PLAN.md의 “band residency” 방향이 올바른 다음 단계임을 이 데이터가 지지함

V28.1 구현 전 우선 분석 과제 (V28.1_PLAN.md 섹션 10 참조):
- **분석 1** (600/800/1000/1200 비교표): iter 600/800/1000/1200 report zip에서 다리별 수치 추출 필요
- **분석 2** (RL residency 추이): iter 600→2001 사이 RL이 언제, 얼마나 빠르게 빠졌는지 확인 필요
- **분석 3** (800 영상 확인): 실제 4족보행 수준 육안 확인 필요

---

## 13. 실측 데이터 기반 심층 분석 (2026-03-16 tracing)

### 13.1 전체 iteration 비교표 (heartbeat 실측)

아래는 heartbeat_reports.jsonl에서 추출한 iter별 핵심 수치 전체다.
run 전환 지점(iter 1001, 2001)은 새 run의 첫 측정값이므로 run 재기동 직후 상태를 반영한다.

| iter | reward | survival | validity | FL contact | FR contact | RL contact | RR contact | RL propulsion | RL usage | usage_min | rear_usage_diff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | -5.1 | 11.4% | ❌ | 0.115 | 0.120 | 0.090 | 0.092 | 0.076 | 0.061 | 0.061 | — |
| 201 | 66.1 | 34.9% | ✅ | 0.432 | 0.434 | 0.253 | 0.280 | 0.205 | 0.417 | 0.417 | — |
| 301 | 236.2 | 46.2% | ✅ | 0.436 | 0.444 | 0.386 | 0.407 | 0.330 | 0.865 | 0.865 | — |
| 401 | 333.0 | 48.1% | ✅ | 0.440 | 0.447 | 0.397 | 0.415 | 0.350 | 0.874 | 0.874 | — |
| 500 | 381.4 | 100.0% | ✅ | 0.438 | 0.445 | 0.383 | 0.410 | 0.330 | 0.861 | 0.861 | — |
| 601 | 409.9 | 100.0% | ✅ | 0.440 | 0.447 | 0.375 | 0.405 | 0.339 | 0.853 | 0.853 | — |
| 701 | 441.4 | 100.0% | ✅ | 0.441 | 0.449 | 0.387 | 0.412 | 0.348 | 0.864 | 0.864 | — |
| 801 | 475.1 | 100.0% | ✅ | 0.443 | 0.450 | 0.390 | 0.415 | 0.347 | 0.867 | 0.867 | — |
| 901 | 498.0 | 100.0% | ✅ | 0.441 | 0.448 | 0.359 | 0.410 | 0.322 | 0.838 | 0.837 | 0.132 |
| **1000** | 542.3 | 100.0% | **❌** | 0.433 | 0.448 | **0.146** | 0.408 | **0.142** | **0.203** | 0.203 | — |
| **1001** | 153.7 | 18.7% | **❌** | 0.262 | 0.279 | **0.048** | 0.286 | **0.046** | **0.028** | 0.028 | — |
| 1101 | 420.1 | 100.0% | ❌ | 0.386 | 0.413 | 0.025 | 0.370 | 0.025 | 0.013 | 0.013 | — |
| 1202 | 563.9 | 100.0% | ❌ | 0.410 | 0.432 | 0.031 | 0.400 | 0.030 | 0.017 | 0.017 | — |
| 1302 | 620.4 | 100.0% | ❌ | 0.415 | 0.439 | 0.018 | 0.405 | 0.018 | 0.008 | 0.008 | — |
| 1402 | 626.9 | 100.0% | ❌ | 0.418 | 0.441 | 0.016 | 0.407 | 0.015 | 0.007 | 0.007 | — |
| 1501 | 604.9 | 100.0% | ❌ | 0.413 | 0.438 | 0.014 | 0.402 | 0.014 | 0.006 | 0.006 | — |
| 1601 | 673.0 | 100.0% | ❌ | 0.420 | 0.443 | 0.015 | 0.408 | 0.015 | 0.007 | 0.007 | — |
| 1701 | 672.1 | 100.0% | ❌ | 0.421 | 0.444 | 0.017 | 0.410 | 0.017 | 0.008 | 0.008 | — |
| 1801 | 660.5 | 100.0% | ❌ | 0.419 | 0.442 | 0.019 | 0.408 | 0.018 | 0.009 | 0.009 | — |
| 1901 | 697.9 | 100.0% | ❌ | 0.423 | 0.447 | 0.013 | 0.413 | 0.013 | 0.006 | 0.006 | — |
| 2001 | 209.0 | 19.2% | ❌ | 0.259 | 0.215 | **0.012** | 0.260 | **0.012** | **0.005** | 0.005 | 0.298 |
| 2102 | 561.3 | 100.0% | ❌ | 0.385 | 0.400 | 0.011 | 0.380 | 0.011 | 0.005 | 0.005 | — |
| 2203 | 687.9 | 100.0% | ❌ | 0.415 | 0.435 | 0.010 | 0.405 | 0.009 | 0.004 | 0.004 | — |
| 2300 | 716.0 | 100.0% | ❌ | 0.418 | 0.438 | 0.010 | 0.408 | 0.010 | 0.004 | 0.004 | — |
| 2400 | 733.6 | 100.0% | ❌ | 0.420 | 0.440 | **0.009** | 0.410 | 0.009 | **0.004** | 0.004 | — |

---

### 13.2 RL residency 추이 분석 (전 구간)

RL contact의 변화를 구간별로 요약하면 다음과 같다.

#### 구간 1: 성장기 (iter 100~801)

- iter 100: 0.090 → iter 201: 0.253 (+0.163, +181%)
- iter 201: 0.253 → iter 801: 0.390 (+0.137, 점진적 상승)
- 이 구간은 RL이 지속적으로 성장하며 band 진입

#### 구간 2: 초기 약세 (iter 801~1000)

- iter 801: 0.390 → iter 901: 0.359 (−0.031, −8%)
- iter 901: 0.359 → iter 1000: 0.146 (−0.213, −59%)
- **iter 901→1000 사이 급락이 핵심**: 단 100 iter 만에 39% 손실

#### 구간 3: 붕괴 확정 (iter 1000~1101)

- iter 1000: 0.146 → iter 1001: 0.048 (−0.098, run 재기동 직후)
- iter 1001: 0.048 → iter 1101: 0.025 (−0.023)
- run 재기동 후에도 회복 없음 → 정책 자체가 이미 RL을 버린 상태

#### 구간 4: 고착기 (iter 1101~2400)

- iter 1101~2400: 0.009~0.031 범위 내에서 변동
- **회복 없는 plateau** — RL은 사실상 완전히 배제된 stable local optimum 진입
- iter 2000~2400: 추가 악화 (0.014 → 0.009)

**결론**: RL collapse는 iter 901~1000 사이에 시작되어 iter 1001에서 돌이킬 수 없는 수준으로 악화됐다.
실제 임계 구간은 **iter 901~1001**이며, 이 100~200 iter를 막는 것이 V28.1의 핵심이다.

---

### 13.3 "역설적 reward 상승" 분석

V28에서 가장 주목해야 할 패턴은 **RL이 붕괴한 이후에도 reward가 계속 상승했다**는 점이다.

| 구간 | RL contact | reward | 해석 |
| --- | --- | --- | --- |
| iter 600~800 (건강) | 0.375~0.390 | 410~475 | 4발 기여 정상 |
| iter 1101 (붕괴 초기) | 0.025 | 420 | reward 일시 회복 |
| iter 1202 | 0.031 | 564 | reward 계속 상승 |
| iter 1402 | 0.016 | 627 | reward 더 상승 |
| iter 2300 | 0.010 | 716 | reward 최고점 근접 |
| iter 2400 | 0.009 | 734 | reward 최고점 |

**메커니즘 해석**:

RL이 죽은 이후에 reward가 오히려 높아진 이유는 다음과 같다.

1. **3발 exploit의 효율화**: RL을 배제하자 나머지 3발(FL/FR/RR)이 더 자유롭게 band 중심에 안착 가능. 3발 각각의 target-band reward가 높아짐.

2. **survival penalty 제거**: RL이 접지 불안정을 일으키는 "방해 요소"였다면, RL을 제거함으로써 오히려 생존률이 안정됨. (iter 1101부터 survival 100% 회복)

3. **single_limb_validity_penalty 한계**: RL이 완전히 꺼진 상태에서 이 penalty가 얼마나 reward를 깎았는지 확인 필요. 3발의 band reward 합이 penalty를 초과했을 가능성 있음.

4. **cooperation reward의 역설**: cooperation reward가 FL/FR/RR 3발만으로도 어느 정도 발동됐을 가능성 있음 (diagonal pair 중 FL-RR이 살아있음).

**V28.1에 대한 시사점**:

이 패턴이 의미하는 것은, **penalty 기반으로만 RL collapse를 막는 것은 충분하지 않다**는 점이다.
3발 exploit의 total reward가 penalty를 이기면 local optimum이 안정화된다.
따라서 V28.1은 **RL이 band 안에 있을 때의 추가 이득**(residency reward, min-leg cooperation)이 핵심이다.

---

### 13.4 front/rear 비대칭 진행 패턴

V28 데이터에서 front(FL/FR) vs rear(RL/RR)의 contact 비대칭이 어떻게 진행됐는지 추적한다.

**초기 형성 (iter 201)**:

- FL: 0.432, FR: 0.434 (front 평균: 0.433)
- RL: 0.253, RR: 0.280 (rear 평균: 0.267)
- **front-rear gap: 0.166** — 이미 iter 201에서 앞다리 우세 형성

**성공 구간 수렴 (iter 301~801)**:

- iter 301: front 0.440, rear 0.397 → gap 0.043 (수렴)
- iter 801: front 0.447, rear 0.403 → gap 0.044 (안정적 수렴)
- **좋은 상태 = front-rear gap이 0.04~0.05 수준으로 관리됨**

**붕괴 전 이상 징후 (iter 901)**:

- rear_left_right_usage_diff: 0.132 (**처음으로 보고에 등장**)
- 이는 RL usage vs RR usage 차이가 벌어지기 시작했다는 신호
- iter 801 대비 RL contact 0.031 하락 (-8%) — 아직 band 안이지만 하향 압력 존재

**붕괴 시작 (iter 1000)**:

- FL: 0.433, FR: 0.448 (front 평균: 0.441)
- RL: **0.146**, RR: 0.408
- **rear 내부 gap: 0.262** — RR은 건강하지만 RL만 붕괴
- rear_usage_diff가 극단적으로 벌어짐

**핵심 발견**: front-rear 전체 gap이 아니라, **rear 내부의 RL-RR 비대칭이 먼저 발생**했다.
iter 901에서 이미 rear_left_right_usage_diff가 0.132였고, iter 1000에서 급락했다.
**V28은 이 rear 내부 비대칭을 감지하고 억제하는 장치가 없었다.**

---

### 13.5 iter 1000 임계점의 성격 규명

iter 1000은 단순히 "붕괴가 시작된 iter"가 아니다. 데이터를 보면 다음 두 가지 가설 중 하나가 맞다:

#### 가설 A: iter 800~1000 사이에 점진적으로 RL이 약해졌고 iter 1000에 측정된 것

- iter 801: RL 0.390 → iter 901: RL 0.359 (-0.031)
- iter 901: RL 0.359 → iter 1000: RL 0.146 (-0.213)
- **iter 901~1000 사이에 급락이 집중됨**

#### 가설 B: iter 1000 직전에 갑작스러운 정책 전환이 있었다

- iter 901에서는 validity pass (✅) 였고 RL이 0.359
- iter 1000에서 갑자기 validity fail (❌) 이고 RL이 0.146
- **단 100 iter 만에 -59% 급락** → 점진적 악화보다 정책 전환에 가깝다

데이터만으로는 구분이 어렵지만, **iter 901~1000 사이 어느 시점에 정책이 RL을 버리는 방향으로 전환됐을 가능성**이 높다.
이는 단순 floor 아래로 떨어진 것이 아니라, **RL을 배제하는 것이 reward 관점에서 유리하다는 정책 발견**이 있었음을 시사한다.

**V28.1에 대한 시사점**:

- iter 800~1000 사이에 `rear_pair_residency_symmetry_penalty`와 `per_leg_band_residency_reward`가 이미 활성화되어 있어야 한다
- V28.1_PLAN.md의 Stage 3(iter 600~800)부터 residency reward를 켜는 것이 맞다

---

### 13.6 단계별 reward 기여 분석

heartbeat TOP5 reward contributor 변화를 추적한다.

**iter 201 (성장 초기)**:

1. forward velocity (leading)
2. survival bonus
3. trot gait reward
4. `per_leg_contact_target_band` (Layer C 진입 확인 ✅)
5. `per_leg_propulsion_target_band`

**iter 600~800 (성공 구간) 추정**:

- target-band 관련 항목들이 TOP reward contributor로 안착
- cooperation reward도 기여 중
- V28 설계 의도가 온전히 작동하는 구간

**iter 1202~2400 (붕괴 고착 후)**:

- `per_leg_contact_target_band`가 TOP5에서 RL 기여분 소실
- FL/FR/RR 3발의 target-band reward만 남음
- `rear_left_contact_collapse` flag가 명시적으로 보고됨
- `single_limb_validity_penalty`가 작동하지만 3발 reward를 이기지 못함

**핵심 관찰**: iter 1202 이후 **reward는 계속 올랐지만 그 구성이 바뀌었다** — 4발 협력 보상에서 3발 최적화 보상으로 전환.
이 전환이 보이지 않았던 이유는 total reward 수치만 보면 증가처럼 보이기 때문이다.

---

### 13.7 Run 재기동 직후 패턴 (run boundary 분석)

V28은 3개 run으로 나뉘어 자동 resume됐다. 각 run boundary 직전/직후를 비교한다.

#### Boundary 1: iter 1000 → 1001

| 측정 | iter 1000 (run 1 마지막) | iter 1001 (run 2 첫 측정) |
| --- | --- | --- |
| reward | 542.3 | 153.7 (-72%) |
| survival | 100.0% | 18.7% (-81%) |
| RL contact | 0.146 | 0.048 (-67%) |
| RL usage | 0.203 | 0.028 (-86%) |

- run 재기동 시 reward와 survival이 급락하는 것은 **checkpoint로부터 새 환경에서 재평가**하기 때문
- 그러나 RL contact도 급락 → 정책 자체가 이미 RL을 포기한 상태임을 재기동 직후 측정이 확인

#### Boundary 2: iter 2001 → 2002 이후

| 측정 | iter 2001 (run 3 첫 측정) | iter 2102 |
| --- | --- | --- |
| reward | 209.0 | 561.3 (+168%) |
| survival | 19.2% | 100.0% |
| RL contact | 0.012 | 0.011 |

- 재기동 직후 생존률 급락 패턴이 반복
- RL은 0.012 → 0.011 → 변화 없음 → 정책이 3발 exploit에 이미 완전 수렴됨

**결론**: run boundary의 survival 급락은 정상적인 checkpoint-reeval 패턴. 그러나 RL contact의 지속적 저하는 정책 레벨의 문제다.

---

### 13.8 V28에서 작동한 것과 작동하지 않은 것 (실측 기반)

#### 작동한 것 (데이터로 확인됨)

| 항목 | 확인 iter | 근거 |
| --- | --- | --- |
| Layer C target-band reward | iter 201 | TOP5 4위 진입, reward +71pts |
| 4발 validity pass | iter 201~1000 | validity = true 유지 |
| cooperation reward | iter 400~900 | 4발 동시 band 진입 구간 유지 |
| all-limb suppression 회피 | 전 구간 | V27.1a와 달리 학습 살아남음 |
| TAP 억제 | iter 201+ | TAP suspicion 사라짐 |

#### 작동하지 않은 것 (데이터로 확인됨)

| 항목 | 실패 iter | 근거 |
| --- | --- | --- |
| RL band residency 유지 | iter 901~1000 | RL contact 0.359 → 0.146 |
| rear pair 내부 대칭 유지 | iter 901 | rear_left_right_usage_diff 0.132 등장 |
| 3발 exploit 억제 | iter 1001+ | RL=0 상태에서 reward 687~734 달성 |
| RL collapse 조기 감지 | iter 901~1000 | 임계 구간에서 경보 없이 급락 |

---

### 13.9 트레이너 종합 의견

이 데이터를 전체적으로 보면 다음과 같은 결론이 도출된다.

#### 1. V28은 설계 검증 측면에서 완전한 성공이었다

iter 201에서 Layer C가 즉시 작동했고, iter 600~800에서 4발 모두 target-band 안에서 협력하는 상태가 실제로 만들어졌다. 이는 이전 V23~V27 계열에서 한 번도 없었던 일이다.

#### 2. 실패의 근원은 "3발이 4발보다 유리한 구조적 조건"이다

iter 901~1000에서 RL을 포기하는 정책 전환이 일어난 이유는 단순히 RL이 약해서가 아니다. **3발 exploit이 4발 유지보다 reward 효율이 높았기 때문**이다. penalty가 이 유인을 이기지 못했다.

#### 3. 임계 구간은 iter 901~1000이다

이 100 iter 동안 RL contact가 0.359 → 0.146으로 급락했고, 이후 run 재기동 후 0.048까지 하락했다. 이 구간을 막지 못하면 이후는 회복이 없다. V28.1의 residency 감시는 이 구간 이전(iter 800~)부터 작동해야 한다.

#### 4. 평균 기반 지표의 맹점이 실제로 발생했다

iter 1202에서 reward는 563으로 높았지만 RL contact는 0.031이었다. 총 reward만 보면 "훈련 잘 됨"처럼 보이지만 실제로는 이미 3발 구조였다. **단일 약세 다리를 감추는 평균 효과**가 실제로 발생했다.

#### 5. V28.1_PLAN.md의 방향은 데이터가 지지한다

- `per_leg_band_residency_reward`: 필요성 확인 (RL이 band에서 서서히 빠짐)
- `rear_pair_residency_symmetry_penalty`: 필요성 확인 (iter 901에서 rear_left_right_usage_diff 등장)
- `cooperation_min_leg_factor`: 필요성 확인 (RL=0에서도 reward 높았음)
- `late_phase_band_exit_penalty`: 필요성 확인 (iter 1000 직전 경보 없이 급락)

#### 6. Stage 3 활성화 시점을 iter 800이 아닌 iter 700~800으로 앞당길 것을 권장한다

iter 901에서 이미 rear_left_right_usage_diff가 등장했다. 이는 iter 800 체크포인트가 좋았던 것이 우연이 아니라, **iter 800에서 간신히 유지되다가 iter 900부터 무너지기 시작한 것**임을 의미한다. residency penalty를 iter 800이 아닌 **iter 700부터** 점진적으로 켜는 것이 더 안전하다.

#### 7. 다음 훈련 착수 조건

- V28.1_PLAN.md 기반으로 reward 함수 수정 완료 후 착수 권장
- 특히 `rear_pair_residency_symmetry_penalty`와 `cooperation_min_leg_factor`는 필수 포함
- iter 900 시점 heartbeat에서 `rear_left_right_usage_diff`가 0.05 이상이면 즉시 경고 필요
