# V59 Plan: Stand-First to Small-Walk Transition

> 작성/갱신: 2026-04-04 ~ 2026-04-05
> 현재 코드 truth 기준 버전: `V59.C`
> 현재 성공 런 해석: `2026-04-05_11-24-24`는 실질적으로 `V59.B`

---

## 0. 현재 결론

```text
V59.B 성격 런은 성공:
  - 4발 접지 유지
  - 발 들기 종료 0%
  - 넘어짐 0%
  - ep_len 1000 고정
  - 작은 전진 tracking 성공

하지만 아직 실제 보행은 아님:
  - contact_ratio ≈ 0.999
  - swing_time ≈ 0.001
  - clearance ≈ 0
  - diagonal_coupling = 0

즉 현재 상태는:
  "잘 서고, 조금 전진은 하지만, 아직 swing gait는 아니다"
```

냉정한 판단:
- `V59.C` 하나만으로 사용자가 원하는 "자연스러운 첫 걸음"이 바로 나올 가능성은 낮다.
- 이유는 현재 정책이 이미 `4발 접지 + quasi-static drift` local optimum에 강하게 수렴했기 때문이다.
- 따라서 이후 단계는 한 번에 해결하는 단일 버전이 아니라, local optimum을 순차적으로 깨는 multi-stage curriculum이어야 한다.

---

## 1. 코드 Truth

### 1.1 Robot / Actuator

현재 [spot_micro.py](/mnt/d/project/spot_micro_rl/source/spot_micro_rl/spot_micro_rl/robots/spot_micro.py) 기준:

```text
activate_contact_sensors: True
merge_fixed_joints:       False

Actuator:
  type:       ImplicitActuatorCfg
  stiffness:  20.0
  damping:    0.5
  effort_limit_sim: 없음

Init pose:
  z:          0.222
  shoulder:   ±0.15
  leg:        -0.66
  foot:       1.05
```

핵심:
- `merge_fixed_joints=False`가 현재 contact reporting 정상화의 필수 조건
- `toe_link` contact가 실제로 들어오며, `True`일 때는 이 경로가 깨졌음
- 현재는 stand-first bootstrap을 위해 `Implicit + stiffness=20`을 사용 중

### 1.2 Reward / Termination 핵심

현재 [spot_micro_rl_env_cfg.py](/mnt/d/project/spot_micro_rl/source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py) 기준 공통 stand-first 블록:

```text
action_warmup_steps: 5
stand base action scale: 0.04

commands:
  heading_command: False
  rel_standing_envs: 1.0 (base stand block)
  lin_vel_x/y: 0
  ang_vel_z: 0

terminations:
  min_height:       0.14
  bad_orientation:  custom grace termination
  feet_lifted:      grace + consecutive dropout
  base_contact:     base_link only

rewards:
  flat_orientation_bonus
  standing_height
  track_lin_vel_xy_exp
  track_ang_vel_z_exp
  feet_on_ground
  joint_default_pos
  feet_lift_penalty
  contact_foot_velocity_penalty
  action_rate_l2
  dof_torques_l2
  flat_orientation_l2
  lin_vel_z_l2
  ang_vel_xy_l2
```

현재 [rewards.py](/mnt/d/project/spot_micro_rl/source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py) 기준:
- `feet_lifted_termination`은 **consecutive dropout** 방식으로 수정됨
- `contact_foot_velocity_penalty` 존재함
- `all_feet_on_ground`, `feet_lift_penalty`, `bad_orientation_grace` 사용 중

---

## 2. V59.B 성공 런

기준 런:
- [2026-04-05_11-24-24](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-05_11-24-24)

직접 실행 resume까지 포함한 실제 최신 상태는 live stdout 기준:

```text
Learning iteration: 2276 / 6400
Mean reward:        324.36
Mean episode length: 1000.00

Episode_Termination:
  time_out:         1.0000
  feet_lifted:      0.0000
  base_contact:     0.0000
  bad_orientation:  0.0000
  min_height:       0.0000

Reward:
  track_lin_vel_xy_exp:  1.9697
  track_ang_vel_z_exp:   0.9879
  standing_height:       2.9209
  feet_on_ground:        5.9941
  flat_orientation_bonus: 4.9818
```

