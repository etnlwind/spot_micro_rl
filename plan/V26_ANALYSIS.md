# V26 통합 분석 문서

> 작성: 2026-03-15
> 완료: 2026-03-15 (V26 iter 1000 + V26.1 iter 1903, 훈련 중단)
> 상태: **실패** — symmetric floor도 이미 고착된 RL collapse를 해결하지 못함
> 목적: V26 설계 철학, V26.1 구현 계획, 실험 결과, 실패 분석 전체를 단일 문서로 정리

---

## 0. 최종 판정

**판정: V26.1 실패 — symmetric 구조도 이미 고착된 RL collapse를 해결하지 못함**

### V26.1 (07-08-50) iter 1903 기준

| 다리 | contact_ratio | propulsion | limb_usage | swing_time | 판정 |
|------|--------------|------------|------------|------------|------|
| FL | — | — | — | — | (미측정) |
| FR | — | — | — | — | (미측정) |
| RL | **0.000205** | **0.000069** | **0.000041** | **0.989** | ❌ **COLLAPSE** |
| RR | **0.880** | **0.566** | **0.915** | **0.109** | ✅ 정상 |

**V26.1_PLAN 판정 기준 대비**:

| 기준 | 기준값 | 실제값 (iter 1903) | 판정 |
|------|--------|-------------------|------|
| contact_ratio_rl | ≥ 0.10 | **0.000205** | ❌ 초과 실패 |
| propulsion_rl | ≥ 0.05 | **0.000069** | ❌ 초과 실패 |
| limb_usage_rl | ≥ 0.10 | **0.000041** | ❌ 초과 실패 |
| swing_time_rl | < 0.90 | **0.989** | ❌ 초과 실패 |
| rear_usage_diff | < 0.40 | **0.915** | ❌ 초과 실패 |

iter 600 기준에 따르면 훈련은 600 이후에 중단됐어야 함. iter 1903까지 지속된 것은 heartbeat 자동 중단 로직이 개입하지 않았기 때문.

**V26 교훈 (V27 설계에 반영)**:
- symmetric floor 접근 자체는 맞다 — iter 200 일시 4발 통과로 확인됨
- 문제는 weight 규모(-20)와 ramp 취약구간이었다
- V27: symmetric 구조 유지 + V25 수준 강도(-60 근접) + ramp 취약구간 제거

→ **훈련 중단. V27 fresh start로 전환.**

---

## 1. 배경: V25 실패 → V26 필요성

V25는 `rear_left_contact_floor_penalty -60`으로 RL collapse를 막는 데는 성공했으나, 정책이 RR을 대신 포기했다. **비대칭 패널티의 근본 한계: 특정 다리만 지목하면 collapse는 다른 다리로 이동.**

| 버전 | collapse 위치 | 원인 |
|------|-------------|------|
| V23/V24 | RL | exploit 차단 없음, weight 부족 |
| V25 | RR (RL 회복됨) | RL-only penalty → collapse 이동 |
| V26 목표 | 없음 | 모든 다리에 동일 기준 적용 |

---

## 2. V26 설계 철학

### 2.1 한 줄 정의

**V26은 "예쁜 보행"이 아니라, "부하가 분산되고 파손 위험이 낮은 자연스러운 4족보행"을 목표로 하는 버전이다.**

V23~V25가 exploit 잡기, validity 세우기, 직접 처방 고민 단계였다면, V26은 목표 자체를 바꾼다.

> **전진 성공보다, 건강한 보행을 먼저 학습시키는 구조**

### 2.2 관점 전환

**기존 관점:** 앞으로 잘 가는가 / 안 넘어지는가 / trot처럼 보이는가

**V26 관점:**
- 하중이 4다리에 적절히 분산되는가
- 특정 다리에 지속 과부하가 없는가
- 불필요한 고빈도 접촉/충돌이 없는가
- 접촉 품질이 좋은가
- 그 결과로 자연스럽고 안정적이고 예뻐 보이는가

"예쁜 보행"은 목표가 아니라 **좋은 하중 분산과 낮은 파손 위험의 결과**로 본다.

### 2.3 설계 철학 5원칙

