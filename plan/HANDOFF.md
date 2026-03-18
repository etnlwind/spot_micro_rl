# HANDOFF.md

> 마지막 업데이트: 2026-03-18
> 최신 커밋: 미커밋 (develop 브랜치)

---

## 1. 현재 목표

**V31.2 앞다리 Swing 강제 — Joint-Level 접근**

| 버전 | 결과 | 비고 |
|------|------|------|
| V28.2 | ✅ rear 대칭 달성 | iter 1703 rear_usage_diff=0.012 |
| V28.3 | ❌ front contact 고착 | FL/FR 0.83+ 유지 — cap 패널티로 해결 불가 |
| V29 | ❌ residency 목표 미달 | band_high 설정 오류로 reward gradient 없음 |
| V29.2 | ❌ 중단 | supervisor silent crash로 iter 201에서 중단 |
| V30 | 🟡 부분 성공 | 학습 품질 향상, FL/FR lock-in 방향 불변 (iter 724 종료) |
| V31 | ❌ 대각 2발 고착 | front_alternation이 고정역할 보상 → FR+RL 완전 붕괴 |
| V31.1 | ❌ 대각 2발 고착 | front_both_ground + min_swing_ratio도 역할 분리 유발 → RL 완전 붕괴 |
| **V31.2** | 🟡 **훈련 중** | contact-level 패널티 전폐, joint-level 보상으로 전환 |

---

## 2. V31.2 핵심

### 문제 (V31~V31.1, contact-level 접근 실패)

V31의 4개 신규 함수 중 contact-level 패널티 3개가 모두 **대각선 역할 분리**를 유발:
- `front_alternation`(V31): abs(FL-FR) → 한쪽만 영구 swing이 최적 → **비활성화**
- `front_both_ground`(V31.1): FL*FR → 한쪽만 떼면 OK → 역할 고정 → **비활성화**
- `min_swing_ratio`(V31.1): swing 부족 다리에 패널티 → 특정 다리를 영구 swing 배정 → **비활성화**

**공통 실패 메커니즘**: step-level contact 기반 → PPO가 "어떤 다리를 희생할지" 선택하면 패널티 회피 가능.

### V31.1 실측 데이터 (iter 1001)

| 다리 | contact | swing | propulsion |
|------|---------|-------|------------|
| FL | **0.874** | 0.103 | 0.726 |
| FR | 0.593 | 0.383 | 0.546 |
| RL | **0.027** | **0.950** | 0.027 |
| RR | 0.758 | 0.219 | 0.493 |

FL+RR 대각 고접지, FR+RL 반대 대각 불안정 — V31과 방향만 바뀐 동일 패턴.

### V31.2 해결: Joint-Level 접근

뒷다리 활성화(V15~V16)에서 성공한 joint-level 보상을 앞다리에 미러:

| reward | V31.1 | V31.2 | 이유 |
|--------|-------|-------|------|
| front_swing_bonus | +12 ramp | +12 (유지) | 앞발 들기 양의 인센티브 |
| front_both_ground | -15 ramp | **0 (비활성화)** | 대각 역할 분리 유발 |
| min_swing_ratio | -20 ramp | **0 (비활성화)** | 대각 역할 분리 유발 |
| **front_joint_velocity** | 없음 | **+15 ramp (신규)** | rear_joint_velocity(+20) 미러 |
| **front_joint_frozen** | 없음 | **-40 ramp (신규)** | rear_joint_frozen(-60) 미러 |

**핵심**: joint-level 패널티는 개별 관절 단위 → FL 관절이 안 움직이면 FL에 직접 패널티. "FR이 대신" 불가.

Curriculum ramp: iter 100~400.

---

## 3. V30 분석 요약 (→ `plan/V30_ANALYSIS.md`)

- 초기 자세 대칭(leg=-0.71, foot=1.31) → 학습 효율 대폭 향상 (reward 323 vs V29 max 303)
- FL/FR contact lock-in 방향은 불변 → 물리 자세가 아닌 reward 구조 문제 확정
- iter 644→724: late_phase_band_exit 패널티 급증으로 reward 급락 (V29와 동일 패턴)

---

