# Current State — 2026-03-14

## 1. 문서 목적

2026-03-14 세션 기준 실제 코드 상태, 운영 상태, 최근 설계 결정, 남은 작업을 정리한 handoff 문서.

---

## 2. Executive Summary

- 코드베이스는 `TRAIN_VERSION = "V24"` 로 전환 완료.
- V24 핵심 변경은 **limb validity gating** — rear-left collapse 및 좌우 비대칭을 명시적으로 차단.
- 현재 active run `2026-03-13_18-53-26`은 iter 1800+ 진행 중이며, gait/posture는 개선되고 있으나 limb validity는 아직 미통과.
- 운영 레이어에 **자동 주기적 영상 리포트** 기능이 추가됨 (매 1000 iter, 훈련 정지 → 녹화 → 재개).
- 2026-03-14 세션 종료 시점에 supervisor/heartbeat는 모두 정지된 상태.

---

## 3. Live Runtime Snapshot

문서 작성 시점 스냅샷:

| 항목 | 값 |
|------|-----|
| branch | `develop` |
| latest commit | `3f58591` |
| active run | `2026-03-13_18-53-26` |
| 최신 checkpoint | `model_1800.pt` |
| training status | **정지** (세션 중 수동 정지) |
| supervisor | **정지** |
| heartbeat | **정지** |

다음 세션에서는 supervisor 재시작 후 훈련 재개 필요.

---

## 4. V24 구현 내용

### 4.1 새로운 Reward Term

| reward | weight | 목적 |
|--------|--------|------|
| `limb_usage_min_penalty` | -12.0 | 가장 덜 쓰인 사지 usage < 0.30 시 패널티 |
| `rear_left_right_usage_diff_penalty` | -8.0 | rear-left/right 사용량 차이 > 0.18 시 패널티 |

두 패널티 모두 iter 200~600에 걸쳐 선형 ramp(-3.0 → -12.0, -2.0 → -8.0), 속도 게이트 적용(min_vel=0.05).

### 4.2 Ops 추가

| 파일 | 변경 |
|------|------|
| `scripts/common.py` | `LIMB_VALIDITY_THRESHOLDS`, `compute_limb_validity_metrics()`, validity stage 판정 로직 |
| `scripts/utils/evaluate_limb_gate_checkpoint.py` | checkpoint 단위 limb validity 수동 평가 |
| `scripts/utils/analyze_training.py` | limb validity 열 추출, collapse detection, workbook 기록 |

### 4.3 관련 로그 산출물 (V24)

| 경로 | 내용 |
|------|------|
| `logs/rsl_rl/spot_micro_flat/spotmicro_v24_training_master_log.xlsx` | V24 master workbook |
| `logs/rsl_rl/spot_micro_flat/spotmicro_v24_checkpoint_review.xlsx` | V24 checkpoint review |
| `logs/rsl_rl/spot_micro_flat/<run>/spotmicro_v24_run_*_training_log.xlsx` | per-run workbook |

---

## 5. 현재 훈련 결과 해석

### 5.1 긍정적 지표

- iter 600 이후 생존율 100% 안정화
- reward 지속 상승 (271 → 489 at iter 1803)
- gait score A, posture score B 수준 달성

### 5.2 해결되지 않은 문제

- **rear-left collapse 지속**: 모든 checkpoint에서 `contact=0.00, swing=0.99, propulsion=0.00`
- **rear 좌우 비대칭**: diff 0.93 (기준 0.18 대비 5배 초과)
- **limb_validity_gate 미통과**: iter 600+ 전체가 `enforced_fail` 판정

### 5.3 현재 해석

V24 penalty가 정상 작동하고 있다. 문제는 현재 reward 구조가 rear-left를 사용하지 않고도 높은 보상을 얻을 수 있는 경로가 존재한다는 것. 훈련을 더 진행하며 self-correction 여부를 관찰하는 것이 우선이다.

---

## 6. 운영 아키텍처 현황

### 6.1 Active 파일

| 파일 | 책임 |
|------|------|
| `scripts/common.py` | 상태 해석, Telegram 전송, artifact lookup, formatter, V24 workbook export, limb validity 분석 |
| `scripts/supervisor.py` | Telegram 명령 루프, local CLI, start/stop/report/view/shutdown 처리 |
| `scripts/heartbeat.py` | 텍스트 heartbeat (100 iter) + **자동 영상 리포트 (1000 iter)** |

### 6.2 자동 영상 리포트 (신규, 2026-03-14)

`heartbeat.py`에 추가된 기능:

- **매 1000 iter마다** 자동으로 훈련 정지 → 영상 녹화 → Telegram 전송 → 훈련 재개
- 해당 milestone의 **정확한 checkpoint** 사용 (model_1000.pt, model_2000.pt 등)
- heartbeat/supervisor 장애로 **누락된 milestone이 복수 개**이면 순차 보완
- 메시지: 정상(`AUTO VIDEO REPORT — iter N`), 누락 보완(`iter N (누락 보완 K/M)`)
- 영상 녹화 실제 소요: 약 5~7분 (5 views × ~50초 + zip/분석)

환경 변수로 변경 가능:
```
VIDEO_REPORT_ITER_STEP=1000  (기본값)
```

### 6.3 Supervisor 명령

- `start`, `stop`, `status`, `report`, `front`, `rear`, `top`, `side`, `help`, `shutdown`

---

## 7. 다음 세션 우선 할 일

1. **supervisor 재시작** → `supervisor.cmd --listen`
2. **훈련 재시작** → Telegram `/start` 또는 `supervisor.cmd --start`
3. **iter 1800 video report 소급 생성 여부 결정**
   - heartbeat가 재시작되면 milestone=1000이 이미 기록에 없으므로 자동 소급 시도
   - model_1000.pt 기준으로 영상 + 리포트 생성됨
4. **iter 2000~3000 구간 관찰**
   - rear-left collapse self-correction 여부
   - limb_usage_min이 0.30에 접근하는지 추이 확인
5. **결과에 따라 분기**
   - self-correction 징후 있으면 계속 진행
   - 없으면 threshold 재검토 또는 rear reward 구조 분석

---

## 8. 참고 문서

- `plan/MEMORY.md` — active handoff
- `plan/V24_PLAN.md` — V24 설계 및 분석
- `plan/V23_PLAN.md` — V23 배경
