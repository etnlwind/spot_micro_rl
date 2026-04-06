# V60 실험 보고서: From-Scratch 4족 보행 학습

> 작성/갱신: 2026-04-07
> 현재 코드 truth 기준 버전: `V60.H`
> 기반: V59.B 서기 마스터 → V59.D 보행 전환 실패 → V60 from-scratch

---

## 배경

V59.B에서 SpotMicro의 서기 학습에 완전 수렴했다 (ep_len 1000, 4발 접지 99.9%, 수평 99.8%).
이 서기 정책을 기반으로 보행을 가르치려 했으나(V59.D), **정적 균형(서기)과 동적 균형(보행)은 완전히 다른 스킬**이라는 것이 확인되었다. 서기 정책이 너무 강하게 수렴해 보행으로 전환이 불가능했고, curriculum 파일이 env_cfg를 덮어쓰는 버그도 발견되었다.

따라서 V60에서는 **from-scratch로 보행을 처음부터 학습**하기로 결정했다.

---

## 쉽게 보는 V60 전체 흐름

이 문서는 숫자와 reward 이름이 많아서, 먼저 **왜 이런 버전들이 생겼는지**를 쉬운 말로 정리한다.

### 출발점
- V59.B에서 이미 "잘 서는 정책"은 만들었다.
- 하지만 그 정책은 **정적으로 버티는 능력**이지, **발을 움직이며 균형을 잡는 능력**은 아니었다.
- 그래서 V59에서 바로 걷기로 넘기려 했던 시도(V59.D)는 실패했고, 결국 **V60은 from-scratch 보행 학습**으로 새로 시작했다.

### V60에서 실제로 부딪힌 문제
- 처음에는 "살아남고 전진하는 것" 자체는 금방 배웠다.
- 하지만 RL은 가장 쉬운 해를 찾아가기 때문에, 처음엔 **오른뒤(RR)만 거의 안 쓰는 비대칭 exploit**이 생겼다.
- 그 exploit을 penalty로 잡았더니 이번에는 **네 발 다 거의 붙어 있는 정적 접지 해**로 갔다.
- 정적 해를 깨려고 gait incentive를 올리면 **앞다리만 흔들거나**, 반대로 **뒷다리만 흔드는** 새 exploit이 생겼다.
- front/rear 균형 penalty를 넣자 네 다리 swing은 어느 정도 고르게 되었지만, 이번엔 **대각선 교대 패턴**은 끝내 생기지 않았다.

### 그래서 V60이 말해준 것
- "발을 드는 것"과 "좋은 보행 패턴"은 전혀 다르다.
- "균형 있게 흔드는 것"과 "대각선으로 교대하는 것"도 전혀 다르다.
- 즉 V60의 핵심 교훈은:
  1. exploit 제거
  2. 정적 해 제거
  3. front/rear 균형 확보
  4. 그 다음에야 diagonal alternation
  순서로 가야 한다는 점이다.

### 버전별 한 줄 요약

| 버전 | 왜 만들었나 | 뭘 보려고 했나 | 실제 결과 | 왜 다음으로 갔나 |
|------|-------------|----------------|-----------|------------------|
| V60.A | V59 전환 실패 후, 보행을 처음부터 다시 배우게 하려고 | 살아남으면서 전진이 되는지 | 생존/추종은 성공, RR 비사용 exploit 발생 | 1발 exploit을 직접 막아야 했음 |
| V60.B | RR 비사용 exploit을 약한 penalty로 먼저 눌러보려고 | 약한 penalty로도 교정이 되는지 | 거의 안 바뀜 | penalty가 너무 약했음 |
| V60.C | RR exploit을 강하게 끊으려고 | per-leg penalty를 세게 주면 즉시 교정되는지 | RR exploit은 즉시 교정, 대신 4발 정적 접지 | 비대칭은 고쳤지만 gait는 사라짐 |
| V60.D | 정적 접지를 깨기 위해 gait incentive를 전반적으로 올리려고 | 전역 gait reward가 4발 swing을 여는지 | 앞다리만 swing, 뒷다리 고착 | 이미 잘 움직이는 쪽만 더 강화됨 |
| V60.E | 뒷다리를 직접 들어보게 만들려고 | rear 전용 보상이 rear swing을 여는지 | 거의 반응 없음 | rear 보상만 더한다고 정적 해가 깨지지 않음 |
| V60.F | 정적 해 자체를 싸지 않게 만들려고 | rear 비접촉 시간이 실제로 생기는지 | rear swing 폭발, front 고착 | 한쪽만 유도하면 반대쪽이 고착 |
| V60.G | front/rear 균형을 맞추려고 | 4발 swing을 고르게 만들 수 있는지 | 균형은 개선, diagonal은 0 | 균형과 교대는 별개라는 게 드러남 |
| V60.H | diagonal alternation을 직접 유도하려고 | 대각선 교대가 실제로 생기는지 | 진행 중 | 500 iter에서 판정 예정 |

### 체크포인트를 왜 `model_24100.pt`로 잡았나

V60.H는 V60.G 런의 최신이 아니라 **중간 체크포인트 `model_24100.pt`**에서 resume한다.

