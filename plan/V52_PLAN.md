# V52 Plan: Min Height Termination + Data-Driven Weight Redesign

> 작성: 2026-03-29
> 상태: **완료 — height 안정 성공, front_lift 하락 재발 → leg_lift 구조 문제 발견 → V53으로 이관**

---

## 실험 일지

### 출발점

`V51`은 "낮은 자세를 완전히 금지하지 못한다"는 한계를 남겼다.
그래서 `V52`는 anti-crouch를 더 직접적으로 만드는 쪽으로 이동했다.

### 처음 계획

```text
1. soft height gate는 유지
2. 너무 낮아지면 min_height termination으로 강제 종료
3. 필요하면 symmetry/weight도 같이 재설계
```

### 실제로 한 일

`V52`는 사실 두 단계였다.

```text
V52
- min_height termination 추가
- soft gate 유지

V52.1
- 실측 기반으로 weight 재설계
- front_rear_symmetry 등 보조 조정
```

### 결과

```text
- height 안정 자체는 성공
- 하지만 front_lift 하락은 다시 재발
- 장기적으로 귀뚜라미 보행 고착
```

### 결정적 발견

이 버전에서 처음으로
`leg_lift reward의 평균 구조가 앞다리 사용을 오히려 불리하게 만든다`는
구조적 원인을 문서화했다.

즉 `V52`는 단순 실패가 아니라,
`앞다리를 왜 버리는가`를 수치적으로 설명해낸 버전이었다.

## 1. 왜 Min Height Termination이 필요한가

### V51의 한계

V51 boot-gated w=40에서 초반 front_lift 0.257 달성 → iter 3300에서 0.035로 급락.

```
V51 height gate:
  h > 0.21 → penalty = 0
  h = 0.19 → penalty = -20
  h < 0.17 → penalty = -32

문제: h=0.19~0.21 범위에서 "약간의 penalty를 감수하며 낮은 자세 유지"
→ 크롤링은 차단, 적당히 낮은 자세의 귀뚜라미는 차단 못함
```

### V52 전략: soft gate + hard termination

```
Soft gate (V51 유지): walking reward에 높이 조건부 penalty
Hard termination (V52 추가): h < 0.15m이면 에피소드 강제 종료
  → 크롤링 전략 완전 차단
  → boot-gated: 부팅 시에는 termination OFF
```

---

## 2. V52 변경 사항

### 2.1 min_height_termination

```python
# 0.15m 이하 시 에피소드 종료 (boot-gated)
min_height_termination = 0.15  # meters
boot_gated = True  # gait_gate 해제 전에는 OFF
```

### 2.2 기존 V51 유지

```python
height_walking_gate_weight = 40.0  # boot-gated
boot_standing_initial = 20.0
boot_standing_floor = 10
height_k = 500
```

### 2.3 front_rear_symmetry 추가

```python
front_rear_symmetry_weight = 8.0
# 앞뒤 다리의 움직임 대칭성 보상
```

---

## 3. V52 타임라인 (전체 실측)

```
iter  | stride | f_lift | standing_ht | 비고
  300 |  1.22  | 0.191  |    0.225    | 부팅 직후 — front_lift 최고점
  400 |  2.90  | 0.200  |    0.212    |
  500 |  4.74  | 0.177  |    0.212    |
  600 |  5.17  | 0.189  |    0.189    | height gate 아직 OFF (boot phase)
  700 |  5.87  | 0.171  |    0.204    |
  800 |  6.19  | 0.156  |    0.187    | *** stride peak, front_lift 꺾임 시작 ***
  900 |  6.14  | 0.141  |    0.196    |
 1000 |  6.18  | 0.117  |    0.195    | front_lift 급락 진행
 1200 |  6.24  | 0.092  |    0.193    |
 1500 |  6.39  | 0.066  |    0.198    |
 2000 |  6.46  | 0.063  |    0.192    | 귀뚜라미 고착
 3000 |  5.73  | 0.038  |    0.189    |
 3300 |  5.76  | 0.035  |    0.190    | front_lift 사실상 0
```

**패턴**: iter 800(stride 6 도달) 이후 front_lift 급락. height는 0.19로 안정.
**결론**: height gate + min_height는 **anti-crouch 성공, anti-cricket 실패**.

### 주요 지표 비교

