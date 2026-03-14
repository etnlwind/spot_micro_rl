# Current State — 2026-03-15

## [2026-03-15 최신] V26.1 훈련 시작

| 항목 | 값 |
|------|-----|
| 상태 | V26.1 훈련 진행 중 (fresh run) |
| TRAIN_VERSION | `"V26"` |
| supervisor PID | 18064 |
| 진입점 | `logs\_launch_supervisor.cmd` |
| 핵심 설계 | Symmetric Existence Floor + Load Sharing (8 reward terms) |
| 이전 버전 | V25 실패 — iter 400, RR collapse (비대칭 패널티의 한계) |

상세 내용은 [V26.1_PLAN.md](V26.1_PLAN.md) 참조.

---

## 1. 문서 목적

2026-03-14 야간 세션 기준 실제 코드 상태, 운영 상태, 버그 수정 내역, 다음 할 일을 정리한 handoff 문서.

**[2026-03-14 추가]** V24 훈련 종료. iter 2002까지 진행. 목표 미달성 — V25 설계 필요.
**[2026-03-15 추가]** V25 훈련 종료. iter 400, RR collapse — V26.1 전환.

---

## 2. Executive Summary

- V24 코드베이스 유지. 훈련은 iter 1800에서 재개하여 현재 진행 중.
- **버그 수정 완료**: 자동 영상 리포트 후 훈련 재시작이 안 되던 문제, heartbeat 재시작 시 중복 리포트 문제.
- **진입점 구조 정리**: `supervisor.cmd`(루트) → `scripts/supervisor.cmd` → `scripts/supervisor.py`.
- supervisor/heartbeat/훈련 모두 실행 중. 다음 비디오 리포트는 iter 2000.

---

## 3. Live Runtime Snapshot

| 항목 | 값 |
|------|-----|
| branch | `develop` |
| latest commit | `147ef5f` |
| active run | `2026-03-14_18-29-12` (model_1800.pt에서 재개) |
| training status | **실행 중** |
| supervisor PID | 11528 |
| heartbeat | **실행 중** |
| 다음 영상 리포트 | iter 2000 |

---

## 4. 버그 수정 내역 (2026-03-14 세션)

### 4.1 훈련 자동 재시작 실패 (`_launch_training_command`)

**원인**: `DETACHED_PROCESS | CREATE_NO_WINDOW` 플래그로 실행 시 콘솔이 완전히 분리되어 `conda activate`가 실패 → 훈련이 아무 출력 없이 조용히 종료.

**수정** (`scripts/common.py`):
- `_launch_training_command`에서 `DETACHED_PROCESS` 제거
- `_popen_hidden_cmd` 방식으로 변경 (stdout → `training_launch.log`)
- `_escape_cmd_echo_text` 미사용 함수 제거

### 4.2 heartbeat 재시작 시 중복 영상 리포트 (`heartbeat.py`)

**원인**: heartbeat 재시작 또는 새 런 감지 시 `last_video_milestone`을 0으로 초기화 → 이미 완료된 iter 1000을 반복 시도 → 훈련 강제 종료 후 새 런에서 model_1000.pt 없음 → 무한 반복.

**수정** (`scripts/heartbeat.py`):
- `_get_resume_checkpoint_iter()` 함수 추가: `state.json`의 `active_checkpoint`에서 iter 번호 파싱
- 런 변경 감지 시 resume checkpoint iter 이하의 milestone은 자동 skip

```python
resume_iter = _get_resume_checkpoint_iter()
if resume_iter > 0:
    skip_up_to = (resume_iter // args.video_iter_step) * args.video_iter_step
    last_video_milestone = max(last_video_milestone, skip_up_to)
```

---

## 5. 진입점 구조 (정리 완료)

```
supervisor.cmd          ← 사용자 실행 진입점 (루트, 1줄 위임)
    └→ scripts/supervisor.cmd   ← conda 경로 자동 탐색, python 전체 경로 실행
           └→ scripts/supervisor.py  ← 실제 구현
```

