# Current State — 2026-03-12

## 1. 문서 목적

이 문서는 2026-03-12 세션 종료 시점의 **실제 코드 상태**, **실행 중인 운영 상태**, **최근 설계 결정**, **남은 작업**을 구조적으로 정리한 handoff 문서다. 버전별 분석 문서를 대체하지 않는다. 대신, 현재 active 경로에서 무엇이 사실인지 빠르게 복원하는 용도다.

---

## 2. Executive Summary

- 현재 프로젝트는 `TRAIN_VERSION = "V23"` 코드베이스에서 flat training run을 재개한 상태다.
- 운영 레이어는 `scripts/common.py`, `scripts/supervisor.py`, `scripts/heartbeat.py` 3개 파일 중심으로 수렴했다.
- 2026-03-12 세션에서 가장 큰 변경은 **context freshness 문제 해결**과 **heartbeat 정보량 복원**이다.
- 상태 해석은 더 이상 `state.json` 단독이 아니라, **live process cmdline + same-run latest checkpoint + run-matched cached artifact** 조합으로 동작한다.

---

## 3. Live Runtime Snapshot

문서 작성 시점 스냅샷:

| 항목 | 값 |
|------|-----|
| branch | `develop` |
| latest commit | `de58e68` |
| active run | `2026-03-11_22-38-08` |
| active checkpoint | `model_600.pt` |
| status mode | `training` |
| iter snapshot | `613 / 15000` |
| supervisor_version | `de58e68 | latest | pid 81716` |
| heartbeat_version | `de58e68 | latest | pid 65060` |

주의:

- 위 pid와 iter는 시점 스냅샷이다.
- 이후 세션에서 같은 run이더라도 iter는 더 진행돼 있을 수 있다.

---

## 4. 2026-03-12에서 실제 해결된 것

### 4.1 stopped-state checkpoint 오판 수정

문제:

- training이 정지된 뒤 report/view가 stale `active_checkpoint`를 계속 사용할 수 있었다.

해결:

- same-run 안의 최신 checkpoint를 다시 탐색해서 우선 사용하도록 변경했다.

영향:

- `report`, `front`, `rear`, `top`, `side`가 training stopped 상태에서도 더 최신 checkpoint 기준으로 동작한다.

### 4.2 live context vs stale cache 문제 축소

문제:

- active run, checkpoint, cached artifact가 `state.json` 위주로 해석되면서 stale 값이 섞일 수 있었다.

해결:

- live training process cmdline을 우선 사용
- cached ZIP/video는 현재 active run과 path가 맞는 경우만 사용
- display iteration도 live/current 기준으로 계산

영향:

- `/status`, video caption, `/report` 결과가 실제 실행 상태와 더 잘 맞는다.

### 4.3 heartbeat 가독성과 정보량 복원

문제:

- 운영 heartbeat가 지나치게 축약되어, 사람이 읽기에도 AI에게 넘기기에도 정보 손실이 컸다.

해결:

- legacy heartbeat의 좋은 요소를 `scripts/common.py::format_report()`에 복원
- 텔레그램 실제 전송을 여러 차례 수동 검증하며 section formatting을 다듬음

최종 포함 섹션:

- iter/reward/ep_len/termination/best-worst
- 운영 판정
- 우선 KPI
- 코어 품질
- KPI 상태
- 핵심 추세
- 보행 보상 추세
- 페널티 추세
- 동작 품질
- 학습 지표
- TOP5 기여 보상
- TOP5 패널티
- 보상 추이
- 학습 단계
- 좋은 점
- 문제점
- AI 분석 의견
- 참고

### 4.4 status에 process freshness 표시 추가

상태 출력은 현재 다음을 포함한다.

- `supervisor_version`
- `heartbeat_version`
- `latest/stale`
- `pid`

이 값은 코드 파일 mtime과 process `create_time` 비교로 계산된다.

---

## 5. 운영 아키텍처

### 5.1 active 파일

| 파일 | 책임 |
|------|------|
| `scripts/common.py` | 상태 해석, Telegram 전송, artifact lookup, formatter, V23 workbook export |
| `scripts/supervisor.py` | Telegram/local command 처리, train/report/view orchestration |
| `scripts/heartbeat.py` | read-only heartbeat polling loop |

### 5.2 supervisor 명령 집합

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

### 5.3 artifact 동작 규칙

- training 중: 최신 기존 artifact만 전송
- training stopped: 현재 active checkpoint 기준으로 새 artifact 생성 가능
- heartbeat는 read-only이며 훈련 프로세스를 바꾸지 않음

---

## 6. Heartbeat Formatting Final Decision

최종 포맷 원칙:

- 상단 summary 5줄은 `•`
- 같은 depth의 소제목은 전부 **bold**
- 이모지/아이콘으로 시작하는 KPI/trend 줄은 bullet 없이 바로 표시
- 일반 설명/보조 문장 줄은 `•`

예:

```html
• iter: 613 / 15,000 (4.1%)
• reward: 376.864 (avg10: 379.242)

<b>운영 판정: 🟢 계속 진행</b>
• 생존 100.0%로 초기 기준 통과
• 양호: forward_velocity, diagonal_coupling, trot_gait

<b>우선 KPI (gait quality first)</b>
🟡 기립높이: +0.1556 ➡️ (+1.3%) [형성중]
🟢 전진속도: +1.2110 📈 (+55.0%) [양호]
```

실전 검증:

- 수동 Telegram heartbeat 전송 다회 성공
- 최종 로그에서 `• iter: ...` 포맷 확인

---

## 7. V23 코드와 계획의 현재 관계

현재는 “V23이 아직 계획만 있는 상태”가 아니다.

이미 코드에 들어간 것:

- `TRAIN_VERSION = "V23"`
- shoulder target / stance width 계열 V23 phase-1 조정
- raw posture/style/jitter metric export
- V23 workbook generation (`run/master/checkpoint review`)
- V23 운영 score/logging layer

아직 남은 것:

- 현재 run 결과를 본 뒤 실제 V23 posture-first refinement 실험 결과를 본격적으로 비교
- front-view 중심 style ranking과 manual shortlist 루프 정교화
- 필요시 distal jitter / front-rear balance refinement를 2단계로 분리 진행

---

## 8. 다음 세션에서 먼저 할 일

1. 현재 active run이 1000 iter 전후까지 정상적으로 이어지는지 heartbeat와 video 기준으로 확인
2. 실제 stopped-state report/view 한 번 더 수행해서 latest checkpoint 선택이 계속 맞는지 검증
3. V23_PLAN 기준으로 “이미 끝난 instrumentation/ops baseline”과 “아직 남은 reward/style 실험”을 혼동하지 않도록 유지

---

## 9. 참고 문서

- `plan/MEMORY.md`
- `plan/PROJECT_HISTORY.md`
- `plan/V23_PLAN.md`
- `plan/V22_ANALYSIS.md`
- `plan/V21_ANALYSIS.md`