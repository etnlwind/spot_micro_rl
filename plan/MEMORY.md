# MEMORY.md — Active AI Session Handoff
> 목적: 새 세션이 이 문서 하나로 현재 상태, 운영 구조, 최근 변경, 다음 할 일을 빠르게 복원하도록 작성.
> 마지막 갱신: 2026-03-14 야간
> 기준 커밋: `147ef5f`

---

## 1. 한 줄 요약

SpotMicro RL V24 코드베이스. 훈련 iter 1800에서 재개 중. 자동 영상 리포트 버그 수정 완료. 다음 리포트 iter 2000.

---

## 2. 지금 바로 알아야 할 현재 상태

| 항목 | 값 |
|------|-----|
| active run | `2026-03-14_18-29-12` (model_1800.pt에서 재개) |
| training | **실행 중** |
| supervisor | **실행 중** (`supervisor.cmd --listen`으로 시작) |
| heartbeat | **실행 중** |
| 다음 영상 리포트 | iter 2000 |

---

## 3. 진입점 (중요)

```bat
supervisor.cmd --listen     ← 유일한 공식 진입점
```

구조: `supervisor.cmd`(루트) → `scripts/supervisor.cmd` → `scripts/supervisor.py`

**절대 다른 방법으로 supervisor 시작하지 말 것.**

---

## 4. 최근 버그 수정 (2026-03-14)

### 훈련 자동 재시작 실패

- **원인**: `_launch_training_command`가 `DETACHED_PROCESS`로 실행 → 콘솔 없음 → `conda activate` 실패
- **수정**: `_popen_hidden_cmd` 방식으로 변경 (`scripts/common.py`)

### heartbeat 재시작 시 중복 영상 리포트

- **원인**: 새 런 감지 시 `last_video_milestone` 0으로 리셋 → 이미 완료한 milestone 재시도 → 훈련 반복 종료
- **수정**: resume checkpoint iter 파싱 후 이하 milestone skip (`scripts/heartbeat.py`, `_get_resume_checkpoint_iter()`)

---

## 5. 운영 동작 흐름

```
supervisor.cmd --listen
    → supervisor.py (Telegram 폴링)
    → heartbeat.py 자동 시작
        → 100 iter: 텍스트 heartbeat
        → 1000 iter: 훈련 정지 → 영상 5 views → Telegram → 훈련 재시작
```

Telegram 명령: `/start` `/stop` `/status` `/report` `/front` `/rear` `/top` `/side` `/help` `/shutdown`

---

## 6. V24 Reward 구조

| reward | weight | 내용 |
|--------|--------|------|
| `limb_usage_min_penalty` | -12.0 | 4개 사지 중 최소 usage < 0.30 시 패널티 |
| `rear_left_right_usage_diff_penalty` | -8.0 | rear 좌우 usage 차이 > 0.18 시 패널티 |

iter 200~600 선형 ramp. 속도 게이트 min_vel=0.05.

---

## 7. 훈련 진행 상황

| iter | reward | limb_validity | 비고 |
|------|--------|---------------|------|
| 1000 | ~430 | enforced_fail | rear-left collapse 지속 |
| 1800 | 489 | enforced_fail | gait A, posture B |

rear-left: `contact=0.00, swing=0.99, propulsion=0.00` — self-correction 미확인

---

## 8. 다음 우선순위

1. iter 2000 자동 영상 리포트 정상 수신 확인
2. iter 2000~3000 rear-left collapse self-correction 여부 관찰
3. 미개선 시 threshold 조정 또는 rear reward 구조 재검토

---

## 9. 작업 시 주의

- supervisor는 반드시 `supervisor.cmd --listen`으로만 시작
- 훈련 시작/중단은 Telegram `/start` `/stop` 또는 supervisor CLI
- 직접 python/프로세스 kill 하지 말 것 — supervisor가 상태 추적을 잃음
- `logs/_launch_*.cmd` 파일들은 런타임 생성 임시 파일 (수동 실행 대상 아님)

---

## 10. 문서 맵

1. `plan/MEMORY.md` — 이 문서
2. `plan/CURRENT_STATE_2026-03-15.md` — 현재 세션 상세 (버그 수정 포함)
3. `plan/CURRENT_STATE_2026-03-14.md` — 이전 세션 상태
4. `plan/V24_PLAN.md` — V24 설계 및 분석
