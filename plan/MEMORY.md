# MEMORY.md — Active AI Session Handoff
> 목적: 새 세션이 이 문서 하나로 현재 학습 상태, 운영 구조, 최근 변경, 다음 할 일을 빠르게 복원하도록 작성.
> 마지막 갱신: 2026-03-12 17:10
> 기준 커밋: `de58e68`

---

## 1. 한 줄 요약

SpotMicro RL 프로젝트는 현재 **V23 코드베이스**에서 flat 환경 학습을 다시 돌리고 있으며, 운영 계층은 `scripts/common.py` 중심으로 **live-process-aware context resolution**, **V23 workbook export**, **rich heartbeat**, **Telegram supervisor**까지 정리된 상태다.

---

## 2. 지금 바로 알아야 할 현재 상태

### 2.1 라이브 런타임 스냅샷

이 문서 갱신 시점 기준:

| 항목 | 값 |
|------|-----|
| active run | `logs/rsl_rl/spot_micro_flat/2026-03-11_22-38-08` |
| active checkpoint | `model_600.pt` |
| mode | `training` |
| latest iter snapshot | `613 / 15000` |
| mean reward | `376.864` |
| mean episode length | `244.2` |
| verdict | `🟢 계속 진행` |
| supervisor version | `de58e68 | latest` |
| heartbeat version | `de58e68 | latest` |

중요:

- 위 수치는 **문서 갱신 시점 스냅샷**이다. 실제 iter/reward는 계속 변한다.
- active run / checkpoint는 더 이상 `state.json`만 믿지 않고, **실행 중인 training process cmdline**과 같은 run 안의 최신 checkpoint를 우선해 해석한다.

### 2.2 현재 무엇이 안정화됐는가

- training / heartbeat / supervisor 프로세스는 모두 분리되어 동작한다.
- `status`는 `supervisor_version`, `heartbeat_version`, `latest/stale`, `pid`를 표시한다.
- heartbeat는 짧은 알림 수준이 아니라, 사람이 읽고 AI가 후속 해석에 사용 가능한 **상세 진단 텍스트**로 복원됐다.
- Telegram `/start` 이후 Isaac Lab 초기화가 느려도, 조기 오판 없이 실제 training process를 기준으로 상태를 본다.
- training stopped 상태에서는 stale checkpoint가 아니라 **같은 run 안의 최신 checkpoint**를 우선 사용한다.

---

## 3. 최근 중요 변경 (2026-03-12)

### 3.1 운영 신뢰도 쪽 변경

최근 반영 커밋 흐름:

| 커밋 | 요약 |
|------|------|
| `b78f89f` | training 정지 후에도 same-run 최신 checkpoint 우선 사용 |
| `6485446` | `status`에 supervisor/heartbeat version + freshness 표시 |
| `44d7169` | 상세 heartbeat 섹션 복원 |
| `23fafd1` | top-level heartbeat bullet formatting 조정 |
| `de58e68` | 최종 heartbeat section formatting 정리 |

핵심 결과:

- `resolve_active_run_dir()` / `resolve_active_checkpoint()` / `resolve_context()`가 live process 우선 해석 구조로 정리됨
- cached artifact (`last_report_zip`, cached videos)는 active run과 path가 맞을 때만 신뢰
- video caption iteration도 stale checkpoint 번호가 아니라 current display iteration을 사용

### 3.2 Heartbeat 포맷 최종 상태

현재 heartbeat는 다음 원칙을 따른다.

- 상단 요약 블록은 `•` bullet 사용
- `운영 판정`, `우선 KPI`, `코어 품질`, `학습 지표`, `좋은 점`, `문제점` 등 같은 depth의 소제목은 모두 **bold**
- 이모지로 시작하는 KPI/trend 줄은 접두 bullet 없이 바로 시작
- 설명성 문장과 리스트성 보조 항목은 `•` bullet 사용
- contact 기반 stride/cycle 계열은 **참고 지표**로만 명시

실제 heartbeat는 다음 계층을 포함한다.

- iter / reward / ep_len / termination / best-worst
- 운영 판정
- 우선 KPI
- 코어 품질
- KPI 상태
- 핵심 추세
- 보행 보상 추세
- 페널티 추세
- 동작 품질
- 학습 지표
- TOP5 기여 보상 / 패널티
- 보상 추이
- 학습 단계
- 좋은 점 / 문제점
- AI 분석 의견
- 참고

### 3.3 실전 검증 여부

2026-03-12 세션에서 아래를 직접 확인했다.

- status 텍스트 생성 성공
- heartbeat 텍스트 수동 렌더링 성공
- Telegram으로 heartbeat 수동 전송 성공
- heartbeat / supervisor 재시작 후 두 프로세스 모두 `latest`로 표기됨
- 과도하게 남아 있던 idle PowerShell shell 정리 후에도 training/supervisor/heartbeat 생존 확인

---

## 4. 코드 구조와 역할 분담

