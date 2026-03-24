# HANDOFF.md

> 마지막 업데이트: 2026-03-22
> 최신 커밋: develop 브랜치

---

## 1. 현재 목표

**Anti-Splay 해결 — V38.3: Soft CaT prob 0.0015, 15000 iter 완주 중**

| 버전 | 결과 | 비고 |
|------|------|------|
| V32.1 | 부분 성공 | front lock-in 해소, 하지만 거미형 벌어짐 + 셔플링 |
| V33~V34 | 실패 | 근본 재설계/커리큘럼 시도, 부팅 불가 |
| V35~V35.5 | 부팅 성공 | alive_bonus(10) + contacts ramp + 저속 command 3결합, 100% 재현 |
| V36 | 부분 성공 | anti-shuffle 성공(stride +34%), anti-splay 실패(shoulder_dev 0.54 고착) |
| V37~V37.2 | 한계 확인 | L2 penalty -10까지 올려도 splay 행동 변화 없음 |
| V38 | 실패 | CaT threshold ramp, 0.6이 너무 타이트 → iter 600 즉시 붕괴 |
| V38.1 | 실패 | CaT threshold ramp 완화, splay 57% → 붕괴 (phase transition) |
| V38.2 | 부분 성공 | Soft CaT prob 0.0004, 안정적이나 shoulder_dev 0.518 정체 |
| **V38.3** | **진행 중** | Soft CaT prob 0.0015, shoulder_dev 0.537→0.457 (**-14.9%**), **0.45 정체 관찰 중** |

---

## 2. V38.3 현재 상황 (2026-03-22)

### Run: `2026-03-22_08-03-25` (iter ~4000 / 15000)

| iter | shoulder dev | splay% | ep_len | stride | 비고 |
|------|-------------|--------|--------|--------|------|
| 800 | 0.537 | 0.0% | 250 | 6.05 | CaT 시작 |
| 1500 | 0.512 | 10.7% | 238 | 6.22 | |
| 2000 | 0.492 | 17.7% | 227 | 6.44 | 8% 감소 기준 통과 |
| 2500 | 0.476 | 24.0% | 221 | 6.80 | |
| 3000 | 0.456 | 30.3% | 215 | 6.73 | ramp 완료 |
| 3500 | 0.457 | 30.2% | 195 | 6.65 | **정체 + ep_len < 200** |

### 현재 판단

**최종 결과** (iter 6600, 조기 중단):
- shoulder_dev 0.537→0.451 (**-16%**) — 역대 최대 감소
- 0.45에서 3000 iter 정체 확정 → 조기 중단
- splay 30% 안정, ep_len 216, stride 7.23

**V38 시리즈 결론**: CaT로 0.54→0.45 달성. 그 이상은 벌칙만으로 한계.
**V38.3.1 실패**: resume + L2 강화 시도 → critic 무효화 + curriculum 미복원으로 성과 소실.

**현재**: V39.1.1 조기 중단 (iter 4500). Reward 구조 분석 완료. 새 방향 검토 중.

**V39 경과**:
- V39.1 (2.0 Hz): reward shape 결함 (공짜 baseline 0.50) → FAIL
- V39.1.1 (shape +1/-1, weight 20): 스크리닝 PASS, 하지만 본실험 실패
  - shoulder dev 0.438 (V38.3의 0.45 대비 -0.012, 미미)
  - stride 7.23→4.40 (-39% 악화)
  - **CPG가 splay 해결 못하고 stride만 악화**

### Reward 구조 분석 결과

0.45 장벽의 원인: **물리적 접지 안정성 한계점**
- 0.54→0.45: splay 줄이면 순이익 (+4.17) → CaT가 밀어넣음
- 0.45 이하: contact_band 손실 > stance_w 이득 → 정체
- 좁은 stance에서 접지 안정성이 급격히 떨어지는 것이 근본 원인
- reward 조정만으로는 해결 불가

### 가설 검증 완료

| 가설 | 결과 |
|------|------|
| L2 penalty로 splay 교정 (V37) | ❌ reward 채널 상쇄 |
| CaT discount 채널 (V38) | 🟡 0.45까지만 |
| CPG gait 교정 → splay 해결 (V39) | ❌ stride 악화, splay 미변화 |
| reward 불균형이 원인 | 🟡 부분 — 0.45가 물리적 손익분기점 |

### 현재 위치 해석

