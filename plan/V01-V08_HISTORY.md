# V1~V8: 기본기 확립 — 서기에서 Flat 보행까지
> **기간**: 2026-02-15 ~ 2026-02-20  
> **환경**: Flat terrain  
> **목표**: 서기 → 걷기 → 트로트 걸음걸이 기초 확립 → Rough 전이학습 소스 생성

---

## 1. Phase 1: 서기 성공 (iter 0 ~ 22,600)

### 문제
로봇이 쪼그리기 자세에서 일어서지 못함. 다리가 떨리기만 함.

### 근본 원인
```python
# 잘못된 설정: target_type="none"
# → PhysX DriveAPI가 생성되지 않음 → DCMotor 토크가 관절에 전달 불가

# 수정: target_type="position"
# → PhysX drive interface 활성화 → 모터 제어 정상 작동
```

### 결과
- iter 22,600에서 **안정적 서기 달성**
- 체크포인트: `2026-02-16_10-54-39/model_22600.pt`

---

## 2. Phase 2: 걷기 전환 (iter 22,600 ~ 28,700)

### 문제
서기는 하지만 전혀 걷지 않음. 서기 보상이 이동 보상보다 압도적.

### 해결
```python
# 보상 리밸런싱
forward_velocity: 1.0 → 150.0  # 150배 증가
standing_height: 5.0 → 30.0
```

### 결과
- 보행 행동 출현, 하지만 다리 떨림(진동 보행) 문제 발생

---

## 3. Phase 3: 진동 해결 + 보상 튜닝 (V1~V4)

### 핵심 문제→해결 과정

| 순서 | 문제 | 해결 |
|:---:|------|------|
| 1 | 서기만 함 | `forward_velocity_reward` 정규화 + `stationary_penalty` |
| 2 | 다리 떨림 | `action_rate_l2 = -0.5` |
| 3 | 발 끌기(셔플링) | `foot_clearance_reward` 추가 (target 10cm) |
| 4 | **진동 보행** | **`decimation 4→8` (50Hz→25Hz)** — 물리적 차단 |
| 5 | 제자리 트로트 | 모든 gait 보상에 `velocity gating` 추가 |
| 6 | 작은 보폭 | `action_scale 0.5→1.0`, 관절 제약 완화 |
| 7 | 벌레처럼 기어다님 | 높이 목표 0.21→0.24, 높이 페널티 강화 |

### 학습 체인

| 버전 | 폴더 | 체크포인트 | 보상 | 특징 |
|------|------|-----------|:---:|------|
| Baseline | `2026-02-17_03-57-39` | model_9999 | +273 | 서있기만 함 |
| Walking | `2026-02-17_19-39-15` | model_14998 | — | 첫 보행 (다리 떨림) |
| Smooth | `2026-02-18_12-21-30` | model_19997 | +37 | 떨림 제거 (발 끌기) |
| Clearance | `2026-02-18_16-40-58` | model_24996 | +248 | 발 높이 들기 (진동) |
| **V1** | `2026-02-19_03-33-03` | model_11800 | ~870 | 높이↑, 24576 envs |
| **V2** | `2026-02-19_05-58-20` | model_12200 | ~986 | feet_air_time 완화 |
| **V3** | `2026-02-19_09-27-19` | model_12300 | ~1078 | standing_height 강화 |
| **V4** | `2026-02-19_09-59-53` | model_13400 | — | 엄격한 트로트 페어 |

### V4 핵심 변경: trot_gait 곱셈 방식
```python
# pair_a_sync × pair_b_sync × anti_phase
# 세 조건 모두 충족해야 보상 → 너무 엄격해서 학습 막힘
```

---

## 4. V5~V7: 미세 조정 (커밋 없이 진행)

- **trot_gait**: 곱셈(AND) → **0.4×mean + 0.6×min** (min-heavy 결합)
  - AND 조건이 너무 엄격 → 최악 성분 중시 방식으로 완화
- **same_side_penalty** 신설: 바운딩/페이싱 감지
- **trot_gait weight**: 50 → 150
- **same_side_penalty weight**: -80

---

## 5. V8: Flat 최종 모델 + Rough 전이학습 (2026-02-20)

### 커밋: `c96d6d8`

### V8 Flat 최종 모델
- 폴더: `spot_micro_flat/2026-02-19_20-40-30`
- 체크포인트: `model_900.pt` (48차원 관측)

### Flat→Rough 전이학습 과정
1. `scripts/transfer_flat_to_rough.py` 실행
2. 공통 48차원 가중치 유지
3. height_scan 54차원 → Xavier 초기화
4. 결과: `spot_micro_rough/transferred_from_v8_flat/model_0.pt` (102차원)

### Rough 환경 설정
- `SpotMicroRoughEnvCfg` 신설 (SpotMicroFlatEnvCfg 상속)
- Height scanner: RayCaster, 0.1m 해상도, 0.8×0.5m 그리드
- 지형 6종: 계단, 역계단, 랜덤 박스, 울퉁불퉁, 경사(상/하)
- 스케일 조정: step_height 2~8cm (SpotMicro 24cm 체고 맞춤)
- 초기 자세: 쪼그리기(0.13m) → **서기(0.20m)** — leg=-0.5, foot=1.2
- `soft_joint_pos_limit_factor = 0.7`: foot 관절 과접힘 방지

---

## 6. 이 시기의 교훈

| 교훈 | 근거 |
|------|------|
| **PhysX DriveAPI 필수** | `target_type="position"` 없으면 모터 토크 전달 불가 |
| **decimation으로 진동 물리적 차단** | 4→8로 제어 주파수 낮춰서 진동 보행 근본 해결 |
| **velocity gating** | 이동 없이 제자리 트로트만 하는 꼼수 방지 |
| **0.4mean + 0.6min > 곱셈(AND)** | 너무 엄격한 조건은 학습을 막음 |
| **단계적 접근** | 서기→걷기→발들기→트로트 순서대로 진행 |
| **전이학습 효과** | Flat 기본기 → Rough 확장 시 학습 속도 향상 |

---

## 7. V8 보상 구조 (27개)

| 보상 | 가중치 | 설명 |
|------|:---:|------|
| trot_gait | 150.0 | 대각 페어 교대 (0.4mean+0.6min) |
| forward_velocity | 40.0 | 전진 (target 0.5 m/s) |
| standing_height | 40.0 | 높이×수평 결합 |
| shoulder_neutral | -25.0 | 어깨 중립 |
| foot_clearance | 20.0 | 스윙 시 발 높이 10cm |
| height_bonus | 20.0 | 높이 비례 |
| flat_orientation_l2 | -20.0 | 수평 유지 |
| swing_stride | 15.0 | 보폭 |
| same_side_penalty | -80.0 | 바운딩/페이싱 억제 |
| base_height_l2 | -50.0 | 높이 0.24m |
| undesired_contacts | -100.0 | 비정상 접촉 |
| feet_below_knees | -500.0 | 발-무릎 역전 |
