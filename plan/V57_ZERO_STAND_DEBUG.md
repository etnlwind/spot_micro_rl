# V57 Zero-Action Stand Debug Log

## 날짜: 2026-04-03


## 목표
SpotMicro가 zero-action(action=0)으로 서 있을 수 있는지 확인한다.
4족 로봇은 support polygon 안에 CoM이 있으면 테이블처럼 수동적으로 서 있을 수 있어야 하며,
서 있지 못할 경우 물리 설정에 문제가 있는 것으로 판단한다.

---

## 배경
- V57.B1: stand-first bootstrap (걷기 전에 서기부터)
- 이전 세션에서 FK calibration + 대칭 init pose 완성
- init_z=0.194, stiffness=16, damping=2, effort_limit=15
- zero_stand_probe로 테스트한 결과 로봇이 서 있지 못하여, 본 디버깅 세션 개시

---

## 테스트 환경
- `scripts/utils/zero_stand_probe.py`: action=0을 매 step 전송하고 joint/torque/contact 기록
- headless 모드 (`cmd.exe /c` 통해 WSL→Windows 실행)
- 16 envs, Isaac Lab + PhysX, decimation=4 (50Hz), step_dt=0.02s
- DCMotor actuator: `target = raw_action * scale + offset`
  - scale=1.0, offset=default_joint_pos=init_pos (확인 완료)
  - action=0 → target = init_pos

---

## 시간순 테스트 기록

### Test 1: 기존 설정 확인 (init_z=0.194, Kp=16, Kd=2, effort=15)

**가설**: 이전 세션에서 실패했던 설정 재확인

**로그**: `logs/diagnostics/zero_probe_latest.log`

**결과**:
```
step=1:   height=0.2030 (init 0.194에서 상승), ang_xy=3.79, toe_fz=ALL 0.0
step=10:  rear_left_leg=-1.37 (init -0.70), rear_right_leg=-2.17 (폭주)
step=50:  terminated=6.25%, height=0.108
step=90:  terminated=50%, height=0.104
step=100: terminated=44%, height=0.108, mean_ep_len=15
```

**관찰**:
1. Step 1에서 height가 0.194→0.203으로 **상승** (9mm) — 상향 반발력 발생
2. 후방 다리 토크 step 1부터 포화:
   - rear_left_foot_torque=-15.0 (포화)
   - rear_right_foot_torque=-15.0 (포화)
   - rear_right_leg_torque=15.0 (포화)
3. 전방 다리는 상대적으로 안정, 후방이 먼저 붕괴
4. **모든 개별 toe_fz = 0.0** (하지만 toe_contact_mean=0.0476 > 0)
5. 비대칭: 후방 > 전방, 우측 > 좌측 순으로 불안정

**초기 분석**:
- height 상승 → 지면에서 밀어올림 → toe sphere가 지면에 관통된 것으로 추정
- toe_fz=0인데 toe_contact_mean>0 → 센서 인덱싱 문제 의심

---

### URDF 질량 분석

robot.py, URDF 확인:

**총 질량 5.30 kg**:
- base_link: 2.80 kg
- lidar_link: 0.50 kg (base 위, z+0.035)
- rear_link: 0.20 kg (base 뒤)
- front_link: 0.20 kg (base 앞)
- 다리 × 4: shoulder 0.10 + leg 0.15 + foot 0.10 + toe 0.05 = 0.40 kg/leg = 1.60 kg

**merge_fixed_joints 후 base 합성 질량**: 2.80 + 0.50 + 0.20 + 0.20 = 3.70 kg
**다리당 지지 하중**: 5.30/4 = 1.325 kg = ~13 N

**정적 torque 추정**:
- 다리당 13 N × lever arm (~0.05m max) = ~0.65 Nm
- effort_limit 15 Nm 대비 4.3% → **정적으로는 충분**

---

### 핵심 발견: toe sphere 지면 관통