**중요 발견 (ep_len 정규화 분석):**
이전 분석에서 "0.45 이하에서 contact 손실"로 결론지었으나, ep_len으로 정규화하면 **per-step contact/propulsion 품질은 splay와 무관하게 동일**. contact_band 하락은 CaT 에피소드 단축에 의한 누적값 감소일 뿐, 실제 접지 안정성 저하가 아님.

따라서 0.45 plateau의 원인은 "contact 손실"이 아니라 **"policy의 탐색 한계"**:
- entropy 0.3 이하로 수렴 → 새로운 행동 시도 불가
- CaT 30% 압력 하의 안전한 local optimum에 갇힘
- contact가 안 무너지므로 CaT prob 추가 상향이 가능

### 다음 단계: V40 실험 계획 (`plan/V40_PLAN.md`)

**V40-A: 탐색 촉진 + Positive Incentive** (1순위)
- contact 보호가 아닌 "탐색 촉진"으로 방향 전환
- CaT prob 추가 상향 (contact 안 무너지니 가능)
- positive posture reward (어깨 모으면 직접 보상)
- CPG phase reward 강화 (V39.1.1보다 강한 weight)

**V40-B: Target band 편향 점검** → 정규화 분석으로 편향 없음 확인, 우선순위 하향

**V40-C: 구조적 검증** (A 실패 시)

---

## 3. V38 시리즈 전체 경과

### V38 — Binary CaT (실패)
- threshold 0.6→0.4 ramp, probability 0.1→0.3
- iter 600에서 99.3% 종료, 즉시 붕괴

### V38.1 — Binary CaT 완화 (실패)
- threshold 0.8→0.45, probability 0.03→0.15
- iter 1800에서 splay 57%, ep_len 10 — phase transition으로 붕괴

### V38.2 — Soft CaT (부분 성공)
- `prob(dev) = base_prob × clamp((max_dev - 0.3) / 0.3, 0, 1)`, prob 0.0004
- phase transition 제거, 안정적이지만 shoulder_dev 0.518 정체 (9% 종료율 무시)

### V38.3 — Soft CaT prob 3.75x (진행 중)
- prob 0.0004→0.0015
- shoulder_dev 0.537→0.457 달성, 하지만 0.45에서 새 local optimum

### 핵심 발견
- **L2 penalty는 reward 채널** — agent가 다른 보상으로 상쇄 가능
- **CaT는 discount factor 채널** — 상쇄 불가, 하지만 local optimum은 존재
- **Soft CaT는 phase transition 없이 안정적** — prob 조절만으로 압력 제어
- **DoneTerm은 매 step 호출** — probability는 `(1-p)^ep_len`으로 역산 필수

---

## 3. V36 결과 분석

| 지표 | V35.5 (기준) | V36 | 변화 | 판정 |
|------|-------------|-----|------|------|
| ep_len | 250 | 250 | 동일 | 부팅 완벽 |
| shoulder_dev | 0.544 rad | 0.543 | 0% | anti-splay 무효 |
| stride_length | 4.533 | 6.084 | +34% | anti-shuffle 성공 |
| swing_stride | 0.522 | 1.192 | +128% | 대폭 개선 |
| feet_air_time | -9.541 | -7.070 | +26% | 체공 개선 |

---

## 4. 프로젝트 현재 상태

### 코드
```
브랜치: develop
상태: V38.1 env_cfg/rewards.py 변경 완료
훈련: V38.1 진행 중 (run 2026-03-21_09-08-16)
```

### 주요 파일
| 파일 | 내용 |
|------|------|
| `source/.../spot_micro_rl_env_cfg.py` | V38.1 환경 설정 (CaT DoneTerm + 커리큘럼) |
| `source/.../mdp/rewards.py` | V38.1 보상 함수 (shoulder_splay_termination + CaT ramp) |
| `plan/V38_PLAN.md` | V38~V38.1 설계 + V38 결과 + V38.1 파라미터 |
| `plan/V37_PLAN.md` | V37~V37.2 설계 + 결과 |
| `plan/QUADRUPED_RL_RESEARCH.md` | 연구 조사 (CaT 논문 포함) |

### IsaacOps
- `isaac_ops/listen.cmd` -> 통합 listener (Telegram 명령 + heartbeat + 영상)
- `isaac_ops/cli.cmd` -> CLI 도구 (status, hb, stop, start, resume)

---