- `23100` 부근: 아직 front/rear 분포가 덜 풀려 있었다.
- `24100` 부근: 네 다리 swing이 충분히 분산되었고, tracking도 아직 크게 무너지지 않았다. **"다음 구조를 얹기 가장 좋은 균형점"**.
- `25100` 부근: 네 다리 swing은 더 많아졌지만, tracking이 더 떨어지고, diagonal은 끝까지 0이었다.

---

## 누적 iter 요약

| 버전 | 구간 | 추가 iter | 유형 |
|------|------|----------|------|
| V60.A | 0→8300 | 8300 | from-scratch |
| V60.B | 8300→12600 | 4300 | resume |
| V60.C | 11300→13000 | 1700 | resume (B 중간에서) |
| V60.D | 13000→15800 | 2800 | resume |
| V60.E | 15800→16600 | 800 | resume |
| V60.F | 16600→17600 | 1000 | resume |
| V60.G | 17600→25100 | 7500 | resume |
| V60.H | 24100→? | 진행 중 | resume (G 중간에서) |
| **합계** | | **~26400** | |

---

## 실험에서 보는 핵심 지표와 해석법

이 문서에는 지표 이름이 반복해서 나온다. 처음 보는 사람도 바로 읽을 수 있도록, 각 지표가 실제로 무엇을 뜻하는지 적어둔다.

### 생존/안정성 지표
- `ep_len`
  - 한 episode가 얼마나 오래 살아남았는지
  - `1000`이면 사실상 full episode 생존
- `time_out`
  - 넘어지거나 강제 종료가 아니라 **끝까지 살아남아 종료**된 비율
- `base_contact`
  - 몸통이 바닥에 닿은 비율
- `bad_orientation`
  - 자세가 너무 무너져 종료된 비율

즉:
- `ep_len`과 `time_out`이 높고
- `base_contact`, `bad_orientation`이 낮으면
기본 안정성은 좋다고 본다.

### 움직임/보행 지표
- `contact_ratio_*`
  - 각 발이 바닥에 붙어 있던 비율
  - 너무 높으면 그 발은 거의 안 들고 있는 것
  - 너무 낮으면 그 발은 거의 안 쓰고 공중에 두는 것
- `swing_time_*`
  - 각 발이 공중에 있던 비율
  - `contact_ratio`와 같이 보면 어떤 다리가 고착됐는지 바로 보인다
- `feet_air_time`
  - 전체적으로 발을 들고 있는 패턴이 얼마나 생기는지 보는 지표
- `rear_air_time`
  - 뒷다리 쪽 비접촉 시간을 따로 보던 시기의 보조 지표
- `foot_clearance`, `rear_clearance`
  - 발을 들긴 드는데, 실제로 "조금이라도 높이" 드는지 보는 지표

즉:
- `contact_ratio ≈ 1.0`이면 정적 접지에 가깝고
- `swing_time`이 한 다리만 높으면 비대칭 exploit 가능성이 높다
- 네 다리 swing이 모두 0이 아니면, 최소한 정적 해는 어느 정도 깨졌다고 본다

### 패턴/구조 지표
- `diagonal_coupling_raw`
  - 단순히 발을 드는지를 넘어서,
  - **대각선 pair가 교대하는 구조**가 생겼는지를 본다
- `fr_swing_balance`
  - 앞다리 평균 swing과 뒷다리 평균 swing의 차이
- `fr_contact_balance`
  - 앞다리 평균 contact와 뒷다리 평균 contact의 차이

즉:
- `fr_* balance`는 "얼마나 균형적인가"
- `diagonal_coupling_raw`는 "그 균형이 실제 교대 구조로 이어졌는가"
를 본다고 이해하면 된다.

### 추종 성능 지표
- `track_lin_vel_xy_exp`
  - 전진 속도 명령을 얼마나 잘 따라가는지
- `track_ang_vel_z_exp`
  - yaw/회전 명령을 얼마나 잘 따라가는지
- `forward_velocity`
  - 실제로 앞으로 나가고 있는지 직접 보는 보조 reward

즉:
- 보행 구조가 좋아도 `track_lin`이 크게 무너지면 실용성이 떨어진다
- 반대로 `track_lin`이 높아도 `diagonal_coupling=0`이면 좋은 gait라고 보긴 어렵다

### 버전 판정 원칙
각 버전은 보통 아래 순서로 본다.

1. **안정성은 유지되는가**
   - `ep_len`, `time_out`, `base_contact`
2. **이전 버전의 병변이 줄었는가**
   - 예: RR 비사용, front 고착, rear 고착
3. **이번 버전이 만들고 싶던 구조가 생겼는가**
   - 예: rear swing, 4발 균형 swing, diagonal coupling
4. **새 exploit가 생기지는 않았는가**
   - 한쪽만 들기, 정적 접지 회귀, tracking 붕괴 등

즉 이 문서에서 "성공"은
무조건 최종 보행 완성을 뜻하지 않는다.
그 단계가 **의도한 구조 변화를 만들었는가**를 먼저 본다.

---

## V59.D: 서기→보행 전환 (실패)

**목적:** V59.B에서 학습한 서기 정책(model_2700)을 기반으로, reward만 바꿔서 보행으로 전환할 수 있는지 확인.

**설정:**
- Resume from: `2026-04-05_17-31-45/model_2700.pt`
- 변경: standing_envs=0→0, vel_x=(0, 0.2), feet_air_time 추가, feet_on_ground=0