**FK 계산**:
- toe link center: body_z - 0.1937m below
- init_z=0.194 → toe link center z = 0.194 - 0.1937 = 0.0003m (지면 위 0.3mm)

**URDF toe collision**: sphere radius = 0.02m
- sphere 바닥 = 0.0003 - 0.02 = **-0.0197m (지면 아래 20mm)**

**이것이 step 1 height 상승의 원인으로 확인됨.**
- PhysX가 관통 해소하며 로봇을 위로 밀어올림
- max_depenetration_velocity=1.0 제한이 있지만 impulse 발생

---

### Test 2: effort_limit=50 (토크 포화 가설 검증)

**가설**: 후방 다리 토크가 15 Nm에서 포화되어 position hold 실패. effort를 올리면 해결되는지 확인.

**변경**: saturation_effort=50, effort_limit=50 (나머지 동일)

**로그**: `logs/diagnostics/zero_probe_effort50.log`

**결과**:
```
step=1:  rear_left_foot_torque=-19.91 (이전 -15.0), rear_right_foot=-15.65
step=10: 다수 관절 20-25 Nm, rear_right_leg=25.96
step=50: terminated=37.5% (이전 6.25% 대비 6배 악화)
step=70: terminated=68.8%
```

**결론**: **토크 포화가 원인이 아닌 것으로 판명.** 높은 토크 → 높은 반발 에너지 → 심한 진동 → 조기 종료.

**원복**: effort=15로 복원

---

### Test 3: init_z=0.22 (toe sphere clearance 확보)

**가설**: 20mm 관통이 문제. init_z를 올려서 toe sphere가 지면 위에 있게 하면 해결되는지 확인.

**변경**: init_z=0.22 (sphere 바닥 = 0.22 - 0.194 - 0.02 = +0.006m, 6mm 여유)

**로그**: `logs/diagnostics/zero_probe_z022.log`

**결과**:
```
step=1:  height=0.203 (0.22에서 17mm 하락), ang_xy=?? (이전 로그에서 미기록)
step=50: terminated=0% (개선)
step=80: terminated=50%
step=100: terminated=31%
```

**관찰**:
- 50 step까지 생존 (이전 6.25% → 0%) — 관통 제거 효과 확인
- 그러나 이후 불안정해짐
- RL_toe만 간헐적 접촉 (fz=9.96 at step 30), FL/FR/RR = 0 지속

---

### Test 4: stiffness=40, damping=5, effort=25 (강한 PD)

**가설**: PD가 너무 약해서 position hold 실패. 더 강한 PD로 해결 가능한지 확인.

**변경**: Kp=40, Kd=5, effort=25, init_z=0.22

**로그**: `logs/diagnostics/zero_probe_strong_pd.log`

**결과**:
```
step=1:  height=0.203, 대부분 토크 포화 (±25)
step=20: many joints at ±25 Nm saturated, rear legs to -2.2
step=50: terminated=6.25% → step=90: 56%
```

**결론**: 강한 spring이 접촉 impulse를 증폭. 강한 PD가 안정성을 향상시키지 않는 것으로 확인됨.

---

### Test 5: fix_base=True (body 고정, 다리만 테스트)

**가설**: body 움직임을 제거하고 다리 PD만 고립 테스트

**변경**: fix_base=True, Kp=16, Kd=2, effort=15, init_z=0.22

**로그**: `logs/diagnostics/zero_probe_fixbase.log`

**결과 (200 steps, terminated=0% 전체)**:
```
step=1:
  FL_shoulder=-0.032, FL_leg=-0.734, FL_foot=1.381
  FL_shoulder_torque=1.05, FL_leg_torque=6.55, FL_foot_torque=6.48

step=10:
  FL_foot=1.510, FL_foot_torque=15.0 (포화)
  FL_leg=-0.829, FL_leg_torque=10.69

step=100:
  FL_foot=1.528, FL_foot_torque=15.0 (여전히 포화)
  FL_leg=-0.889, FL_leg_torque=12.11
  FL_shoulder=+0.046 (init -0.04에서 부호 반전)

step=160:
  FL_foot=1.528, FL_foot_torque=15.0
  FL_leg=-0.922, FL_leg_torque=12.56
```

