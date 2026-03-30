# V55 Plan: 검증된 기반 복구 후 Phase 보조 삽입

> 작성: 2026-03-30
> 상태: **설계 승인 대기**
> 목적: `V54`에서 드러난 handoff collapse를 교훈으로 삼아, 성공이 검증된 boot/gait 기반 위에서 phase를 보조 신호로 다시 검증한다.

---

## 1. 결론

현재 최적 전략은 `clean V54를 계속 미세조정`하는 것이 아니라, `V47/V53 계열의 검증된 기반을 복구한 뒤 phase를 auxiliary reward로 삽입`하는 것이다. 이 전략 변경을 별도 메이저 버전 `V55`로 정의한다.

핵심 이유:

1. `V43-E`, `V47`은 boot 성공 기록이 있다.
2. `V54.3~V54.4`는 clean start에는 성공했지만 boot 생존성이 계속 하락했다.
3. 현재 실패는 one-leg exploit 이전에 `handoff collapse`가 먼저 온다.
4. 즉, 지금 부족한 것은 phase 수식이 아니라 `phase를 받아낼 locomotion 기반`이다.

---

## 2. 목표 재정의

이번 플랜의 목표는 두 단계다.

### 2.1 단기 목표

`V47/V53급 boot 생존성`을 다시 확보한다.

성공 조건:

- iter `300`에서 `mean_episode_length > 80`
- iter `500`에서 `mean_episode_length > 120`
- 4발 `contact_ratio`가 모두 바닥으로 가지 않음

### 2.2 중기 목표

phase 신호가 실제로 gait structure를 만드는지 `보조 신호` 상태에서 검증한다.

성공 조건:

- phase reward를 넣어도 boot가 무너지지 않음
- `diagonal_coupling_raw`가 `0.0` 고착에서 벗어남
- 특정 다리 희생 없이 `contact_ratio`가 유지됨

### 2.3 장기 목표

phase reward가 실제 구조 형성에 기여한다는 증거가 모이면, 그때부터 legacy/bridge를 천천히 덜어내고 phase-centric 구조로 이동한다.

---

## 3. V54 실패 해석과 V55로 올리는 이유

현재 `V54.4` 런(`2026-03-30_07-03-05`)에서 확인된 사실:

- `curriculum_500.pt`에서도 `_crr_gate_paused=True`
- `_crr_alpha12=0`, `_crr_alpha23=0`
- 그런데 `iter 500 fallback`으로 boot handoff는 강제 시작
- `mean_episode_length`: `21.35 -> 11.65 -> 10.38 -> 11.06 -> 8.71 -> 4.94 -> 4.36`
- `phase_contact`는 `step 600`에서도 `~0.0015`
- `diagonal_coupling_raw=0.0`

해석:

1. boot가 성공하지 못한 상태에서
2. handoff가 강제로 시작됐고
3. phase reward는 아직 locomotion 주연 역할을 못 했다.

따라서 지금 문제는 `phase_contact 집계 방식`보다 먼저 `기반 locomotion 자체가 약하다`는 것이다.

이 문서를 `V54B`가 아니라 `V55`로 두는 이유는 명확하다.

- `V54`는 clean phase-centric handoff 계열 실험이다.
- 이번 문서는 handoff를 잠정 포기하고 baseline recovery를 우선한다.
- 즉, 같은 실험군의 세부 분기가 아니라 전략 축이 바뀐다.

---

## 4. 새 전략의 설계 원칙

### 원칙 1: 작동하는 기반을 먼저 복구한다

`작동하는 시스템을 고치지 말 것`이라는 기존 교훈을 따른다.

즉:

- `V47`의 강한 boot 생태계
- `V53`의 앞다리 사용 문제 인식

를 기반으로 삼고, phase는 그 위에 얹는다.

### 원칙 2: phase는 처음부터 주연이 아니다

초기 phase는 `teacher`, `regularizer`, `structure probe` 역할만 수행한다.

즉:

- locomotion을 혼자 책임지지 않는다
- boot/handoff의 주 제어축이 아니다
- 먼저 "정말 유효한 신호인가"를 본다

### 원칙 3: handoff보다 병행 검증이 먼저다

이번 단계에서는 `boot -> phase hard/soft handoff` 자체를 목표로 하지 않는다.

