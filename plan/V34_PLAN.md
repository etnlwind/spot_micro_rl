# V34 Plan — rel_standing_envs 기반 3-Phase 커리큘럼 (서기→걷기)

**작성일**: 2026-03-19
**상태**: 구현 완료, 훈련 대기

---

## 배경

V33~V33.3: "서기도 못 하는데 4발 보행 + 전진" 동시 요구 → 실패
- V33: 근본 재설계(122→28개), rear 전부 제거 → 붕괴
- V33.1: standing_height 강화 → 동일 패턴 붕괴
- V33.2: rear 절반 복구 → 3발 exploit (RR 고정)
- V33.3: per-limb penalty → 학습 자체 억제 (reward -13, iter 585)
- V33.4: reward weight=0 Phase 분리 시도 → 관측-보상 불일치 발견, 폐기

**근본 원인**: `rel_standing_envs=0.0`에서 바로 보행 요구. 서기 안정화 기회 없음.

## 핵심 아이디어

Isaac Lab 내장 `rel_standing_envs` + command range 커리큘럼으로 **1개 Env** 안에서 서기→걷기 전환.
- Standing env: command=0 자동 할당 → `track_lin_vel_xy_exp(1.5)`가 "0 추적 성공" = 서기 보상
- 3개 별도 Env 대신 1개 Env + 커리큘럼 → critic 연속성 유지, checkpoint 전환 불필요

## 3-Phase 커리큘럼

| | Phase 1: Stand (0~200) | Phase 2: Transition (200~500) | Phase 3: Walk (500+) |
|--|----------------------|---------------------------|-------------------|
| `rel_standing_envs` | 0.8 | 0.8→0.1 | 0.1 |
| `lin_vel_x` | (0.01, 0.15) | →(0.1, 0.5) | (0.1, 0.5) |
| `ang_vel_z` | (-0.15, 0.15) | →(-0.5, 0.5) | (-0.5, 0.5) |
| `forward_velocity` | 0.0 | 0→5.0 | 5.0 |
| `stationary_penalty` | 0.0 | 0→-3.0 | -3.0 |
| `rear_both_ground` | 0.0 | 0→-60.0 | -60.0 |
| `min_swing_ratio` | 0.0 | 0→-15.0 | -15.0 |
| `limb_usage_min` | 0.0 | 0→-5.0 | -5.0 |
| `single_limb_validity` | 0.0 | 0→-5.0 | -5.0 |

### Phase 1 (iter 0~200) — 서기 집중
- 80% env: command=0 (서기), 20% env: 극저속 (0.01~0.15)
- `track_lin_vel_xy_exp=1.5` 처음부터 ON → standing env에서 서기 보상 역할
- `standing_height=15.0`, `base_height_l2=-15.0`, `flat_orientation_l2=-5.0` 활성
- `rear_joint_frozen=-60.0` 활성 — 관절 동결 방지
- gait reward (trot_gait=40, feet_air_time=20): min_vel=0.001이므로 정지 시 자연 무력화

### Phase 2 (iter 200~500) — 점진 전환
- `rel_standing_envs` 0.8→0.1 선형 감소
- command range 점진 확대
- 전진/per-limb reward 선형 ramp

### Phase 3 (iter 500+) — 본격 보행
- 모든 보상 최종 weight로 안정
- rel_standing_envs=0.1 (약간의 standing 유지)

## V33.4 대비 핵심 차이

| | V33.4 | V34 |
|-|-------|-----|
| 서기 메커니즘 | reward weight=0 | `rel_standing_envs=0.8` |
| tracking reward | 0 (꺼짐) | 1.5 (처음부터 ON) |
| command range | 고정 (0.01, 0.5) | 커리큘럼 (0.01,0.15)→(0.1,0.5) |
| Phase 전환 | iter 500~800 | iter 200~500 |
| 관측-보상 일치 | 불일치 (command 무시 학습) | 일치 (standing env에 command=0) |

## 파일 변경

| 파일 | 변경 |
|------|------|
| `spot_micro_rl_env_cfg.py` | V34, track_lin_vel=1.5 복원, rel_standing=0.8, 초기 command 좁게, CurrTerm 교체 |
| `rewards.py` | `standing_first_curriculum` → `stand_walk_curriculum` 교체 |
| `.env` | TRAIN_VERSION=V34 |

## 체크포인트 기준

| iter | 확인 | 판단 |
|------|------|------|
| 100 | standing_height > 2.0, ep_length > 50 | Phase 1 서기 학습 진행 중 |
| 200 | 4발 안정 기립, standing env에서 진동 없음 | Phase 2 진입 준비 |
| 350 | 20% env가 저속 전진 시작, RR usage > 0 | 전환 순조 |
| 500 | rel_standing=0.1, forward_velocity > 0 | Phase 3 진입 |
| 800 | 4발 보행 형성, trot 패턴 | V34 성공/실패 판정 |

## 리스크

1. **Phase 1 gait reward 간섭** — trot_gait(40), feet_air_time(20) 등이 min_vel=0.001로 정지 시 거의 0이지만, 미세 진동 시 작은 신호 발생 가능 → 모니터링
2. **command range 변경 타이밍** — 다음 resample부터 적용, 즉시 반영 안 됨 → 자연스러운 전환
3. **rel_standing_envs 직접 수정** — Isaac Lab 소스에서 cfg를 resample 시 직접 읽으므로 안전하나, 공식 API는 아님
4. **per-limb penalty V33.3보다 약화** — min_swing_ratio -15(V33.3: -25), limb_usage -5(-10), single_limb -5(-15) → 서기 후 자연스러운 4발 사용 기대
