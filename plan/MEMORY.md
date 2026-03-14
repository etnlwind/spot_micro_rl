# MEMORY.md — Active AI Session Handoff
> 목적: 새 세션이 이 문서 하나로 현재 학습 상태, 운영 구조, 최근 변경, 다음 할 일을 빠르게 복원하도록 작성.
> 마지막 갱신: 2026-03-14
> 기준 커밋: `3f58591`

---

## 1. 한 줄 요약

SpotMicro RL 프로젝트는 현재 **V24 코드베이스**에서 limb validity gating을 도입한 상태이며, 운영 계층은 `scripts/heartbeat.py`에 **자동 주기적 영상 리포트** (매 1000 iter) 기능이 새로 추가됐다.

---

## 2. 지금 바로 알아야 할 현재 상태

### 2.1 라이브 런타임 스냅샷

| 항목 | 값 |
|------|-----|
| active run | `logs/rsl_rl/spot_micro_flat/2026-03-13_18-53-26` |
| 최신 checkpoint | `model_1800.pt` |
| training | **정지** (2026-03-14 세션 중 수동 정지) |
| supervisor | **정지** |
| heartbeat | **정지** |

**다음 세션 시작 시 supervisor 재시작 + 훈련 재개 필요.**

### 2.2 훈련 진행 상황

| iter | reward | survival | gait | posture | limb_validity |
|------|--------|----------|------|---------|---------------|
| 600 | 323 | 100% | A | C | enforced_fail |
| 1000 | ~430 | 100% | A | B | enforced_fail |
| 1800 | 489 | 100% | A | B | enforced_fail |

- gait/posture는 좋아지고 있으나 rear-left collapse 지속 → limb validity 미통과
- rear-left: contact=0.00, swing=0.99, propulsion=0.00 패턴 반복

---

## 3. V24 변경 요약

### 3.1 새로운 Reward

| reward | weight | 내용 |
|--------|--------|------|
| `limb_usage_min_penalty` | -12.0 | 4개 사지 중 최소 usage < 0.30 시 패널티 |
| `rear_left_right_usage_diff_penalty` | -8.0 | rear 좌우 usage 차이 > 0.18 시 패널티 |

iter 200~600에 걸쳐 선형 ramp. 속도 게이트 적용 (min_vel=0.05).

### 3.2 Ops 추가

- `LIMB_VALIDITY_THRESHOLDS`, `compute_limb_validity_metrics()` — common.py
- `evaluate_limb_gate_checkpoint.py` — 수동 limb validity 평가 유틸
- `analyze_training.py` — limb validity 열, collapse 감지, workbook 기록

---

## 4. 자동 영상 리포트 (신규)

`heartbeat.py`에 추가:

- **매 1000 iter**: 훈련 정지 → 해당 milestone checkpoint로 영상 생성 → Telegram 전송 → 훈련 재개
- 누락 milestone 복수 시 순차 소급 보완
- 환경변수: `VIDEO_REPORT_ITER_STEP=1000`
- 실제 소요: 약 5~7분

```
supervisor 재시작 후 heartbeat가 뜨면
milestone=1000 이 jsonl에 없으므로 자동으로 model_1000.pt 기준 소급 영상 생성 시작됨
```

---

## 5. 코드 구조

### 5.1 Active 운영 파일

| 파일 | 역할 |
|------|------|
| `scripts/common.py` | 상태 해석, Telegram, artifact, formatter, V24 workbook, limb validity |
| `scripts/supervisor.py` | Telegram 명령 루프, start/stop/report/view/shutdown |
| `scripts/heartbeat.py` | 텍스트 heartbeat (100 iter) + 자동 영상 리포트 (1000 iter) |
| `source/.../spot_micro_rl_env_cfg.py` | `TRAIN_VERSION = "V24"`, limb penalty 설정 |
| `source/.../mdp/rewards.py` | `limb_usage_min_penalty`, `rear_left_right_usage_diff_penalty`, `_compute_limb_usage_proxy` |

### 5.2 운영 동작 원칙

- `start` / `stop`만 훈련 상태를 바꾼다
- `report/front/rear/top/side`: 훈련 중이면 최신 artifact 전송, 정지 시 새로 생성
- heartbeat 자동 영상 리포트: 훈련 정지 → 녹화 → 재개 (누락 보완 포함)

---

## 6. 로그 산출물

| 경로 | 내용 |
|------|------|
| `logs/rsl_rl/spot_micro_flat/spotmicro_v24_training_master_log.xlsx` | V24 master workbook |
| `logs/rsl_rl/spot_micro_flat/spotmicro_v24_checkpoint_review.xlsx` | V24 checkpoint review |
| `logs/rsl_rl/spot_micro_flat/<run>/heartbeat_reports.jsonl` | heartbeat + video report 기록 |
| `logs/supervisor.log` | supervisor 운영 로그 |
| `logs/heartbeat.log` | heartbeat / 영상 리포트 로그 |

---

## 7. 다음 우선순위

1. supervisor 재시작 → 훈련 재개
2. heartbeat 자동 소급 영상 리포트 (model_1000.pt) 수신 확인
3. iter 2000~3000 구간에서 rear-left collapse self-correction 여부 관찰
4. limb_usage_min이 0.30에 접근 못 하면 threshold 조정 또는 rear reward 구조 재검토

---

## 8. 작업 시 주의

- Windows 백그라운드 터미널은 `(base)` 에서 뜬다. `conda activate env_isaaclab` 명시 필요.
- `conda run` 쓰지 않는다.
- training 실행: `C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py ...` 형태 유지.
- 상태 해석은 `state.json` 단독이 아니라 live process cmdline + latest checkpoint 기준으로.
- play.py 영상 녹화 실제 소요: 5 views × ~50초 = 약 5분 (40분 아님).

---

## 9. 문서 맵

1. `plan/MEMORY.md` — 이 문서, 가장 짧은 active handoff
2. `plan/CURRENT_STATE_2026-03-14.md` — 현재 세션 상태 상세
3. `plan/V24_PLAN.md` — V24 설계, 구현, 분석
4. `plan/V23_PLAN.md` — V23 배경 참고용
