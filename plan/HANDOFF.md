# HANDOFF.md

> 마지막 업데이트: 2026-03-17
> 최신 커밋: `ff62aff` (develop 브랜치)

---

## 1. 현재 목표

**V29.2 훈련 진행 중**

| 버전 | 결과 | 비고 |
|------|------|------|
| V28.2 | ✅ rear 대칭 달성 | iter 1703 rear_usage_diff=0.012 |
| V28.3 | ❌ front contact 고착 | FL/FR 0.83+ 유지 — cap 패널티로 해결 불가 |
| V29 | ❌ residency 목표 미달 | band_high 설정 오류로 reward gradient 없음 |
| **V29.2** | 🟡 **훈련 중** | iter 201, run `2026-03-17_23-06-20` |

---

## 2. V29 실패 원인 (→ `plan/V29_ANALYSIS.md`)

1. `contact_residency band_high=0.65` → FL/FR(0.84)이 band 밖 → residency reward 0
2. `per_leg_contact_target_band band_high=0.45` → RL/RR(0.49)도 band 밖 → 전 다리 gradient 없음
3. `front_rear_support_balance_penalty weight=0.0` → front dominance 방치
4. enforce 시작 iter 625 → gait 안정화 전 패널티 → gait B→C 퇴행

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

**`scripts/common.py`**
- KPI 경보 threshold: RR residency 0.30 → **0.15**

---

## 4. 수퍼바이저/인프라 개선 (이번 세션)

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

## 5. V29.2 훈련 모니터링

### 초기 신호 (iter 201 — 정상)
- `per_leg_contact_target_band` TOP5 진입 (+1.4656) ✅ — V29.2 변경 즉시 작동
- `front_rear_balance: 0.1072` — 초기치로 양호
- 생존율 11.7%, 낙상 96% — 정상 초기 구간

### 체크포인트 기준

| iter | 핵심 지표 | 판정 기준 |
|------|----------|---------|
| 400 | contact_target_band reward 추이 | RL/RR band 진입 확인 |
| 500 | F-R contact gap | < 0.25 목표 (V29는 0.36) |
| 600 | gait | ⭐ B 유지 (V29는 625에서 enforce로 퇴행) |
| 800 | residency enforce 시작 | RR residency > 0.10 이어야 진입 의미 있음 |
| 1000 | RR residency | > 0.20 목표 (V29는 0.134) |
| 1000 | gait | ⭐ B 유지 (V29는 🟡 C로 퇴행) |

### 경보 기준

| 지표 | 경보 | 액션 |
|------|------|------|
| 생존율 (iter 400+) | < 80% | front_rear penalty 완화 검토 |
| F-R contact gap (iter 600) | > 0.30 | balance penalty 효과 없음 → 재검토 |
| RR residency (iter 1000+) | < 0.15 🔴 | V29.2 실패 판정 |
| gait (iter 800) | 🟡 C | enforce 타이밍 추가 지연 검토 |

---

## 6. 현재 브랜치 상태

```
브랜치: develop
최신 커밋: ff62aff — Add V29 analysis and V29.2 plan documents
원격 동기화: ✅ push 완료
```

### 최근 커밋 목록
```
ff62aff Add V29 analysis and V29.2 plan documents
483c627 Implement V29.2: fix residency band + front dominance penalty
08434ff Fix version mismatch: auto fresh-start on TRAIN_VERSION upgrade
b9c2d17 Add train_version to supervisor status output
a802076 Remove heartbeat launch polling — fire-and-forget
1579805 Optimize supervisor/heartbeat response latency
```

---

## 7. 주의사항

### 운영
- **supervisor는 반드시 프로젝트 루트의 `supervisor.cmd`로만 실행**
- **rewards.py / env_cfg.py 수정 시 supervisor 재시작 필수**
- **WSL2에서 git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`

### 코드
- **버전별 상수는 TRAINING_CONFIG에서 읽어야 함** (rewards.py에 하드코딩 금지)
- **TRAIN_VERSION 변경 시 supervisor 재시작** — 실행 중 프로세스는 구버전 코드 사용

### V29.2 설계 원칙
- `per_leg_contact_target_band` band_high=0.75 → RL/RR(0.49)이 band 안 → 양의 gradient
- `front_rear_support_balance_penalty` weight=-4.0 → F-R gap 0.36 즉각 패널티
- enforce 타이밍 iter 800 → gait 안정화 충분히 확보 후 잔류 학습

### 참고 문서
- `plan/V29_ANALYSIS.md` — V29 실패 상세 분석
- `plan/V29.2_PLAN.md` — V29.2 설계 및 성공 기준
- `plan/V29_PLAN.md` — V29 원래 설계

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
