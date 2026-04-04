# V58 Plan: Isaac Lab 표준 Locomotion 복귀

> 작성: 2026-04-03
> 상태: V58.B1 학습 진행 중, rollout/velocity tracking 성공
> 목적: V57.B1 stand-first 실패 후, Isaac Lab 표준 locomotion 구조로 전환. 77개 heuristic을 10개 표준 reward로 교체.

---

## 0. 현재 구현 기준 요약 (2026-04-03 최신)

아래 값이 **현재 코드 truth**이며, 이하 초기 초안 내용보다 우선한다.

### 0.1 현재 V58.B1 구현

```text
TRAIN_VERSION:        V58.B1

[Actuator]
type:                 ImplicitActuatorCfg
effort_limit:         15.0
stiffness:            shoulder=12, leg=28, foot=8
damping:              shoulder=4, leg=5, foot=2

[Init pose]
init_z:               0.185
shoulder:             ±0.04
leg:                  -0.70
foot:                 1.35

[Control / Commands]
action_scale:         0.30
episode_length:       20.0 s
rel_standing_envs:    0.2
rel_heading_envs:     0.5
lin_vel_x:            (0.0, 0.3)
lin_vel_y:            (0.0, 0.0)
ang_vel_z:            (-0.2, 0.2)

[Reset / Termination]
joint position range: (0.8, 1.2)
joint velocity range: (0.0, 0.0)
min_height:           0.12
bad_orientation:      1.1 rad
base_contact:         ON (base_link|.*shoulder_link|.*leg_link)

[Rewards]
track_lin_vel_xy_exp: +1.0
track_ang_vel_z_exp:  +0.5
feet_air_time:        +0.05
lin_vel_z_l2:         -2.0
ang_vel_xy_l2:        -0.05
action_rate_l2:       -0.01
dof_acc_l2:           -2.5e-7
dof_torques_l2:       -1e-5
undesired_contacts:   -1.0
flat_orientation_l2:  -0.5
standing_height:      +0.5, target=0.18, sigma=0.05
                      standing_vel_threshold=0.05 (standing env만 적용)
```

### 0.2 왜 이렇게 바뀌었나

```text
1. 초기 V58 (Implicit):
   - 학습 rollout은 잘 살았지만 GUI에서 물리적으로 과하게 버티는 자세가 관찰됨

2. V58.B1 1차 (IdealPD):
   - 더 honest하지만 bad_orientation으로 거의 즉사
   - effort_limit 15→25로 올려도 ep_len/track reward가 오히려 악화
   - 즉 문제는 "토크 절대량 부족" 하나로 설명되지 않음

3. 따라서 현재 V58.B1:
   - locomotion bootstrap용 actuator를 다시 Implicit로 복귀
   - 대신 bad_orientation을 보조로 완화(1.1)하고
   - 실제 실패는 min_height/base_contact로 자르도록 재정렬
   - action/command는 계속 보수적으로 유지
```

### 0.3 현재 해석

```text
현재 V58.B1의 핵심 병목은 "낮아서 죽음"보다
"orientation gate가 실제 엎드림보다 먼저 잘라 rollout이 죽는 것"에 더 가깝다.

따라서 현재 bootstrap 해법은
- IdealPD를 더 미는 것보다
- Implicit로 살아 있는 rollout을 확보하고
- 나쁜 자세는 min_height/base_contact로 자르며
- action/command disturbance를 줄이는 것
으로 정리한다.
```

### 0.4 현재 런 상태 (2026-04-03 15:07:44)

최신 fresh run 기준:

```text
ep_len:               964.7
mean_reward:          +27.0
time_out:             96.9%
bad_orientation:      0.48%
min_height:           0.0%
base_contact:         2.98%
track_lin_vel_xy:     0.903
track_ang_vel_z:      0.444
standing_height:      0.097
```

해석:

```text
1. V57/V58 실패 구간은 벗어남
   - die-fast 해소됨
   - 대부분 timeout까지 생존
   - velocity tracking 정상 작동

2. 현재 남은 주된 리스크는 base_contact
   - orientation 문제는 사실상 해결
   - min_height도 거의 발생 안 함
   - 일부 env에서 몸통/다리 접촉이 잔존할 가능성 있음

3. 현재 단계 판단
   - 지금은 런을 건드리지 않고 계속 가는 게 맞음
   - 체크 포인트는 bad_orientation이 아니라 base_contact와 gait quality
```

### 0.5 다음 단계 후보 (V58.B2)

