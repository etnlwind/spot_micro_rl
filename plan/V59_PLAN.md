# V59 Plan: 실물 서보 기반 Stand-First Locomotion

> 작성: 2026-04-04 ~ 04-05
> 상태: **서기 학습 성공** (101 iter, timeout 98%, 4발 접지 98%)
> 목적: 실물 기반 URDF 질량 + merge_fixed_joints=False로 서기 → 보행 학습

---

## 0. 핵심 성과 (2026-04-05)

```text
서기 학습 결과 (101 iters):
  ep_len:          994 / 1000 (거의 max)
  time_out:        98% (거의 전부 생존)
  feet_lifted:     2% (미미)
  standing_height: 2.74 / 3.0 (91%)
  feet_on_ground:  5.89 / 6.0 (98%)
  flat_orientation: 4.91 / 5.0 (98%)
  reward:          +179

로봇이 4발 접지 + 수평 유지 + 목표 높이(205mm) 유지하면서 서 있음.
```

---

## 1. 현재 설정 (코드 truth)

```text
[URDF — 실물 기준 질량]
총 질량:          1.41 kg (원본 5.3kg에서 수정)
base 링크:        0.001 kg (더미, PhysX 기본 1kg 방지용 inertial 추가)
base_link:        0.500 kg
velocity:         100.0 (PhysX maxJointVelocity)

[Actuator]
type:             ImplicitActuatorCfg
stiffness:        20.0
damping:          0.5
effort_limit_sim: 없음 (토크 무제한, Sim2Real 시 제한 추가 예정)

[URDF 변환]
merge_fixed_joints: False (핵심! True면 toe_link contact reporting 불가)

[Init pose — spot_mini_mini 기본 자세]
init_z:           0.222
shoulder:         ±0.15
leg:              -0.66
foot:             1.05

[Env — V59 stand-first]
action_scale:     0.04
action_warmup:    5 steps
commands:         vel=0, standing=100%

[Terminations]
min_height:       0.14
bad_orientation:  30° + grace 3초 (150 steps)
feet_lifted:      grace 25 steps + consecutive 8 steps
base_contact:     base_link만

[Rewards — 9개]
flat_orientation_bonus:          +5.0  (수평 유지)
standing_height:                 +3.0  (target=205mm, sigma=0.03)
track_lin_vel_xy:                +2.0  (가만히 서기)
track_ang_vel_z:                 +1.0
feet_on_ground:                  +6.0  (4발 접지)
joint_default_pos:               -4.0  (init pose 유지)
feet_lift_penalty:              -20.0  (발 들기 벌)
contact_foot_velocity_penalty:   -5.0  (toe 미끄럼 금지)
action_rate_l2:                  -0.5  (최소 움직임)
dof_torques_l2:                  -0.02 (부하 최소화)
flat_orientation_l2:             -3.0  (기울면 벌)
lin_vel_z_l2:                    -2.0  (상하 흔들림)
ang_vel_xy_l2:                   -1.0  (기울어짐 속도)
```

---

## 2. 핵심 발견 요약

### URDF 질량 (5.3kg → 1.41kg)
- 원본 mike4192 URDF는 "guesses" 값 (모든 fork가 상속)
- base 링크에 inertial 태그 누락 → PhysX 1.0kg 기본값 할당
- 실물 BOM 기준으로 재설정

### merge_fixed_joints=False 필수
- True면 toe_link가 foot_link에 병합 → contact reporting 완전 불가 (전 body 0N)
- False면 toe_link 독립 → 4발 접촉 정상 감지
- 이것이 V58 시리즈에서 contact 기반 reward가 안 먹었던 근본 원인

### DCMotor vs ImplicitActuator
- DCMotor: effort_limit 클램핑으로 init pose 유지 불가 (1.4kg에서도)
- ImplicitActuator: PhysX 내장 PD로 안정적 서기 가능
- 토크 제한은 Sim2Real 단계에서 domain randomization으로 추가

### feet_lifted termination의 consecutive_steps
- 1 step 판정: 미세 진동(contact dropout)으로 100% 즉사
- 8 step 연속: 실제 발 들기만 감지 → 학습 성공의 결정적 요인

### contact_foot_velocity_penalty
- toe 접지 중 미끄럼 방지 → "toe 고정 + body correction" 유도
- 서기 학습의 핵심 행동 유도

---

## 3. 다음 단계

### 서기 → 보행 전환
1. 현재 서기 체크포인트에서 resume
2. vel 명령 추가 (standing_envs 0.2, vel_x 0~0.5)
3. feet_air_time reward 추가
4. feet_lifted termination 완화 또는 제거
5. action_scale 0.04 → 0.25 (보행에 필요한 범위)

### Sim2Real
1. effort_limit_sim 추가 (STS3215 3Nm)
2. domain randomization (질량 ±20%, 토크 ±30%)
3. 학습된 policy의 실제 토크 사용량 검증

---

## 4. 변경 파일

| 파일 | 변경 |
|------|------|
| `spotmicroai_realistic_inertia.urdf` | 질량 실물 기준 (5.3→1.41kg), base inertial 추가, velocity 100 |
| `robots/spot_micro.py` | ImplicitActuator stiffness=20, merge_fixed_joints=False |
| `spot_micro_rl_env_cfg.py` | V59 stand-first 블록 (9 rewards, 4 terminations) |
| `mdp/rewards.py` | flat_orientation_bonus, feet_lift_penalty, feet_lifted_termination(consecutive), contact_foot_velocity_penalty, bad_orientation_grace 추가 |

---

## 5. 교훈

```text
1. URDF 질량은 반드시 실물 기준 검증
2. merge_fixed_joints=True는 contact reporting을 깨뜨림
3. contact 기반 reward/termination은 threshold + consecutive 조합이 핵심
4. zero-action stand test를 gating test로 먼저 통과해야 학습 시작
5. action_scale은 물리적으로 발이 안 뜨는 범위 내에서 설정
6. 서기 학습: "발 고정 + body correction"을 유도하는 reward 구조 필요
```