### 4.1 현재 active 운영 파일

| 파일 | 역할 |
|------|------|
| `scripts/common.py` | 상태 해석, process 탐지, Telegram 전송, report/video helper, V23 workbook export, heartbeat/status formatter |
| `scripts/supervisor.py` | Telegram 명령 루프, local CLI, start/stop/report/view/shutdown 처리 |
| `scripts/heartbeat.py` | read-only heartbeat polling loop, heartbeat history 기록, Telegram 송신 |
| `source/.../spot_micro_rl_env_cfg.py` | 현재 학습 reward/target 정의, `TRAIN_VERSION = "V23"` |
| `source/.../mdp/rewards.py` | V23 raw metric export, posture/stance/foot-jitter 관련 계산 |

### 4.2 legacy와 active를 혼동하지 말 것

- active 파일은 `scripts/supervisor.py`, `scripts/heartbeat.py`, `scripts/common.py`다.
- `scripts/legacy/heartbeat.py`, `scripts/legacy/supervisor.py`는 **참고용 보관본**이다.
- legacy heartbeat는 richer formatter의 아이디어 소스였지만, 현재 실제 송신 코드는 `scripts/common.py::format_report()`를 쓴다.

---

## 5. 운영 동작 규칙

### 5.1 supervisor 명령

현재 active 명령:

- `start`
- `stop`
- `status`
- `report`
- `front`
- `rear`
- `top`
- `side`
- `help`
- `shutdown`

### 5.2 report/view 원칙

- training 중이면 기존 최신 artifact만 전송한다.
- training stopped 상태에서만 현재 active checkpoint 기준으로 새 artifact를 생성한다.
- heartbeat는 read-only다. training process를 중단하거나 재개하지 않는다.

### 5.3 상태 해석 원칙

- live training process가 있으면 그것이 가장 신뢰도 높은 source다.
- stopped 상태에서는 같은 run 안의 최신 checkpoint를 우선 사용한다.
- stale cached path는 active run과 맞지 않으면 버린다.

---

## 6. V23 기준 핵심 파일과 산출물

### 6.1 학습/환경 쪽

| 파일 | 포인트 |
|------|--------|
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py` | `TRAIN_VERSION = "V23"`, shoulder target/stance width 관련 V23 조정 포함 |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py` | `compute_v23_raw_metrics()`, `accumulate_v23_raw_metrics()`, `reset_v23_raw_metric_extras()` |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env.py` | raw metric extras를 episode reset에 연결 |

### 6.2 운영/로그 산출물

| 경로 | 내용 |
|------|------|
| `logs/rsl_rl/spot_micro_flat/<run>/heartbeat_reports.jsonl` | heartbeat history record |
| `logs/rsl_rl/spot_micro_flat/<run>/spotmicro_v23_run_<run>_training_log.xlsx` | per-run V23 workbook |
| `logs/rsl_rl/spot_micro_flat/spotmicro_v23_training_master_log.xlsx` | master workbook |
| `logs/rsl_rl/spot_micro_flat/spotmicro_v23_checkpoint_review.xlsx` | checkpoint review workbook |
| `logs/training_launch.log` | detached training launch 로그 |
| `logs/heartbeat.log` | heartbeat 송신/루프 로그 |
| `logs/supervisor.log` | supervisor 운영 로그 |

---

## 7. 문서 맵

현재 문서 읽기 순서 추천:

1. `plan/MEMORY.md`
2. `plan/CURRENT_STATE_2026-03-12.md`
3. `plan/V23_PLAN.md`
4. `plan/V22_ANALYSIS.md`
5. 필요 시 버전별 히스토리 문서

문서 역할:

- `MEMORY.md`: 가장 짧은 active handoff
- `CURRENT_STATE_2026-03-12.md`: 이번 세션 기준 운영/코드 상태 상세 정리
- `PROJECT_HISTORY.md`: 프로젝트 전체 연대기 개요
- `V23_PLAN.md`: 남은 V23 실험 계획

---

## 8. 지금 시점의 다음 우선순위

1. 현재 run `2026-03-11_22-38-08`의 초기 구간이 heartbeat/영상 기준으로 정상적으로 이어지는지 계속 관찰
2. 다음 실제 stop/report/view 사이클에서 same-run latest checkpoint 선택이 계속 맞는지 재검증
3. V23 posture-first refinement와 운영 계측 레이어를 문서상 분리 유지한 채, 실제 reward 실험을 다시 시작

---

## 9. 작업 시 주의

- Windows 백그라운드 터미널은 `(base)`에서 뜬다. `conda activate env_isaaclab`를 명시적으로 먼저 실행한다.
- `conda run`은 쓰지 않는다.
- training process에는 `Select-Object -First N` 같은 파이프를 걸지 않는다.
- training 실행은 항상 `C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py ...` 형태를 유지한다.
- 운영 문제를 볼 때는 `state.json`만 보지 말고 process cmdline, current run path, latest checkpoint를 같이 본다.
