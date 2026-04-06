# V60 Plan: From-Scratch Walking + Asymmetry Exploit Correction

> 작성/갱신: 2026-04-06
> 현재 코드 truth 기준 버전: `V60.F`
> 기반: V59.B 서기 마스터 → V59.D 보행 전환 실패 → V60 from-scratch

---

## 0. 현재 결론

```text
V60.A (from-scratch 보행):
  - ep_len 1000 (100% 생존)
  - tracking 96% (track_lin_vel_xy_exp = 4.8/5.0)
  - forward_velocity = 1.29 (약간 전진)
  - 하지만 RR 비대칭 exploit 발생:
    - contact_ratio_rr = 0.02 (98% 공중)
    - 나머지 3발: FL=0.89, FR=0.94, RL=0.93
    - diagonal_coupling = 0.000

V60.B (비대칭 penalty 추가, V60.A resume):
  - penalty -3.0이 부족하여 RR 교정 실패
  - cr_RR: 0.02 -> 0.033 (3000 iter에 +1.3%만 개선)
  - 선형 외삽 시 정상화까지 5만+ iter 필요

V60.C (penalty 대폭 상향, V60.B resume):
  - per_leg_contact_min: -3 -> -10
  - per_leg_excess_swing: -3 -> -10
  - rear_lr_balance: 신규 -5
  - 결과: RR 비대칭 exploit 완전 교정 (cr_RR 0.033→0.997)
  - 하지만 4발 모두 정적 접지 (swing 2~4%, diagonal_coupling=0)

V60.D (static bias 약화 + gait incentive 강화, V60.C resume):
  - feet_air_time: 4→8, foot_clearance: 2→6
  - contact_foot_velocity: -1.0→-0.3, joint_default_pos: -0.5→-0.2
  - 초기 결과 (112 iter):
    - 앞다리 swing 증가: FL +97%, FR +182%
    - 뒷다리 여전히 고착: RL/RR swing < 0.003
    - diagonal_coupling = 0.000
  - 판정: no-go (앞다리만 swing, 뒷다리 고착)

V60.E (rear swing 생성 집중, V60.D resume):
  - rear_foot_clearance_reward: +6 신규 (뒷다리 전용)
  - foot_clearance: 6→3 (front 약화)
  - static bias 제거: contact_foot_vel=0, joint_default=-0.1, height=1.0
  - 대칭 penalty 완화: -10→-6
  - yaw OFF, standing_envs=0.0, min vel=0.05
  - 진행 중...
```

---

## 1. 버전 히스토리

### V59.B: 서기 마스터 (성공)
- Run: `2026-04-05_11-24-24`
- 결과: ep_len 1000, feet_on_ground 99.9%, 수평 99.8%
- 핵심: ImplicitActuator stiffness=20 + merge_fixed_joints=False + 실물 URDF 1.41kg

### V59.D: 서기→보행 전환 (실패)
- Run: `2026-04-05_17-31-45` (model_2700 resume)
- 결과: 서기 정책이 너무 강해 보행으로 전환 불가
- 발견: curriculum 파일이 env_cfg reward weight를 덮어쓰는 버그
  - restore_curriculum_snapshot()이 저장된 weight로 복원
  - env_cfg에서 feet_on_ground=0으로 설정해도 curriculum이 6.0으로 복원
  - 해결: 버전 변경 시 reward/termination 복원 자동 skip

### V60.A: From-Scratch 보행 (부분 성공)
- Run: `2026-04-05_21-12-36`
- 설정:
  - action_scale=0.25, standing_envs=0.2, vel_x=(0, 0.3)
  - feet_lifted termination 제거
  - feet_on_ground=0, feet_lift_penalty=0
  - forward_velocity=+3.0, feet_air_time=+2.0
- 결과: 생존+tracking 우수, RR 비대칭 exploit 발생
- 교훈: feet_air_time이 1발만 들어도 보상 → 가장 쉬운 1발 들기로 수렴

### V60.B: 비대칭 Penalty 추가 (효과 부족)
- Run: `2026-04-06_10-51-10` (model_8300 resume)
- 설정:
  - per_leg_contact_min: -3.0 (min_ratio=0.15)
  - per_leg_excess_swing: -3.0 (max_swing=0.70)
  - feet_air_time: weight 2→4, threshold 0.3→0.1
  - forward_velocity: 3→5
- 결과: penalty가 약해서 RR 교정 실패 (cr_RR 0.02→0.033)
- 교훈: penalty weight는 양수 reward budget 대비 수치 검증 필수

### V60.C: Penalty 강력 상향 (RR 교정 성공)
- Run: `2026-04-06_16-46-38` (model_11300 resume)
- 변경:
  - per_leg_contact_min: -3 → -10
  - per_leg_excess_swing: -3 → -10
  - rear_lr_balance: 신규 -5 (RL/RR pair 불균형 표적)
- 수치 검증: penalty 합계 -8.55/step vs 양수 ~15/step
- 결과: **RR 비대칭 exploit 완전 교정** (cr_RR 0.033→0.997, ~100 iter 만에)
- 새 문제: 4발 모두 정적 접지 (swing 2~4%, diagonal_coupling=0)
- 교훈: penalty weight는 Codex 권장 범위(-8~-12)를 신뢰해야 함

### V60.D: Static Bias 약화 + Gait Incentive 강화 (no-go)
- Run: `2026-04-06_19-14-18` (model_13000 resume)
- 변경:
  - feet_air_time: +4 → +8, foot_clearance: +2 → +6
  - contact_foot_velocity: -1.0 → -0.3, joint_default_pos: -0.5 → -0.2
