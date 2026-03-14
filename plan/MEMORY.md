# MEMORY.md — Active AI Session Handoff

> 목적: 새 세션이 이 문서 하나로 현재 상태, 운영 구조, 최근 변경, 다음 할 일을 빠르게 복원하도록 작성.
> 마지막 갱신: 2026-03-15 (V26.1 훈련 시작)
> 기준 커밋: `866f995`

---

## 1. 한 줄 요약

SpotMicro RL **V26.1 훈련 시작** — Symmetric Existence Floor + Load Sharing.
V25에서 비대칭 패널티가 collapse 위치만 이동시킨 실패 교훈으로, 모든 다리에 동일 기준 적용.

---

## 2. V23~V26 경과 요약

| 버전 | 판정 | 핵심 실패/교훈 |
|------|------|----------------|
| V23 | 실패 | rear-left 3족 보행 exploit. contact sensor `foot_link` 오매핑 |
| V24 | 실패 | collapse 고착 후 패널티가 교정이 아닌 회피를 유도 |
| V25 | **실패 (iter 400)** | RL 회복 → RR collapse. 비대칭 패널티의 근본 한계 |
| **V26.1** | **훈련 중** | 8개 symmetric reward term |

---

## 3. V26.1 구현 내용

### 새로 추가된 reward term (8개)

**Existence Floor — iter 0~200 ramp (초기값→최종값)**

| term | 최종 weight | 역할 |
|------|------------|------|
| `per_leg_contact_floor` | -20.0 | 각 다리 contact_ratio < 0.10 시 패널티 |
| `per_leg_propulsion_floor` | -15.0 | 각 다리 propulsion < 0.05 시 패널티 (fake contact 차단) |
| `limb_usage_min_penalty` | -15.0 | 4다리 중 최소 usage < 0.10 시 패널티 |

**Load Sharing — iter 200~350 ramp (0→최종값)**

| term | 최종 weight | 역할 |
|------|------------|------|
| `rear_left_right_usage_diff_penalty` | -10.0 | rear 좌우 usage 편중 억제 |
| `front_left_right_usage_diff_penalty` | -8.0 | front 좌우 usage 편중 억제 |
| `rear_left_right_propulsion_diff_penalty` | -8.0 | rear 좌우 추진 편중 억제 |
| `front_rear_support_balance_penalty` | -5.0 | 앞/뒤 지지 편중 억제 |

**Gait Exploit 차단**

| term | weight | 역할 |
|------|--------|------|
| `diagonal_coupling_soft_gate_reward` | +25.0 | 모든 다리 대칭 gate (min_contact=0.15) |

### 제거된 term
- `rear_left_contact_floor_penalty` (V25 비대칭 패널티 — 제거)

### gait_gate 동작
- floor/load ramp는 gait_gate에 의해 멈추지 않음 (존재 floor는 항상 진행)
- Phase 1→2, 2→3 ramp만 ep_len 기준으로 pause 가능

---

## 4. 진입점 (중요)

```bat
logs\_launch_supervisor.cmd     ← 유일한 공식 진입점
```

- supervisor PID 18064 실행 중 (2026-03-15 기준)
- 훈련 시작: Telegram `/start` → 확인 프롬프트에 y/Y로 시작하는 단어 입력 (yes, Yes, YES 등)

---

## 5. 현재 상태

| 항목 | 값 |
|------|-----|
| training | V26.1 시작 (fresh run) |
| supervisor | PID 18064 실행 중 |
| TRAIN_VERSION | `"V26"` |
| active run | 2026-03-15 시작 예정 |

---

## 6. V26.1 판정 기준

### iter 200 — CRITICAL 경고
- 어느 다리든 `contact_ratio < 0.05`
- 어느 다리든 `propulsion ≈ 0`

### iter 300 — 중단 검토
위 패턴 지속 → V26.1 실패 판정. V26.2 (direct-fix 추가) 전환 검토.

### iter 400 — 기본 중단값
- 어느 다리든 `contact_ratio < 0.02` 지속
- 어느 다리든 `propulsion < 0.02` 지속
→ reward/survival 무관하게 즉시 중단.

### iter 600 — 무조건 중단
collapse 지속 시 즉시 중단.

---

## 7. 작업 시 주의

- supervisor는 반드시 `logs\_launch_supervisor.cmd`으로만 시작
- 훈련 시작/중단은 Telegram `/start` `/stop`
- `/start` 확인 프롬프트: y/Y로 시작하는 모든 입력 허용 (yes, Yes, YES 등) — 2026-03-15 수정
- `logs/_launch_*.cmd` 파일들은 런타임 생성 임시 파일 (수동 실행 대상 아님)
- 직접 python/프로세스 kill 하지 말 것 — supervisor가 상태 추적을 잃음

---

## 8. 문서 맵

| 문서 | 내용 |
|------|------|
| `plan/MEMORY.md` | 이 문서 — active handoff |
| `plan/CURRENT_STATE_2026-03-15.md` | V25 종료 + V26.1 시작 세션 상세 |
| `plan/V26.1_PLAN.md` | V26.1 구현 계획 + 판정 기준 **(active)** |
| `plan/V26_ANALYSIS.md` | V26 설계 철학 |
| `plan/V25_ANALYSIS.md` | V25 실패 분석 (iter 400, RR collapse) |
| `plan/V24_ANALYSIS.md` | V24 실패 분석 |
