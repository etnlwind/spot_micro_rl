# V40 Plan: 0.45 Plateau 돌파

> 작성: 2026-03-24
> 상태: 설계 중

---

## 1. Context

### 확인된 사실

1. **CaT는 0.54→0.45까지 효과적** — Soft CaT (prob 0.0015, 30% 에피소드 종료)로 달성
2. **0.45에서 plateau 형성** — 3000 iter 이상 정체
3. **V39.1.1 CPG는 phase following이 약했음** (raw 0.26) — 유도 부족이지 불가능이 아님

### 0.45 plateau 원인: 두 가지 경쟁 가설

**가설 A: CaT 압력 부족**
- ep_len 정규화 분석에서 per-step contact/propulsion은 splay 수준과 무관하게 안정적
- 이것이 맞다면 CaT prob를 올려도 contact가 무너지지 않으므로, 더 강한 압력으로 0.45를 돌파 가능
- 단, 정규화 평균이 안정적이라고 해서 좁은 stance에서의 접지 분산/안정성까지 동일하다는 보장은 없음

**가설 B: 좁은 stance에서의 접지 안정성 한계**
- CaT가 더 강해져도 좁은 stance에서 넘어지거나 접지 품질이 떨어져 ep_len 붕괴
- 정규화 평균은 유지되더라도 극단 구간(넘어지기 직전)에서의 품질 저하가 plateau 원인

**현재 유력**: 가설 A가 유력하지만 확정 아님. V40-A 실험으로 직접 검증.

### 핵심 질문

**"CaT prob를 0.003으로 올리면 0.45 plateau를 돌파할 수 있는가?"**

이 단일 변수 실험으로 가설 A/B를 구분:
- **shoulder dev < 0.42 + ep_len > 200** → 가설 A 지지 (CaT 압력 부족이었음)
- **ep_len < 180 붕괴** → 가설 B 지지 (contact 문제 여전히 존재)
- **shoulder dev ≈ 0.45 정체 + ep_len 유지** → 둘 다 아닌 새로운 한계

---

## 2. ep_len 정규화 분석 (참고 — 확정 결론 아님)

V38.3 데이터에서 Episode_Reward를 ep_len=250 기준으로 정규화:

| iter | dev | ep_len | contact_band(raw) | contact_band(norm) |
|------|-----|--------|-------------------|-------------------|
| 800 | 0.537 | 250 | 15.34 | 15.34 |
| 3000 | 0.456 | 215 | 13.42 | 15.58 |
| 6000 | 0.456 | 216 | 12.97 | 15.01 |

정규화 후 contact_band/prop_band/shoulder_neutral 모두 안정.
**해석**: ep_len confound가 존재하므로 raw Episode_Reward만으로 "contact 손실"을 결론내리면 안 됨.
**주의**: 이것이 "contact 완전 무관"을 의미하진 않음. 접지 품질의 분산, 좁은 stance에서의 실제 안정성은 별도 검증 필요.

---

## 3. V40-A: CaT prob 단일 변수 실험 (1순위)

### 설계

**변경: CaT probability_final 0.0015 → 0.003 (2배). 나머지 전부 동일.**

- Soft CaT framework 그대로 (threshold 0.3, margin 0.3)
- 기존 50개 reward 그대로
- CPG phase clock 제거 (V38.3 구성으로 복귀)
- from-scratch

### 수치 검증

```
probability_final = 0.003
ep_len = 250, dev = 0.54일 때:

(1 - 0.003 × 0.8)^250 = (1 - 0.0024)^250 = 0.549 → 45.1% 에피소드 종료

| dev  | scale | per-step   | ep 종료율 |
|0.30  | 0.0   | 0          | 0%        |
|0.40  | 0.33  | 0.00099    | 22%       |
|0.45  | 0.50  | 0.00150    | 31%       | ← V38.3 plateau 지점
|0.50  | 0.67  | 0.00201    | 39%       |
|0.54  | 0.80  | 0.00240    | 45%       |
|0.60  | 1.00  | 0.00300    | 53%       |
```