| 지표 | V51 (iter 3300) | V52 (iter 3300) | 변화 |
|------|:---------------:|:---------------:|:----:|
| standing_height | 0.19 | **0.19 (안정)** | height 유지 성공 |
| **front_leg_lift** | 0.035 | **0.035** | **귀뚜라미 재발** |

height 유지에는 성공했으나, **front_leg_lift는 여전히 하락**.
min_height termination이 크롤링은 차단하지만 귀뚜라미는 다른 원인.

---

## 4. 핵심 데이터 분석: 앞다리 포기의 경제학

### 전체 reward delta (iter 600 vs iter 3300)

V52에서 iter 600 (앞다리 사용) → iter 3300 (앞다리 포기)의 **실측 reward 변화**:

#### 앞다리 포기로 인한 이득 (penalty 감소) — 상위 10개

| reward | iter600 | iter3300 | delta | 원인 |
|--------|---------|----------|-------|------|
| **stance_width_penalty** | -18.43 | -11.21 | **+7.23** | 앞다리 안 벌려서 |
| rear_left_right_prop_diff | -5.66 | -1.46 | +4.20 | 뒷다리만 쓰니 좌우 차이 감소 |
| joint_vel_l2 | -10.45 | -6.45 | +4.00 | 움직이는 관절 수 감소 |
| dof_acc_l2 | -6.72 | -3.01 | +3.72 | 가속하는 관절 수 감소 |
| front_lr_prop_diff | -4.62 | -1.08 | +3.55 | 앞다리 안 쓰니 차이 자체 없음 |
| action_rate_l2 | -6.24 | -3.17 | +3.07 | action 변화 감소 |
| foot_extension | -11.95 | -9.40 | +2.55 | 발 뻗기 줄어듦 |
| rear_pair_contact_diff | -4.86 | -2.45 | +2.41 | 뒷다리 접지 패턴 안정 |
| contact_residency | +0.00 | +2.10 | +2.10 | 접지 시간 안정화 |
| ang_vel_xy_l2 | -3.80 | -1.93 | +1.87 | pitch/roll 진동 감소 |
| **이득 합계** | | | **+34.70** | |

#### 앞다리 포기로 인한 손실 (walking reward 감소) — 상위 10개

| reward | iter600 | iter3300 | delta | 원인 |
|--------|---------|----------|-------|------|
| **late_phase_band_exit** | -1.96 | -15.28 | **-15.28** | band 구간 이탈 증가 |
| leg_lift | +10.13 | +5.16 | -4.97 | 전체 다리 들기 감소 |
| rear_alternation | +6.75 | +3.39 | -3.36 | 뒷다리 교대 약화 |
| rear_joint_velocity | +11.77 | +9.26 | -2.50 | 뒷다리 속도 감소 |
| four_limb_cooperation | +5.35 | +3.05 | -2.30 | 4족 협동 감소 |
| alive_bonus | +9.98 | +7.91 | -2.07 | ep_len 감소 |
| per_leg_contact_band | +14.91 | +13.11 | -1.80 | 접지 band 이탈 |
| stance_propulsion | +5.76 | +3.95 | -1.81 | 추진력 감소 |
| per_leg_propulsion_band | +9.90 | +8.24 | -1.65 | 추진 band 이탈 |
| forward_vel_bootstrap | +5.35 | +3.97 | -1.38 | 전진 속도 감소 |
| **손실 합계** | | | **-28.94** | |

#### 순이익 계산

```
앞다리 포기 이득: +34.70/step (주로 penalty 감소)
앞다리 포기 손실: -28.94/step (주로 walking reward 감소)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
순이익: +5.76/step → 앞다리 포기가 합리적 전략
```

**최대 단일 요인: stance_width_penalty (+7.23)** — 이것 하나가 순이익(+5.76)보다 큼.

### 추정 vs 실측의 교훈

tracking weight 설계 시 앞다리 engagement cost를 **1.3/step으로 추정** → **실측 14.36/step (11배 과소추정)**.
이로 인해 track_ang weight=6.0을 제안했으나, 실측 breakeven은 14.3 → **제안값이 breakeven에 한참 못 미침**.

**교훈 #29**: 실측 가능한 데이터가 있으면 반드시 데이터부터 분석. 추정으로 파라미터 설계하지 말 것.

---

## 5. V52.1: 실측 기반 Weight 재설계

### 설계 원리