- 결과 (2817 iter):
  - 앞다리 swing 대폭 증가: FL 0.040→0.218, FR 0.022→0.338
  - 뒷다리 완전 고착: RL/RR swing 0.003~0.006
  - FR 단독 과부상 (FL의 1.5~2배)
  - diagonal_coupling: 0.000, penalty 합산 -2.41 (증가 중)
- 교훈: 전체 gait incentive는 이미 swing이 나오는 앞다리만 강화, 뒷다리 전용 유도 필요

### V60.E: Rear Swing 생성 집중 (현재)
- Resume from: `2026-04-06_19-14-18/model_15800.pt`
- 변경:
  - rear_foot_clearance_reward: +6 신규 (RL/RR 전용 보상)
  - foot_clearance: 6 → 3 (front 약화)
  - static bias 제거: contact_foot_vel=0, joint_default=-0.1, standing_height=1.0
  - 대칭 penalty 완화: -10 → -6
  - yaw OFF (ang_vel_z=0), standing_envs=0.0, min vel_x=0.05
- 결과: no-go (RL swing 0.007, RR swing 0.013, 835 iter 플라토)
- 교훈: rear 보상을 더 얹는 것만으로는 부족 — 정적 접지 해 자체가 여전히 더 싼 구조

### V60.F: 정적 접지 해를 이득 아니게 만드는 구조 전환 (현재)
- Resume from: `2026-04-06_21-27-33/model_16600.pt`
- 철학 전환: "rear를 더 밀자" → "정적 해가 더 이상 싸지 않게"
- 변경:
  - lin_vel_x min: 0.05 → 0.12 (느린 정적 전진 불허)
  - track_lin: 5 → 4 (정밀 추종보다 실제 전진)
  - standing_height: 0.0, joint_default_pos: 0.0 (static bias 완전 제거)
  - rear_feet_air_time_reward: +6 신규 (rear 비접촉 시간 직접 보상)
  - foot_clearance(전체): 0.0 (front clearance OFF)
  - 대칭 penalty: -6→-3, rear_lr: -5→-2
  - yaw OFF, standing_envs=0.0
- 결과: 뒷다리 swing 폭발(RL=0.78, RR=0.93), 하지만 앞다리 고착(FL/FR 99% 접지)
- 교훈: 한쪽만 유도하면 다른쪽 고착 — front/rear 균형 설계 필요

### V60.G: Front/Rear Pair Balance + Diagonal Coupling (현재)
- Resume from: `2026-04-06_22-30-44/model_17600.pt`
- 철학: "한쪽만 들면 손해, 균형 있게 교대하면 이득"
- 변경:
  - rear_air_time: 6→1, rear_clearance: 6→1 (rear 과다 억제)
  - foot_clearance: 0→3 (전역 복원)
  - front_rear_swing_balance_penalty: -5 (앞뒤 swing 차이 벌칙)
  - front_rear_contact_balance_penalty: -5 (앞뒤 contact 차이 벌칙)
  - simple_diagonal_coupling_reward: +2 (약한 trot 유도)
- 성공 기준: 4발 모두 swing>0, front/rear gap 감소, diagonal_coupling>0, ep_len>850

---

## 2. 핵심 발견

### Curriculum 복원 버그
- `restore_curriculum_snapshot()`이 resume 시 env_cfg reward weight를 덮어씀
- 해결: 새 reward가 있거나 weight가 다르면 자동 skip
- 위치: rewards.py `restore_curriculum_snapshot()` 함수

### 서기→보행 전환의 근본 어려움
- 서기 정책은 정적 균형(static balance)만 학습
- 동적 균형(발 움직이면서 안 넘어지기)은 완전히 다른 스킬
- from-scratch가 resume 전환보다 효과적 (V60 > V59.D)

### 1발 들기 Exploit
- feet_air_time reward가 1발만 들어도 양수 → 최소 비용 exploit
- 해결: per-leg contact min + excess swing + rear pair balance

### 정적 4발 접지 해 (V60.C→D)
- RR 교정 후 4발 모두 99%+ 접지, swing 2~4%
- feet_air_time/foot_clearance 강화로 앞다리만 swing 증가
- 뒷다리는 여전히 고착 → front-rear 비대칭 새 패턴 발생
- 교훈: 전체 gait incentive만으로는 뒷다리가 안 깨짐, 뒷다리 전용 유도 필요 가능성

---

## 3. Go/No-Go 기준

### V60.C 성공 기준 → **달성**
- contact_ratio_rr > 0.15: **0.997** (달성)
- swing_time_rr < 0.70: **0.003** (달성)
- ep_len > 900: **1000** (달성)

### V60.D 성공 기준
- contact_ratio가 전반적으로 0.99 아래 (swing 시작)
- swing_time이 전 다리에서 의미 있게 증가
- clearance가 상승
- diagonal_coupling이 0에서 벗어남
- ep_len > 900, RR 비사용 재발 없음

### V60.D 결과 → no-go → V60.E로 전환

### V60.E 결과 → no-go → V60.F로 전환
- RL swing 0.007, RR swing 0.013 (835 iter 플라토)
- rear 보상을 더 얹는 것만으로는 정적 해를 깨지 못함

### V60.F 성공 기준
- swing_time_rl > 0.02
- swing_time_rr > 0.02
- rear_air_time >= 0
- ep_len > 850

### V60.F 실패 시 다음 단계
- 정적 해 여전히 유지 → rear contact_ratio 상한 penalty (과접지 벌칙)
- 또는 front_rear_swing_diff 직접 penalty
- 또는 from-scratch V61 (reward 구조 근본 재설계)
