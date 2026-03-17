# HANDOFF.md

> 마지막 업데이트: 2026-03-18
> 최신 커밋: 미커밋 (develop 브랜치)

---

## 1. 현재 목표

**V30 초기 자세 대칭 교정 — 앞다리 과접지 근본 원인 제거**

| 버전 | 결과 | 비고 |
|------|------|------|
| V28.2 | ✅ rear 대칭 달성 | iter 1703 rear_usage_diff=0.012 |
| V28.3 | ❌ front contact 고착 | FL/FR 0.83+ 유지 — cap 패널티로 해결 불가 |
| V29 | ❌ residency 목표 미달 | band_high 설정 오류로 reward gradient 없음 |
| V29.2 | 🟡 훈련 중 | iter 201, run `2026-03-17_23-06-20` |
| **V30** | 🔧 **준비 중** | 초기 자세 대칭 교정 (물리적 근본 원인 제거) |

---

## 2. V30 핵심: 초기 자세 비대칭 발견 및 교정

### 문제 발견

V28.2~V29.2까지 6개 버전 동안 FL/FR contact 0.83+ 고착이 어떤 reward/penalty로도 해결되지 않은 근본 원인:

**초기 자세(leg=-0.5, foot=1.2)에서 발끝 배치가 극단적 비대칭:**

```
이전: 앞발 +118mm / 뒷발 -68mm (CoM 기준) → 비율 1.75:1
     → 앞다리 하중 34.9% / 뒷다리 65.1%
     → 앞발을 들면 118mm 지지점 상실 → 심각한 불안정
     → PPO가 앞다리 접지 유지를 최적 전략으로 학습 (local optimum)
```

URDF CoM 자체는 정중앙(-2.7mm)이므로 질량 분포는 원인이 아님.
`base_rotate`의 π 회전 + `foot joint offset(-0.01 X)` + `leg=-0.5, foot=1.2` 조합이 비대칭 생성.

### 교정 (`spot_micro.py`)

```python
# 이전 (V1~V29.2)
pos = (0.0, 0.0, 0.20)
".*leg": -0.5,  ".*foot": 1.2

# V30
pos = (0.0, 0.0, 0.192)    # 발끝 지면 +2mm (이전: 4.2mm 낙하)
".*leg": -0.71, ".*foot": 1.31  # 앞/뒤 발끝 대칭
```

| | 이전 | V30 |
|---|---|---|
| 앞발 CoM 기준 거리 | 121.1 mm | **93.0 mm** |
| 뒷발 CoM 기준 거리 | 64.9 mm | **93.0 mm** |
| 대칭 오차 | 56.1 mm | **0.0 mm** |
| 하중 배분 (앞/뒤) | 34.9% / 65.1% | **50.0% / 50.0%** |
| 스폰 낙하 | 4.2mm | **0mm** (2mm 여유) |

### 스폰 불안정 원인도 동시 해결

이전 스폰 높이 0.20m에서 발끝이 지면 위 4.2mm → 매 에피소드 시작 시 로봇 낙하 후 충격.
V30에서 0.192m로 변경하여 발끝이 지면 위 2mm (안전 여유) 유지.

---

## 3. V29.2 변경사항 (→ `plan/V29.2_PLAN.md`)

**`source/.../spot_micro_rl_env_cfg.py`**

| 항목 | V29 | V29.2 |
|------|-----|-------|
| TRAIN_VERSION | V29 | **V29.2** |
| contact_residency band | [0.25, 0.65] | **[0.20, 0.85]** |
| prop_residency band_high | 0.65 | **0.70** |
| per_leg_contact_target_band band_high | 0.45 | **0.75** |
| per_leg_contact_target_band weight | 0.5 | **3.0** |
| front_rear_support_balance_penalty | weight=0.0 | **weight=-4.0, max_diff=0.25** |
| residency enforce 시작 | iter 600 | **iter 800** |

---

## 4. 수퍼바이저/인프라 개선

| 항목 | 변경 |
|------|------|
| 명령 ACK 지연 | `_build_command_ack()` — status/help/stop 등 즉시 반환 (psutil 스캔 없음) |
| ACTIVE 메시지 지연 | heartbeat launch 전에 먼저 전송 |
| psutil 스캔 중복 | `_scan_all_managed_processes()` 1회 통합 (기존 5회) |
| tfevents 캐시 | mtime+size 기반 — 파일 불변 시 재파싱 없음 |
| status snapshot TTL | 30초 캐시 |
| heartbeat launch polling | 제거 — fire-and-forget |
| train_version.txt | 버전 변경 시 항상 덮어쓰기 (기존: 최초 1회만) |
| 버전 불일치 감지 | supervisor 시작 시 자동 감지 → 경고 or 자동 fresh start |
| training_launch.log | 20MB 초과 시 rotation |
| status에 train_version 표시 | 추가 |

---

## 5. 현재 브랜치 상태

```
브랜치: develop
상태: 미커밋 변경 있음 (V30 init pose + 문서 정리)
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

### V30 설계 원칙
- 초기 자세 대칭이 물리적 전제조건 — reward 설계보다 먼저 해결해야 할 문제
- `leg=-0.71, foot=1.31`: 앞/뒤 동일 각도로 발끝 대칭 달성
- 스폰 높이 0.192m: 낙하 충격 제거
- V29.2의 reward 변경사항은 그대로 유지 (대칭 자세 위에서 더 효과적일 것으로 예상)

### 참고 문서
- `plan/V29_ANALYSIS.md` — V29 실패 상세 분석
- `plan/V29.2_PLAN.md` — V29.2 설계 및 성공 기준
- `plan/V29_PLAN.md` — V29 원래 설계

---

## 7. 프로젝트 5대 교훈 (V1~V29.2)

1. **output=0 reward는 weight를 올려도 0** — band 밖이면 gradient 소멸
2. **패널티만으로는 고착된 local optimum 탈출 불가** — 인센티브 구조 변경 필요
3. **비대칭 보호는 붕괴를 이동시킬 뿐** — 전체 다리에 동일 기준 적용
4. **critic reset + 대규모 reward 변경 = 발산** — from-scratch가 안전
5. **물리적 비대칭이 있으면 reward로 극복 불가** — 초기 자세 대칭이 전제조건 ★ NEW

---

## 8. V29 실측 참고값 (iter 1000, 훈련 종료)

| 지표 | V29 실측 | V29.2 목표 |
|------|----------|-----------|
| mean reward | 169 (max 303 @ iter 502) | > 280 지속 |
| FL/FR contact | 0.845 | < 0.80 |
| RL/RR contact | 0.487 | > 0.55 |
| F-R gap | 0.358 | < 0.20 |
| RR residency | 0.134 | > 0.20 |
| gait @ iter 1000 | 🟡 C | ⭐ B |