**핵심 발견**:
1. **완벽 대칭**: 4다리 모두 동일한 joint angle/torque (L/R 부호만 반대)
2. **Foot torque = +15.0 (포화)** — 모든 4다리, step 10부터 끝까지
3. **Leg이 느리게 드리프트**: -0.70 → -0.92 (200 steps에 걸쳐)
4. **Foot도 드리프트**: 1.32 → 1.528 (step 10 이후 정체)
5. **Shoulder 부호 반전**: init FL=-0.04 → +0.046

**수치 검증 (핵심 미해결 사항)**:

Foot at step 100: current=1.528, target=1.32 (offset 확인됨)
- PD torque = 16 × (1.32 - 1.528) = 16 × (-0.208) = **-3.33 Nm**
- Velocity ≈ 0 (quasi-static) → damping ≈ 0
- 예상 total = **-3.33 Nm**
- **실제 reported = +15.0 Nm** ← 부호 반대, 크기 4.5배

Gravity torque on foot (no ground contact, free hanging):
- distal mass = foot(0.10) + toe(0.05) = 0.15 kg
- lever arm ≈ 0.038m (combined CoM)
- gravity torque = 0.15 × 9.81 × 0.038 = **0.056 Nm**
- **0.056 Nm vs reported 15 Nm → 268배 차이**

---

### Debug: action offset 확인

probe에 debug 출력 추가하여 실제 offset/scale 확인:

**로그**: `logs/diagnostics/zero_probe_debug.log`

```
[DEBUG] joint_names=['front_left_shoulder', 'front_right_shoulder', 'rear_left_shoulder', 'rear_right_shoulder', 'front_left_leg', 'front_right_leg', 'rear_left_leg', 'rear_right_leg', 'front_left_foot', 'front_right_foot', 'rear_left_foot', 'rear_right_foot']
[DEBUG] default_joint_pos=['-0.0400', '0.0400', '-0.0400', '0.0400', '-0.7000', '-0.7000', '-0.7000', '-0.7000', '1.3200', '1.3200', '1.3200', '1.3200']
[DEBUG] action_term=joint_pos offset=['-0.0400', '0.0400', '-0.0400', '0.0400', '-0.7000', '-0.7000', '-0.7000', '-0.7000', '1.3200', '1.3200', '1.3200', '1.3200']
[DEBUG] action_term=joint_pos scale=1.0
```

**확인 결과**: default_joint_pos = init_pos, offset = init_pos. action=0 → target = init_pos **정상 확인.**

그럼에도 foot torque가 +15.0 (target 방향과 반대)으로 보고됨.

---

### Test 6: damping=10, effort=15, init_z=0.22 (강한 감쇠)

**가설**: 높은 damping으로 진동 억제. 느리지만 안정적인지 확인.

**변경**: Kd=10 (나머지 동일, fix_base=False)

**로그**: `logs/diagnostics/zero_probe_highdamp.log`

**결과 (terminated=0% through 140 steps)**:
```
step=1:   height=0.227, FL_leg=-0.641 (init -0.70에서 +0.06 이동)
step=10:  rear_left_leg=-1.748, rear_right_leg=-1.695
step=50:  height=0.090, all legs deeply bent
step=100: height=0.076, legs at -2.5 (joint limit 근처)
step=140: height=0.073, terminated=0%
```

**관찰**:
1. **terminated = 0%** — 감쇠가 진동 억제에 효과적
2. 그러나 **서서히 주저앉음** (height 0.22 → 0.07)
3. 다리가 극단값으로 드리프트 (leg: -0.70 → -2.5)
4. **PD가 중력을 이기지 못함** — effort_limit 내에서도 position hold 실패