해석:
- stand manifold는 사실상 형성 완료
- 4발 접지, 수평 유지, 발 들기 억제는 성공
- 작은 전진 추종도 성공

하지만 gait 측면은 여전히 미약:

```text
contact_ratio_fl/fr/rl/rr: 0.9990
swing_time_fl/fr/rl/rr:    0.0010
front_clearance_mean_raw:  0.0000
rear_clearance_mean_raw:   0.0000
diagonal_coupling_raw:     0.0000
```

즉:
- `stand + quasi-static drift`는 맞음
- `실제 swing gait`는 아직 아님

### 2.1 direct resume 결과

`model_1400.pt`에서 headless direct resume를 수행했을 때,
Isaac Lab은 같은 폴더에 이어 쓰지 않고 **새 런 디렉터리**를 생성했다.

기준 direct resume 런:
- [2026-04-05_14-59-28](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-05_14-59-28)

확인된 내용:

```text
latest scalar step:      2685
mean_reward:             323.15
mean_episode_length:     1000.0
feet_lifted:             0.0
time_out:                1.0
latest checkpoint:       model_2600.pt
```

해석:
- direct resume 이후에도 stability는 그대로 유지됨
- `feet_lifted=0`, `time_out=1.0`이 계속 유지되어 stand manifold는 매우 견고함
- 하지만 gait 쪽은 여전히 quasi-static drift 수준으로 남아 있음

---

## 3. 핵심 발견

### 3.1 merge_fixed_joints=False는 필수

실제 디버그 결과:
- `merge_fixed_joints=True`에서는 `toe_link` contact reporting이 깨졌음
- `False`로 바꾸자 4발 접촉력이 즉시 정상 검출됨

결론:
- 현재 SpotMicro 자산에서는 `toe_link` contact 기반 reward/termination을 쓰려면 `merge_fixed_joints=False`가 필수

### 3.2 contact dropout 1-step 즉사는 잘못된 설계였음

초기 문제:
- 화면상 4발이 붙어 있어도
- 미세한 toe contact dropout 한 번으로 `feet_lifted=100%` 즉사

수정:
- `feet_lifted_termination`에 `consecutive_steps` 도입

결과:
- stand task가 처음으로 정상 작동
- `feet_lifted 100% -> 0% 수준`으로 안정화

### 3.3 V59.B는 성공했지만, swing이 생길 이유는 거의 없음

성공 원인:
- `feet_on_ground` 강한 양의 보상
- `feet_lift_penalty`
- `contact_foot_velocity_penalty`
- `joint_default_pos`
- `standing_height`

문제:
- 발을 들면 손해는 강하지만
- 잘 들면 이득은 거의 없음

즉 현재 정책은 자연스럽게:
- 4발 접지
- 미끄럼 최소화
- quasi-static body drift
로 수렴

---

## 4. 버전 해석 정리

### 4.1 현재 런

현재 잘 나온 런 [2026-04-05_11-24-24](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-05_11-24-24)은
실질적으로 **`V59.B`** 성격으로 보는 것이 맞다.

이유:
- 코드 명시상 `V59`였던 시점부터 시작
- 실제 기능은 stand-first 성공 + micro-forward drift 단계
- 이후 version naming을 재정리하며 `V59.C`를 다음 단계로 정의함

### 4.2 현재 코드

현재 [spot_micro_rl_env_cfg.py](/mnt/d/project/spot_micro_rl/source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py) 의 `TRAIN_VERSION`은 **`V59.C`**다.

즉:
- 현재 런 = `V59.B`로 해석
- 현재 코드 = 다음 resume용 `V59.C`

### 4.3 direct resume 저장 위치 교정

초기에는 direct resume가 기존 [2026-04-05_11-24-24](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-05_11-24-24) 폴더에 이어 쓴다고 잘못 해석했으나,
실제 저장 위치는 새 폴더 [2026-04-05_14-59-28](/mnt/d/project/spot_micro_rl/logs/rsl_rl/spot_micro_flat/2026-04-05_14-59-28) 이었다.

