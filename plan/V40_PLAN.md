# V40 Plan: 0.45 Plateau 돌파

> 작성: 2026-03-24
> 상태: V40-A 실험 완료

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

### 핵심 질문

**"CaT prob를 0.003으로 올리면 0.45 plateau를 돌파할 수 있는가?"**

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
**주의**: 이것이 "contact 완전 무관"을 의미하진 않음.

---

## 3. V40-A: CaT prob 단일 변수 실험

### 설계

**변경: CaT probability_final 0.0015 → 0.003 (2배). 나머지 전부 동일.**

- Soft CaT framework 그대로 (threshold 0.3, margin 0.3)
- 기존 50개 reward 그대로
- CPG phase clock 제거 (V38.3 구성으로 복귀)
- from-scratch

### 수치 검증

```
probability_final = 0.003

| dev  | scale | per-step   | ep 종료율 |
|0.30  | 0.0   | 0          | 0%        |
|0.40  | 0.33  | 0.00099    | 22%       |
|0.45  | 0.50  | 0.00150    | 31%       | ← V38.3 plateau 지점
|0.54  | 0.80  | 0.00240    | 45%       |
```

### 판정 매트릭스

| 결과 | 해석 | 다음 행동 |
|------|------|----------|
| dev < 0.42, ep_len > 200 | **가설 A**: CaT 압력 부족이었음 | 성공 |
| dev < 0.42, ep_len < 180 | **가설 A+B**: CaT가 밀어넣었지만 ep_len 붕괴 | prob 중간값(0.002) |
| dev ≈ 0.45 정체, ep_len > 200 | CaT prob 단독 불충분 | V40-B 또는 positive reward |
| dev ≈ 0.45 정체, ep_len < 180 | CaT 과압 + contact 문제 | prob 하향 + 다른 접근 |

### 리스크

1. **ep_len 하락** — 초기 구간에서 ep_len이 크게 악화될 위험. dev가 내려가면 회복 가능.
2. **V38.3 반복** — 0.45에서 또 정체 시 CaT prob 단독 상향으로는 불충분.

---

## 4. V40-A 실험 결과

Run: `2026-03-24_16-11-29` (prob 0.003, 20480 envs, from-scratch)

### 훈련 데이터

| iter | shoulder dev | splay% | ep_len | stride | V38.3 dev | V40-A 우위 |
|------|-------------|--------|--------|--------|-----------|-----------|
| 800 | 0.537 | 0.0% | 250 | 6.05 | 0.537 | - |
| 1000 | 0.524 | 6.1% | 245 | 6.16 | 0.532 | -0.008 |
| 1500 | 0.484 | 19.8% | 226 | 6.49 | 0.512 | -0.028 |
| 2000 | **0.448** | 31.9% | 210 | 6.09 | 0.492 | -0.044 |
| 2500 | **0.416** | 42.1% | 198 | 5.71 | 0.476 | -0.060 |
| 3000 | **0.386** | 51.0% | 177 | 5.47 | 0.456 | -0.070 |
| 3500 | 0.386 | 51.2% | 182 | 5.43 | - | **plateau** |
| 4000 | 0.384 | 51.1% | 170 | 5.18 | - | **plateau** |

### 가설 판정

**가설 A 확정: CaT 압력 부족이 0.45 plateau의 주 원인이었다.**

- 0.45 돌파: iter 2000 (V38.3보다 1000 iter 빠름)
- 0.42 판정 기준: iter 2500에서 달성
- 최종 도달: **0.384** (V38.3 대비 -16%)

**가설 B도 부분 발현:**

- ep_len 250→170 (splay 51%로 에피소드 절반 CaT 종료)
- 판정 매트릭스 매핑: **"dev < 0.42, ep_len < 180"** → CaT가 밀어넣었지만 ep_len 붕괴

### 새 plateau 분석

0.384에서 새 plateau 형성 (iter 3000~4000):
- V38.3의 0.45 plateau와 동일 구조가 반복
- splay 51% 안정 — agent가 "51% 에피소드 손실 감수" 전략
- ep_len 170 — 학습 품질 저하, 180 임계 아래
- stride 5.18 — 하락 추세

### 교훈

1. **CaT prob 상향은 효과적** — 0.45→0.384, prob 2배만으로 -16%
2. **ep_len 대가가 큼** — 250→170, splay 51%
3. **새 plateau는 ep_len 한계** — splay 51%에서 에피소드가 짧아 학습 불가
4. **CaT prob 단독 상향의 천장 ~0.38** — prob를 더 올리면 ep_len만 더 떨어짐
5. **0.38 이하는 CaT 외 추가 전략 필요**

---

## 5. V40-B: Target band 편향 검증 (보류)

V40-A 데이터에서 contact_band를 shoulder dev 구간별로 분석 가능:
- dev > 0.50 구간 / dev 0.45~0.50 / dev < 0.45
- 구간별 contact_band 분산/최저값 비교
- 별도 훈련 없이 분석 가능

---

## 6. V40-C: 구조적 검증 (보류, A+B 실패 시)

- shoulder joint limit 축소
- action scale 제한
- default pose 조정

---

## 7. 판정 기준

**성과 지표 (주 판정: shoulder dev):**
1. shoulder dev < 0.42 (주지표)
2. splay% 추이 (보조)
3. ep_len > 200
4. stride > 5.0

**원인 진단 지표:**
5. policy entropy — 구간별 (초기/중기/후기)
6. contact_band per-step (ep_len 정규화)
7. late_phase_band_exit per-step

**판정 원칙:**
주 판정은 shoulder dev 기준, splay%는 보조.
shoulder dev < 0.42 + ep_len > 200 동시 달성 = 성공.

---

## 8. 다음 방향 후보

| 후보 | 내용 | 기대 효과 |
|------|------|----------|
| prob 유지 + **positive posture reward** | 어깨 모으면 직접 보상 | ep_len 회복 + dev 추가 감소 |
| **prob 0.002 중간값** | ep_len 200+ 유지 | dev 0.40 근처, 안정적 학습 |
| **num_envs 8192** | 탐색 다양성 증가 | entropy 유지, plateau 돌파 가능 |

---

## 9. 참고

- V38_PLAN.md: CaT 시리즈 결과 + 교훈 11개
- V39_PLAN.md: CPG 실험 + reward 구조 분석 + ep_len 정규화 발견
- HANDOFF.md: 전체 현황