**기대:** 서기를 이미 아는 정책이 발을 조금씩 떼기 시작하면서 보행으로 전환.

**결과:** 서기 정책이 너무 강하게 수렴해 있어서, 보행 reward를 줘도 발을 떼지 않음. 또한 **curriculum 파일이 env_cfg reward weight를 덮어쓰는 버그** 발견 — env_cfg에서 feet_on_ground=0으로 설정해도 curriculum이 6.0으로 복원하고 있었음.

**버그 수정:** `restore_curriculum_snapshot()`에 버전 변경 감지 로직 추가. 저장된 weight와 현재 env_cfg weight가 다르면 reward/termination 복원을 자동 skip.

**교훈:** 정적 균형(서기)과 동적 균형(보행)은 완전히 다른 스킬. resume 전환보다 from-scratch가 맞다.

**판정:** 실패 → V60 from-scratch 결정.

---

## V60.A: From-Scratch 보행 학습

**Run:** `2026-04-05_21-12-36` | **iter 0→8300 (8300 iter, from-scratch)**

### 목적
서기 없이 처음부터 동적 균형과 보행을 동시에 학습시킨다.

### 설정

**Commands:**
- action_scale=0.25 (Isaac Lab 표준)
- standing_envs=0.2 (20% 서기, 80% 보행)
- vel_x=(0.0, 0.3), ang_vel_z=(-0.3, 0.3)

**Terminations:**
- feet_lifted=None (보행 자유)
- base_contact, bad_orientation(30deg, 3s grace), min_height(0.14m)

**Rewards:**
| reward | weight | 설명 |
|--------|--------|------|
| track_lin_vel_xy_exp | +5.0 (std=0.15) | 속도 추종 핵심 |
| forward_velocity | +3.0 | 전진 직접 보상 |
| flat_orientation_bonus | +3.0 | 수평 유지 |
| feet_air_time | +2.0 (thr=0.3) | 발 들기 유도 |
| standing_height | +2.0 (target=0.205m) | 높이 유지 |
| track_ang_vel_z_exp | +2.0 (std=0.25) | 회전 추종 |
| flat_orientation_l2 | -2.0 | 수평 penalty |
| lin_vel_z_l2 | -2.0 | 수직 진동 억제 |
| contact_foot_velocity | -1.0 | 발 미끄럼 방지 |
| ang_vel_xy_l2 | -1.0 | 롤/피치 억제 |
| joint_default_pos | -1.0 | 관절 초기값 유지 |
| action_rate_l2 | -0.05 | 부드러운 동작 |
| dof_torques_l2 | -0.0001 | 토크 절약 |
| feet_on_ground | 0.0 | 비활성 |
| feet_lift_penalty | 0.0 | 비활성 |

### 기대값
- 500 iter 내 생존 학습
- 1000 iter 내 전진 시작
- 3000 iter 내 발 들기 시작
- diagonal_coupling > 0 (trot 패턴 발현)

### 실제 결과 (iter 8100 기준)

| 지표 | 값 | 판정 |
|------|-----|------|
| ep_len | 1000/1000 | **성공** (100% 생존) |
| track_lin_vel_xy_exp | 4.80/5.0 (96%) | **성공** |
| forward_velocity | 1.29 | 약간 전진 |
| cr_FL / cr_FR / cr_RL / cr_RR | 0.888 / 0.938 / 0.935 / **0.020** | **문제: RR 비사용** |
| sw_FL / sw_FR / sw_RL / sw_RR | 0.112 / 0.062 / 0.065 / **0.980** | **문제: RR만 공중** |
| clearance_RR | 34mm (나머지 1~2mm) | RR만 높이 들림 |
| diagonal_coupling_raw | 0.000 | **실패** |
| entropy | -11.4 | 탐색 완전 종료 |

### 분석
생존과 tracking은 우수하지만, RR(오른쪽 뒷발) 하나만 98% 공중에 띄우고 나머지 3발로 서있는 **비대칭 exploit** 발생. `feet_air_time`이 1발만 들어도 양수 보상을 주므로, 가장 비용이 적은 "1발 들기"를 최적해로 찾은 것. entropy -11.4로 정책이 완전히 수렴하여 자체 탈출 불가.

### 교훈
- feet_air_time이 1발만 들어도 보상 → 최소 비용 exploit 발생
- 보행 패턴 없이 "1발 흔들기"가 충분한 reward를 줌

### 판정
**부분 성공** — 생존+tracking 우수, 보행 패턴 실패

### 다음 단계
RR 비대칭 exploit을 per-leg penalty로 직접 교정 → V60.B

---

## V60.B: 비대칭 Penalty 추가

**Run:** `2026-04-06_10-51-10` | **iter 8300→12600 (4300 iter, V60.A resume)**

### 목적
per-leg contact_min과 excess_swing penalty를 추가하여 RR 비사용 exploit을 교정한다.

### V60.A 대비 변경점
| 항목 | V60.A | V60.B | 변경 이유 |
|------|-------|-------|----------|
| per_leg_contact_min | 없음 | **-3.0** (min_ratio=0.15) | 한 다리 비사용 벌칙 (신규) |
| per_leg_excess_swing | 없음 | **-3.0** (max_swing=0.70) | 영구 공중부양 벌칙 (신규) |
| feet_air_time | +2.0 (thr=0.3) | **+4.0** (thr=0.1) | threshold 낮춰 4발 유도 |
| forward_velocity | +3.0 | **+5.0** | 전진 강화 |
| foot_clearance | 없음 | **+2.0** | 발 높이 보상 (신규) |
| standing_envs | 0.2 | **0.1** | 보행 비중 증가 |

