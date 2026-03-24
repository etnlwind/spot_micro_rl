# V40 Plan: 0.45 Plateau 돌파

> 작성: 2026-03-24
> 상태: 설계 중

---

## 1. Context

### 현재까지 확인된 것

1. **CaT는 0.54→0.45까지 효과적** — Soft CaT (prob 0.0015, 30% 에피소드 종료)로 달성
2. **0.45 이하에서 contact/propulsion 손실이 커짐** — 좁은 stance에서 접지 안정성 급감
3. **현재 policy는 narrow stance에서 안정적 접지 패턴을 못 만듦**
4. **V39.1.1 CPG는 phase following이 약했음** (raw 0.26) — 유도 부족이지 불가능이 아님

### 아직 미확정인 것

1. narrow-stance gait 자체가 학습 가능한지
2. contact_target_band가 wide stance에 편향되어 있는지
3. propulsion_target_band가 narrow stance를 불리하게 두는지
4. 구조적/기구학적 한계가 실제 핵심 원인인지

### 핵심 질문

**"0.45 이하 narrow stance에서도 contact_band를 유지할 수 있는 gait가 학습 가능한가?"**

---

## 2. Reward ep_len 정규화 분석 (중요 발견)

### 기존 분석의 오류

이전 분석에서 "splay 줄이면 contact_band 손실"로 결론지었으나, **ep_len confound**가 있었음.

**정규화 전** (raw Episode_Reward):
| iter | dev | ep_len | contact_band | 해석 |
|------|-----|--------|-------------|------|
| 800 | 0.537 | 250 | 15.34 | |
| 3000 | 0.456 | 215 | 13.42 | contact -1.92 → "splay 줄이면 contact 손실" |

**정규화 후** (ep_len=250 기준):
| iter | dev | ep_len | contact_band(norm) | 해석 |
|------|-----|--------|-------------------|------|
| 800 | 0.537 | 250 | 15.34 | |
| 3000 | 0.456 | 215 | **15.58** | **per-step 접지 품질 동일 또는 개선!** |
| 6000 | 0.456 | 216 | **15.03** | 안정 |

**모든 주요 reward가 정규화 후 안정적:**
- contact_band: 15.34→15.58→15.03 (변화 없음)
- prop_band: 10.49→10.60→10.72 (변화 없음)
- shoulder_neutral: -7.01→-6.96→-6.98 (변화 없음)

### 수정된 해석

1. **contact/propulsion 안정성은 splay와 무관** — narrow stance에서도 per-step 접지 품질 동일
2. **이전 "0.45에서 contact 손실" 분석은 ep_len confound** — CaT가 에피소드를 짧게 만든 것뿐
3. **contact_target_band는 wide stance 편향 아님** — band_low=0.20으로 narrow stance에서도 충분히 달성 가능
4. **0.45 plateau의 원인은 contact 손실이 아닌 다른 곳**

### 0.45 plateau 재해석

CaT 30% 에피소드 종료 상태에서 agent가 더 이상 어깨를 모으지 못하는 이유:
- contact 문제가 아님 (per-step 품질 동일)
- **"어깨를 모을 방법을 찾지 못한 것"** — policy의 탐색 한계
- entropy가 이미 수렴 (0.3 이하) → 새로운 행동 시도 불가
- 30% CaT 압력 하에서 안전한 local optimum에 갇힘

---

## 3. 실험 계획 (재검토)

### V40-A: Narrow-stance gait 유도 강화 (1순위)

**기존 V40-A 설계 (Phase-Conditioned Contact Band)는 불필요해짐** — contact_band는 splay 편향이 아니었음.

**수정된 V40-A 방향**:

문제가 "contact 손실"이 아니라 "policy 탐색 한계"라면:
1. **entropy 유지/증가 전략** — policy가 다양한 행동을 시도할 수 있도록
2. **더 강한 positive posture reward** — "어깨 모으면 직접 보상" 추가
3. **CaT prob 추가 상향** — 0.0015→0.003 (contact가 안 무너지니까 가능)
4. **CPG phase reward 강화** — V39.1.1보다 훨씬 강한 weight (50+)

핵심 전환: "contact 보호" → "탐색 촉진 + positive incentive"

### V40-B: Contact/propulsion target band 편향 점검 (2순위)

**정규화 분석으로 편향 없음 확인** → V40-B 우선순위 하향 또는 불필요.
band_low=0.20은 narrow stance에서도 충분히 달성 가능.

### V40-C: 구조적 검증 (3순위, A 실패 시)

- shoulder joint limit 축소
- action scale 제한
- default pose 조정

---

## 4. 판정 기준

### V40-A 판정 (iter 3000~5000)

2축 분리 판정 유지 (최근 500 iter 평균):

**Axis 1: Splay/Posture**
1. shoulder dev < 0.42 (V38.3의 0.45 대비 명확한 개선)
2. splay% 재하락

**Axis 2: Gait 구조**
3. contact_band가 유지되면서 shoulder dev 감소 (동시 개선)
4. FL/FR contact ratio < 0.70
5. stride > 5.0 (V39.1.1의 4.4 악화 방지)

**공통**
6. ep_len > 200

### 판정 원칙

V40의 최종 성공은 Axis 1과 Axis 2의 동시 개선으로만 판정. 한 축만 개선 시 부분 성공.

---

## 5. 참고

- V38_PLAN.md: CaT 시리즈 결과 + 교훈 11개
- V39_PLAN.md: CPG 실험 + reward 구조 분석
- HANDOFF.md: 전체 현황
