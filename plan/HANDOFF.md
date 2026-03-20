# HANDOFF.md

> 마지막 업데이트: 2026-03-21
> 최신 커밋: develop 브랜치

---

## 1. 현재 목표

**Anti-Splay 해결 — L2 penalty 커리큘럼 한계 확인, Barrier/CaT 전환 준비**

| 버전 | 결과 | 비고 |
|------|------|------|
| V32.1 | 🟡 부분 성공 | front lock-in 해소, 하지만 거미형 벌어짐 + 셔플링 |
| V33~V34 | ❌ 실패 | 근본 재설계/커리큘럼 시도, 부팅 불가 |
| V35~V35.5 | ✅ 부팅 성공 | alive_bonus(10) + contacts 램프 + 저속 command 3결합, 100% 재현 |
| V36 | 🟡 부분 성공 | anti-shuffle 성공(stride +34%), **anti-splay 실패**(shoulder_dev 0.54 고착) |
| V37 | ❌ 실패 | 3변수 동시 변경(shoulder -15, stance -8, height 0.22) → iter 600 보행 붕괴 |
| **V37.2** | 🟡 **한계 확인** | shoulder만 -6→-10 단일 변경, 보행 유지하나 splay 개선 없음 (0.532 vs 0.543) |

---

## 2. V37 → V37.2 경과

### V37 (실패)
- **설계**: shoulder -6→-15, stance -3→-8, height 0.23→0.22 동시 커리큘럼 (iter 500~1000)
- **결과**: iter 600에서 보행 붕괴 (reward 181→-92, ep_len 250→6)
- **원인**: 교훈 #12 위반 — 3변수 동시 변경이 학습 안정성 파괴
- **교훈**: splay_ramp 시작 직후 100 iter 이내 급격한 reward 하락은 커리큘럼 과도 신호

### V37.2 (L2 한계 확인)
- **설계**: shoulder만 -6→-10 단일 변경, 느린 ramp (iter 500~1500), stance/height 고정
- **결과**: 보행 완벽 유지 (ep_len 247-250), reward 회복 중, **BUT shoulder_dev 0.532 (V36: 0.543)**
- **결론**: L2 penalty를 -10까지 올려도 splay 행동 변화 없음. 보행 보상(+180) 대비 penalty 비율이 구조적으로 부족

### 핵심 발견
**L2 penalty 커리큘럼 방식의 근본 한계 확인**:
- 약하게 주면(-6~-10) 무시됨 (전체 reward의 1% 미만)
- 강하게 주면(-15) 보행 자체가 붕괴
- → Barrier 함수 또는 CaT(Constraints as Terminations) 같은 구조적 접근 필요

---

## 3. V36 결과 분석

| 지표 | V35.5 (기준) | V36 | 변화 | 판정 |
|------|-------------|-----|------|------|
| ep_len | 250 | 250 | 동일 | ✅ 부팅 완벽 |
| shoulder_dev | 0.544 rad | 0.543 | 0% | ❌ anti-splay 무효 |
| stride_length | 4.533 | 6.084 | +34% | ✅ anti-shuffle 성공 |
| swing_stride | 0.522 | 1.192 | +128% | ✅ 대폭 개선 |
| feet_air_time | -9.541 | -7.070 | +26% | ✅ 체공 개선 |

### Shoulder Dev 추이 (V36)
iter 100: 0.091 → iter 300: 0.184 → iter 500: 0.529 → iter 800: 0.543 (고착)

**패턴**: 보행 학습 시 안정성을 위해 다리를 벌리는 것이 보상적으로 유리. penalty(-6.0)가 보행 보상 합(+180) 대비 너무 약해서 무시됨.

---

## 4. 프로젝트 현재 상태

### 코드
```
브랜치: develop
상태: V37.2 env_cfg/rewards.py 변경 완료
훈련: V37.2 완료 — L2 penalty 한계 확인, 다음 단계(V38 Barrier/CaT) 준비
```

### 주요 파일
| 파일 | 내용 |
|------|------|
| `source/.../spot_micro_rl_env_cfg.py` | V37.2 환경 설정 (splay_ramp 커리큘럼) |
| `source/.../mdp/rewards.py` | V37.2 보상 함수 (splay_ramp 로직) |
| `plan/V37_PLAN.md` | V37~V37.2 설계 + 결과 문서 |
| `plan/V36_PLAN.md` | V36 설계 + 결과 |
| `plan/V35_PLAN.md` | V35 시리즈 전체 경과 |
| `plan/QUADRUPED_RL_RESEARCH.md` | 연구 조사 (최신 논문 포함) |

### IsaacOps
- `isaac_ops/listen.cmd` → 통합 listener (Telegram 명령 + heartbeat + 영상)
- `isaac_ops/cli.cmd` → CLI 도구 (status, hb, stop, start, resume)
- listener가 V37 run을 자동 인식하여 heartbeat 전송 중

---

## 5. 프로젝트 19대 교훈 (V1~V37)

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
16. **reward weight=0 Phase 분리 → 관측-보상 불일치** — rel_standing_envs 사용
17. **재현성 먼저 확인** — "성공" 버전이라도 최소 2회 실행 검증 (V32.1 = 25% 성공률)
18. **alive_bonus는 locomotion RL의 기본** — 초기 탐색 실패 시 local min 탈출 불가
19. **penalty가 전체 reward의 1% 미만이면 무시됨** — 5~10%는 되어야 행동 변경 유도

---

## 6. 향후 로드맵

### 단기 (V38)
| 단계 | 핵심 변경 | 목표 |
|------|----------|------|
| **V38** (다음) | Barrier-based penalty 또는 CaT | L2 대체, shoulder_dev < 0.3 |

### 중기 (V39~V40)
| 단계 | 핵심 변경 | 목표 |
|------|----------|------|
| V39 | Energy regularization + 보상 정리 (50→25개) | 자연스러운 보행 |
| V40 | Gait phase clock 또는 CPG layer | 명시적 trot 강제 |

### 장기
- Sim-to-real (Solo-12 논문 참고, 경량 로봇은 domain randomization 적음)
- 보상 15~20개로 최종 정리

### 참고 논문 (V38+ 핵심)
- Barrier-Based Style Rewards (KAIST, ICRA 2025) — [arXiv 2409.15780](https://arxiv.org/abs/2409.15780)
- CaT: Constraints as Terminations (IROS 2024) — [arXiv 2403.18765](https://arxiv.org/abs/2403.18765)
- ROGER: Adaptive Reward Gain (2025) — [arXiv 2510.10759](https://arxiv.org/html/2510.10759v1)
- 전체 목록: `plan/QUADRUPED_RL_RESEARCH.md`

---

## 7. 주의사항

### 운영
- **listener는 `isaac_ops/listen.cmd`로 실행** (구 supervisor.cmd 대체)
- **CLI: `isaac_ops/cli.cmd <command>`** (status, hb, stop, start, resume)
- **rewards.py / env_cfg.py 수정 시 listener 재시작 불필요** (훈련 프로세스만 재시작)
- **WSL2에서 git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`
- **Windows cp949 이모지 crash**: print에 이모지 금지, ASCII 텍스트 사용

### 코드
- **TRAIN_VERSION 단일 소스**: env_cfg.py line 7
- **버전별 상수는 TRAINING_CONFIG에서 읽기** (rewards.py에 하드코딩 금지)