### 기대값
- 500 iter 내 cr_RR이 0.15 이상으로 회복
- penalty가 3발 보행 이득을 압도

### 실제 결과 (iter 11372 기준, 3000 iter 훈련)

| 지표 | V60.A | V60.B | 변화 |
|------|-------|-------|------|
| cr_RR | 0.020 | **0.033** | +0.013 (미미) |
| sw_RR | 0.980 | 0.967 | -0.013 (미미) |
| per_leg_contact_min | - | -0.44/step | 작동 중이지만 약함 |
| per_leg_excess_swing | - | -0.96/step | 작동 중이지만 약함 |
| penalty 합산 | - | **-1.40/step** | vs 양수 ~15/step |
| ep_len | 1000 | 1000 | 유지 |

### 분석
penalty가 작동하고 있지만 양수 reward budget(~15/step)에 비해 크기가 절대적으로 부족. 3발 보행으로 얻는 이득이 penalty를 상쇄. 선형 외삽 시 cr_RR=0.15 도달까지 **5만+ iter** 필요.

**사후 수치 검증:** penalty -3.0 × raw 0.117 = -0.35/step. 3발로 얻는 추가 이득 ~+2/step. penalty가 이득의 **1/6** 수준.

### 교훈
- penalty weight는 양수 reward budget 대비 수치 검증 필수
- -3.0은 양수 15 대비 한참 부족
- 당시에는 penalty를 너무 보수적으로 잡았고, 그게 실수였다. 실제로는 `-8~-12` 수준의 강한 penalty가 필요했다.

### 판정
**no-go** — 4300 iter에도 cr_RR 0.033

### 다음 단계
검증된 필요 범위(`-8~-12`)까지 penalty를 대폭 상향 → V60.C

---

## V60.C: Penalty 강력 상향 — RR 교정 성공

**Run:** `2026-04-06_16-46-38` | **iter 11300→13000 (1700 iter, V60.B resume)**

### 목적
충분히 강한 수준인 `-10`으로 penalty를 상향하고, rear pair balance penalty를 추가하여 RR exploit을 즉시 교정한다.

### V60.B 대비 변경점
| 항목 | V60.B | V60.C | 변경 이유 |
|------|-------|-------|----------|
| per_leg_contact_min | -3.0 | **-10.0** | 3.3x 상향 |
| per_leg_excess_swing | -3.0 | **-10.0** | 3.3x 상향 |
| rear_lr_balance | 없음 | **-5.0** | RL/RR pair 불균형 표적 (신규) |

### 사전 수치 검증
| penalty | weight | 예상 raw | per-step |
|---------|--------|---------|----------|
| per_leg_contact_min | -10 | 0.117 | -1.17 |
| per_leg_excess_swing | -10 | 0.267 | -2.67 |
| rear_lr_balance | -5 | 0.942 | -4.71 |
| **합계** | | | **-8.55** (vs 양수 ~15) |

### 기대값
- 500 iter 내 cr_RR > 0.15
- penalty가 3발 보행 이득과 경쟁 가능

### 실제 결과 (iter 12143 기준)

| 지표 | V60.B | V60.C | 변화 |
|------|-------|-------|------|
| cr_RR | 0.033 | **0.997** | **+0.964 (완전 교정!)** |
| sw_RR | 0.967 | 0.003 | -0.964 |
| cr_FL / cr_FR / cr_RL | 0.91/0.96/0.98 | 0.96/0.98/1.00 | 전부 접지 |
| diagonal_coupling | 0.000 | 0.000 | 변화 없음 |
| ep_len | 1000 | 1000 | 유지 |
| mean_reward | 275 | 268 | 소폭 하락 (penalty 비용) |

**교정 속도:** ~100 iter 만에 cr_RR 0.033→0.997 달성. resume 직후 ep_len 36 폭락 후 즉시 회복.

### 분석
RR exploit **완전 교정 성공**. 하지만 새 문제 발생: 4발 모두 99%+ 접지 (swing 2~4%). 로봇이 "발을 안 드는 게 가장 안전"이라는 새 local optimum을 찾음. diagonal_coupling=0 유지.

### 교훈
- penalty weight는 reward budget과 경쟁 가능한 수준(`-8~-12`)까지 올려야 함
- -3.0 → -10.0 상향이 즉각 효과 (100 iter)
- 비대칭 교정 후 정적 접지 해로 전환하는 패턴 확인

### 판정
**Go** — RR 교정 성공. 새 문제: 정적 접지 해.

### 다음 단계
정적 접지 해를 깨기 위한 gait incentive 강화 → V60.D

---

## V60.D: Gait Incentive 강화 — 앞다리만 반응

**Run:** `2026-04-06_19-14-18` | **iter 13000→15800 (2800 iter, V60.C resume)**

### 목적
static bias를 약화하고 gait incentive를 대폭 강화하여 4발 모두 swing을 시작하게 한다.