실측 데이터에서 앞다리 포기의 순이익 +5.76을 **역전**시키는 weight 조정.

### Raw Score 분석 (Episode_Reward / weight)

| reward | raw@600 | raw@3300 | diff |
|--------|---------|---------|------|
| stance_width_penalty (w=-3.0) | 6.143 | 3.735 | -2.408 |
| four_limb_cooperation (w=8.0) | 0.668 | 0.381 | -0.287 |
| leg_lift (w=15.0) | 0.675 | 0.344 | -0.331 |

### 5개 시나리오 시뮬레이션 결과

```
A: sw=-1.5, flc=16, ll=20 → net=-1.80 (마진 31%) ← 채택
B: sw=-1.5, flc=16, ll=25 → net=-3.46 (마진 60%)
C: sw=-2.0, flc=16, ll=20 → net=-0.60 (마진 10%, 불안정)
D: sw=-2.0, flc=20, ll=20 → net=-1.74 (마진 30%)
E: sw=-1.5, flc=20, ll=25 → net=-4.60 (마진 80%, 과도)
```

**시나리오 A 채택**: 보수적이면서 충분한 마진 (31%).

### 변경 (iter 600에서 resume)

| 항목 | V52 | V52.1 | 근거 |
|------|:---:|:-----:|------|
| stance_width_penalty | -3.0 | **-1.5** | 최대 단일 요인(+7.23) 절반화 → +3.61로 감소 |
| four_limb_cooperation | 8.0 | **16.0** | 4족 협동 2배 강화 |
| leg_lift | 15.0 | **20.0** | 다리 들기 33% 증가 |

### 예상 효과 (수치 검증)

```
V52 순이익: +5.76
  stance_width 절반: -3.62 (7.23 → 3.61)
  flc 2배: -2.50 추가 (4족 보상 증가)
  leg_lift 33%: -1.64 추가 (들기 보상 증가)
━━━━━━━━━━━━━━━━━━━━━━━━━━━
V52.1 예상 net: +5.76 - 7.76 = -1.80/step
→ 앞다리 사용이 유리 (마진 31%)
```

### Resume 시 curriculum snapshot 충돌 문제

weight를 바꾸면서 resume하면 old snapshot이 new weight를 덮어씀.
해결: version 비교 자동 판단:

```
V52 → V52.1 resume: version 다름 → snapshot 스킵 → deterministic recompute (새 weight 적용)
V52.1 → V52.1 resume: version 같음 → snapshot 복사 (정상 resume)
```

---

## 6. V52.1 결과 + leg_lift 구조 문제 발견

### V52.1 타임라인 (iter 650~1000, 매 50)

```
iter  | stride | f_lift | r_lift | fr_sym | 비고
  650 |  0.50  | 0.177  | 0.988  |  2.50  | resume 직후
  700 |  1.27  | 0.146  | 1.473  |  1.85  |
  750 |  2.00  | 0.131  | 1.455  |  1.71  |
  800 |  2.80  | 0.133  | 1.393  |  1.85  | front_lift 안정화 시작
  850 |  3.79  | 0.136  | 1.255  |  2.22  | *** front_lift 유지! ***
  900 |  5.05  | 0.132  | 1.124  |  2.57  | stride 5+ 돌파
  950 |  5.79  | 0.126  | 1.052  |  2.84  |
 1000 |  6.01  | 0.118  | 0.956  |  3.12  | stride 6 도달, front_lift 하락 시작
```

V52에서 iter 800~1000은 front_lift 0.16→0.12 급락 구간이었는데,
V52.1은 0.13으로 유지 → **weight 변경 효과 있음. 하지만 장기적 하락은 동일.**

### iter 1172 결과

| 지표 | V52 (iter 3300) | V52.1 (iter 1172) | 변화 |
|------|:---------------:|:-----------------:|:----:|
| front_leg_lift | 0.035 | **0.091** | 2.6배 개선 |
| stride | - | 진행 중 | - |

V52 대비 2.6배 개선이지만 **여전히 하락 추세** — weight 조정으로는 부족.

### leg_lift per-leg breakdown (V52.1 iter 1000)

```
leg_lift_fl:  0.088  (Front Left)
leg_lift_fr:  0.061  (Front Right)
leg_lift_rl:  0.716  (Rear Left)   → 앞다리의 8배
leg_lift_rr:  0.565  (Rear Right)  → 앞다리의 7배
```