현재 런은 살아 있지만, GUI/추가 분석상 일부 env가
`발을 거의 안 들고 뒤다리로 끄는 drag propulsion`일 가능성이 있다.

따라서 **현재 런은 iter 1000까지 유지**하고,
다음 실험 트랙 V58.B2 후보는 아래 우선순위로 본다.

```text
1. feet_air_time 강화
   - weight:    0.05 → 0.15~0.20
   - threshold: 0.5  → 0.2

2. standing_height 소폭 강화
   - weight: 0.5 → 1.0
   - 단, standing_vel_threshold command gate는 유지

3. diagonal_coupling / gait-shaping은 마지막
   - 발을 들기 시작한 뒤에도 drag가 남을 때만 검토
   - 현재 단계에서 바로 넣으면 reward 구조가 다시 복잡해질 수 있음
```

### 0.6 문서 읽는 법

이 문서의 이하 섹션 중
- ImplicitActuator
- action_scale 0.5
- rel_standing_envs 0.5
- bad_orientation 1.5
같은 값은 **초기 V58 초안 기록**일 수 있다.

현재 설계/코드/실험 기준은 반드시 **Section 0**을 우선한다.

---

## 1. 왜 V58인가

### V57.B1의 교훈

```text
1. 물리 디버깅은 성공:
   - URDF velocity 10→20 (bang-bang 해결)
   - init_z에 toe sphere radius 포함
   - DCMotor velocity saturation이 standing의 구조적 병목임을 규명
   - ImplicitActuator로 zero-action standing 달성 (height=0.1441 완벽 정지)

2. 하지만 stand-first RL 학습은 실패:
   - IdealPDActuator + stand-only reward → die-fast (per-step reward 음수)
   - penalty가 Isaac Lab 표준 대비 10~50배 과다
   - joint_vel_l2(-0.1)가 die-fast의 61% 지배
   - ang_vel_xy(-0.5), action_rate(-0.5) 등도 표준 대비 극도로 과다

3. 핵심 깨달음:
   - 물리가 정상이면 표준 구조가 작동한다
   - 77개 heuristic보다 표준 10개 reward가 낫다
   - stand-first보다 velocity tracking이 더 자연스러운 학습 경로
```

### V58의 철학

```text
"Isaac Lab 표준을 신뢰하고, SpotMicro 크기만 보정한다."
```

---

## 2. V57.B1 대비 핵심 변경 (초기 V58 초안 기록)

| 항목 | V57.B1 | V58 | 이유 |
|------|--------|-----|------|
| Actuator | IdealPD (effort=15) | **ImplicitActuator (effort=15)** | PhysX 연속시간 PD, 표준 |
| Reward 수 | 14개 custom | **10개 표준** | heuristic 제거 |
| 주연 reward | standing_height(+5.0) | **track_lin_vel(+1.0)** | velocity tracking |
| 명령 | vel=0 (서기만) | **vel=0~0.5 + standing 50%** | locomotion |
| action_scale | 0.25 | **0.5** | 표준값 |
| Episode | 10s | **20s** | 표준값 |
| Joint randomization | OFF (1.0,1.0) | **ON (0.7,1.3)** | 표준 |
| Penalty 수준 | 10~50배 과다 | **Isaac Lab 표준** | die-fast 방지 |

---

## 3. Reward 구조 (초기 V58 초안 vs 현재 B1)

### Per-step Net Reward 검증

| 시나리오 | 양수 합 | 음수 합 | NET | 판정 |
|----------|---------|---------|-----|------|
| 서기 (초기) | +1.03 | -0.10 | **+0.93** | PASS |
| 보행 (중기) | +0.86 | -0.27 | **+0.60** | PASS |
| 넘어짐 | +0.30 | -1.75 | **-1.45** | 올바른 gradient |

### Reward Table (초기 V58 초안 기록)

```text
[양수 — 주연]
track_lin_vel_xy_exp:  +1.0    (std=0.5)
track_ang_vel_z_exp:   +0.5    (std=0.5)
feet_air_time:         +0.125  (sensor: .*foot_link, threshold=0.5)

[음수 — Isaac Lab 표준 수준]
lin_vel_z_l2:          -2.0
ang_vel_xy_l2:         -0.05   (V57.B1은 -0.5로 10배 과다였음)
action_rate_l2:        -0.01   (V57.B1은 -0.5로 50배 과다였음)
dof_acc_l2:            -2.5e-7
dof_torques_l2:        -1e-5
undesired_contacts:    -1.0    (base_link|shoulder|leg)

[SpotMicro 전용]
flat_orientation_l2:   -0.5    (표준은 0.0, SpotMicro는 가벼워서 필요)
```