### V60.C 대비 변경점
| 항목 | V60.C | V60.D | 변경 이유 |
|------|-------|-------|----------|
| feet_air_time | +4.0 | **+8.0** | 2x 상향, 발 들기 강력 유도 |
| foot_clearance | +2.0 | **+6.0** | 3x 상향, 높이 보상 |
| contact_foot_velocity | -1.0 | **-0.3** | static bias 약화 |
| joint_default_pos | -0.5 | **-0.2** | 관절 자유도 확대 |

### 기대값
- 200 iter 내 4발 모두 contact_ratio < 0.99
- 전체 swing_time 의미 있게 증가
- diagonal_coupling > 0

### 실제 결과 (iter 15800 기준, 2800 iter)

| 지표 | V60.C | V60.D | 변화 |
|------|-------|-------|------|
| sw_FL | 0.040 | **0.218** | +445% (대폭 증가) |
| sw_FR | 0.022 | **0.338** | +1436% (폭발적 증가) |
| sw_RL | 0.002 | 0.005 | +150% (미미) |
| sw_RR | 0.003 | 0.006 | +100% (미미) |
| clearance_FL / clearance_FR | 1.4mm / 1.1mm | **4.6mm / 8.1mm** | 상승 |
| clearance_RL / clearance_RR | 0.03mm / 0.04mm | 0.04mm / 0.05mm | 변화 없음 |
| diagonal_coupling | 0.000 | 0.000 | |
| penalty 합산 | -0.1 | **-2.41** (증가 중) | |

### 분석
gait incentive가 **이미 swing이 나오는 앞다리만** 더 강화. FR이 FL의 1.5~2배로 과부상 발생. 뒷다리는 접지 상태에서 propulsion을 하므로 들 이유가 없음. penalty가 -2.41까지 증가했지만 FR의 swing은 수렴하지 않음.

### 교훈
- 전역 gait incentive는 이미 움직이는 쪽만 강화
- 안 움직이는 쪽(뒷다리)에는 gradient가 도달하지 않음
- 뒷다리 전용 유도가 필요

### 판정
**no-go** — 앞다리만 swing, 뒷다리 완전 고착

### 다음 단계
rear 전용 clearance 보상 추가 → V60.E

---

## V60.E: Rear 전용 보상 추가 — 효과 없음

**Run:** `2026-04-06_21-27-33` | **iter 15800→16600 (800 iter, V60.D resume)**

### 목적
rear 전용 clearance 보상(+6)을 추가하고 front를 약화하여 뒷다리 swing을 직접 유도한다.

### V60.D 대비 변경점
| 항목 | V60.D | V60.E | 변경 이유 |
|------|-------|-------|----------|
| rear_foot_clearance | 없음 | **+6.0** | rear 전용 유도 (신규) |
| foot_clearance | +6.0 | **+3.0** | front 약화 |
| contact_foot_velocity | -0.3 | **0.0** | static bias 완전 제거 |
| joint_default_pos | -0.2 | **-0.1** | 추가 자유도 |
| standing_height | 2.0 | **1.0** | static bias 약화 |
| per_leg_contact/swing | -10.0 | **-6.0** | 과도 억제 완화 |
| ang_vel_z | (-0.3, 0.3) | **(0, 0)** | yaw OFF |
| standing_envs | 0.1 | **0.0** | 100% 보행 |
| lin_vel_x min | 0.0 | **0.05** | 최소 전진 |

### 기대값
- rear_clearance +6이 뒷다리 swing 신호를 직접 줌
- 500 iter 내 sw_RL/RR > 0.03

### 실제 결과 (iter 16600 기준, 800 iter)

| 지표 | V60.D | V60.E | 변화 |
|------|-------|-------|------|
| sw_RL | 0.005 | **0.007** | +0.002 (미미) |
| sw_RR | 0.006 | **0.013** | +0.007 (미미) |
| rear_clearance reward | - | 0.029 | 신호 극미 |
| clearance_RL/RR | 0.04mm | 0.04mm | 변화 없음 |
| prop_RL/RR | - | 0.39/0.35 | 접지 추진 충분 |

### 분석
뒷다리가 접지 상태에서도 propulsion 0.35~0.39로 충분한 추진력을 냄. "뒷다리를 들지 않아도 전진이 되고 reward 손실도 없다"는 local optimum. rear_clearance +6이 추가됐지만 뒷다리가 swing을 시작하지 않으면 gradient가 0이라 학습 신호 자체가 형성 안 됨.

### 교훈
- rear 보상을 더 얹는 것만으로는 부족
- 정적 접지 해 자체가 여전히 더 싸다
- "더 밀기"가 아니라 "정적 해를 이득 아니게 만들기"로 전환 필요

### 판정
**no-go** — 800 iter 플라토

### 다음 단계
"rear를 더 밀자"가 아니라 "정적 해가 더 이상 싸지 않게" → V60.F

---

## V60.F: 정적 해 구조 전환 — 뒷다리 폭발, 앞다리 고착

**Run:** `2026-04-06_22-30-44` | **iter 16600→17600 (1000 iter, V60.E resume)**

### 목적
정적 접지로는 충분한 reward를 받지 못하게 만들어, 로봇이 스스로 발을 들기 시작하게 한다. 철학 전환: "rear를 더 밀자" → "정적 해가 더 이상 싸지 않게".

