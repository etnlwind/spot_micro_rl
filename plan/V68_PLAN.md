# V68 PLAN: Reference Trajectory Tracking (성공)

## 1. 배경

V1~V67까지의 실험 종합 결론:
- **"RL이 좋은 gait를 발견하게 하자"** → exploit whack-a-mole (V63~V67 반복 실패)
- **"이상적 trot을 정의하고 따라가게 하자"** → 새 접근

V63.I가 **보행 품질 최고** (stride 4.35, propulsion 균등, GUI 자연스러움)이지만 **대칭 부족** (12.6%p).
V67이 **대칭 최고** (2.7%p)이지만 **보행 품질 붕괴** (stride 2.23).

## 2. 접근: Policy Trajectory Mining

### Step 1: V63.I Rollout 녹화
- `scripts/rsl_rl/record_trajectory.py`
- V63.I model_4999, 16 envs, 1000 steps (20초)
- Joint pos/vel, action, root vel/ang_vel, toe positions 저장
- vx = 0.38 m/s 안정 전진 확인

### Step 2: 궤적 분석
- `scripts/analyze_trajectory.py`
- Frequency: **2.01 Hz** (25 steps/cycle)
- L/R bias 확인: front leg bias +0.18 (FL이 더 앞)
- Phase-normalized 1 cycle 추출

### Step 3: 대칭화
- FL/RR pair ↔ FR/RL pair: phase-shifted 평균
- Shoulder: magnitude 평균 후 부호 재적용
- **L/R 비대칭 89.9% 감소** (1.83 → 0.18)
- Reference: `logs/ideal_trot_reference.json` (7.1 KB)

### Step 4: Reference Tracking Reward
```python
def reference_trot_tracking_reward(env, ...):
    phase = (t * frequency + offset) % 1.0
    ref_target = interpolate(reference, phase)  # 25-step cycle
    err = |actual_joints - ref_target|.sum()
    reward = exp(-err / sigma)
```

## 3. V68 Reward 구조

| Reward | Weight | 역할 |
|--------|--------|------|
| **ref_tracking** | **10.0** | 주연 — 대칭화 궤적 추적 |
| true_trot_pattern | 2.0 | 보조 — intra_sync 유지 |
| swing_body_forward | 4.0 | 보조 — 전진 |
| effective_stride | 5.0 | 보조 — 보폭 |
| per_leg_contact_min | -8.0 | 방어 — 다리 미사용 차단 |
| shoulder_neutral | -4.0 | 방어 — 어깨 벌림 억제 |
| leg_lr_symmetry | -2.0 | 보조 안전장치 |
| + Phase randomization | — | 초기 대칭 (V66.1) |

## 4. 결과

### 수치 (iter 2500, 최적 구간)
| 지표 | V63.I | V67 | **V68** |
|------|------|------|------|
| 대칭 diff | 12.6%p | 2.7%p | **1.5%p** |
| stride | 4.35 | 2.23 | **4.40** |
| timeout | 99.95% | 98.9% | **100%** |
| reward | 386 | 226 | **475** |
| GUI | FR/RR 이상 | drift/slip | **"보행 좋아 보인다"** |

### 학습 추이
```
iter 550:  대칭 1.7%p, stride 3.58 (부팅 완료)
iter 962:  대칭 2.3%p, stride 4.39 (V63.I 초과!)
iter 1412: 대칭 2.0%p, stride 4.42 (안정)
iter 2236: 대칭 1.2%p, stride 4.38 (역대 최저 diff!)
iter 3372: 대칭 9.8%p, stride 4.41 (미세 상승)
iter 4014: 대칭 12.7%p, stride 1.55 (후반 하락)
```

### 최적 체크포인트: model_2000 ~ model_2500
- 대칭 1~2%p + stride 4.4 + timeout 100%
- 후반(iter 3500+) 편향 재발 → 중간 체크포인트가 최고

### GUI 확인
- model_2500: **사용자 "보행 좋아 보인다"** — V63~V68 전체 시리즈 첫 긍정 GUI 판정
- V63.I model_2000 비교: V63.I는 "FR/RR 이상, 몸 세우기" 관찰됨
- V68 model_2500: 대칭 + stride + 자연스러움 동시 달성

## 5. 왜 V68이 성공했는가

### Open-loop IK sweep 실패 → Policy trajectory mining
- Open-loop IK: 역방향 이동 (vel=-0.15) → 물리적 추진 재현 불가
- V63.I policy 궤적: 실제 동역학에서 전진 가능한 궤적 → 추진 메커니즘 내장

### V63.I의 장점만 추출
- **추진력**: V63.I policy가 학습한 실제 push/stance 역학
- **대칭화**: L/R pair 평균으로 편향 제거
- **Reference tracking**: RL이 이 궤적을 따라가면서 자체 최적화

### Phase randomization 병행
- 초기 gradient 편향 제거 (V66.1 검증)
- Reference tracking이 후반 편향도 억제

## 6. model_2500 정량 리포트 (Best Checkpoint)

40초 rollout (2000 steps, 77 gait cycles) 기반.

| 항목 | 값 | 판정 |
|------|------|------|
| Forward speed | 0.308 m/s | ✅ |
| Lateral drift | 0.003 m/s (1%) | ✅ 직진 |
| Body height | 0.240 m ±0.005 | ✅ 안정 |
| Roll rate std | 0.155 rad/s | ✅ |
| Pitch rate std | 0.264 rad/s | ✅ |
| Yaw rate std | 0.092 rad/s | ✅ |
| Cost of Transport | 6.97 | 기준 |
| L/R joint asymmetry | 0.338 | ✅ |
| Gait frequency | 2.00 Hz | ✅ 설계 일치 |
| GUI 판정 | "보행 좋아 보인다" | ✅ |

## 7. 한계와 후속 과제

### 한계
- iter 3500+ 후반에 편향 재발 (12.7%p) + stride 하락
- **최적 체크포인트(iter 2500)를 선택해야 함** — 완주(5000)가 최적 아님

### 후속 과제
1. **Domain randomization**: push recovery, mass/friction 변동
2. **Rough terrain**: 경사/계단/요철 지형 적응
3. **Height scanner**: 장애물 인식 observation 추가
4. **Sim-to-real**: 실기체 배치 검증

## 7. 핵심 교훈

> **"RL이 발견하게"가 아니라 "검증된 궤적을 따라가게"가 정답이었다.**

V1~V67까지의 reward engineering 한계를 **policy trajectory mining + 대칭화**로 돌파.
V63.I의 동역학적 추진력 + V67의 대칭 목표를 **reference tracking**으로 결합.