1. **4다리 존재 보장**: 한 다리라도 사실상 사라지면 실패
2. **하중 분산 우선**: 특정 다리에 하중이 몰리면 실패
3. **접촉 품질 우선**: 접촉 횟수가 아니라 필요한 순간에 부드럽게 지지하는 접촉
4. **충격/고빈도 발질 억제**: 짧고 빠른 다리질, contact oscillation, 충격성 touchdown 강하게 억제
5. **스타일은 마지막**: validity → load sharing → stability 이후에 style

### 2.4 4층 reward 구조

```
Layer A. Survival / Basic Stability     — 넘어지지 않기, 자세/높이/orientation
Layer B. Limb Validity                  — 4발 실제 참여, single-limb collapse 금지
Layer C. Load Sharing / Contact Quality — 하중 편중 억제, 충격 억제, 고빈도 발질 억제
Layer D. Efficient Gait / Style         — trot timing, diagonal, posture, compact stance
```

**B, C가 D보다 앞이라는 점이 핵심.**

"contact quantity"가 아니라 "contact quality": "닿아라"는 floor만, 제대로 닿는 것을 보상.

---

## 3. V26.1 구현 계획 (V26-A-lite 본선)

V26.1은 V26 철학의 1차 본선 구현: **4발 존재 보장 + 하중 분산을 일반(대칭) 구조만으로 해결할 수 있는지 검증.**

### 3.1 구현 reward term (8개)

| # | 이름 | 역할 | 분류 |
|---|------|------|------|
| 1 | `limb_usage_min_penalty` | 4개 중 하나라도 usage 낮으면 강하게 감점 | Existence Floor |
| 2 | `per_leg_contact_floor_penalty` | 각 다리 최소 contact 보장 | Existence Floor |
| 3 | `per_leg_propulsion_floor_penalty` | 각 다리 최소 propulsion 보장 (fake contact 차단) | Existence Floor |
| 4 | `rear_left_right_usage_diff_penalty` | 뒷다리 좌우 usage 편중 억제 | Load Sharing |
| 5 | `front_left_right_usage_diff_penalty` | 앞다리 좌우 usage 편중 억제 | Load Sharing |
| 6 | `rear_left_right_propulsion_diff_penalty` | 뒷다리 좌우 추진 편중 억제 | Load Sharing |
| 7 | `front_rear_support_balance_penalty` | 앞/뒤 전체 지지 편중 억제 | Load Sharing |
| 8 | `diagonal_coupling_soft_gate` | collapse 다리 포함 diagonal reward soft attenuation | Exploit 차단 |

모든 penalty는 soft (연속 함수). binary 금지.

**제외 (V26.2로 이월)**: contact_oscillation, touchdown_impact, micro_step, stance_quality

### 3.2 Floor threshold

V25 iter 400 실측 기준 (붕괴 다리 usage=0.003, 정상 다리 usage=0.930):

| 항목 | threshold | weight |
|------|----------|--------|
| per-leg contact floor | 0.10 | -20 |
| per-leg propulsion floor | 0.05 | (soft) |
| per-leg usage floor | 0.10 | (soft) |
| left/right usage diff | > 0.40 | (soft) |
| left/right propulsion diff | > 0.40 | (soft) |
| front/rear support diff | > 0.50 | (soft, 앞뒤 비대칭 허용) |

### 3.3 Ramp 스케줄

| iter | 내용 |
|------|------|
| 0~80 | survival 중심. validity floor 최소 강도(10%) on |
| 80~200 | validity floor 빠르게 강화. 조기 collapse 차단 |
| 200~350 | load sharing penalty ramp-up |
| 350+ | full-strength |

### 3.4 판정 기준

| iter | 조건 | 동작 |
|------|------|------|
| 200 | 어떤 다리든 contact_ratio < 0.05 or propulsion ≈ 0 | CRITICAL 알림, 계속 관찰 |
| 300 | 위 패턴 지속 | V26.1 실패 판정, V26.2 전환 검토 |
| 400 | 어떤 다리든 contact_ratio < 0.02 or propulsion < 0.02 | 즉시 중단 |
| 600 | single-limb collapse 지속 | reward 무관 즉시 중단 |