### leg_lift_reward 구조 문제 발견

`leg_lift_reward`는 **스윙 다리의 평균**으로 계산:

```python
# rewards.py 내부
return swing_reward.sum(dim=1) / num_swing
```

이 평균 구조가 만드는 **perverse incentive** 계산:

```
Case A: 뒷다리만 스윙 (trot 중 2발)
  avg(0.72, 0.57) = 0.645 × w20 = 12.9/step

Case B: 4발 모두 스윙 (trot 중 4발)
  avg(0.09, 0.06, 0.72, 0.57) = 0.36 × w20 = 7.2/step

차이: 12.9 - 7.2 = 5.7/step
→ 앞다리를 추가하면 점수가 5.7 낮아짐
→ 앞다리 사용 = 사실상 -5.7/step penalty
```

**교훈 #30**: reward의 평균 기반 함수는 다수파(뒷다리)가 점수를 지배 → 소수파(앞다리) 사용을 penalty화.

### Tracking weight 추정 실패

tracking weight 설계 시 앞다리 engagement cost를 **1.3/step으로 추정** → **실측 14.36/step (11배 과소추정)**.
이로 인해 track_ang weight=6.0을 제안했으나, 실측 breakeven은 14.3 → **제안값이 breakeven에 한참 못 미침**.

---

## 7. Infrastructure 개선

### 7.1 launch_training 중복 실행 방지

```python
# launch.lock 파일 기반 lock
# /resume 600 이 2회 처리되어 2개 run 디렉토리 생성된 문제 수정
# 실행 시 lock 생성, 완료/실패 시 해제
```

### 7.2 Version 기반 Curriculum Snapshot 판단

```python
# resume 시 source version과 current version 비교
# source != current → snapshot 스킵 → deterministic recompute (새 weight 적용)
# source == current → snapshot 복사 (정상 resume)
```

### 7.3 listen.cmd PID 체크

```
# listen.cmd 시작 시 기존 프로세스 감지 후 kill 확인
```

### 7.4 listen.cmd CRLF 문제

```
# Write 도구가 LF로 저장 → CMD 파싱 실패
# 해결: sed 변환 필요 (LF → CRLF)
```

### 7.5 stall detection /stop 후 비활성화

```
# /stop 후 stall detection이 auto-resume 트리거하는 문제
# 의도적 stop에서는 stall detection 비활성화
```

---

## 8. 핵심 교훈

| # | 교훈 | 출처 |
|---|------|------|
| 29 | 파라미터 설계 시 추정 금지, 실측 데이터 먼저 분석 | V52.1 앞다리 비용 분석 |
| 30 | reward의 평균 기반 함수는 다수파가 점수를 지배 → 소수파 사용을 penalty화 | V52.1 leg_lift 4발 평균 |
| 31 | .cmd 파일은 CRLF 필수, Write 도구 후 sed 변환 | listen.cmd 파싱 실패 |
| 32 | launch_training 중복 실행 방지 lock 필요 | V52.1 /resume 2회 처리 |
| 33 | stall detection은 /stop 후 비활성화 필수 (의도적 stop != crash) | V52.1 auto-resume 오작동 |

---

## 9. 판정 기준 (사후 평가)

| 시점 | 기준 | V52 | V52.1 | 판정 |
|------|------|:---:|:-----:|:----:|
| iter 600 | height 안정 | 0.19 OK | 0.19 OK | 성공 |
| iter 1200 | front_lift > 0.10 | 0.035 NG | 0.091 NG | **실패** |
| 전체 | 귀뚜라미 해결 | 실패 | 개선만 | **실패** |

height gate + termination으로 크롤링 차단 성공, 그러나 **귀뚜라미의 근본 원인은 leg_lift_reward의 평균 구조**.

---

## 10. 다음 단계

leg_lift_reward의 4발 평균이 앞다리 사용을 penalty화 → V53에서 **앞다리 전용 front_leg_lift_reward** 추가.

---

## 11. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | min_height_termination 0.15m (boot-gated), front_rear_symmetry w=8 |
| `env_cfg.py` | V52.1: stance_width -3→-1.5, flc 8→16, leg_lift 15→20 |
| `launch_training.py` | launch.lock 중복 실행 방지 |
| `curriculum.py` | version 기반 curriculum snapshot 판단 |
| `listen.cmd` | PID 체크 + kill 확인 |
