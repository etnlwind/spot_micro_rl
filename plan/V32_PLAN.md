# V32 Plan — feet_air_time 핵심 전환

**작성일**: 2026-03-18
**상태**: ❌ 실패 (iter 2262에서 중단)

---

## V32 설계 (원본)

| 파라미터 | V31.2 | V32 | 근거 |
|---------|-------|-----|------|
| feet_air_time weight | 8.0 | 30.0 | 핵심 swing 유도 |
| feet_air_time threshold | 0.1 | 0.3 | legged_gym(0.5)의 60% |
| front_swing_bonus | 12.0 ramp | 0 | feet_air_time 대체 |
| front_joint_velocity | 15.0 ramp | 0 | ground-based 진동 실패 |
| front_joint_frozen | -40.0 ramp | 0 | 위와 동일 |
| rear_swing | 15.0 | 8.0 | rear bias 축소 |
| rear_alternation | 30.0 | 15.0 | rear bias 축소 |
| rear_joint_velocity | 20.0 | 12.0 | rear bias 축소 |

## V32 실패 분석

### 실측 데이터

| iter | mean_reward | ep_length | feet_air_time | FL_c | FR_c | RL_c | RR_c |
|------|------------|-----------|---------------|------|------|------|------|
| 100 | -35.9 | 12.7 | -0.25 | N/A | N/A | N/A | N/A |
| 500 | -11.6 | 14.2 | -0.30 | 0.000 | 0.000 | 0.000 | 0.000 |
| 1000 | -15.7 | 14.0 | -0.31 | 0.086 | 0.086 | 0.061 | 0.042 |
| 2200 | -10.8 | 15.0 | -0.35 | 0.099 | 0.091 | 0.054 | 0.044 |

### 실패 원인 3가지

1. **threshold 0.3초 과도** (리스크 #1 적중)
   - SpotMicro는 작은 로봇 — V31.2에서 FL swing_time=0.145, FR=0.203
   - threshold 0.3초보다 짧아서 feet_air_time이 항상 음수
   - 학습 신호 없음 → 개선 불가

2. **rear 축소 과다** (리스크 #2 적중)
   - rear_alternation: V31.2 실측 17.2 → V32 실측 0.13 (130배 감소)
   - rear_joint_velocity: 19.3 → 0.64
   - rear가 무너지면서 4발 전부 붕괴, episode_length 15 (즉시 넘어짐)

3. **동시 변경 3가지** — 어떤 변경이 주 원인인지 분리 불가
   - threshold 변경 + rear 축소 + front 비활성화를 한꺼번에 적용

### 교훈 #12
**한 번에 하나만 변경** — 동시에 3가지(threshold, rear 축소, front 비활성화) 변경하면 실패 원인 분리 불가 ★ V32

---

# V32.1 Plan — 보수적 feet_air_time 강화

**작성일**: 2026-03-19
**상태**: 훈련 준비

## 설계 원칙

V31.2 대비 **최소 변경** — front 전용 보상만 비활성화하고, feet_air_time weight만 강화.

## 변경 사항

| 파라미터 | V31.2 | V32 (실패) | V32.1 | 근거 |
|---------|-------|-----------|-------|------|
| feet_air_time weight | 8.0 | 30.0 | **20.0** | V31.2에서 -0.45 → 약 -1.1 수준, rear 보상(18~17)과 경쟁 |
| feet_air_time threshold | 0.1 | 0.3 | **0.1** | V31.2 FL swing=0.145 → threshold 0.1이면 양의 보상 가능 |
| front_swing_bonus | 12.0 ramp | 0 | **0** | 교훈 #9 유지 — 다리별 전용 보상 제거 |
| front_joint_velocity | 15.0 ramp | 0 | **0** | ground-based 진동으로 실패 확인 |
| front_joint_frozen | -40.0 ramp | 0 | **0** | 위와 동일 |
| rear_swing | 15.0 | 8.0 | **15.0** | 원복 — rear 안정성 유지 |
| rear_alternation | 30.0 | 15.0 | **30.0** | 원복 |
| rear_joint_velocity | 20.0 | 12.0 | **20.0** | 원복 |

## 핵심 논리

1. **V31.2에서 작동하던 것은 유지** — rear 보상 구조 원복
2. **V31.2에서 실패한 것만 제거** — front 전용 보상 비활성화 (교훈 #9)
3. **feet_air_time 강화로 front swing 유도** — weight 8→20 (×2.5)
   - V31.2에서 feet_air_time=-0.45 (weight 8) → V32.1 예상 약 -1.1 (weight 20)
   - rear_joint_velocity(18.7), rear_alternation(16.6)과 경쟁 가능한 규모
   - 앞발이 체공하면 양의 보상, 붙어있으면 음의 보상 → 방향성 제공

## 리스크

1. **feet_air_time 20.0도 부족할 수 있음** — V31.2에서 -0.45였으니 20.0으로도 -1.1 수준. rear 보상(18+17=35)에 비해 약함
   - 대안: weight 25로 올리기
2. **front 전용 보상 제거만으로 rear bias 완화 안 될 수 있음** — rear가 여전히 reward 1~2위
   - 대안: rear 보상 소폭 축소 (20→18, 30→25)
3. **episode_length가 V31.2 수준(길음)으로 복귀하면 feet_air_time 효과 검증 가능**
   - V32처럼 즉시 넘어지면 feet_air_time 평가 자체가 불가

## 성공/실패 기준

### 성공
- mean_reward > 300
- F-R contact gap < 0.25 (V31.2: 0.316에서 개선)
- feet_air_time > -0.2 (V31.2: -0.45에서 개선)
- FL, FR contact < 0.75 (V31.2: 0.81, 0.77에서 개선)

### 부분 성공 → V32.2
- rear 안정적이나 front 여전히 고착 → feet_air_time weight 25~30으로 추가 강화

### 실패 → V33
- mean_reward < 200 @iter 500 또는 즉시 넘어짐
- feet_air_time이 front lock-in에 영향 없음 → contact schedule (trot phase clock) 도입