### V60.E 대비 변경점
| 항목 | V60.E | V60.F | 변경 이유 |
|------|-------|-------|----------|
| lin_vel_x min | 0.05 | **0.12** | 느린 정적 전진 불허 |
| track_lin | 5.0 | **4.0** | 정밀추종→실제전진 |
| standing_height | 1.0 | **0.0** | static bias 완전 제거 |
| joint_default_pos | -0.1 | **0.0** | static bias 완전 제거 |
| rear_feet_air_time | 없음 | **+6.0** | rear 비접촉 시간 직접 보상 (신규) |
| foot_clearance(전체) | +3.0 | **0.0** | front clearance OFF |
| per_leg_contact/swing | -6.0 | **-3.0** | 과도 억제 완화 |
| rear_lr_balance | -5.0 | **-2.0** | 완화 |

### 기대값
- lin_vel_x min=0.12로 정적 해가 tracking을 만족 못 하게 됨
- standing_height=0 + joint_default=0으로 정적 해의 이점 제거
- 1000 iter 내 rear swing 시작

### 실제 결과 (iter 17600 기준, 1000 iter)

| 지표 | V60.E | V60.F | 변화 |
|------|-------|-------|------|
| sw_FL | 0.19 | **0.007** | **고착** (접지 99%) |
| sw_FR | 0.22 | **0.008** | **고착** (접지 99%) |
| sw_RL | 0.007 | **0.782** | **폭발적 증가** |
| sw_RR | 0.013 | **0.934** | **폭발적 증가** |
| cr_FL / cr_FR | 0.80/0.76 | **0.99/0.99** | 완전 접지 |
| cr_RL / cr_RR | 1.00/0.99 | **0.22/0.07** | 대부분 공중 |
| forward_velocity | 2.9 | **3.98** | 상승 |
| diagonal_coupling | 0.000 | 0.000 | |

### 분석
lin_vel_x min=0.12 + standing_height=0 + rear_air_time=6이 정적 해를 완전히 깨뜨림. **하지만** front clearance OFF + rear 전용 보상이 "뒷다리만 흔들기" 해로 수렴. V60.D의 "앞다리만 흔들기"가 정확히 뒤집어진 것.

### 교훈
- **한쪽 pair만 유도하면 반대쪽 고착** — V60 시리즈의 가장 중요한 교훈
- front clearance만 주면 → 앞다리만 흔듦 (V60.D)
- rear clearance만 주면 → 뒷다리만 흔듦 (V60.F)
- front/rear를 동시에 균형 설계해야 함

### 판정
**부분 성공** — 정적 해 타파 + rear swing 증명. front 고착 발생.

### 다음 단계
front/rear pair balance penalty 도입 → V60.G

---

## V60.G: Front/Rear Pair Balance — 균형 달성, 교대 미발생

**Run:** `2026-04-06_23-22-03` | **iter 17600→25100 (7500 iter, V60.F resume)**

### 목적
"한쪽만 들면 손해, 균형 있게 교대하면 이득" — front/rear swing/contact 균형 penalty와 약한 diagonal coupling reward를 도입한다.

### V60.F 대비 변경점
| 항목 | V60.F | V60.G | 변경 이유 |
|------|-------|-------|----------|
| rear_air_time | +6.0 | **+1.0** | rear 과다 억제 |
| rear_clearance | +6.0 | **+1.0** | rear 과다 억제 |
| foot_clearance(전역) | 0.0 | **+3.0** | 전역 복원 |
| fr_swing_balance | 없음 | **-5.0** | 앞뒤 swing 차이 벌칙 (신규) |
| fr_contact_balance | 없음 | **-5.0** | 앞뒤 contact 차이 벌칙 (신규) |
| diagonal_coupling | 없음 | **+2.0** | 약한 trot 유도 (신규) |

### 신규 reward 함수
- `front_rear_swing_balance_penalty`: |front_swing_avg - rear_swing_avg|
- `front_rear_contact_balance_penalty`: |front_contact_avg - rear_contact_avg|
- `simple_diagonal_coupling_reward`: sync × anti_phase × swing_gate

### 기대값
- 2000 iter 내 front/rear swing gap 감소
- 4발 모두 의미 있는 swing
- diagonal_coupling > 0

### 실제 결과 (주요 구간 추이)

| iter | sw_FL | sw_FR | sw_RL | sw_RR | fr_balance | diag_raw |
|------|-------|-------|-------|-------|-----------|----------|
| 17700 | 0.003 | 0.009 | 0.758 | 0.895 | -4.1 | 0.000 |
| 19000 | 0.05 | 0.12 | 0.45 | 0.70 | -2.5 | 0.000 |
| 21000 | 0.10 | 0.18 | 0.35 | 0.55 | -1.5 | 0.000 |
| 24100 | 0.15 | 0.22 | 0.28 | 0.40 | -0.8 | 0.000 |
| 25100 | 0.20 | 0.25 | 0.25 | 0.35 | -0.5 | 0.000 |

### 분석
**성공:** front/rear gap이 7500 iter에 걸쳐 지속 축소. **처음으로 4발 모두 의미 있는 swing 달성.**

**실패:** diagonal_coupling_raw가 전 구간(7500 iter) **0.000**. 교대 패턴은 자동 발생 안 함.