V38.3(prob 0.0015)에서 dev 0.45 = 26% 종료.
V40-A(prob 0.003)에서 dev 0.45 = **31% 종료** (비슷하지만 0.45 이하에서 압력 차이 커짐).
dev 0.40에서: V38.3=12% vs V40-A=**22%** (거의 2배).

### 이 실험이 검증하는 것

| 결과 | 해석 | 다음 행동 |
|------|------|----------|
| shoulder dev < 0.42, ep_len > 200 | **CaT 압력 부족이었음**. contact 문제 아님 | 완주, 성공 |
| shoulder dev < 0.42, ep_len < 180 | CaT가 밀어넣었지만 **ep_len 붕괴** — contact 문제 존재 | prob 중간값(0.002) 시도 |
| shoulder dev ≈ 0.45 정체, ep_len > 200 | **CaT prob 단독 상향으로는 불충분** — 다른 레버 필요 | V40-B 또는 positive reward |
| shoulder dev ≈ 0.45 정체, ep_len < 180 | CaT 과압 + contact 문제 | prob 하향 + 다른 접근 |

### 리스크

1. **ep_len 하락 리스크** — dev가 0.54에 머무르는 초기 구간에서 ep_len이 크게 악화될 위험
   - 하지만 dev가 내려가면 종료율도 내려감 (Soft CaT 특성)
   - 적응 시 ep_len 회복 가능. 고정 dev 가정의 이론값보다 실제는 나을 수 있음
2. **V38.3과 동일 결과** — 0.45에서 또 정체
   - 이 경우 CaT prob 단독 상향으로는 불충분. threshold/margin 조정 또는 다른 접근 필요

---

## 4. V40-B: Target band 편향 검증 (2순위, 병행 가능)

V40-B는 폐기하지 않고 **가벼운 검증 축으로 유지**.

"band_low=0.20은 이론적으로 narrow stance에서 달성 가능"은 맞지만,
실제 policy가 narrow stance에서 band를 "더 비싸게" 달성하는지는 미검증.

**검증 방법**: V40-A 실험 중 contact_band를 shoulder dev 구간별로 분석
- dev > 0.50 구간에서의 contact_band per-step
- dev 0.45~0.50 구간
- dev < 0.45 구간 (도달 시)
- 구간별 contact_band 분산/최저값 비교

이것은 별도 훈련 없이 V40-A 데이터에서 분석 가능.

---

## 5. V40-C: 구조적 검증 (3순위, A 실패 시)

- shoulder joint limit 축소
- action scale 제한
- default pose 조정

A, B 결과를 보고 결정.

---

## 6. 판정 기준

### V40-A 판정 (iter 3000~5000, 최근 500 iter 평균)

**성과 지표 (주 판정은 shoulder dev 기준, splay%는 보조):**
1. **shoulder dev < 0.42** (주지표 — V38.3의 0.45 대비 명확한 개선)
2. splay% 추이 (보조 — 상승→안정→재하락 패턴)
3. ep_len > 200
4. stride > 5.0

**원인 진단 지표** (왜 좋아졌는지/안 좋아졌는지):
5. **policy entropy** — 구간별 추적:
   - iter 0~500: 초기 탐색이 살아있는지
   - iter 500~1500: CaT 활성화 전후 탐색 변화
   - iter 1500~3000+: plateau 진입 시 탐색이 말라붙는지
6. **contact_band per-step** (ep_len 정규화) — contact 안정성 실제 추이
7. **late_phase_band_exit per-step** — narrow stance에서의 접지 품질

### 판정 원칙

주 판정은 shoulder dev 기준, splay%는 보조적으로 확인.
V40의 최종 성공은 shoulder dev < 0.42 + ep_len > 200 동시 달성.
shoulder dev가 내려가면서 ep_len도 유지되면 가설 A(CaT 압력 부족) 지지.
shoulder dev는 내려가지만 ep_len 붕괴하면 가설 B(contact 문제 존재) 지지.

---

## 7. 참고

- V38_PLAN.md: CaT 시리즈 결과 + 교훈 11개
- V39_PLAN.md: CPG 실험 + reward 구조 분석 + ep_len 정규화 발견
- HANDOFF.md: 전체 현황