- `supervisor.ps1` (루트): PowerShell용 래퍼, `supervisor.cmd` 호출
- **반드시 `supervisor.cmd --listen`으로만 시작**
- `logs/_launch_supervisor.cmd`: 런타임 생성 임시 파일 (진입점 아님)

### 실행 커맨드

```
supervisor.cmd --listen
```

### Telegram 명령

`/start`, `/stop`, `/status`, `/report`, `/front`, `/rear`, `/top`, `/side`, `/help`, `/shutdown`

---

## 6. 운영 동작 흐름

```
supervisor.cmd --listen
    → supervisor.py 시작 (Telegram 폴링)
    → heartbeat.py 자동 시작
        → 100 iter마다 텍스트 heartbeat
        → 1000 iter마다:
            1. 훈련 정지 (common.stop_training)
            2. 영상 녹화 (5 views)
            3. Telegram 전송
            4. 훈련 재시작 (common.launch_training → _launch_training_command)
```

`launch_training`은 `_popen_hidden_cmd`로 실행 → 콘솔 유지 → `conda activate` 정상 작동 → `training_launch.log`에 출력 기록.

---

## 7. V24 최종 훈련 결과

### 7.1 run별 summary

| run | iter 범위 | 최종 reward | survival | gait | limb_validity |
|-----|----------|------------|----------|------|---------------|
| `2026-03-13_18-53-26` | 0 → 1803 | 489 | 100% | A | 전 구간 fail |
| `2026-03-14_18-29-12` | 1800 → 2002 | ~544 | 100% | A | 전 구간 fail |

### 7.2 per-iter 지표 (최종 run, training_launch.log)

| 지표 | 전 구간 관측 범위 | 판정 |
|------|----------------|------|
| contact_ratio_rl | 0.0002 ~ 0.0004 | 완전 평탄, 개선 없음 |
| propulsion_rl | 0.0001 ~ 0.0002 | 완전 평탄, 개선 없음 |
| stance_time_rl | 0.0002 ~ 0.0004 | contact와 동일 |
| swing_time_rl | 0.97 ~ 0.99 | 거의 항상 공중 |
| contact_ratio_rr | 0.81 ~ 0.89 | 정상 |
| propulsion_rr | 0.61 ~ 0.65 | 정상 |

### 7.3 limb_usage_min 추이 (전 실험 구간)

| iter | limb_usage_min | 비고 |
|------|---------------|------|
| 381 | 0.1040 | 패널티 ramp 초기, 수치 존재 |
| 500 | 0.0451 | 하락 시작 |
| 600 | 0.00379 | collapse 고착, enforce 진입 |
| 800 | 0.000362 | 계속 하락 |
| 1803 | 0.000079 | |
| 1900 | 0.000065 | 최솟값 근접 |

단조 감소 — 패널티가 교정이 아닌 회피를 유도함.

### 7.4 결론

- **V24 목표(limb_validity_gate 통과) 달성 실패**
- self-correction 없음, 200 iter 연속 c_rl < 0.001
- 패널티 방식만으로 고착된 collapse를 되돌리는 것은 불가능

---

## 8. 다음 우선순위 (V25 설계)

1. **per-limb 직접 패널티**: rear-left contact_ratio에 lower-bound penalty 직접 부여
2. **collapse 사전 차단**: validity 패널티를 iter 0부터 적용 (ramp 제거 또는 시작점 앞당김)
3. **restart-on-collapse 전략**: iter 300 이전 collapse 감지 시 run 즉시 종료 후 재시작
4. **reward 경로 차단**: 3다리 보행으로 diagonal_coupling 보상을 얻지 못하도록 수정

---

## 9. 참고 문서

- `plan/MEMORY.md` — active handoff (가장 짧은 요약)
- `plan/V24_ANALYSIS.md` — V24 설계 및 분석
- `plan/CURRENT_STATE_2026-03-14.md` — 이전 세션 상태
