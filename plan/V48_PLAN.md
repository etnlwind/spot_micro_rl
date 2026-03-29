# V48 Plan: Standing Pose Correction + Realism Experiments

> 작성: 2026-03-27
> 상태: **완료 — V48-B 채택, V48-C/D 실패 → Two-track 전략 결정**

---

## 1. 왜 자세 보정이 필요한가

### V47 비디오 관찰

V47이 stride 6.29, coupling 0.46으로 V38.3 수준을 복원했지만, **비디오에서 몸이 너무 낮고 다리가 과도하게 접혀 있었다**.

| 증상 | 설명 |
|------|------|
| 몸 높이 | 목표(0.23m) 대비 낮은 자세로 학습 |
| 다리 접힘 | leg joint가 과도하게 굽어 무릎이 몸 아래로 |
| 기울어짐 | 앞으로 약간 기울어진 자세 |

### 원인 분석: toe 위치 33mm 오프셋

leg joint default = -0.71 설정에서 toe가 shoulder 수직선보다 **33mm 앞**에 위치:

```
shoulder 수직선
    |
    |  33mm
    |<--->
    |    toe (leg=-0.71)
```

이 오프셋이 로봇을 뒤로 기울게 만들고, 학습된 정책이 이를 보상하기 위해 **낮은 자세**를 채택함.

### FK vs 시뮬레이터 실측: 핵심 교훈

URDF에 **180도 yaw rotation**이 적용되어 있어 순수 FK 계산이 부정확:

```
FK 수식: shoulder → upper_leg → lower_leg → toe
  ↑ URDF 180도 yaw가 중간에 들어감 → 좌표 변환 오류

시뮬레이터 body_pos_w: 직접 월드 좌표 반환 → 신뢰 가능
```

**교훈**: FK 수식 대신 **시뮬레이터 body_pos_w 실측만 신뢰**. 이 프로젝트에서 URDF 좌표 변환 관련 진단이 뒤틀린 이력이 여러 차례 있었음.

---

## 2. V48: Standing Pose 보정

### 변경 사항

```python
# joint_default_pose에서 leg joint 수정
leg_default = -0.97  # was -0.71
# toe가 shoulder 수직선에 위치하도록 보정
# 시뮬레이터 body_pos_w로 검증
```

보정 근거:
- leg=-0.71: toe가 shoulder보다 33mm 앞 → 뒤로 기울어짐
- leg=-0.97: toe가 shoulder 수직선 바로 아래 → 수직 자세
- 시뮬레이터에서 body_pos_w 확인하여 검증

---

## 3. V48-B: Init Height 수정

V48에서 init height가 0.30m (deterministic trot 테스트에서 사용한 값)으로 남아 있었음.

```python
# init_height 복원
init_height = 0.22  # was 0.30 (deterministic trot test value)
```

0.30m은 로봇이 허공에서 시작하여 떨어지는 상태 — 0.22m이 standing pose에서의 적절한 높이.

---

## 4. V48-C: 현실 질량 분산 (실패)

### 동기

실제 SpotMicro 로봇의 질량 분포를 반영하여 sim-to-real gap 줄이기 시도.

### 변경

```python
# base_link 질량에 서보/SBC/배터리 추가
total_mass = 6.54  # was 5.3 kg
# 개별 부품:
#   서보 모터 (12개): ~1.0 kg 추가
#   SBC (Raspberry Pi 등): ~0.1 kg
#   배터리: ~0.14 kg
```

### 결과: 보행 불안정

| 지표 | V48-B | V48-C |
|------|-------|-------|
| 안정성 | 정상 보행 | 보행 불안정 |
| 원인 | - | 질량 증가로 토크 대비 무게 비율 악화 |

질량 5.3 → 6.54kg (23% 증가)으로 기존 effort=15.0에서 충분한 토크 마진이 사라짐.

---

## 5. V48-D: 현실 토크 제한 (실패)

### 동기

V48-C에 더해 실제 MG996R 서보 모터의 stall torque를 반영.

### 변경

```python
# effort_limit: 관절별 차등 적용
effort_limit = [1.5, 5.0, 5.0]  # shoulder, upper_leg, lower_leg
# was: 15.0 (전 관절 동일)
# MG996R stall torque 기준
```

### 결과: 서기 불가

| 지표 | V48-B | V48-D |
|------|-------|-------|
| ep_len | 정상 | ~10 (즉시 넘어짐) |
| 상태 | 정상 서기 | 서기 불가 |
| 원인 | - | 토크/체중 비 부족 (6.54kg + 1.5~5.0 Nm) |

effort 1.5~5.0 Nm으로는 6.54kg 로봇의 자중을 지탱할 수 없었음.

---

## 6. 결론: Two-Track 전략

### V48-C/D 실패의 의미

보행 기본이 안 잡힌 상태에서 realism 추가는 **시기상조**:

```
Track 1 (현재): Walking baseline 확보
  → V48-B 설정 (원본 mass, 원본 effort, leg=-0.97)
  → stride, coupling, height, front_leg_lift 문제 먼저 해결

Track 2 (미래): Sim-to-Real Realism
  → 질량 분산, 토크 제한, 지면 마찰 등
  → Track 1의 보행이 안정적인 후에 적용
```

### V48-B 최종 설정 (이후 버전 기반)

```python
leg_default = -0.97       # V48 보정
init_height = 0.22        # V48-B 복원
mass = 5.3                # 원본 유지
effort_limit = 15.0       # 원본 유지
boot_standing = True      # V47에서 추가
```

---

## 7. 핵심 교훈

| # | 교훈 | 출처 |
|---|------|------|
| 1 | FK 수식 대신 시뮬레이터 body_pos_w 실측만 신뢰 | V48 URDF 180도 yaw |
| 2 | 보행 baseline 없이 realism 추가는 시기상조 | V48-C/D 실패 |
| 3 | 토크/체중 비가 임계치 이하면 학습 자체가 불가 | V48-D effort 1.5~5.0 |
| 4 | 한 번에 하나만 변경: 질량과 토크를 동시에 바꾸면 원인 분리 불가 | V48-C→D |

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | leg_default -0.71→-0.97, init_height 0.30→0.22 |
| `env_cfg.py` | V48-C: base_link mass 5.3→6.54 |
| `env_cfg.py` | V48-D: effort_limit 15.0→[1.5, 5.0, 5.0] |
| (V48-C/D는 revert) | V48-B 설정으로 복귀 |
