# MEMORY.md — Active AI Session Handoff
> 목적: 새 세션이 이 문서 하나로 현재 상태, 운영 구조, 최근 변경, 다음 할 일을 빠르게 복원하도록 작성.
> 마지막 갱신: 2026-03-14 (V24 종료)
> 기준 커밋: `05d34d8`

---

## 1. 한 줄 요약

SpotMicro RL **V24 종료 — 목표 미달성**. rear-left collapse 전 구간 지속. V25 설계 필요.

---

## 2. V24 최종 결과

| 항목 | 결과 |
|------|------|
| 최종 run | `2026-03-14_18-29-12` |
| 훈련 범위 | iter 1800 → 2002 |
| 최종 reward | ~544 |
| survival | 100% (iter 600+) |
| gait | A |
| posture | B |
| limb_validity_gate | **전 구간 enforced_fail** |
| rear-left contact | 0.0002~0.0004 (사실상 0) |
| rear-left swing | 0.97~0.99 (항상 공중) |
| self-correction | **없음** |

**핵심 실패 원인**: ramp 패널티 적용 이전에 collapse가 이미 고착. 패널티가 교정이 아닌 회피를 유도.

---

## 3. 진입점 (중요)

```bat
supervisor.cmd --listen     ← 유일한 공식 진입점
```

구조: `supervisor.cmd`(루트) → `scripts/supervisor.cmd` → `scripts/supervisor.py`

**절대 다른 방법으로 supervisor 시작하지 말 것.**

---

## 4. 운영 동작 흐름

```
supervisor.cmd --listen
    → supervisor.py (Telegram 폴링)
    → heartbeat.py 자동 시작
        → 100 iter: 텍스트 heartbeat
        → 1000 iter: 훈련 정지 → 영상 5 views → Telegram → 훈련 재시작
```

Telegram 명령: `/start` `/stop` `/status` `/report` `/front` `/rear` `/top` `/side` `/help` `/shutdown`

---

## 5. 현재 상태

| 항목 | 값 |
|------|-----|
| training | **정지** (V24 종료) |
| supervisor | 확인 필요 |
| 코드베이스 | V24 유지 중 |

---

## 6. V25 설계 방향

V24 실패에서 도출된 교훈:

1. **per-limb 직접 패널티**: rear-left contact_ratio에 lower-bound penalty 직접 부여 (min_usage 방식 폐기)
2. **패널티 시작점 앞당김**: iter 0부터 적용, ramp 제거 또는 시작 iter를 0으로
3. **restart-on-collapse**: iter 300 이전 collapse 감지 시 run 즉시 종료 후 재시작
4. **reward 경로 차단**: 3다리 보행으로 diagonal_coupling 보상을 얻지 못하도록 수정

---

## 7. 작업 시 주의

- supervisor는 반드시 `supervisor.cmd --listen`으로만 시작
- 훈련 시작/중단은 Telegram `/start` `/stop` 또는 supervisor CLI
- 직접 python/프로세스 kill 하지 말 것 — supervisor가 상태 추적을 잃음
- `logs/_launch_*.cmd` 파일들은 런타임 생성 임시 파일 (수동 실행 대상 아님)

---

## 8. 문서 맵

1. `plan/MEMORY.md` — 이 문서
2. `plan/CURRENT_STATE_2026-03-15.md` — V24 최종 세션 상세
3. `plan/V24_ANALYSIS.md` — V24 설계, 결과, 원인 분석, V25 제언
4. `plan/V23_ANALYSIS.md` — V23 배경
