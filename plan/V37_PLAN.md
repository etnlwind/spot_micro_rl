# V37 Plan — Anti-Splay 강화 (부팅 안정화 + Anti-Shuffle 유지)

**작성일**: 2026-03-20
**상태**: 훈련 중 (iter ~100, 2026-03-20 15:28 시작)

---

## 배경

### V36 결과 (iter 800)

| 지표 | V35.5 (기준선) | V36 | 변화 | 판정 |
|------|--------------|-----|------|------|
| ep_len | 250 | 250 | 동일 | ✅ 부팅 완벽 |
| shoulder_dev | 0.544 rad | 0.543 | 0% | ❌ anti-splay 무효 |
| stance_width_front | 0.320m | 0.310 | -3% | 미미 |
| stride_length | 4.533 | 6.084 | **+34%** | ✅ anti-shuffle 성공 |
| swing_stride | 0.522 | 1.192 | **+128%** | ✅ 대폭 개선 |
| feet_air_time | -9.541 | -7.070 | **+26%** | ✅ 체공 개선 |

**결론**: Anti-shuffle은 효과적이지만, anti-splay(shoulder=-6.0, stance=-3.0, height=0.23)는 벌레보행을 막지 못함. shoulder_dev 0.54 rad(31°)로 고착.

### Anti-Splay 실패 분석

V36에서 shoulder_dev 추이:
- iter 100: 0.091 (거의 중립 — 아직 안 걸음)
- iter 300: 0.184 (걷기 시작 → 벌어지기 시작)
- iter 500: 0.529 (급격히 벌어짐)
- iter 700-800: 0.543-0.544 (고착)

**패턴**: 보행을 배우면서 안정성을 위해 다리를 벌리는 것이 보상적으로 유리함. shoulder_neutral=-6.0 penalty가 보행 보상(forward_vel=8.0, standing_height=10.0 등)에 비해 상대적으로 약해서 무시됨.

### 왜 shoulder=-8.0(V35)은 실패했는가?

V35에서 -8.0이 실패한 건 부팅 메커니즘 부재 때문이었다. V36에서 부팅은 안정적이므로, -8.0 이상도 시도 가능. 다만 -8.0은 V35에서 테스트 안 됨(이모지 crash로 인한 혼동).

---

## 전략

Anti-splay를 **2~3배 더 강하게** + **다각도 접근**:

1. **shoulder_neutral weight 대폭 강화**: -6.0 → -12.0
2. **stance_width_penalty weight 강화**: -3.0 → -6.0
3. **height target 추가 하향**: 0.23 → 0.22 (V35 수준)
4. **shoulder symmetry 강화**: 좌우 대칭 penalty 활용

### 근거

현재 shoulder_dev=0.54에서 shoulder_neutral의 episode reward는 -1.16. 이것은 전체 reward(+180) 대비 0.6%에 불과. **penalty가 전체 보상 대비 5~10%는 되어야 행동 변경을 유도**할 수 있음.

- weight -12.0이면: episode reward ≈ -1.16 × (12/6) = -2.3 → 전체 대비 1.3% (아직 약할 수 있음)
- weight -20.0이면: episode reward ≈ -3.9 → 전체 대비 2.2%

하지만 penalty를 너무 높이면 보행 자체를 억제. **커리큘럼 방식**이 더 안전:
- iter 0~500: shoulder=-6.0 (부팅 보호)
- iter 500~1000: shoulder=-6.0 → -15.0 (점진 강화)

---

## 변경 사항 (V36 → V37)

### Option A: 강한 고정값

| 파라미터 | V36 | V37 | 근거 |
|---------|-----|-----|------|
| `shoulder_neutral.weight` | -6.0 | **-12.0** | 2배 강화 |
| `stance_width_penalty.weight` | -3.0 | **-6.0** | 2배 강화 |
| `base_height_l2.target_height` | 0.23 | **0.22** | 추가 하향 |
| `standing_height.target_height` | 0.23 | **0.22** | 일관성 |

### Option B: 커리큘럼 방식 (권장)

boot_ramp와 유사하게, anti-splay penalty를 점진적으로 강화:

| 파라미터 | iter 0~500 | iter 500~1000 | iter 1000+ |
|---------|-----------|--------------|-----------|
| `shoulder_neutral` | -6.0 | -6.0 → -15.0 | -15.0 |
| `stance_width_penalty` | -3.0 | -3.0 → -8.0 | -8.0 |
| `base_height_l2 target` | 0.23 | 0.23 → 0.22 | 0.22 |

**장점**: 부팅 구간에서는 약한 penalty → 보행 학습 후 splay 교정
**구현**: `reward_weight_curriculum`에 `splay_ramp` 파라미터 추가

### Anti-Shuffle (V36에서 유지)

| 파라미터 | 값 | 비고 |
|---------|-----|------|
| stride_length_ramp | 200~500 | V36 유지 |
| stride_length_max | 15.0 | V36 유지 |
| feet_air_time threshold | 0.25 | V36 유지 |
| swing_stride weight | 4.0 | V36 유지 |

### 부팅 안정화 (V35.5에서 유지)

| 파라미터 | 값 | 비고 |
|---------|-----|------|
| alive_bonus | 10.0 | 유지 |
| boot_ramp_end | 300 | 유지 |
| boot_undesired_contacts_floor | -20.0 | 유지 |
| boot_vel | (0.01, 0.05) → (0.1, 0.5) | 유지 |

---

## 파일 변경 목록