### 현재 V58.B1 reward 실제값

```text
track_lin_vel_xy_exp:  +1.0
track_ang_vel_z_exp:   +0.5
feet_air_time:         +0.05   (sensor: .*foot_link, threshold=0.5)
lin_vel_z_l2:          -2.0
ang_vel_xy_l2:         -0.05
action_rate_l2:        -0.01
dof_acc_l2:            -2.5e-7
dof_torques_l2:        -1e-5
undesired_contacts:    -1.0
flat_orientation_l2:   -0.5
standing_height:       +0.5, target=0.18, sigma=0.05
                      standing_vel_threshold=0.05
```

---

## 4. 물리 설정 (V57 디버깅 성과 유지)

```text
Actuator:              ImplicitActuatorCfg
effort_limit:          15.0 (V57 검증 연속성)
stiffness:             shoulder=12, leg=28, foot=8
damping:               shoulder=4, leg=5, foot=2
init_z:                0.185
init pose:             leg=-0.70, foot=1.32 (Z자형)
URDF velocity:         20.0
max_depenetration:     0.2
soft_joint_pos_limit:  0.7
```

---

## 5. 환경 설정 (초기 V58 초안 기록)

```text
decimation:            4 (50Hz)
episode_length:        20s
action_scale:          0.5

[Commands]
rel_standing_envs:     0.5 (50% standing, 50% velocity)
lin_vel_x:             (0.0, 0.5)
lin_vel_y:             (0.0, 0.0)
ang_vel_z:             (-0.5, 0.5)

[Events]
position_range:        (0.7, 1.3)  (foot soft limit 보호)
velocity_range:        (0.0, 0.0)
push_robot:            None (SpotMicro 가벼워서 비활성)

[Terminations]
min_height:            0.10
bad_orientation:       1.5 rad (~86°, parent default)
shoulder_splay:        None

[Curriculum]
없음 (flat reward landscape)

[Observations]
phase_clock:           OFF
```

---

## 6. Contact Sensor 중요 사항

```text
merge_fixed_joints=True → toe_link가 foot_link에 병합
→ body_names=".*toe_link"는 작동 안 할 수 있음
→ V58에서는 ".*foot_link" 사용 (Isaac Lab SpotMicro 공식 예제와 동일)

feet_air_time.sensor_cfg = SceneEntityCfg("contact_forces", body_names=".*foot_link")
undesired_contacts.sensor_cfg = SceneEntityCfg("contact_forces", body_names="base_link|.*shoulder_link|.*leg_link")
```

---

## 7. Isaac Lab 표준과의 차이점 (초기 V58 초안 기록)

| # | 항목 | Isaac Lab 표준 | V58 | 이유 |
|---|------|---------------|-----|------|
| 1 | flat_orientation_l2 | 0.0 (비활성) | **-0.5** | SpotMicro 5.3kg, roll/pitch 취약 |
| 2 | rel_standing_envs | 0.0 | **0.5** | 서기 우선 학습 |
| 3 | position_range | (0.5, 1.5) | **(0.7, 1.3)** | foot soft limit 보호 |

나머지는 **100% Isaac Lab 표준**.

---

## 8. 성공 기준

### iter 100 (boot viability)
```text
- ep_len > 500 유지
- bad_orientation < 20%
- track_lin_vel_xy > 0.3 (올라오기 시작)
```

### iter 300 (locomotion emergence)
```text
- track_lin_vel_xy > 0.5
- ep_len 유지
- GUI: 일부 로봇이 앞으로 이동 시작
- 셔플링이 아닌 실제 전진
```

### iter 1000 (stable gait)
```text
- track_lin_vel_xy > 0.7
- 안정적 trot 패턴
- 영상: 자연스러운 4족 보행
```

현재 상태:

```text
track_lin_vel_xy ≈ 0.90  → PASS
time_out ≈ 0.97          → PASS
bad_orientation < 1%     → PASS
남은 과제: base_contact / drag propulsion 여부
```

---

## 9. 실패 시 대응 (V58.1)

문제가 확인되면 한 항목씩 추가:

```text
V58.1: shoulder_neutral(-1.0) 추가  (if splay > 0.15)
V58.2: base_height_l2(-1.0) 추가    (if height < 0.15)
V58.3: push_robot 복원              (if robustness 부족)
V58.4: rel_standing_envs 0.5→0.8    (if standing 불안정)
```