## 4. 수퍼바이저/인프라 개선

| 항목 | 변경 |
|------|------|
| write_log() 안전화 | print()/file I/O 각각 try/except — DETACHED_PROCESS silent crash 방지 |
| _build_status_snapshot() 캐시 수정 | return 전 cache 할당 — 30초 TTL 정상 작동 |
| heartbeat 훈련 복구 | _training_stopped_by_heartbeat flag + finally 블록 |
| 3초 ACK 규칙 | Y 확인 시 즉시 ACK → launch_training은 이후 처리 |
| UX 메시지 개선 | "FRESH START" → "새 훈련", 불필요한 표현 제거 |
| 명령 ACK 지연 | `_build_command_ack()` — psutil 스캔 없이 즉시 반환 |
| tfevents 캐시 | mtime+size 기반 — 파일 불변 시 재파싱 없음 |
| 버전 불일치 감지 | supervisor 시작 시 자동 감지 → .env 자동 동기화 |

---

## 5. 현재 브랜치 상태

```
브랜치: develop
상태: 미커밋 변경 있음 (V31.2 reward + config)
훈련: V31.2 run 2026-03-18_17-43-22 (iter 0+)
```

---

## 6. 주의사항

### 운영
- **supervisor는 반드시 프로젝트 루트의 `supervisor.cmd`로만 실행**
- **rewards.py / env_cfg.py / spot_micro.py 수정 시 supervisor 재시작 필수**
- **WSL2에서 git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`

### 코드
- **버전별 상수는 TRAINING_CONFIG에서 읽어야 함** (rewards.py에 하드코딩 금지)
- **TRAIN_VERSION 변경 시 supervisor 재시작** — 실행 중 프로세스는 구버전 코드 사용

### V31.2 설계 원칙
- contact-level 패널티는 모두 대각 역할 분리를 유발 → **전폐**
- joint-level(관절 속도/동결)은 개별 다리 단위로 작동 → 역할 분리 불가
- rear 활성화(V15~V16)에서 검증된 구조를 앞다리에 대칭 적용

### 참고 문서
- `plan/V31_PLAN.md` — V31 설계 + V31/V31.1 실패 분석 + V31.2 수정
- `plan/V30_ANALYSIS.md` — V30 분석 (학습 품질 향상, lock-in 불변)
- `plan/V29_ANALYSIS.md` — V29 실패 분석
- `plan/V29.2_PLAN.md` — V29.2 설계 및 성공 기준

---

## 7. 프로젝트 8대 교훈 (V1~V31.2)

1. **output=0 reward는 weight를 올려도 0** — band 밖이면 gradient 소멸
2. **패널티만으로는 고착된 local optimum 탈출 불가** — 인센티브 구조 변경 필요
3. **비대칭 보호는 붕괴를 이동시킬 뿐** — 전체 다리에 동일 기준 적용
4. **critic reset + 대규모 reward 변경 = 발산** — from-scratch가 안전
5. **물리적 비대칭이 있으면 reward로 극복 불가** — 초기 자세 대칭이 전제조건
6. **특정 행동의 부재는 패널티로 해결 불가** — 해당 행동에 대한 명시적 보상이 필요 ★ V31
7. **step-level alternation은 역할 분리를 보상** — temporal alternation과 다름 ★ V31
8. **contact-level 패널티는 대각 역할 분리를 유발** — joint-level 접근이 필요 ★ V31.1→V31.2

---

## 8. 실측 참고값

| 지표 | V30 @724 | V31 @421 | V31.1 @1001 | V31.2 목표 |
|------|----------|----------|-------------|-----------|
| mean reward | 257 | — | 65 | > 200 |
| FL contact | 0.826 | 0.815 | **0.874** | < 0.70 |
| FR contact | 0.841 | 0.031 | 0.593 | < 0.70 |
| RL contact | 0.420 | 0.150 | **0.027** | > 0.35 |
| RR contact | 0.510 | 0.805 | 0.758 | > 0.35 |
| F-R gap | 0.365 | — | 0.341 | < 0.20 |
| 패턴 | FL+FR 고접지 | FL+RR 대각 | FL+RR 대각 | 4발 균형 |
