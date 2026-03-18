# V32 Plan — feet_air_time 핵심 전환

**작성일**: 2026-03-18
**상태**: 훈련 준비

---

## 1. 배경

### V31.2 실패 요약
- front_joint_velocity(+15) 버그 수정 후 정상 작동 (14.5 @iter500)
- 그러나 FL contact 0.81, FR 0.77 — **앞발이 땅에 붙은 채 관절만 진동**
- joint-level 보상이 ground-based 진동을 구별하지 못함
- F-R gap 0.316 — V30(0.365)과 비슷, 근본 해결 안 됨

### 연구 조사 결과 (QUADRUPED_RL_RESEARCH.md)
- legged_gym(ETH RSL): **feet_air_time** 1개로 4발 swing 유도 (weight=1.0, threshold=0.5)
- Walk These Ways(CMU): gait phase clock으로 trot 패턴 명시
- AllGaits: CPG 커플링으로 구조적 강제
- **공통점**: 다리별 전용 보상 없이 4발 공통 보상/구조로 해결

---

## 2. V32 핵심 변경

### A. feet_air_time 강화 (핵심)

| 파라미터 | V31.2 | V32 | 근거 |
|---------|-------|-----|------|
| weight | 8.0 | **30.0** | 50+ 보상 환경에서 rear_joint_velocity(19.3)와 경쟁 |
| threshold | 0.1초 | **0.3초** | legged_gym(0.5)의 60%, SpotMicro 크기 감안 |

**동작 원리**: 착지 순간 `(체공시간 - 0.3초) × weight` 보상.
- 0.3초 이상 체공 → 양의 보상
- 0.3초 미만 → 음의 보상 (땅에 붙어있으면 패널티)
- **4발 모두 동일 기준** → front/rear 구분 없이 균등하게 swing 유도

### B. Front 전용 보상 전폐

| reward | V31.2 | V32 | 이유 |
|--------|-------|-----|------|
| front_joint_velocity | +15 ramp | **0** | ground-based 진동으로 보상 획득 |
| front_joint_frozen | -40 ramp | **0** | 위와 동일 |
| front_swing_bonus | +12 ramp | **0** | feet_air_time이 대체 |
| front_alternation | 0 | 0 | V31.1에서 이미 비활성 |
| front_both_ground | 0 | 0 | V31.2에서 이미 비활성 |
| min_swing_ratio | 0 | 0 | V31.2에서 이미 비활성 |

### C. Rear bias 축소

V31.2에서 rear 전용 보상이 reward 1~2위를 차지하며 front-rear 비대칭 유발:

| reward | V31.2 | V32 | output @V31.2 |
|--------|-------|-----|--------------|
| rear_joint_velocity | 20.0 | **12.0** | 19.3 (1위) |
| rear_alternation | 30.0 | **15.0** | 17.2 (2위) |
| rear_swing | 15.0 | **8.0** | 3.2 |

---

## 3. 예상 reward 구도 (V32)

| 순위 | reward | 예상값 | 비고 |
|------|--------|--------|------|
| 1 | **feet_air_time** | +10~20 | 4발 공통 swing (핵심) |
| 2 | per_leg_contact_target_band | ~14 | 기존 유지 |
| 3 | rear_joint_velocity | ~12 | 축소 |
| 4 | leg_lift | ~11 | 기존 유지 |
| 5 | rear_alternation | ~9 | 축소 |

feet_air_time이 rear 전용 보상보다 높거나 비슷한 수준이 되어야 front-rear 균형이 가능.

---

## 4. 성공/실패 기준

### 성공
- F-R contact gap < 0.15 (V31.2: 0.316)
- FL, FR contact < 0.65 (V31.2: 0.81, 0.77)
- feet_air_time > 0 (양수 — 체공시간 > 0.3초)
- mean_reward > 300

### 실패 → V33 (contact schedule)
- F-R gap > 0.25 @iter 500
- feet_air_time이 여전히 음수 @iter 500
- threshold 0.3초가 SpotMicro에 불가능한 경우

---

## 5. 리스크

1. **threshold 0.3초가 과도**: SpotMicro는 작은 로봇이라 체공시간이 짧을 수 있음. 만약 모든 발이 0.3초 미만이면 feet_air_time이 항상 음수 → 학습 저해. 대안: 0.2초로 낮추기
2. **rear 축소 과다**: rear_joint_velocity 20→12, rear_alternation 30→15가 너무 크면 rear도 무너질 수 있음. 대안: 단계적 축소
3. **50+ 보상 환경에서 단일 보상의 한계**: feet_air_time 30.0도 다른 보상 합산에 밀릴 수 있음. 대안: 보상 항목 대폭 정리 (V34)