## 5. 프로젝트 21대 교훈 (V1~V38)

1. **output=0 reward는 weight를 올려도 0** — band 밖이면 gradient 소멸
2. **패널티만으로는 고착된 local optimum 탈출 불가** — 인센티브 구조 변경 필요
3. **비대칭 보호는 붕괴를 이동시킬 뿐** — 전체 다리에 동일 기준 적용
4. **critic reset + 대규모 reward 변경 = 발산** — from-scratch가 안전
5. **물리적 비대칭이 있으면 reward로 극복 불가** — 초기 자세 대칭이 전제조건
6. **특정 행동의 부재는 패널티로 해결 불가** — 해당 행동에 대한 명시적 보상이 필요
7. **step-level alternation은 역할 분리를 보상** — temporal alternation과 다름
8. **contact-level 패널티는 대각 역할 분리를 유발** — joint-level 접근이 필요
9. **다리별 전용 보상(front_*, rear_*)은 역할 분리 유발** — 4발 공통 보상이 안전
10. **보상 50개+는 항목 간 상호작용 예측 불가** — 성공한 프레임워크는 15~20개
11. **Gait 패턴은 "발견"보다 "지시"가 안정적** — phase clock/CPG 구조적 강제
12. **한 번에 하나만 변경** — 단, 구조 자체가 틀리면 대폭 재설계 필요
13. **높이 목표와 서있기 보상은 충분해야 함** — 양의 보상 부족 시 정지/넘어짐 학습
14. **4발 공통 보상은 초기 부팅 신호를 제공하지 못함** — rear 전용 보상이 부팅의 핵심
15. **서기도 못 하면서 보행+전진 동시 요구 불가** — 단계적 학습 필요
16. **reward weight=0 Phase 분리 -> 관측-보상 불일치** — rel_standing_envs 사용
17. **재현성 먼저 확인** — "성공" 버전이라도 최소 2회 실행 검증 (V32.1 = 25% 성공률)
18. **alive_bonus는 locomotion RL의 기본** — 초기 탐색 실패 시 local min 탈출 불가
19. **penalty가 전체 reward의 1% 미만이면 무시됨** — 5~10%는 되어야 행동 변경 유도
20. **CaT threshold는 실측 dev의 1.5배 이상으로 시작** — V38에서 1.1배로 즉시 붕괴
21. **CaT probability는 0.03~0.05에서 시작** — 0.1도 과도, 점진 강화 필수

---

## 6. 향후 로드맵

### 단기 (V38.1~V39)
| 단계 | 핵심 변경 | 목표 |
|------|----------|------|
| **V38.1** (현재) | CaT 파라미터 완화 (threshold 0.8->0.45, prob 0.03->0.15) | shoulder_dev < 0.35 |
| V38.2 (필요 시) | CaT 추가 조정 | V38.1 결과에 따라 |

### 중기 (V39~V40)
| 단계 | 핵심 변경 | 목표 |
|------|----------|------|
| V39 | Energy regularization + 보상 정리 (50->25개) | 자연스러운 보행 |
| V40 | Gait phase clock 또는 CPG layer | 명시적 trot 강제 |

### 장기
- Sim-to-real (Solo-12 논문 참고, 경량 로봇은 domain randomization 적음)
- 보상 15~20개로 최종 정리

### 참고 논문 (V38+ 핵심)
- CaT: Constraints as Terminations (IROS 2024) — [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)
- Barrier-Based Style Rewards (KAIST, ICRA 2025) — [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)
- ROGER: Adaptive Reward Gain (2025) — [arXiv 2510.10759](https://arxiv.org/html/2510.10759v1)
- 전체 목록: `plan/QUADRUPED_RL_RESEARCH.md`

---

## 7. 주의사항

### 운영
- **listener는 `isaac_ops/listen.cmd`로 실행** (구 supervisor.cmd 폐기)
- **CLI: `isaac_ops/cli.cmd <command>`** (status, hb, stop, start, resume)
- **rewards.py / env_cfg.py 수정 시 listener 재시작 불필요** (훈련 프로세스만 재시작)
- **WSL2에서 git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`
- **Windows cp949 이모지 crash**: print에 이모지 금지, ASCII 텍스트 사용

### 코드
- **TRAIN_VERSION 단일 소스**: env_cfg.py line 7
- **버전별 상수는 TRAINING_CONFIG에서 읽기** (rewards.py에 하드코딩 금지)
