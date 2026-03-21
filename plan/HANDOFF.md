# HANDOFF.md

> 마지막 업데이트: 2026-03-21
> 최신 커밋: develop 브랜치

---

## 1. 현재 목표

**Anti-Splay 해결 — V38.1: CaT (Constraints as Terminations) 파라미터 완화 재시도**

| 버전 | 결과 | 비고 |
|------|------|------|
| V32.1 | 부분 성공 | front lock-in 해소, 하지만 거미형 벌어짐 + 셔플링 |
| V33~V34 | 실패 | 근본 재설계/커리큘럼 시도, 부팅 불가 |
| V35~V35.5 | 부팅 성공 | alive_bonus(10) + contacts ramp + 저속 command 3결합, 100% 재현 |
| V36 | 부분 성공 | anti-shuffle 성공(stride +34%), anti-splay 실패(shoulder_dev 0.54 고착) |
| V37~V37.2 | 한계 확인 | L2 penalty -10까지 올려도 splay 행동 변화 없음 |
| V38 | 실패 | CaT threshold 0.6이 너무 타이트, iter 600 즉시 붕괴 |
| **V38.1** | **훈련 중** | CaT 완화: threshold 0.8->0.45, prob 0.03->0.15, ramp 800~2500 |

---

## 2. V38 -> V38.1 경과

### V38 (실패 — 2026-03-21)
- **설계**: CaT 도입, shoulder splay > threshold -> 확률적 에피소드 종료
- **파라미터**: threshold 0.6->0.4, probability 0.1->0.3, ramp iter 500~1500
- **결과**: iter 400에서 부팅 성공 (ep_len 247, reward 170), iter 500 CaT 활성화 직후 iter 600에서 즉시 붕괴 (ep_len 11, CaT 종료율 99.3%)
- **원인**: threshold 0.6이 실측 dev 0.54에 너무 가까움 (margin 0.06). probability 0.1도 과도
- **교훈**: CaT threshold는 실측 dev의 1.5배 이상, probability는 0.03~0.05에서 시작

### V38.1 (훈련 중 — 2026-03-21)
- **설계**: V38 동일 구조, 파라미터만 대폭 완화
- **파라미터 변경**: threshold 0.8->0.45, probability 0.03->0.15, ramp iter 800~2500
- **Run**: `2026-03-21_09-08-16`
- **초기 상태 (iter 500)**: 부팅 성공 (ep_len 242, reward 180, CaT 아직 OFF)

### 핵심 발견
**L2 penalty -> CaT 전환의 핵심 포인트**:
- L2 penalty는 reward 채널 — agent가 다른 보상으로 상쇄 가능 (V37.2에서 확인)
- CaT는 discount factor 채널 — terminated=True면 미래 보상=0, 상쇄 불가
- 단, CaT는 "너무 타이트하면 보행 자체를 포기"하는 새로운 failure mode 존재
- threshold/probability의 보수적 설정이 필수

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