**사후 리뷰로 발견된 설계 결함:**
1. diagonal_coupling의 초기 구현이 contact ratio 유사성만 보상 → 4발 접지도 높은 점수
2. balance penalty의 가장 쉬운 해가 "균형 있는 정지" (4발 접지면 차이=0)
3. 수정: anti_phase + swing_gate 조건 추가 (정적 접지=0, 교대만 보상)

### 교훈
- balance penalty로 균형은 잡히나, 교대 패턴(trot)은 자동 발생 안 함
- "균형 있는 흔들림"과 "구조화된 보행 패턴"은 완전히 다른 문제
- diagonal coupling에 anti-phase + swing_gate 필수

### 판정
**부분 성공** — 4발 균형 swing 최초 달성, diagonal 미발생

### 체크포인트 선택
`model_24100.pt` — 균형 최적 시점. 25100은 tracking 붕괴 시작.

### 다음 단계
diagonal coupling 2→8 강화 + balance penalty 완화 → V60.H

---

## V60.H: 대각선 교대 구조 직접 유도 (현재 진행 중)

**Resume from:** `2026-04-06_23-22-03/model_24100.pt` | **iter 24100→ (500 iter 판정)**

### 목적
V60.G에서 달성한 4발 균형 swing 위에, **대각선 교대(trot) 패턴을 핵심 보상으로 직접 밀어서** diagonal_coupling_raw > 0을 달성한다.

### V60.G 대비 변경점
| 항목 | V60.G | V60.H | 변경 이유 |
|------|-------|-------|----------|
| diagonal_coupling | +2.0 | **+8.0** | 핵심 드라이버로 4x 상향 |
| feet_air_time | +8.0 | **+5.0** | gait 약화 (balance 우선) |
| foot_clearance | +3.0 | **+2.0** | gait 약화 |
| fr_swing_balance | -5.0 | **-2.0** | balance 완화 |
| fr_contact_balance | -5.0 | **-2.0** | balance 완화 |
| rear_air_time | +1.0 | **0.0** | rear 전용 제거 |
| rear_clearance | +1.0 | **0.0** | rear 전용 제거 |

### 전체 reward 구조 (V60.H 최종)
| reward | weight | 역할 |
|--------|--------|------|
| diagonal_coupling | **+8.0** | **핵심: 대각선 교대 유도** |
| feet_air_time | +5.0 (thr=0.1) | 전역 발 들기 |
| forward_velocity | +5.0 | 전진 |
| track_lin_vel_xy_exp | +4.0 (std=0.15) | 속도 추종 |
| flat_orientation_bonus | +3.0 | 수평 |
| foot_clearance | +2.0 | 전역 높이 |
| track_ang_vel_z_exp | +2.0 | 회전 |
| per_leg_contact_min | -3.0 | 한 다리 비사용 방지 |
| per_leg_excess_swing | -3.0 | 영구 공중 방지 |
| fr_swing_balance | -2.0 | 앞뒤 균형 |
| fr_contact_balance | -2.0 | 앞뒤 균형 |
| flat_orientation_l2 | -2.0 | |
| lin_vel_z_l2 | -2.0 | |
| rear_lr_balance | -2.0 | RL/RR 균형 |
| ang_vel_xy_l2 | -1.0 | |
| standing_height | 0.0 | OFF |
| joint_default_pos | 0.0 | OFF |
| contact_foot_velocity | 0.0 | OFF |
| rear_air_time | 0.0 | OFF |
| rear_clearance | 0.0 | OFF |
| feet_on_ground | 0.0 | OFF |
| feet_lift_penalty | 0.0 | OFF |

### 기대값
- 200 iter 내 diagonal_coupling_raw > 0
- 4발 swing 유지 (한쪽 고착 재발 없음)
- ep_len > 900
- 500 iter에서 1차 판정

### 성공 기준
- diagonal_coupling_raw > 0
- 4발 모두 swing > 0
- ep_len > 900
- track_lin이 24100 대비 크게 붕괴하지 않음

### 실패 시 다음 단계
- diagonal_coupling_raw 여전히 0 → phase clock 도입 검토
- 4발 swing 붕괴 → balance penalty 복원
- 또는 from-scratch V61 (CPG/phase clock 기반 근본 재설계)

---

## 다음 단계 설계: V60.I

V60.H까지의 결과를 보면, 이제 문제는 "발을 더 들게 하자"가 아니다.

이미 확인된 것:
- 정적 접지 해는 깨졌다
- 4발 swing은 생겼다
- front/rear 한쪽만 고착되는 문제도 상당 부분 줄었다

하지만 여전히:
- `diagonal_coupling_raw = 0`

즉 현재 남은 문제는
**얼마나 움직이느냐**가 아니라
**언제 어떤 다리가 움직여야 하느냐**이다.

### 왜 V60.I가 필요한가

V60.G와 V60.H는 모두
"reward만 잘 주면 diagonal alternation도 자연스럽게 생기지 않을까?"
라는 가정 위에 있었다.

하지만 실제 결과는 다르게 나왔다.

- V60.G: 4발 swing 균형은 개선, diagonal 0
- V60.H: 4발 swing 분산은 더 좋아짐, diagonal 0

즉 reward만으로는 policy가
**시간 구조를 스스로 발명하지 못하고 있다**는 뜻이다.

그래서 V60.I의 핵심 철학은:

> **이제는 alternation의 "리듬 기준"을 environment가 직접 제공해야 한다.**

### V60.I 목표

- `balanced swing`을 `alternating diagonal gait`로 바꾸기
- 성공 기준:
  - `diagonal_coupling_raw > 0`
  - `ep_len > 900`
  - `track_lin` 급락 없음
  - 특정 다리 고착 재발 없음

### 핵심 설계 변경

#### 1. phase clock 도입

Observation에 다음과 같은 phase 정보를 추가한다.

```text
sin(phase)
cos(phase)
```

여기서 `phase`는 gait cycle의 진행도를 나타낸다.

핵심은:
- policy가 "지금이 어느 다리를 들어야 하는 위상인지"를 알 수 있어야 한다는 점이다.
- 지금까지는 reward만 주고, 그 타이밍 자체는 policy가 알아서 발명해야 했다.

#### 2. diagonal alternation을 phase-aligned reward로 바꿈

현재 `diagonal_coupling`은 결과적으로 "잘 교대했는지"만 본다.
V60.I에서는 여기에 더해,
phase에 따라 **어떤 diagonal pair가 swing이어야 하는지**를 직접 보상한다.

예시:
- phase A: `FL + RR` swing, `FR + RL` stance
- phase B: `FR + RL` swing, `FL + RR` stance

즉 reward는:
- "교대했는가"뿐 아니라
- **"올바른 위상에서 올바른 pair가 swing했는가"**
까지 본다.

#### 3. 기존 reward 구조는 크게 유지

유지:
- `track_lin_vel_xy_exp = 4.0`
- `forward_velocity = 5.0`
- `feet_air_time = 5.0`
- `foot_clearance = 2.0`
- `per_leg_contact_min = -3.0`
- `per_leg_excess_swing = -3.0`
- `fr_swing_balance = -2.0`
- `fr_contact_balance = -2.0`
- `diagonal_coupling = 8.0` 유지 또는 `10.0` 검토

계속 0 유지:
- `rear_air_time`
- `rear_clearance`
- `standing_height`
- `joint_default_pos`
- `contact_foot_velocity`

즉:
- 기존에 만든 "4발 모두 swing하는 바닥"은 유지하고
- 그 위에 **시간 구조만 새로 얹는다**

### command/action

V60.I에서는 reward만 바꾸지 않고, command는 최대한 고정한다.

```text
lin_vel_x = (0.12, 0.3)
ang_vel_z = 0.0
rel_standing_envs = 0.0
action.scale = 0.25
```

이유:
- 지금 문제는 command가 약해서가 아니라
- **구조가 없어서** 생기는 문제이기 때문이다

### resume 지점

V60.I는 `V60.G`가 아니라 **`V60.H` 결과에서 resume**하는 것이 맞다.

이유:
- V60.H가 이미 4발 swing 분산을 더 밀어놨기 때문
- 이제 필요한 건 "더 들게 만들기"가 아니라 "구조화"다

권장:
- 최신 런 [2026-04-07_05-13-42](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-07_05-13-42)
- 다만 너무 뒤 checkpoint보다, tracking이 덜 무너진 **중간 checkpoint**를 잡는 것이 좋다
- 보수적으로는 `model_25500.pt` 전후가 1차 후보

### 1차 판정 기준

`500 iter` 1차 판정:
- `diagonal_coupling_raw > 0`
- 네 다리 `swing_time` 모두 유지
- `ep_len > 900`
- `track_lin > 2.7`

실패 시:
- reward만 더 조정하는 것이 아니라
- **phase-conditioned contact target**을 더 직접적으로 도입해야 한다

### 한 줄 요약

V60.I는
`발을 더 들게 만드는 버전`이 아니라,
**이미 생긴 4발 swing에 시간 구조(phase)를 넣어 diagonal alternation으로 바꾸려는 버전**이다.

---

## 핵심 발견 요약

### 1. Curriculum 복원 버그 (V59.D)
- `restore_curriculum_snapshot()`이 resume 시 env_cfg reward weight를 덮어씀
- 해결: 버전 변경 감지 → 자동 skip

### 2. 서기→보행 전환의 근본 어려움 (V59.D)
- 정적 균형(서기)과 동적 균형(보행)은 완전히 다른 스킬
- from-scratch가 resume보다 효과적

### 3. 1발 들기 Exploit (V60.A)
- feet_air_time이 1발만 들어도 양수 → 최소 비용 exploit

### 4. Penalty Budget 검증 필수 (V60.B→C)
- -3.0은 양수 15 대비 부족, -10이 필요
- 보수적 추정보다 실제 reward budget에 맞는 강한 penalty가 필요함

### 5. 한쪽 유도 → 다른쪽 고착 (V60.D, V60.F)
- front clearance만 → 앞다리만 흔듦
- rear clearance만 → 뒷다리만 흔듦
- **pair 전용 보상은 반대쪽 고착을 유발**

### 6. Balance ≠ Alternation (V60.G)
- balance penalty로 균형은 잡힘
- 하지만 교대 패턴은 자동 발생 안 함
- "균형 있는 정지"도 최적해가 됨

### 7. 교대는 직접 보상 필요 (V60.H)
- anti-phase + swing_gate 조건 필수
- 정적 접지 시 reward=0이 되어야 함