---

### Test 7: stiffness=50, damping=10, effort=50, init_z=0.214 (과잉 강화)

**가설**: 모든 파라미터를 극단적으로 올리면 물리적으로 서 있을 수 있는가.

**변경**: Kp=50, Kd=10, effort=50, init_z=0.214

**로그**: `logs/diagnostics/zero_probe_overpowered.log`

**결과**:
```
step=1:  FL_leg=-0.522 (init -0.70에서 +0.18), height=0.222 (상승)
         foot_torque=50.0 (ALL saturated), leg_torque=-34 to -37
step=10: height=0.252 (추가 상승), 거의 모든 관절 ±50 포화
step=20: terminated=75%
step=30: terminated=100%
```

**결론**: 강한 PD가 착지 impulse를 증폭하여 로봇이 튕겨나감. 전 테스트 중 최악의 결과.

---

### Test 8: init_z=0.214, Kp=16, Kd=5, effort=15 (최종 조합)

**가설**: 올바른 init_z + 튜닝된 PD 파라미터 조합

**변경**: init_z=0.214, Kp=16, Kd=5, effort=15

**로그**: `logs/diagnostics/zero_probe_final.log`

**결과 (테스트 시점 최고 성능)**:
```
step=1:   height=0.222, ang_xy=3.69, 토크 8-15 범위
step=10:  여러 관절 ±15 포화, rear legs 벌어짐
step=50:  terminated=0%, height=0.102
step=80:  terminated=6.25%, ep_len=71
step=100: terminated=6.25%, ep_len=79
step=150: terminated=37.5%
step=190: terminated=31%, ep_len=71
```

**비교표**:

| 설정 | Step 50 term | Step 100 term | Step 100 ep_len |
|------|-------------|--------------|-----------------|
| z=0.194, Kd=2 (원래) | 6.25% | 44% | 15 |
| z=0.22, Kd=2 | 0% | 31% | 24 |
| z=0.22, Kd=10 | 0% | 0% (collapse) | 100 |
| z=0.214, Kd=5 | **0%** | **6.25%** | **79** |
| effort=50 | 37.5% | - | - |
| Kp=40, Kd=5 | 6.25% | 56% | - |
| Kp=50, Kd=10, E=50 | 75%@s20 | - | - |

---

## 미해결 문제

### 1. fix_base torque 불일치 (최우선)

**현상**: body 고정, 다리만 자유, 지면 접촉 없음
- PD target = 1.32 (확인됨)
- foot current = 1.528
- 예상 PD torque = **-3.33 Nm**
- 실제 reported torque = **+15.0 Nm**
- 부호 반대 + 크기 4.5배

**가설**:
1. `robot.data.applied_torque`가 DCMotor output이 아닌 다른 값일 가능성
2. DCMotor 내부에서 예상과 다른 계산 수행 (joint_vel_target이 0이 아닐 수 있음)
3. PhysX joint drive가 stiffness=0에도 불구하고 자체 힘을 가할 가능성
4. 부호 convention: URDF joint axis 방향 vs torque 보고 방향 차이
5. `applied_torque`가 actuator effort가 아닌 PhysX net joint torque일 가능성

**검증 방법**:
- DCMotor의 `computed_effort` vs `applied_effort` 직접 읽기
- `robot.data.joint_pos_target` 확인
- 1-joint 단순 모델로 DCMotor 동작 검증
- Isaac Lab 소스의 applied_torque 할당 코드 추적

### 2. 비대칭 붕괴 패턴

**현상**: fix_base=False에서 항상 rear_right가 먼저 붕괴
- fix_base=True에서는 **완벽 대칭** → URDF/PD 자체는 대칭
- 초기 조건 차이 또는 수치 noise 가능성
- base_rotate (180deg yaw)의 영향 가능성