**원칙: 먼저 표준만으로 돌려보고, 데이터로 확인된 문제만 한 항목씩 추가.**

---

## 10. 첫 런 결과 (초기 V58, iter 43, 2026-04-03 12:51)

```text
ep_len:              954 steps (95% 생존!)
bad_orientation:     5.4%
time_out:            94.6%
per-step reward:     +0.009 (양수, die-fast 해소 확인)
track_lin_vel_xy:    +0.792 (초기값)
track_ang_vel_z:     +0.223

관찰: "제자리에 서있음" — iter 43에서는 정상
      50% standing 명령 + velocity tracking 미학습 단계

V57.B1 대비: ep_len 1→954, die-fast→양수reward — 완전히 다른 세계
```

---

## 11. 전체 로드맵: Sim 성공 → Sim2Real

### 현재 위치

```text
[V58.B1] 살아 있는 locomotion rollout 확보 + tracking 성공
[V58.B2] drag propulsion 제거 / gait quality 개선  ← 다음 후보
```

### Phase 1: Sim 내 Locomotion 확립 (V58.x)

```text
V58.B1:  locomotion bootstrap 확보
         → timeout 90%+, track_lin_vel ~0.9
V58.B2:  feet_air_time / standing_height 미세조정
         → drag propulsion 제거, 발 들기 유도
V58.B3:  필요시 diagonal_coupling/phase 계열 최소 도입
         → trot quality 향상
V58.B4:  flat 안정화 후 rough terrain / robustness
```

### iter 800+ 심층 분석: drag propulsion 진단

현재 B1은 생존 및 tracking에 성공했으나, gait quality는 미완성 상태이다.

관찰/진단:

```text
- track_lin_vel_xy는 높음 (~0.9)
- 하지만 feet_air_time은 거의 0
- diagonal/trot pattern 미출현
- 일부 env는 rear-heavy contact 편향과 drag propulsion 징후
```

해석:

```text
현재 B1의 역할:
- die-fast 제거
- 살아 있는 locomotion rollout 확보
- velocity tracking을 실제로 붙이기

현재 B1의 한계:
- 정상 보행 대신 drag propulsion 해가 잔존
```

따라서 B2의 우선순위는:

```text
1. feet_air_time 강화
2. standing_height 소폭 강화
3. 그래도 drag가 남으면 diagonal_coupling/gait shaping 검토
```

### 역대 문제 vs V58 대응 전략

V1~V57에서 반복된 핵심 문제들과 V58의 대응:

```text
[V58.B2가 해결하는 것]
✅ Die-fast (V57.B1)        → per-step 양수 reward
✅ 77개 heuristic 충돌      → 11개로 축소
✅ Drag propulsion (V58.B1) → feet_air_time 4배 강화 + threshold 절반

[V58.B2 이후 데이터 확인 후 대응할 것]
❓ Splay (V37.2, dev=0.53)  → B3에서 shoulder_neutral 추가 (재발 확인 시)
❓ Front lock-in (V23~V31)  → B4에서 per-leg reward 검토 (재발 확인 시)
❓ Rear collapse (V57+)     → 필요시 rear-specific 보상

[V58 원칙]
한 번에 다 해결하려면 다시 77개로 돌아간다.
한 문제씩, 데이터 기반으로.

순서: 발 들기(B2) → splay(B3) → front/rear 비대칭(B4) → gait quality(B5)
발을 안 드는데 splay를 걱정하는 건 순서가 맞지 않다.
```

### Phase 2: Sim2Real 준비 (V59)

```text
V59.1: Domain Randomization 강화
  - push_robot 복원 (외부 힘 랜덤)
  - mass randomization 확대 (±20%)
  - friction randomization (0.5~1.2)
  - COM randomization 확대
  - 지면 불규칙성 추가 (noise terrain)

V59.2: Actuator 현실화
  - IdealPD → DCMotor (velocity-torque curve)
  - 실제 서보 스펙 반영 (SG90/MG996R)
  - 서보 응답 지연 모델 (10~50ms latency)
  - 백래시/데드존 추가

V59.3: Sensor 현실화
  - 관절 위치/속도 observation noise 추가
  - IMU noise 추가
  - 통신 지연 모델
```

### Phase 3: 실기 전송 (V60+)