---

## 4. V26 vs V26.1 관계

| 구분 | V26 | V26.1 |
|------|-----|-------|
| 런 | 2026-03-15_01-46-44 | 2026-03-15_07-08-50 |
| 시작 방식 | fresh (iter 0부터) | **resume = V26 model_1000.pt** |
| 코드 상태 | uncommitted (+201 lines) | 1c242fe 커밋 (+330 lines) |
| 종료 iter | 1000 (video report) | 1903 (현재 수동 중단 필요) |
| RL 상태 | iter 200 일시 정상 → iter 300부터 붕괴 | 시작부터 붕괴 (V26 상속) |

**V26.1은 V26의 붕괴 상태(model_1000.pt, RL collapse 고착)를 이어받아 시작했다.**
즉 "V26의 붕괴 상태에서 새 reward가 recovery할 수 있는가"를 테스트한 셈이다.

---

## 5. 훈련 경과

### V26 (01-46-44): iter 0~1000

**핵심 발견: iter 200에서 일시적 4발 유효 통과 — V23~V25에서 한 번도 없던 성과**

| iter | reward | limb_valid | usage_min | rear_diff | 비고 |
|------|--------|-----------|-----------|-----------|------|
| 101 | 8.7 | ❌ | 0.104 | 0.023 | 워밍업 |
| **200** | **132.0** | **✅ 통과** | **0.727** | **0.105** | **4발 모두 정상** |
| 301 | 160.8 | ❌ | 0.309 | 0.659 | RL 붕괴 시작 |
| 400 | 211.9 | ❌ | 0.038 | 0.921 | RL 거의 소멸 |
| 501 | 253.1 | ❌ | 0.005 | 0.948 | RL collapse 확정 |
| 700 | 315.2 | ❌ | 0.0004 | 0.925 | — |
| 1000 | 344.3 | ❌ | 0.0001 | 0.933 | video report → V26 종료 |

iter 200 일시 통과의 의미: symmetric floor penalty가 초기 4발 존재 강제에 성공했음. 그러나 iter 200~300 사이 RL collapse 재발 → 일시적 성공에 그침.

### V26.1 (07-08-50): iter 1000~1903

V26 model_1000.pt resume. 시작 시점에 이미 RL 완전 붕괴 상태.

| iter | reward | usage_rl | contact_rl | propulsion_rl | rear_diff |
|------|--------|----------|-----------|--------------|-----------|
| 1002 | 247.4 | 0.000130 | 0.000594 | 0.000387 | 0.767 |
| 1102 | 418.1 | 0.000115 | 0.000571 | 0.000341 | 0.929 |
| 1301 | 418.9 | 0.000066 | 0.000329 | 0.000163 | 0.924 |
| 1500 | 435.5 | 0.000051 | 0.000253 | 0.000121 | 0.915 |
| 1802 | 458.1 | 0.000044 | 0.000218 | 0.000094 | 0.916 |
| 1903 | 467.5 | 0.000041 | 0.000205 | 0.000069 | 0.915 |

RL usage: 0.000130 → 0.000041 (iter 1000→1903, 3배 더 악화). reward: 247 → 467 (RL 붕괴 심화에도 상승 — 3족 보행 최적화).

---

## 6. 실패 원인 분석

### 6.1 근본 원인: Resume bias — 붕괴 상태에서 시작

V26.1은 이미 RL 붕괴를 확립한 model_1000.pt에서 resume됐다. PPO 정책은 iter 1000 동안 "RL 없이 3족 보행으로 최대 reward" 전략을 학습했으며, high-reward 로컬 minimum에 수렴한 상태다.

새 symmetric floor penalty가 추가됐지만:
- RL contact gap ≈ 0.0998 → penalty ≈ -2.0/step (per_leg_contact weight -20 기준)
- 총 reward ≈ 450 대비 **0.44%** — V24의 limb_usage_min과 동일한 희석 문제
- 정책: floor penalty(-2) < 3족 보행 이득(+수백) → RL 포기가 여전히 최적 전략

### 6.2 V26 ramp 취약구간 (iter 200~350)