### 3. toe 접촉 센서 인덱싱

**현상**: `toe_contact_mean > 0`인데 개별 `FL/FR/RL/RR_toe_fz = 0.0`
- scene contact sensor: `prim_path="{ENV_REGEX_NS}/Robot/.*"` (모든 body 추적)
- merge_fixed_joints=True → toe_link가 foot_link에 병합
- probe가 `net_forces_w[:, :, 2]`의 index 0-3을 FL/FR/RL/RR로 가정
- 실제로는 다른 body일 가능성 (base_link=0, shoulder=1, ...)

**검증 방법**:
- contact sensor의 body_names 목록 출력
- 올바른 index로 toe force 읽기

---

## 추가 테스트 (torque 불일치 심층 조사)

### Test 9: PD internals 출력 + fix_base
probe에 computed_torque, joint_pos_target, joint_vel 등 내부 상태 출력 추가.

```
Step 1:  foot=1.378, vel=+0.32, computed=-11.77  (정상)
Step 10: foot=1.499, vel=+10.0(!), computed=+45.57  (bang-bang)
Step 50: foot=1.546, vel=+10.0,  computed=+9.12   (정체)
```
vel이 10.0 = PhysX maxJointVelocity에 고정. computed_torque 부호가 예상과 반대.

### Test 10: URDF velocity=100 + Kp=16 (PhysX 클램프 해제)
- velocity ±66 rad/s 폭주. 악화.

### Test 11: Kp=5 Kd=1 + URDF vel=100 + fix_base
- foot vel=2.7→0.92 (수렴), foot=1.297 (init 1.32 근처)
- torque 0.05~0.25 Nm. 100 steps terminated=0%
- **PhysX vel clamp 제거 + 낮은 Kp = PD 정상 작동**

### Test 12: Kp=5 Kd=1 + URDF vel=100 + free
- Kp=5는 body weight 지탱 불가 (gravity shift 0.31 rad)

### Test 13: URDF vel=20, DCMotor vel=20, Kp=16 Kd=5 + free (최종)

**가설**: URDF vel = DCMotor vel_limit = 10이 문제.
vel=10에서 DCMotor max_effort = 15×(1-10/10) = 0 → 양방향 토크 불가.
둘 다 20이면 vel=10에서 max_effort = 15×(1-10/20) = 7.5 → 양방향 가능.

```
step=100:  terminated=0%, height=0.104, ep_len=100
step=200:  terminated=0%, height=0.100, ep_len=176
step=300:  terminated=0%, height=0.102, ep_len=275
```
**300 steps terminated = 0%.**

---

## 추가 테스트 (standing equilibrium 개선 시도)

### Test 14: DCMotor effort_limit=25 (토크 증가)
**가설**: effort_limit이 부족해서 crouched equilibrium으로 내려감. 올리면 해결되는지 확인.
**결과**: 악화. step 300: 37.5% terminated (이전 0%)
- 높은 effort = 높은 반발 에너지 = 불안정 증가
- **결론: DCMotor에서 effort 증가는 해결책이 아님**

### Test 15: 기둥형 (columnar) pose — leg=-0.35, foot=0.63
**가설**: Z자 다리를 수직에 가깝게 펴면 moment arm 감소 → 적은 토크로 지지 가능
**FK 계산**: height=0.247m (+15%), toe x=0.000
**결과**: 대폭 악화. step 50에서 25% terminated
- leg=-0.35는 theta=0까지 0.35 rad밖에 없어서 착지 충격으로 쉽게 flip
- Z자형 (leg=-0.70)은 0까지 0.70 rad 버퍼 → 더 안정
- **결론: 이론적으로는 타당하나 실제로는 flip zone proximity가 더 위험**

