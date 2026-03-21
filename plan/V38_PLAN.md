# V38 Plan: CaT (Constraints as Terminations) for Anti-Splay

## Context

V37.2에서 L2 penalty 커리큘럼의 구조적 한계 확인:
- shoulder_dev 0.53에서 1300 iter 고착, penalty -11.4까지 올려도 행동 변화 없음
- 원인: L2 penalty는 reward 채널 -- agent가 다른 양의 보상으로 상쇄 가능
- HANDOFF.md 결론: `shoulder_dev > 0.45 -> Barrier/CaT 도입`

CaT를 선택하는 이유 (Barrier 대비):
- Barrier도 결국 reward term -> clamped되면 L2와 같은 문제 재발
- CaT는 discount factor 채널 -- terminated=True일 때 미래 보상=0, 상쇄 불가
- Isaac Lab의 DoneTerm 인프라에 자연스럽게 적합
- Solo-12(2.5kg)에서 검증 -- SpotMicro와 유사 스케일
- 코드 변경 최소 (~50줄 추가, 교훈 #12 준수)

## 코드 변경

### 1. rewards.py -- `shoulder_splay_termination()` 함수 추가
- shoulder_neutral_penalty 바로 뒤에 추가
- max deviation 기반 (4개 어깨 중 최악)
- 확률적 종료 (PPO sharp boundary 불안정 방지)

### 2. rewards.py -- `reward_weight_curriculum()` CaT ramp 블록
- 시그니처에 6개 파라미터 추가: cat_ramp_start/end, threshold/probability initial/final
- splay_ramp 뒤에 CaT ramp 블록: termination_manager를 통해 threshold/probability 조절

### 3. env_cfg.py -- DoneTerm 추가 + 커리큘럼 파라미터
- `terminations.shoulder_splay` DoneTerm 추가 (bad_orientation 다음)
- CaT 커리큘럼 파라미터 추가, splay L2 ramp 고정 (-6.0)

---

## V38 결과: 즉시 붕괴

Run: `2026-03-21_03-49-08`

### 핵심 지표 추이

| iter | reward | ep_len | shoulder_dev | CaT 종료율 | 판정 |
|------|--------|--------|-------------|-----------|------|
| 400 | 170.7 | 247.6 | 0.540 | 0% | 부팅 성공 |
| 500 | 154.5 | 212.9 | 0.471 | 2.1% | CaT 개시 |
| **600** | **-10.3** | **11.7** | 0.017 | **99.3%** | **즉시 붕괴** |
| 1000 | -6.1 | 6.5 | 0.009 | 99.5% | 회복 불가 |
| 1500 | -1.8 | 4.3 | 0.006 | 99.9% | 회복 불가 |

### 붕괴 원인
- threshold_initial=0.6이 부팅 직후 실측 dev(~0.54)에 너무 가까움
- CaT 활성화 즉시 거의 모든 환경이 종료 -> agent는 "즉시 낙하" 회피 전략 학습
- shoulder_dev 0.006은 splay 교정이 아닌 "어깨를 전혀 사용하지 않음" (ep_len 4~8)
- **리스크 #1 (CaT가 보행 억제) 정확히 적중**

### V38 파라미터 (실패)

| 파라미터 | 값 | 문제 |
|---------|-----|------|
| cat_ramp_start | 500 | 부팅 직후, 안정화 불충분 |
| cat_ramp_end | 1500 | ramp 기간 1000 iter, 불충분 |
| threshold_initial | 0.6 | 실측 dev 0.54 대비 margin 0.06 — 너무 타이트 |
| threshold_final | 0.4 | - |
| probability_initial | 0.1 | 10%도 과도 |
| probability_final | 0.3 | 30%는 즉각 붕괴 수준 |

---

## V38.1: 파라미터 완화

Run: `2026-03-21_09-08-16`

### V38 -> V38.1 변경

| 파라미터 | V38 | V38.1 | 변경 이유 |
|---------|-----|-------|----------|
| cat_ramp_start | 500 | **800** | 부팅 충분 안정 후 (boot_ramp_end=300 + 500 iter 여유) |
| cat_ramp_end | 1500 | **2500** | 1700 iter 완만 ramp (V38: 1000 iter) |
| threshold_initial | 0.6 | **0.8** | 실측 dev 0.54에 0.26 여유 (V38: 0.06) |
| threshold_final | 0.4 | **0.45** | 과도 압박 방지 |
| probability_initial | 0.1 | **0.03** | 초기 충격 최소화 (V38: 10x 과도) |
| probability_final | 0.3 | **0.15** | 과도 종료 방지 |

### V38.1 CaT 커리큘럼 스케줄

| iter | CaT | threshold | probability | 기존 시스템 |
|------|-----|-----------|-------------|-----------|
| 0-300 | OFF | 99.0 | 0.0 | boot ramp 활성 |
| 300-800 | OFF | 99.0 | 0.0 | boot 완료, 보행 안정화 |
| 800-2500 | Ramp | 0.8->0.45 | 0.03->0.15 | 정상 훈련 |
| 2500+ | Final | 0.45 | 0.15 | 수렴 |

### V38.1 체크포인트 기준

| iter | 확인 | 통과 | 실패 시 |
|------|------|------|--------|
| 400 | ep_len > 200 | 부팅 정상 | 중단 |
| 800 | shoulder_dev 기록, ep_len > 200 | CaT 시작 전 기준선 | 계속 |
| 1000 | ep_len > 150, reward > 0 | CaT warmup 통과 | threshold_initial -> 1.0 |
| 1500 | shoulder_dev < 0.5 | CaT 효과 시작 | 종료율 확인 |
| 2500 | shoulder_dev < 0.45, ep_len > 200 | CaT ramp 완료 | probability 하향 |
| 3000 | shoulder_dev < 0.35, stride > 6.0 | V38.1 성공 | V38.2 조정 |

## 변경하지 않는 것 (교훈 #12)
- 모든 기존 reward term weight (shoulder_neutral -6.0 고정 포함)
- boot 안정화 3결합 (alive_bonus, contacts ramp, vel ramp)
- anti-shuffle 설정 (stride_length, feet_air_time threshold)
- PPO 하이퍼파라미터
- from-scratch 훈련 (resume 아님)

## V38.2: Soft CaT (진행 중 — 2026-03-22)

### 설계
- **Phase transition 제거**: threshold/margin 고정, probability만 ramp
- `prob(dev) = base_prob * clamp((max_dev - 0.3) / 0.3, 0, 1)`
- probability_final = 0.0004 (step-level, 에피소드 종료율 ~8% at dev=0.54)

### 파라미터
| 파라미터 | 값 | 비고 |
|---------|-----|------|
| threshold | 0.3 | 고정 (목표 dev 근처) |
| margin | 0.3 | 0.3~0.6 구간 선형 |
| probability_final | 0.0004 | step-level per-step |
| cat_ramp | 800~3000 | probability만 ramp |

### Run 1: prob=0.08 (실패 — 즉시 중단)
- Run: `2026-03-21_15-46-35`
- iter 900: splay 56.8%, ep_len 162 — V38.1과 동일 패턴
- **원인**: prob 0.08은 step-level에서 `(1-0.08*0.8)^250 = 0` — 에피소드 100% 종료
- **교훈**: DoneTerm은 매 step 호출, probability는 `(1-p)^ep_len`으로 역산 필수

### Run 2: prob=0.0004 (완료 — sh_dev 정체)
- Run: `2026-03-21_18-53-17` + resume `2026-03-22_04-22-16`

| iter | sh_dev | splay% | ep_len | stride | 비고 |
|------|--------|--------|--------|--------|------|
| 800 | 0.537 | 0.00% | 250.0 | 6.050 | CaT 시작 |
| 1000 | 0.536 | 0.84% | 250.0 | 6.401 | 안정 |
| 1400 | 0.533 | 2.74% | 248.9 | 6.801 | |
| 1800 | 0.530 | 4.16% | 240.1 | 7.140 | |
| 2200 | 0.521 | 5.77% | 241.4 | 4.589 | resume 충격 후 회복 |
| 2600 | 0.521 | 7.27% | 235.2 | 7.273 | |
| 3000 | 0.518 | 9.03% | 242.3 | 7.371 | ramp 완료, sh_dev 정체 |

- **CaT 안정**: ep_len 붕괴 없음, stride 개선 (+22%)
- **sh_dev 정체**: 0.537→0.518 (3000 iter 간 -0.019) — prob 0.0004 너무 보수적
- **결론**: ~9% 에피소드 종료율로는 agent가 어깨 자세를 변경하지 않음

---

## V38.3: Soft CaT prob 3.75x (훈련 중 — 2026-03-22)

### 설계
- V38.2와 동일 구조, **probability_final만 상향**
- probability_final: 0.0004 → **0.0015** (3.75배)
- threshold 0.3, margin 0.3, ramp 800~3000 동일

### 예상 에피소드 종료율 (ramp 완료)

| dev | scale | per-step | ep 종료율 | V38.2 대비 |
|-----|-------|----------|----------|-----------|
| 0.30 | 0.0 | 0 | 0% | 0% |
| 0.40 | 0.33 | 0.000500 | 11.8% | 2.7% |
| 0.50 | 0.67 | 0.001000 | 22.1% | 5.1% |
| **0.54** | **0.80** | **0.001200** | **25.9%** | **9.0%** |
| 0.60 | 1.00 | 0.001500 | 31.3% | 9.5% |

- dev 0.54에서 25.9% → ep_len ~185 (학습 가능)
- dev 0.40으로 개선 시 11.8% → ep_len ~221 (자연스러운 압력 감소)

### Run: `2026-03-22_08-03-25` (진행 중)

## 교훈 (V38~V38.3)
- **CaT threshold는 실측 dev의 1.5배 이상으로 시작**: V38에서 dev 0.54 대비 threshold 0.6 (1.1배) -> 즉시 붕괴
- **DoneTerm은 매 step 호출**: probability 설계 시 `(1-p)^ep_len`으로 에피소드 생존율 역산 필수
- **Soft CaT prob 0.0004는 너무 약함**: 9% 에피소드 종료로는 sh_dev 미변화
- **Soft CaT는 phase transition 없이 안정적**: prob 상향만으로 압력 조절 가능