### `spot_micro_rl_env_cfg.py`
- Line 7: `TRAIN_VERSION = "V37"`
- 커리큘럼 파라미터 추가:
  - `splay_ramp_start=500`, `splay_ramp_end=1000`
  - `splay_shoulder_initial=-6.0`, `splay_shoulder_final=-15.0`
  - `splay_stance_initial=-3.0`, `splay_stance_final=-8.0`
  - `splay_height_initial=0.23`, `splay_height_final=0.22`

### `rewards.py`
- `reward_weight_curriculum` 함수에 splay_ramp 로직 추가
  - iter 500~1000: shoulder_neutral, stance_width_penalty weight 선형 보간
  - iter 500~1000: base_height_l2, standing_height target_height 선형 보간

### `.env`
- `TRAIN_VERSION=V37`

---

## 체크포인트 기준

| iter | 확인 | 판정 |
|------|------|------|
| 100 | ep_len > 30 | 부팅 확인 |
| 400 | ep_len > 200 | 부팅 완료 |
| 500 | shoulder_dev < 0.5 | splay_ramp 시작 전 기준값 |
| 700 | shoulder_dev < 0.4 | splay_ramp 중간 효과 |
| 1000 | shoulder_dev < 0.3, stride > 6.0 | splay_ramp 완료 + shuffle 유지 |
| 1500 | STAND→WALK ramp 시작 | 보행 품질 유지 확인 |

## 리스크

1. **shoulder=-15.0이 보행을 억제할 가능성** — 보행 중 어깨가 약간 벌어지는 건 정상 역학. 과도한 penalty는 보행을 멈추게 할 수 있음. → 커리큘럼으로 점진 적용하여 방지. ep_len이 하락하면 final값 완화.

2. **height 0.22가 기구학적 한계** — init pos=(0,0,0.192). 0.22는 도달 가능하지만 마진이 좁음. → standing_height 보상으로 보완.

3. **splay_ramp와 기존 STAND→WALK ramp 충돌** — splay_ramp(500~1000)은 STAND→WALK ramp(1500~3000) 이전에 완료되므로 충돌 없음.

4. **anti-splay와 anti-shuffle의 상호작용** — 다리를 모으면 stride가 줄어들 수 있음. stride_length와 swing_stride 보상이 이를 보상해야 함.

## 성공 기준

| 지표 | V36 (현재) | V37 목표 |
|------|-----------|---------|
| shoulder_dev | 0.544 rad | **< 0.3 rad** (45% 감소) |
| stance_width_front | 0.310m | **< 0.22m** (30% 감소) |
| stride_length | 6.084 | **> 6.0** (유지 또는 개선) |
| feet_air_time | -7.070 | **> -7.0** (유지 또는 개선) |
| ep_len | 250 | **250 유지** |

## Option A vs B 비교

| | Option A (고정값) | Option B (커리큘럼) |
|--|-----------------|-------------------|
| 구현 난이도 | 낮음 | 중간 |
| 부팅 안전성 | ⚠️ -12.0이 부팅 방해 가능 | ✅ 부팅 구간은 -6.0 유지 |
| 효과 시점 | iter 0부터 즉시 | iter 500~1000 점진 |
| 리스크 | 부팅 실패 가능성 | 낮음 |
| **권장** | | **✅** |

**권장: Option B (커리큘럼)** — 현재 V37에서 구현 중

---

## 논문 기반 대안 분석 (V37 실패 시 V38 후보)

V37의 L2 penalty 커리큘럼이 실패할 경우, 최신 연구에서 더 효과적인 anti-splay 기법들:

### 1. Barrier-Based Style Reward (KAIST, ICRA 2025)
**출처**: [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)

L2 penalty 대신 **로그 배리어 함수** 사용:
```
barrier(x) = -log(margin - |shoulder_angle - target|)
```
- margin 안에서는 penalty ~0 → 부팅 구간에서 자연스럽게 안전
- margin 경계에서 penalty → infinity → splay 원천 차단
- **단일 하이퍼파라미터(margin 폭)** vs V37의 6개 커리큘럼 파라미터

### 2. CaT: Constraints as Terminations (IROS 2024, Solo-12)
**출처**: [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)

shoulder_dev > threshold이면 **확률적 에피소드 종료**:
- 미래 보상이 완전히 차단되므로 매우 강한 학습 신호
- PPO에 최소 수정 (discount factor에 종료 확률 반영)
- **Solo-12 (2.5kg)에서 검증** — SpotMicro와 유사 스케일

### 3. ROGER: Adaptive Reward Gain (2025)
**출처**: [arXiv 2510.10759](https://arxiv.org/html/2510.10759v1)

실제 shoulder_dev 측정값에 따라 **penalty weight를 자동 조절**:
- splay 발생 → weight 자동 증가 / 정상 → weight 감소
- 수동 커리큘럼 스케줄링 완전 불필요

### V37 → V38 전환 기준
| V37 결과 | 판단 | V38 방향 |
|---------|------|---------|
| shoulder_dev < 0.3 | ✅ V37 성공 | 현 구조 유지 + 미세 튜닝 |
| shoulder_dev 0.3~0.45 | 🟡 부분 효과 | weight 추가 강화 (-20) |
| shoulder_dev > 0.45 | ❌ L2 커리큘럼 한계 | **Barrier 함수 또는 CaT** 도입 |
| ep_len < 200 | ❌ 보행 억제 | splay_ramp final 완화 (-12) |