### Test 16: init_z=0.185 + 관절별 차등 gain
**설정**: shoulder Kp=12/Kd=4, leg Kp=28/Kd=5, foot Kp=8/Kd=2
**가설**: 낮은 시작점 + leg gain 강화로 Phase 2→3 전환 지연
**결과 (vs 이전 best DCMotor)**:
```
         이전 (Kp=16 균일, z=0.210)  현재 (관절별, z=0.185)
step 100: height=0.104              height=0.118 (+13%)
step 200: height=0.100              height=0.119 (+19%)
step 300: height=0.102, term=0%     height=0.122, term=6.25%
```
- leg Kp=28이 하중 지지력 향상 → 높이 20% 개선
- 그러나 여전히 crouched 상태 유지 (height 0.12, 다리 크게 벌어짐)

### Test 17: foot/toe inertia 10배 증가 (URDF)
**설정**: foot Iyy 0.0005→0.005, toe Iyy 1e-5→1e-4
**가설**: 저관성이 PD 과잉반응의 원인. 서보 로터 관성 추가로 완화 시도.
**결과**: step 1이 훨씬 안정 (ang_xy=0.10 vs 1.74), 그러나 height 더 낮아짐 (0.073 vs 0.102)
- 높은 관성 = 느린 PD 응답 = body weight에 더 밀림
- **결론: 관성 증가는 초기 안정성 향상, 장기 지지력 하락. 원복 처리.**

---

## DCMotor → ImplicitActuator 전환

### 배경: DCMotor의 구조적 한계
위의 Test 14~17에서 DCMotor 환경 내에서 다양한 시도를 수행:
- effort 증가 → 불안정
- pose 변경 → flip 위험
- gain 분리 → 부분 개선
- inertia 변경 → 트레이드오프

모든 시도에서 height 0.10~0.12 이상 유지 불가. **DCMotor의 velocity-dependent saturation이 구조적 병목으로 확인됨.**

### Test 18: ImplicitActuator (effort_limit 없음)
**변경**: DCMotorCfg → ImplicitActuatorCfg, 같은 gain (12/28/8, 4/5/2)
**결과**:
```
step=50:  height=0.1440, vel_xy=0.0002, ang_xy=0.11
step=100: height=0.1441, vel_xy=0.0006, ang_xy=0.11
step=200: height=0.1441, vel_xy=0.0006, ang_xy=0.10
step=300: height=0.1441, vel_xy=0.0006, ang_xy=0.10
```
- **Step 50 이후 완전 정지.** height 소수점 4자리까지 동일
- **DCMotor와 완전히 다른 결과**: 같은 gain, 같은 pose에서 actuator만 교체

### Test 19: ImplicitActuator + effort_limit=15 (최종 결정)
**가설**: DCMotor와 동일한 토크 제한을 걸어도 standing이 유지되는지 확인.
**결과**: **Test 18과 소수점 4자리까지 동일.**
```
step=50:  height=0.1440
step=100: height=0.1441
step=300: height=0.1441
모든 토크 < 7 Nm (effort_limit 15 Nm 한참 아래)
```
- **정적 평형에서 필요한 최대 토크 = rear_foot -5.90 Nm** (15 Nm 한참 이내)
- **DCMotor의 문제는 effort_limit이 아니라 velocity-dependent saturation이었음** 확정

### Test 20: 600 steps 장기 안정성 + episode reset 확인
**결과**:
```
step=450: height=0.1441 (안정)
step=500: time_out_frac=1.0 → episode reset
step=510: height=0.1627 (새로 착지 중)
step=550: height=0.1441 (다시 안정)
```
- Episode reset 후에도 **동일한 0.1441 평형으로 복귀**
- **무한히 안정적**

### GUI 확인
"서 있다가 잠시 후 뒤로 살짝 내려앉은 상태에서 정지"
= Phase 1 (init height 0.185) → Phase 2 (loaded eq 0.144) → Phase 3 (영구 안정)
**이것이 정상 동작.** 중력 하에서 관절이 약간 압축되는 것은 자동차 서스펜션과 동일한 원리.

---

