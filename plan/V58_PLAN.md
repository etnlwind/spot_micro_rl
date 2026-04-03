# V58 Plan: Isaac Lab 표준 Locomotion 복귀

> 작성: 2026-04-03
> 상태: V58.B1 구현 완료, fresh run 재검증 단계
> 목적: V57.B1 stand-first 실패 후, Isaac Lab 표준 locomotion 구조로 전환. 77개 heuristic을 10개 표준 reward로 교체.

---

## 0. 현재 구현 기준 요약 (2026-04-03 최신)

아래 값이 **현재 코드 truth**이며, 이하 초기 초안 내용보다 우선한다.

### 0.1 현재 V58.B1 구현

```text
TRAIN_VERSION:        V58.B1

[Actuator]
type:                 IdealPDActuatorCfg
effort_limit:         25.0
stiffness:            shoulder=10, leg=20, foot=6
damping:              shoulder=3, leg=4, foot=2

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
bad_orientation:      0.7 rad
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
1. ImplicitActuator:
   - 학습은 잘 살았지만 GUI에서 물리적으로 과하게 버티는 자세가 관찰됨
   - "잘못된 자세 survival" 리스크 때문에 제외

2. IdealPDActuator + effort_limit=15:
   - 더 honest하지만 bad_orientation으로 거의 즉사
   - min_height/base_contact보다 orientation collapse가 먼저 발생

3. 따라서 현재 V58.B1:
   - IdealPD 유지
   - effort_limit을 25로 올려 복원 토크 여유 확보
   - termination은 다시 strict(0.7) 유지
   - 대신 action/command를 보수적으로 줄여 bootstrap 안정성 확보
```

### 0.3 현재 해석

```text
현재 V58.B1의 핵심 병목은 "낮아서 죽음"이 아니라
"복원 전에 기울어져 bad_orientation으로 잘리는 것"이다.

따라서 bootstrap 단계의 해법은
- termination을 계속 느슨하게 푸는 것보다
- IdealPD에 토크 여유를 더 주고
- action/command disturbance를 줄이는 것
으로 본다.
```

### 0.4 문서 읽는 법

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

## 2. V57.B1 대비 핵심 변경

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

## 3. Reward 구조 (10개)

### Per-step Net Reward 검증

| 시나리오 | 양수 합 | 음수 합 | NET | 판정 |
|----------|---------|---------|-----|------|
| 서기 (초기) | +1.03 | -0.10 | **+0.93** | PASS |
| 보행 (중기) | +0.86 | -0.27 | **+0.60** | PASS |
| 넘어짐 | +0.30 | -1.75 | **-1.45** | 올바른 gradient |

### Reward Table

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

## 5. 환경 설정

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

## 7. Isaac Lab 표준과의 차이점 (3개만)

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

## 10. 첫 런 결과 (iter 43, 2026-04-03 12:51)

```text
ep_len:              954 steps (95% 생존!)
bad_orientation:     5.4%
time_out:            94.6%
per-step reward:     +0.009 (양수 → die-fast 아님!)
track_lin_vel_xy:    +0.792 (초기값)
track_ang_vel_z:     +0.223

관찰: "제자리에 서있음" — iter 43에서는 정상
      50% standing 명령 + policy가 아직 velocity tracking 미학습

V57.B1 대비: ep_len 1→954, die-fast→양수reward — 완전히 다른 세계
```

---

## 11. 전체 로드맵: Sim 성공 → Sim2Real

### 현재 위치

```text
[V58] sim에서 걷기 성공시키기 (이상적 환경)  ← 지금 여기
```

### Phase 1: Sim 내 Locomotion 확립 (V58.x)

```text
V58:     표준 reward 11개 + IdealPDActuator + strict termination
         → 서기 + 걷기 자연 발현
V58.1:   shoulder_neutral 추가 (if splay 확인)
V58.2:   base_height_l2 추가 (if 높이 부족)
V58.3:   phase_clock 도입 (if trot 자연 발현 안 됨)
V58.4:   rough terrain 도입 (if flat에서 안정적)
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
  → effort_limit 미적용 → 비현실적 자세 유지 문제
  → 주저앉아도 사망 안 함

3차: IdealPDActuatorCfg (최종) ★
  → effort_limit=15 실제 적용 (비현실적 자세 자연 붕괴)
  → velocity saturation 없음 (bang-bang 방지)
  → V58의 양수 reward 구조에서 die-fast 안 함
```

---

## 13. V58 Termination 변경 이력 (2026-04-03)

```text
1차: min_height=None, bad_orientation=1.5 → 넘어져도 생존
2차: min_height=0.10, bad_orientation=0.7 → 여전히 웅크림 생존
3차: min_height=0.12, bad_orientation=0.5 → 아직 주저앉음 생존
4차: min_height=0.13 + base_contact 복원 → 부분 개선
5차: min_height=0.14, base_contact(base+shoulder+leg), bad_orientation=0.5 (최종) ★
  → 주저앉으면 height<0.14 → 사망
  → body/어깨/윗다리 접촉 → 사망
  → 30° 기울어짐 → 사망
  → per-step 양수 reward라 strict해도 die-fast 안 함
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
