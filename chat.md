# SpotMicro RL 프로젝트 전체 대화 기록

**기간**: 2026-02-14 ~ 2026-02-24  
**프로젝트**: SpotMicro RL (spot_micro_rl)  
**브랜치**: develop  
**환경**: Isaac Lab 4.5.0, RSL-RL PPO, NVIDIA RTX 5080 Laptop 16GB  
**conda 환경**: env_isaaclab  

---

# Phase 1: 프로젝트 초기 설정 및 V1~V4 (2026-02-14 ~ 02-15)

SpotMicro 4족 보행 로봇의 강화학습 프로젝트. Isaac Lab 4.5.0 기반으로 flat terrain에서 trot gait 학습 시작.
V1~V4는 기본 보상 함수 설정 및 초기 보행 패턴 학습 단계.

---

# Phase 2: V5~V8 Flat Terrain 고도화 (02-15)

### V5: 트로트 + 안정성 조합
- trot_gait, same_side_penalty, foot_clearance 등 보상 추가
- 앞다리 위주로 걷기 시작

### V6: 전진 속도 + 다리 들기 강화
- forward_velocity, leg_lift 보상 추가
- 4족 보행 패턴이 나타나기 시작

### V7: 뒷다리 활성화 시도
- rear_swing, rear_alternation 보상 추가
- 뒷다리가 가끔 움직이기 시작하지만 일관성 부족

### V8: Flat 최종 버전
- swing_stride, knee_height 보상 추가
- Flat terrain에서의 최종 학습 완료
- 24,576 parallel envs, ~10,000 iterations

---

# Phase 3: V9~V10 Flat→Rough 전환 (02-15 ~ 02-19)

### V9: Flat→Rough 체중 전이
- `transfer_flat_to_rough.py` 스크립트로 Flat(48dim) → Rough(102dim) 가중치 변환
- Height scanner(54 dim) 관측 추가
- Rough terrain에서 초기 적응 시작

### V10: Rough 지형 보상 조정
- terrain_progress, distance_walked, uphill_bonus 보상 추가
- 커리큘럼 학습 도입 (지형 난이도 점진적 증가)
- 계단/경사면 등반 능력 향상

---

# Phase 4: V11~V12 Rough Terrain 안정화 (02-19 ~ 02-23)

### V11: 보행 안정성 강화
- rear_both_ground 페널티 도입 (-200)
- rear_forward_stride 보상 도입 (250)
- foot_extension 페널티 도입 (-30)
- 뒷다리 교대 개선 시도

### V12: 최종 안정 버전
- 30,400 iterations까지 학습 (약 15시간)
- 커리큘럼 레벨 ~3.4 도달
- 러프 지형에서 안정적 보행
- **문제 발견**: 평지에서 뒷다리를 끌고 다님 (앞다리만 보행)
- 체크포인트: `logs/rsl_rl/spot_micro_rough/2026-02-23_19-41-20/model_30400.pt`

---

# Phase 5: 소스코드 주석 정리 (02-23)

5개 소스 파일의 주석을 한국어로 자연스럽게 재작성:
- `rewards.py` (733줄, 20+ 커스텀 보상 함수)
- `spot_micro_rl_env_cfg.py` (641줄, 환경 설정)
- `spot_micro.py` (~85줄, 로봇 설정)
- `rsl_rl_ppo_cfg.py` (~74줄, PPO 설정)
- `transfer_flat_to_rough.py` (~100줄, 가중치 전이)

---

# Phase 6: PROJECT_HISTORY.md 업데이트 (02-23)

PROJECT_HISTORY.md를 568줄에서 811줄로 확장.
V5~V12까지의 모든 개발 이력을 상세히 기록.
- 커밋: `0e6b826 "docs: PROJECT_HISTORY.md Phase 5-6 update (V5~V12) + comment rewrite"`
- `git push origin develop` 완료

---

# Phase 7: V12 재생 테스트 및 뒷다리 문제 발견 (02-23)

### 재생 테스트
```
python scripts/rsl_rl/play.py --task Isaac-Velocity-Rough-SpotMicro-Play-v0 --num_envs 50
```

### 관찰 결과
- **앞다리**: 정상적인 trot gait으로 보행
- **뒷다리**: 바닥에 고정된 채 끌려다님 (특히 평지에서)
- 러프 지형에서는 약간 움직이지만 여전히 부족

---

# Phase 8: V13 뒷다리 개선 작업 (02-23 ~ 02-24)

## 8-1. 원인 분석

뒷다리가 고정되는 3가지 원인:

1. **물리적 필요 없음**: 평지에서 앞다리만으로 전진 가능 — 뒷다리를 움직일 인센티브 부족
2. **안정성 페널티가 뒷다리 억제**: 
   - `joint_deviation`(-3.0): 뒷다리 관절이 기본값에서 벗어나면 큰 벌점
   - `action_rate_l2`(-1.5): 빠른 동작 변화 제한으로 스윙 개시 억제
   - `flat_orientation_l2`(-15.0): 뒷다리 스윙 시 몸체 흔들림에 페널티