| iter | floor 상태 | load sharing 상태 | 결과 |
|------|-----------|-----------------|------|
| 0~80 | 최소 강도(10%) | off | 4발 균등, reward 낮음 |
| 80~200 | floor ramp-up | off | iter 200 4발 통과 |
| **200~350** | floor full | **load sharing ramp 시작** | **RL collapse 재발** |
| 350+ | full strength | full strength | 이미 붕괴 고착 |

floor penalty는 4발 존재를 강제했지만, load sharing이 아직 개입하기 전에 정책이 "RL을 최소 접촉만 유지하다가 완전 포기"하는 전략으로 전환. ramp-up 공백이 붕괴를 허용했다.

### 6.3 weight 부족 (V25 대비 후퇴)

| 항목 | V25 | V26.1 |
|------|-----|-------|
| 패널티 방식 | `rear_left_contact_floor` -60, ramp 없음 | `per_leg_contact_floor` -20, ramp 있음 |
| 최대 패널티/step | -18 ~ -60 | **-2.0** (gap × -20) |

symmetric 구조를 위해 weight를 낮췄으나, RL collapse 저지 능력도 함께 낮아졌다. V25의 비대칭 처방보다 V26.1의 대칭 처방이 각 다리에 주는 gradient가 오히려 더 약하다.

### 6.4 결론

**symmetric 접근법 자체는 맞다** (iter 200 일시 통과로 확인). 문제는 weight 규모와 ramp 설계였다.

---

## 7. V23~V26.1 실패 패턴 요약

| 버전 | 접근 | 결과 | 실패 이유 |
|------|------|------|-----------|
| V23 | 기본 리워드 | RL collapse | exploit 차단 없음 |
| V24 | usage proxy + limb_usage_min -12 | RL collapse | weight 부족 (reward의 0.7%) |
| V25 | RL 직접 타겟 -60, ramp 없음 | **RR** collapse | 비대칭 → collapse 위치 이동 |
| V26 | symmetric -20, ramp 있음 | RL collapse (iter 300) | ramp 취약구간, weight V25의 1/3 |
| V26.1 | V26 resume + refined | RL collapse 심화 | 붕괴 상태 상속, gradient 불충분 |

**공통 패턴**: collapse 전략이 floor/validity penalty보다 reward가 항상 크다.
해결되지 않은 근본 질문: "floor penalty weight가 얼마나 강해야 3족 보행 local minimum을 탈출할 수 있는가?"

---

## 8. V27 방향 제안

### 핵심 전제: fresh start 필수

V26.1의 실패 요인 중 하나는 이미 붕괴된 model에서 resume한 것. V27은 반드시 fresh start에서 symmetric floor를 검증해야 한다.

### 후보 방향

**방향 A: Weight 대폭 증강 + early full-strength**
- per_leg_contact_floor: -60 (V25 수준으로), ramp 없음 (iter 0부터 full)
- load sharing: -20 이상, 역시 iter 0부터 활성
- "강하게, 처음부터, 대칭으로" — V25의 강도 + V26의 대칭성 결합

**방향 B: 2단계 — floor 먼저, load sharing 나중**
- iter 0~200: floor only, -60 full strength → 4발 존재 강제
- iter 200+: load sharing 추가 → 균형 정착
- ramp 취약구간 제거

**방향 C: reward 재설계 — "3족 보행이 패"**
- forward_velocity, diagonal_coupling 등 주요 positive reward에 limb validity gate 직접 연결
- RL 없으면 주 reward 자체가 0 → floor penalty가 아니라 구조 전환

---

## 9. 인프라 개선사항 (V26.1 시기)

V26.1 커밋(1c242fe)에서 reward 외에 추가된 인프라:
- RL/RR limb 별도 지표 heartbeat/video report 포함 (contact_ratio_rl/rr, propulsion_rl/rr 등)
- `/start` 확인 명령에 y/Y-prefix 단어(yes, Yes, YES) 허용
- 파일명에 버전 포함 (`Report_V26.1_iter{N}_...`)
- report ACK에 target_version 전달 (version mismatch 버그 수정)
- metrics_run_dir 전달 (report summary에 context 표시)
- `resolve_run_dir_for_version` self-contained 런 우선 선택
