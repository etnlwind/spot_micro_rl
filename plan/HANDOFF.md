# HANDOFF.md

> 마지막 업데이트: 2026-03-18
> 최신 커밋: develop 브랜치

---

## 1. 현재 목표

**V32 `feet_air_time` 강화 — 4발 공통 체공시간 보상으로 front lock-in 해결**

| 버전 | 결과 | 비고 |
|------|------|------|
| V28.2 | ✅ rear 대칭 달성 | iter 1703 rear_usage_diff=0.012 |
| V28.3 | ❌ front contact 고착 | FL/FR 0.83+ — cap 패널티로 해결 불가 |
| V29 | ❌ residency 목표 미달 | band_high 설정 오류 |
| V30 | 🟡 부분 성공 | 학습 품질 향상, FL/FR lock-in 불변 |
| V31 | ❌ 대각 2발 고착 | front_alternation이 역할 분리 유발 |
| V31.1 | ❌ 대각 2발 고착 | front_both_ground + min_swing_ratio도 역할 분리 유발 |
| V31.2 | ❌ front lock-in 재발 | joint-level 보상은 작동하나 ground-based 진동으로 보상 획득 |
| **V32** | 🔄 **훈련 준비** | feet_air_time 강화 + front 전용 보상 전폐 + rear bias 축소 |

---

## 2. V31.2 실패 분석

### 버그 수정 효과
- curriculum ramp에서 `front_joint_velocity_max`, `front_joint_frozen_max` 누락 → 수정 후 정상 작동
- front_joint_velocity: 0 → **14.5** (iter 500)

### 실패 원인
- front_joint_velocity=14.5이지만 **FL contact 0.81, FR 0.77** — 앞발이 땅에 붙은 채 관절만 진동
- 진정한 swing(체공)이 아닌 **ground-based 진동**으로 보상 획득
- F-R gap: 0.316 (iter 500) — V30(0.365)과 비슷한 수준
- RL(0.31) vs RR(0.63) rear 비대칭도 발생

### V31.2 iter 500 실측

| 다리 | contact | swing | propulsion |
|------|---------|-------|------------|
| FL | **0.808** | 0.170 | 0.649 |
| FR | **0.769** | 0.208 | 0.630 |
| RL | 0.312 | 0.665 | 0.283 |
| RR | 0.639 | 0.338 | 0.518 |

### V31.2 reward 분석 (iter 500 TOP 10)

| reward | 값 | 비고 |
|--------|-----|------|
| rear_joint_velocity | +19.3 | rear에만 적용 → rear bias |
| rear_alternation | +17.2 | rear에만 적용 → rear bias |
| front_joint_velocity | +14.5 | ground-based 진동으로 획득 |
| per_leg_contact_target_band | +14.0 | |
| leg_lift | +11.5 | |
| joint_vel_l2 | -11.1 | |
| foot_extension | -11.0 | |
| **feet_air_time** | **-0.46** | weight=8, threshold=0.1 → 거의 무시됨 |

---

## 3. V32 설계 — feet_air_time 핵심 전환

### 연구 근거 (`plan/QUADRUPED_RL_RESEARCH.md`)

| 프레임워크 | 4발 swing 유도 방식 |
|-----------|-------------------|
| legged_gym (ETH RSL) | **feet_air_time** (w=1.0, threshold=0.5) |
| Walk These Ways (CMU) | gait phase clock + desired_contact_states |
| AllGaits (CPG) | CPG 커플링 매트릭스 |
| **우리 (V31.2)** | **front_*/rear_* 개별 보상 → 역할 분리 유발** |

**교훈 #9**: 다리별 전용 보상은 "어떤 다리를 희생할지" 최적화 유발 → 4발 공통 보상이 안전

### V32 변경 사항

| 항목 | V31.2 | V32 | 이유 |
|------|-------|-----|------|
| **feet_air_time weight** | 8.0 | **30.0** | 핵심 swing 유도 (50+ 보상 환경에서 경쟁 가능) |
| **feet_air_time threshold** | 0.1초 | **0.3초** | legged_gym(0.5)의 60%, SpotMicro 크기 감안 |
| front_joint_velocity | +15 ramp | **0 (비활성)** | ground-based 진동으로 보상 획득 — 실패 |
| front_joint_frozen | -40 ramp | **0 (비활성)** | 위와 동일 |
| front_swing_bonus | +12 ramp | **0 (비활성)** | feet_air_time이 대체 |
| rear_swing | 15.0 | **8.0** | rear bias 축소 |
| rear_alternation | 30.0 | **15.0** | rear bias 축소 |
| rear_joint_velocity | 20.0 | **12.0** | rear bias 축소 |

### 기대 효과
- feet_air_time(30.0, threshold=0.3)이 **모든 발에 0.3초 이상 체공** 유도
- rear 전용 보상 축소 → front-rear 비대칭 완화
- 앞발이 땅에 붙어있으면 feet_air_time이 음수 → 들어야 보상