3. **보상 기준값 과도**:
   - `rear_forward_stride` 발 속도 기준 0.3 m/s — 느린 보행에서 달성 불가
   - `target_clearance` 0.06m — 작은 들기는 무시

## 8-2. V13 코드 변경

### rewards.py
- `rear_forward_stride_reward` 함수에 `target_fwd_vel: float = 0.3` 파라미터 추가
- 기존: `fwd_score = torch.clamp(rear_fwd_vel / 0.3, 0.0, 1.0)` (하드코딩)
- 변경: `fwd_score = torch.clamp(rear_fwd_vel / target_fwd_vel, 0.0, 1.0)` (파라미터화)

### spot_micro_rl_env_cfg.py (SpotMicroRoughEnvCfg)

| 파라미터 | V12 | V13 | 변경 의도 |
|----------|-----|-----|-----------|
| `joint_deviation` | -3.0 | -2.0 | 뒷다리 관절 움직임 허용 |
| `action_rate_l2` | -1.5 | -1.2 | 빠른 동작 변화 허용 |
| `rear_alternation` | 150 | 200 | 뒷다리 교대 인센티브 강화 |
| `rear_both_ground` | -200 | -300 | 뒷다리 양쪽 동시 접지 페널티 강화 |
| `target_clearance` | 0.06 | 0.04 | 작은 들기도 보상 |
| `target_fwd_vel` | 0.3 (하드코딩) | 0.2 (신규 파라미터) | 느린 발 속도도 보상 |

## 8-3. V13 훈련 시도 1 — 공격적 변경 (실패, 즉시 발산)

처음에는 더 공격적인 값을 시도:
- `rear_both_ground`: -500 (2.5배 증가)
- `rear_forward_stride`: 400 (1.6배 증가)  
- `joint_deviation`: -1.5 (50% 감소)

**결과**: Mean reward → -10^17, value_function_loss → inf  
**원인**: V12 가치함수(critic)가 V12 보상 스케일 기준으로 학습되어 있어, 급격한 보상 변경에 적응 불가

## 8-4. V13 훈련 시도 2 — 완화된 변경 (실패, noise std 음수)

위의 표대로 30~50% 범위로 변경폭 축소.

**결과**: 
- 처음 2~3 iterations 정상 (reward ≈ 486)
- 19 iterations 후 크래시: `RuntimeError: normal expects all elements of std >= 0.0`
- 훈련 폴더: `2026-02-24_06-33-09`

**원인**: value function loss(722,712)가 여전히 높아 adaptive learning rate 폭주 → noise std 음수

## 8-5. 해결 방안: Critic 리셋 + Actor 유지

**선택한 방법**: V12 체크포인트에서 Actor만 보존, Critic/Optimizer/Std 재초기화

### 체크포인트 구조 (`model_30400.pt`)
```
model_state_dict:
  actor.0.weight: (512, 102)   ← 보존
  actor.0.bias: (512,)         ← 보존
  actor.2.weight: (256, 512)   ← 보존
  actor.2.bias: (256,)         ← 보존
  actor.4.weight: (128, 256)   ← 보존
  actor.4.bias: (128,)         ← 보존
  actor.6.weight: (12, 128)    ← 보존
  actor.6.bias: (12,)          ← 보존
  critic.0~6: ...              ← Xavier uniform 재초기화
  std: (12,)                   ← 0.5로 리셋
optimizer_state_dict: {}       ← 삭제
iter: 30400                    ← 유지
```

### Critic 리셋이 최적인 이유
- **From scratch**: ~30,000 iterations(15시간) 필요
- **Critic 리셋**: Actor가 이미 걸음걸이를 알므로 ~5,000 iterations(2~3시간)이면 V12 수준 회복 + 뒷다리 개선 시작
- **Resume 변경폭 축소**: 10~20%까지 줄여도 critic 불안정 위험 존재

### 리셋 스크립트
`scripts/reset_critic.py` 작성 완료:
```
python scripts/reset_critic.py \
  --input logs/rsl_rl/spot_micro_rough/2026-02-23_19-41-20/model_30400.pt \
  --output logs/rsl_rl/spot_micro_rough/2026-02-23_19-41-20/model_30400_critic_reset.pt \
  --init_std 0.5
```

---

# 다음 단계

- [ ] Critic 리셋 스크립트 실행
- [ ] V13 훈련 시작 (리셋된 체크포인트 사용)
- [ ] ~5,000 iterations 후 뒷다리 개선 여부 확인
- [ ] 안정화 후 커밋 & PROJECT_HISTORY.md 업데이트