```text
V60.1: 실기 하드웨어 인터페이스
  - ROS2 또는 직접 시리얼 통신
  - 관절 명령 → 서보 PWM 변환
  - 센서 데이터 수신 파이프라인

V60.2: Zero-shot Transfer 시도
  - sim policy를 실기에 직접 전송
  - 성능 gap 측정
  - 실패 모드 분석

V60.3: Fine-tuning
  - sim2real gap에 따라 domain randomization 조정
  - 필요시 실기 데이터로 fine-tuning
```

### 현재 V58에 없는 Sim2Real 요소 (의도적)

```text
[Actuator] 실제 서보 torque-speed curve, 응답 지연, 백래시 → V59.2
[Randomization] 외부 힘, 큰 질량/마찰 변화, terrain → V59.1
[Sensor] observation noise, IMU noise, 통신 지연 → V59.3
[Hardware] ROS2 인터페이스, 서보 제어 → V60.1

이유: sim에서 먼저 걷기를 성공시킨 후, 현실성 요소를 단계적으로 추가.
한번에 넣으면 디버깅 불가능.
```

---

## 12. V58 Actuator 변경 이력 (2026-04-03)

```text
1차: DCMotorCfg (V57 계승)
  → bang-bang 진동 (velocity saturation)

2차: ImplicitActuatorCfg (zero-action standing 달성)
  → rollout/standing은 잘 살았지만 GUI에서 과하게 버티는 자세 관찰

3차: IdealPDActuatorCfg
  → 더 honest한 actuator를 기대했으나
  → bad_orientation 즉사 (effort_limit=15)

4차: IdealPDActuatorCfg + effort_limit=25
  → 토크 여유를 늘려도 ep_len/track reward가 오히려 악화
  → "토크 절대량 부족" 가설 기각

5차: ImplicitActuatorCfg 복귀 (현재) ★
  → locomotion bootstrap에서 다시 살아 있는 rollout 확보
  → 잘못된 자세는 actuator가 아니라 termination/reward 쪽에서 제어
```

---

## 13. V58 Termination 변경 이력 (2026-04-03)

```text
1차: min_height=None, bad_orientation=1.5 → 넘어져도 생존
2차: min_height=0.10, bad_orientation=0.7 → orientation 즉사 여전
3차: min_height=0.12 + base_contact 복원 → 실제 엎드림/몸통 접촉 terminate
4차: bad_orientation=0.7 strict 유지 + IdealPD 테스트
  → 거의 전부 bad_orientation으로 조기 종료
5차: bad_orientation=1.1 완화 + base_contact/min_height 중심 (현재) ★
  → orientation은 보조
  → 실제 실패는 height/contact로 자름
  → timeout 90%+의 살아 있는 rollout 확보
```

---

## 14. V57 물리 디버깅 성과 참조

> 상세: plan/V57_ZERO_STAND_DEBUG.md (20개 테스트, 시간순)

```text
근본 원인 3개 발견 및 해결:
1. init_z에 toe sphere radius 미포함 → 20mm 관통
2. URDF velocity = DCMotor velocity_limit = 10 → bang-bang 진동
3. DCMotor velocity-dependent saturation → crouched equilibrium

해결: ImplicitActuator 전환 + URDF vel=20 + init_z=0.185 + depenetration=0.2
```

---

## V58 종료 및 V59 전환 (2026-04-04)

### V58 시리즈 결론

```text
V58.B1: 표준 locomotion 복귀 → rollout 성공, drag propulsion 잔존
V58.B2: feet_air_time 강화 → drag 개선 시도
V58.B3: 과도한 penalty → die-fast 재발
V58.B4: 3-Phase 서기→보행 curriculum → 서기 자체가 불안정

핵심 실패 원인:
1. ImplicitActuator + 비균일 PD (foot=8) → 관절 붕괴로 주저앉음
2. 비대칭 init pose (foot=0.87) → CoM-support polygon 불일치
3. 서기/보행 분리 curriculum → 표준 예제는 분리하지 않음
```

### V59 전환 근거

```text
1. Isaac Lab 표준 4족 로봇(Go2, A1)은 전부 DCMotor + 균일 PD + 표준 locomotion
2. "서기가 너무 쉽다"는 문제가 아니라 전제 — 서기가 안 되면 학습 자체가 불가
3. 대칭 Z-bend (foot=-2*leg) → toe가 shoulder 아래, 기하학적 균형
4. DCMotor stiffness=20 전관절 동일 → zero-action에서도 1000 step 서기 확인
```

→ V59_PLAN.md 참조