즉 현재 정리는 아래가 맞다.

```text
2026-04-05_11-24-24 = V59.B 성공 런 (원본)
2026-04-05_14-59-28 = model_1400 기반 direct resume 런
현재 코드 truth = V59.C
```

---

## 5. V59.C 설계와 한계

현재 코드상 `V59.C`는 다음과 같다.

```text
action.scale:                    0.05
rel_standing_envs:               0.8
lin_vel_x:                       (0.0, 0.08)
ang_vel_z:                       0.0
feet_lifted.grace_steps:         40
feet_lifted.consecutive_steps:   10
track_lin_vel_xy_exp.weight:     3.0
feet_on_ground.weight:           5.0
feet_lift_penalty.weight:       -15.0
contact_foot_velocity_penalty:  -3.0
```

의도:
- stand manifold를 유지
- 아주 작은 전진만 얹기
- small-walk transition의 보수적 첫 단계

문제:
1. 여전히 `feet_lifted` hard termination이 남아 있음
2. `feet_on_ground`, `feet_lift_penalty`, `contact_foot_velocity_penalty`가 여전히 강함
3. swing에 대한 양의 보상이 없음
4. `standing_height`, `joint_default_pos` 등 stand bias가 moving env에도 강하게 남음

결론:
- `V59.C`는 안전한 전환 단계로는 적절
- 하지만 실제 gait emergence를 만들기엔 아직 too stand-biased
- 즉 **보행 전환이라기보다 stand-preserving micro-forward 단계**

---

## 6. 이후 단계: V59.D~G 설계

중요:
- 아래 설계는 **보행 완성 보장** 설계가 아니다.
- 대신 현재 local optimum을 깨기 위해 필요한 단계를 충분히 나눈 설계다.
- RL/contact locomotion 특성상 결과는 비결정적이므로, 각 단계를 통과 기준으로 평가하며 넘어가야 한다.

### 6.1 목표

```text
V59.D:
  첫 toe-off / 첫 swing 신호 생성

V59.E:
  짧고 안정된 controlled swing

V59.F:
  swing에서 gait pattern의 첫 형성

V59.G:
  robust small walk
```

### 6.2 철학

standing env:
- 현재 V59.B/C 철학 유지
- 4발 접지, toe 고정, 수평 유지, 기본자세 유지

moving env:
- stand bias를 단계적으로 약화
- swing emergence를 단계적으로 허용
- "발을 들면 손해"만 있는 구조를 버리고
- "잘 들면 약한 이득"이 생기는 구조로 순차 전환

즉 `한 세계`가 아니라 **command-gated 두 세계**를 두고,
`toe-off 생성 -> controlled swing -> pattern -> small walk`
순으로 단계를 나눈다.

### 6.3 V59.D: First Swing

목표:
- 4발 접지 drift에서 벗어나
- 실제 toe-off / swing 신호가 처음 생기게 만들기

권장 파라미터:

```text
commands:
  rel_standing_envs: 0.6 ~ 0.7
  lin_vel_x:         (0.0, 0.12 ~ 0.15)
  ang_vel_z:         0.0 유지

action:
  scale:             0.05 ~ 0.06

moving env bias 완화:
  feet_on_ground:                  2.0 ~ 3.0
  feet_lift_penalty:              -5.0 ~ -8.0
  contact_foot_velocity_penalty:  -1.0 ~ -2.0
  joint_default_pos:              -1.0 ~ -2.0
  standing_height:                 1.0 ~ 2.0

새 positive swing incentive:
  feet_air_time or clearance/leg_lift
  매우 약한 weight부터 시작
```

핵심:
- negative anti-lift 항을 줄이는 것만으로는 부족
- moving env에서 **양의 swing incentive**를 처음 도입해야 함

### 6.4 V59.E: Controlled Swing

목표:
- 발을 들기만 하는 것이 아니라
- 짧고 안정된 swing을 유지

권장 파라미터:

```text
commands:
  rel_standing_envs: 0.5
  lin_vel_x:         (0.0, 0.18)
  ang_vel_z:         0.0

action:
  scale:             0.06

moving env:
  feet_on_ground:                  1.5
  feet_lift_penalty:              -3.0
  contact_foot_velocity_penalty:  -0.8
  joint_default_pos:              -1.0
  standing_height:                 1.0

positive swing:
  feet_air_time:                   0.10 ~ 0.12
  clearance / leg_lift:            아주 소량 추가
```

성공 기준:
- `swing_time`이 계속 상승
- `contact_ratio`가 추가로 하락
- `clearance`가 front/rear 모두 0 초과
- `feet_lifted`가 다시 급증하지 않음

### 6.5 V59.F: First Gait Pattern

목표:
- swing이 아니라 **패턴**이 생기게 만들기

권장 파라미터:

```text
commands:
  rel_standing_envs: 0.3
  lin_vel_x:         (0.0, 0.22)

gait structure:
  diagonal_coupling:        아주 약하게 도입
  same-side 동시 swing 억제: 아주 약하게 도입
```

원칙:
- trot을 강제하지 않음
- 단지 "패턴 없는 랜덤 swing"에서 벗어나게 만들기

성공 기준:
- `diagonal_coupling > 0`
- 좌우 limb usage가 크게 깨지지 않음
- `ep_len`, `timeout` 급락 없음

### 6.6 V59.G: Robust Small Walk

목표:
- 짧지만 안정된 실제 small walk 형성

권장 파라미터:

```text
commands:
  rel_standing_envs: 0.2
  lin_vel_x:         (0.0, 0.30)
  ang_vel_z:         소량 도입
```

이 단계부터:
- gait quality reward를 조금 더 키움
- 이후 Sim2Real용 torque realism / randomization 단계로 이동

### 6.7 Termination 방향

- `base_contact`, `bad_orientation` 유지
- `feet_lifted`는 moving env에서 단계적으로 완화
- standing env에서는 강하게 유지 가능

즉:
- standing env: 발 들면 거의 실패
- moving env: 짧고 통제된 toe-off는 허용

### 6.8 단계별 성공 판정

V59.D 성공:
- `contact_ratio`가 0.999에서 내려오기 시작
- `swing_time`이 0.001보다 올라오기 시작
- `clearance`가 0에서 생기기 시작
- `ep_len`, `timeout`이 크게 무너지지 않음

V59.E 성공:
- 짧고 안정된 swing 유지
- `feet_lifted` 급증 없음
- clearance가 front/rear 모두에서 재현

V59.F 성공:
- `diagonal_coupling > 0`
- limb usage symmetry 유지
- pattern 없는 랜덤 swing에서 탈피

V59.G 성공:
- 짧지만 실제 gait가 반복적으로 유지
- 이후 torque realism 단계로 옮겨갈 수 있는 수준

```text
이후 단계의 핵심은 "한 번에 걷게 만들기"가 아니라
"toe-off -> controlled swing -> pattern -> small walk"를 분리하는 것
```

---

## 7. 작업 파일

| 파일 | 역할 |
|------|------|
| `source/spot_micro_rl/spot_micro_rl/robots/spot_micro.py` | `merge_fixed_joints=False`, `ImplicitActuator(stiffness=20)` |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py` | V59.B/C 및 이후 branch 설정 |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py` | `feet_lifted_termination(consecutive)`, `contact_foot_velocity_penalty` 등 |

---

## 8. 교훈

```text
1. contact sensor 문제의 핵심은 actuator가 아니라 merge_fixed_joints였다.
2. toe contact dropout은 1-step 즉사로 보면 안 되고 consecutive 방식이 필요하다.
3. 좋은 stand policy를 만드는 것과 첫 swing을 만드는 것은 다른 task다.
4. V59.B 성공은 "잘 선다"의 성공이지 "잘 걷는다"의 성공은 아니다.
5. swing을 원하면 발 들기 손해를 줄이는 것만이 아니라, 잘 들었을 때의 작은 양의 보상이 필요하다.
6. V59.C 하나로 원하는 보행이 바로 나오진 않을 가능성이 높다.
7. 버전 naming은 V59.B(성공 런) -> V59.C(보수적 전환) -> V59.D/E/F/G(진짜 swing/gait curriculum)로 보는 것이 가장 자연스럽다.
```