## 분석팀 토론

### 초기 의견: "DCMotor 유지, ImplicitActuator 전환 반대"
근거: 실험 연속성, 원인 분리 필요, DCMotor 설정 미세조정 여지

### 반론: "같은 gain/pose에서 actuator만 바꿨는데 결과가 다르다"
근거: Test 17(DCMotor)=height 0.12 vs Test 18(Implicit)=height 0.144, 동일 설정
→ 병목은 standing equilibrium이 아니라 **actuator realization**

### 의견 수정: "effort_limit=15 유지한 비교 실험은 타당"
Test 19에서 effort_limit=15에서도 동일 결과 → **DCMotor의 velocity saturation이 유일 원인** 확정

---

## 근본 원인 확정 (최종)

### 원인 1: init_z에 toe sphere radius 미포함 (해결)
- init_z=0.194 → toe 구 바닥 지면 아래 20mm → PhysX impulse
- **수정**: init_z=0.210 (4mm 관통 + 느린 depenetration)

### 원인 2: URDF velocity = DCMotor velocity_limit = 10 (해결)
- PhysX 하드 클램프 + DCMotor saturation → bang-bang 진동
- **수정**: 둘 다 20

### 원인 3: DCMotor velocity-dependent saturation (최종 원인)
- DCMotor의 `torque = saturation × (1 - vel/vel_limit)` curve가
  관절이 움직일 때 가용 토크를 줄여서, 정적 평형으로 수렴 불가
- **해결**: ImplicitActuator 전환 (PhysX 연속시간 PD, velocity saturation 없음)
- effort_limit=15 유지 → 같은 토크 제한, 현실성 보존

---

## 최종 적용 변경

| 파일 | 항목 | 이전 | 최종 | 이유 |
|------|------|------|------|------|
| URDF | velocity | 10.0 | **20.0** | PhysX vel clamp 여유 확보 |
| spot_micro.py | actuator | DCMotorCfg | **ImplicitActuatorCfg** | velocity saturation 제거 |
| spot_micro.py | effort_limit | 15.0 (DCMotor) | **15.0 (Implicit)** | 토크 제한 유지 |
| spot_micro.py | init_z | 0.194 | **0.185** | loaded eq 근처 시작 |
| spot_micro.py | stiffness | 16.0 균일 | **shoulder=12, leg=28, foot=8** | 관절별 역할 차등 |
| spot_micro.py | damping | 5.0 균일 | **shoulder=4, leg=5, foot=2** | 관절별 역할 차등 |
| spot_micro.py | max_depenetration | 1.0 | **0.2** | 부드러운 착지 |
| env_cfg.py | target_height | 0.22 | **0.18** | loaded eq (0.144) 위 목표 |
| zero_stand_probe.py | debug output | 없음 | PD internals 출력 | 진단용 유지 |

---

## 핵심 교훈

1. **init_z 계산에 collision geometry 반드시 포함**: FK는 link center만 계산, sphere radius 별도 고려
2. **effort_limit 증가 ≠ 안정성 증가**: 높은 토크 = 높은 반발 에너지
3. **stiffness 증가 ≠ 안정성 증가**: 강한 spring = 접촉 impulse 증폭
4. **기둥형 pose의 함정**: 이론적 moment arm 최소화 vs 실제 flip zone proximity 위험
5. **URDF velocity = DCMotor velocity_limit이면 bang-bang 필연**
6. **DCMotor의 velocity-dependent saturation이 standing의 구조적 병목**: 같은 gain/effort에서 ImplicitActuator만으로 해결
7. **ImplicitActuator + effort_limit = 두 가지 요건 동시 충족**: PhysX 안정성 + 토크 제한 현실성
8. **Isaac Lab 표준은 ImplicitActuator**: A1, ANYmal, Spot 모두 사용
9. **loaded equilibrium은 init height보다 낮음**: 이것은 정상 (중력 하 관절 압축)
