# V59 Plan: 실물 서보 기반 Stand-First Locomotion

> 작성: 2026-04-04 ~ 04-05
> 상태: stand test 검증 완료, 훈련 준비
> 목적: 실물 STS3215 서보(3Nm) + 실측 기반 URDF 질량으로 서기 → 보행 학습

---

## 0. 핵심 발견 (2026-04-05)

### URDF 질량이 실물의 3.2배 과대였음

```text
원본 URDF: 5.3kg (mike4192 원본, "masses are guesses and not correct")
실물 추정: ~1.7kg (3D프린트 + 서보 + RPi + 배터리)
수정 후:   1.41kg

핵심: base 링크에 inertial 태그 없음 → PhysX 기본 1.0kg 할당 (추가 발견)
해결: base에 mass=0.001 추가, 전체 링크 질량 실물 기준 재설정
```

### STS3215 서보(3Nm)로 서기 가능 확인

```text
Stand test (effort=3, stiffness=5, damping=0.5, mass=1.41kg):
  안정 높이: 149mm (init 229mm, -35%)
  pitch: -3.0° (거의 수평)
  500 step 안정적 서기
```

---

## 1. 현재 설정 (코드 truth)

```text
[URDF 질량 — 실물 기준]
base:       0.001 kg (더미, fixed joint 루트)
base_link:  0.500 kg (프레임+RPi+배터리+기타)
lidar:      0.170 kg (RPLidar A1)
front/rear: 0.060 kg each (3D프린트 커버)
shoulder:   0.065 kg x4 (서보 55g + 프린트 10g)
leg:        0.040 kg x4
foot:       0.040 kg x4
toe:        0.010 kg x4
TOTAL:      1.41 kg
URDF velocity: 100 (PhysX maxJointVelocity)

[Actuator — STS3215 실제 스펙]
type:             DCMotor
effort_limit:     3.0 Nm (30kg·cm @ 12V)
saturation:       3.0 Nm
stiffness:        5.0
damping:          0.5
velocity_limit:   19.0 rad/s

[Init pose — 대칭 Z-bend, toe under shoulder]
init_z:     0.229 (FK 정확히)
shoulder:   ±0.05 (3° 벌림)
leg:        -0.52 (29.8°)
foot:       1.04 (59.6°, foot=-2*leg)

[Env — V59 stand-first]
action_scale:     0.03
action_warmup:    5 steps
commands:         vel=0, standing=100%
min_height:       0.13 (loaded eq=149mm, 19mm 여유)
bad_orientation:  0.6 (34°)
```

---

## 2. 경과

### V59 시행착오 (2026-04-04~05)

```text
1. ImplicitActuator stiffness=20 → stand 성공, 하지만 effort_limit 무시 (비현실적)
2. DCMotor effort=15, stiffness=20 → 너무 튕김
3. Go2 비율 스케일링 (effort=8.3, stiffness=9) → 주저앉음
4. effort=3, stiffness=3~15 다양 시도 → 전부 75mm로 붕괴
5. URDF mass 5.3kg 발견 → 실물 1.7kg의 3.2배 과대!
6. base 링크 1.0kg 기본값 발견 → inertial 태그 추가
7. 질량 수정 후 effort=3, stiffness=5 → 149mm 안정 서기!
```

### 핵심 교훈

```text
1. URDF mass가 모든 문제의 근원이었음
   - "서보 토크 부족"이 아니라 "로봇이 3배 무거웠음"
   - mike4192 원본부터 잘못된 추정치를 모든 fork가 상속

2. base 링크 (URDF 루트) inertial 누락 → PhysX 1kg 기본값
   - 눈에 안 보이는 1kg이 총 질량을 2.4kg→1.4kg으로 바꿈

3. force_usd_conversion=True는 USD를 새로 만들지만
   - base 링크 inertial이 없으면 PhysX가 기본값을 넣음
   - URDF 수정 + USD 캐시 삭제 모두 필요
```

---

## 3. 판단 기준

### 성공 (iter 500)
- ep_len > 500
- time_out > 50%
- bad_orientation < 10%
- pitch < 10° (거의 수평)

### 다음 단계
서기 성공 → vel 명령 추가 → 보행 학습 (표준 locomotion)
```

---

## 4. 변경 파일

| 파일 | 변경 |
|------|------|
| `spotmicroai_realistic_inertia.urdf` | 전체 질량 실물 기준 재설정 (5.3→1.41kg), base inertial 추가, velocity 100 |
| `robots/spot_micro.py` | DCMotor effort=3/stiffness=5/damping=0.5, 대칭 Z-bend, shoulder=±0.05 |
| `spot_micro_rl_env_cfg.py` | V59 stand-first 블록, min_height=0.13, posture_violation 삭제 |
| `mdp/rewards.py` | flat_orientation_bonus, shoulder_torque_saturated 추가 |