### 리스크
- threshold 0.3초가 SpotMicro에 너무 클 수 있음 (ANYmal보다 작은 로봇)
- rear 보상 축소가 과하면 rear도 무너질 수 있음
- 50+ 보상 중 feet_air_time이 여전히 경쟁에서 밀릴 수 있음

---

## 4. IsaacOps 인프라

| 항목 | 변경 |
|------|------|
| **isaac_ops/ 패키지** | common.py, listener.py, cli_send.py, cli.cmd, listen.cmd — 독립 실행 가능 |
| **heartbeat 간소화** | TAP/collapse/iter판정/curriculum/posture_raw/AI분석 섹션 제거 |
| **판정 로직 지연** | 워밍업 300→500, enforce 600→1200 (false alarm 방지) |
| **CLI 도구** | `cli.cmd status/hb/stop/start/resume` — 터미널에서 직접 실행 |

---

## 5. 현재 브랜치 상태

```
브랜치: develop
상태: V32 env_cfg 변경 완료, 훈련 준비
훈련: V31.2 종료 (iter 518, front lock-in으로 실패 판정)
```

---

## 6. 주의사항

### 운영
- **listener는 `isaac_ops/listen.cmd`로 실행** (구 supervisor.cmd 대체)
- **CLI: `isaac_ops/cli.cmd <command>`** (status, hb, stop, start, resume)
- **rewards.py / env_cfg.py 수정 시 listener 재시작 불필요** (훈련 프로세스만 재시작)
- **WSL2에서 git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`

### 코드
- **TRAIN_VERSION 단일 소스**: env_cfg.py line 7
- **버전별 상수는 TRAINING_CONFIG에서 읽기** (rewards.py에 하드코딩 금지)

---

## 7. 프로젝트 11대 교훈 (V1~V32)

1. **output=0 reward는 weight를 올려도 0** — band 밖이면 gradient 소멸
2. **패널티만으로는 고착된 local optimum 탈출 불가** — 인센티브 구조 변경 필요
3. **비대칭 보호는 붕괴를 이동시킬 뿐** — 전체 다리에 동일 기준 적용
4. **critic reset + 대규모 reward 변경 = 발산** — from-scratch가 안전
5. **물리적 비대칭이 있으면 reward로 극복 불가** — 초기 자세 대칭이 전제조건
6. **특정 행동의 부재는 패널티로 해결 불가** — 해당 행동에 대한 명시적 보상이 필요
7. **step-level alternation은 역할 분리를 보상** — temporal alternation과 다름
8. **contact-level 패널티는 대각 역할 분리를 유발** — joint-level 접근이 필요
9. **다리별 전용 보상(front_*, rear_*)은 역할 분리 유발** — 4발 공통 보상이 안전 ★ V31.2
10. **보상 50개+는 항목 간 상호작용 예측 불가** — 성공한 프레임워크는 15~20개 ★ 연구조사
11. **Gait 패턴은 "발견"보다 "지시"가 안정적** — phase clock/CPG 구조적 강제 ★ 연구조사

---

## 8. 실측 참고값

| 지표 | V30 @724 | V31.1 @1001 | V31.2 @500 | V32 목표 |
|------|----------|-------------|------------|---------|
| mean reward | 257 | 65 | 416 | > 300 |
| FL contact | 0.826 | 0.874 | **0.808** | < 0.65 |
| FR contact | 0.841 | 0.593 | **0.769** | < 0.65 |
| RL contact | 0.420 | 0.027 | 0.312 | > 0.30 |
| RR contact | 0.510 | 0.758 | 0.639 | > 0.30 |
| F-R gap | 0.365 | 0.341 | **0.316** | < 0.15 |
| feet_air_time | — | — | **-0.46** | > 0 (양수) |
| 패턴 | FL+FR 고접지 | FL+RR 대각 | FL+FR 고접지 | 4발 균형 |

---

## 9. 향후 로드맵

| 단계 | 버전 | 핵심 변경 | 목표 |
|------|------|----------|------|
| **현재** | **V32** | feet_air_time 강화 + rear bias 축소 | F-R gap < 0.15 |
| 다음 | V33 | contact schedule (trot phase clock) 도입 | 명시적 trot 강제 |
| 장기 | V34+ | 보상 항목 대폭 정리 (50개 → 20개) | 안정적 학습 구조 |

### 참고 문서
- `plan/QUADRUPED_RL_RESEARCH.md` — 4족 보행 RL 연구 조사 (legged_gym, Walk These Ways, AllGaits)
- `plan/V31_PLAN.md` — V31 설계 + V31/V31.1/V31.2 분석
- `plan/V30_ANALYSIS.md` — V30 분석