먼저 해야 할 일:

- 기반 locomotion이 살아나는지
- 그 위에 phase 보조 reward가 들어가도 망가지지 않는지
- phase metric이 실제로 따라오는지

### 원칙 4: abort 기준을 더 엄격히 둔다

다음 중 하나면 즉시 abort 검토:

- iter `150`에서 `mean_episode_length < 30`
- iter `300`에서 `mean_episode_length < 50`
- iter `300` 이후 `diagonal_coupling_raw = 0.0` 고착
- 특정 다리 `contact_ratio < 0.01` 고착

---

## 5. 베이스라인 선택

### 권장 베이스: `V47` 생태계 + `V53` 문제 인식

이유:

- `V47`은 boot와 locomotion 모두 실제 성과가 검증됨
- `V53`은 앞다리 미사용 문제를 가장 최근까지 추적한 버전
- `V54`처럼 reward inventory를 과도하게 비우지 않았음

### 구현 방침

실제 코드 베이스는 다음 철학을 따른다.

1. `V47`의 강한 boot/locomotion ecology 복구
2. `V53` 이후 확인된 one-leg/front-leg 문제는 유지
3. phase는 작은 weight로 추가

즉 `phase-only 재설계`가 아니라:

`working baseline + phase probe`

---

## 6. Reward Inventory 설계

### 6.1 유지할 핵심 기반 reward

다음 계열은 유지한다.

- `boot_standing`
- `boot_contact`
- `alive_bonus`
- `standing_height`
- 기존 `V38.3/V47` locomotion 구조 reward
- 현재까지 유효했던 termination / safety

핵심 의도:

- 먼저 `걷는 정책`을 다시 만든다.
- phase가 없어도 최소한 stride와 ep_len이 살아나야 한다.

### 6.2 phase 보조 reward

이번 단계에서 phase는 아래처럼 약하게 넣는다.

```text
phase_contact      2.0 ~ 4.0
phase_clearance    0.5 ~ 1.0
```

권장 시작값:

```text
phase_contact      = 3.0
phase_clearance    = 0.75
```

이 값이 의미하는 것:

- gait의 주연 reward는 아님
- 그러나 policy가 phase 구조를 무시하기 어렵게는 만든다
- boot를 깨뜨릴 정도로 강하지는 않다

### 6.3 penalty

이번 단계에서는 V54.4에서 확인한 완화값을 유지하는 쪽이 유리하다.

```text
action_rate_l2  = -0.30
joint_vel_l2    = -0.10
dof_acc_l2      = -2e-5
```

이유:

- 현재 V54.4에서 이 penalty 완화는 실제로 boot 붕괴를 줄였다
- 이 항목은 되돌리는 것보다 유지하면서 baseline 쪽을 복구하는 편이 낫다

---

## 7. Curriculum 설계

### 7.1 이번 단계의 핵심: handoff를 제거한다

이번 플랜에서는 `iter 500 fallback handoff`를 쓰지 않는다.

즉:

- phase reward는 시작부터 작은 상수 weight로 켠다
- boot bridge를 phase로 넘기는 구조를 이번 단계 목표로 삼지 않는다
- locomotion 기반과 phase signal이 `같이 존재할 때도` 학습이 되는지 본다

### 7.2 왜 handoff를 빼는가

현재는 handoff가 실험 변수를 너무 많이 만든다.

동시에 변하는 것:

- boot reward 감소
- bridge reward 감소
- phase reward 증가
- gait gate 상태

이 상태에선 무엇이 원인인지 분리하기 어렵다.

따라서 이번 단계는:

`handoff 실험`이 아니라 `phase 유효성 검증 실험`

이다.

### 7.3 다음 단계에서만 handoff 재도입

아래 조건이 만족될 때만 handoff를 다시 설계한다.

- baseline locomotion이 안정적
- phase auxiliary 삽입 후에도 성능 유지
- phase metric이 실제로 상승

---

## 8. phase_contact 집계 방식

이번 플랜에서는 `floor-only`를 바로 쓰지 않는다.

이유:

- 현재 V54.4에서 `floor + EMA + min_target`는 초기 phase reward를 너무 sparse하게 만들었다
- auxiliary 단계에서는 reward density가 더 중요하다

권장 순서:

### Stage B1

```text
aggregation = mean_min
```

설계:

```text
score = 0.5 * mean(c_i) + 0.5 * min(c_i)
```

여기서 `c_i`는 per-leg compliance EMA.

### Stage B2

phase가 실제로 먹히는 증거가 나오면 그때:

```text
aggregation = floor
```

로 이동한다.

즉 one-leg exploit 방지 장치는 `처음부터 최대로` 거는 것이 아니라, 정책이 최소 locomotion을 확보한 뒤 강화한다.

---

## 9. 실험 단계

### Experiment B1: Baseline Recovery + Weak Phase

목적:

- boot와 locomotion 복구
- phase 신호가 같이 있어도 정책이 죽지 않는지 확인

설정:

```text
base          = V47/V53 ecology
phase_contact = 3.0
phase_clear   = 0.75
handoff       = 없음
fallback      = 없음
phase agg     = mean_min
```

성공 기준:

- iter `300`: `ep_len > 80`
- iter `500`: `ep_len > 120`
- `diagonal_coupling_raw > 0.05`
- 특정 발 `contact_ratio` 바닥 고착 없음

### Experiment B2: Same Base + Stronger Phase

전제:

- B1이 성공

설정:

```text
phase_contact = 5.0
phase_clear   = 1.5
```

목표:

- phase가 실제 구조 형성에 기여하는지 확인

성공 기준:

- stride/coupling 개선
- ep_len 유지
- phase reward 상승

### Experiment B3: Delayed Handoff Reintroduction

전제:

- B2까지 성공

설정:

- 그때만 boot/bridge 일부를 서서히 줄인다
- release 조건은 `iteration`이 아니라 `metric` 기반이어야 한다

예:

```text
release only if:
mean_episode_length > 150
and diagonal_coupling_raw > 0.08
and min(contact_ratio_*) > 0.03
for N updates
```

---

## 10. 모니터링 지표

### 필수 지표

- `Train/mean_episode_length`
- `Train/mean_reward`
- `Episode_Reward/phase_contact`
- `Episode_Reward/phase_clearance`
- `Episode_Reward/diagonal_coupling_raw`
- `Episode_Reward/contact_ratio_fl`
- `Episode_Reward/contact_ratio_fr`
- `Episode_Reward/contact_ratio_rl`
- `Episode_Reward/contact_ratio_rr`

### 보조 지표

- `boot_standing`
- `standing_height`
- `track_lin_vel_xy_exp`
- `dof_acc_l2`
- `joint_vel_l2`
- `action_rate_l2`

### 체크포인트

```text
iter 0     | 설정 반영 여부
iter 100   | boot 생존
iter 300   | locomotion 기반 형성
iter 500   | phase 보조 삽입 상태 평가
iter 1000  | diagonal/contact 구조 수렴 평가
```

---

## 11. 성공/실패 판정

### 성공

다음이 동시에 만족되면 성공 방향:

1. `ep_len`이 계속 상승 또는 유지
2. `phase_contact`가 0 고착이 아님
3. `diagonal_coupling_raw`가 0에서 벗어남
4. 특정 다리 희생 없이 contact가 유지됨

### 실패

다음 중 하나면 실패:

1. boot 생존성 자체가 다시 무너짐
2. phase를 넣자마자 ep_len 하락
3. `diagonal_coupling_raw = 0.0` 지속
4. one-leg exploit 재발

---

## 12. 이번 플랜의 핵심 차별점

기존 `V54`는:

`clean phase-centric design을 먼저 만들고, 그 설계를 학습시키려 했다`

이번 `V55`는:

`이미 걷는 기반을 먼저 복구하고, phase가 그 기반 위에서 실제 도움이 되는지 검증한다`

즉 이 플랜은 철학 후퇴가 아니다.

오히려 더 현실적인 순서다:

1. 걷게 만든다
2. phase가 진짜 도움이 되는지 본다
3. 도움이 확인되면 그때 phase 중심으로 축소한다

---

## 13. 최종 추천

바로 실행할 1순위는 `Experiment B1`이다.

한 줄 요약:

`지금은 clean V54를 더 밀 때가 아니라, 검증된 기반 위에 약한 phase를 얹어 "phase가 실제로 구조를 만드는가"부터 증명해야 한다.`
