# MEMORY.md — AI Session Handoff Document
> **목적**: 새 세션에서 AI가 이 파일만 읽으면 프로젝트 컨텍스트를 즉시 복원할 수 있도록 작성.  
> **갱신 시점**: 매 세션 종료 시, 또는 중요 의사결정 발생 시.  
> **마지막 갱신**: 2026-03-03 15:00

---

## 1. 프로젝트 한 줄 요약

SpotMicro 4족 로봇이 **trot 걸음걸이**(대각 교대보행)로 걷도록 강화학습(PPO)으로 훈련. 현재 **V16 Flat 훈련 중** — 뒷다리 끌림 문제 해결을 위해 `diagonal_joint_coupling_reward` 도입.

---

## 2. 기술 스택

| 항목 | 값 |
|------|-----|
| Isaac Lab | v2.3.0 |
| Isaac Sim | 5.1.0.0 |
| IsaacLab 경로 | `C:\IsaacLab` |
| Python | 3.10, conda env `env_isaaclab` |
| GPU | NVIDIA RTX 5080 Laptop 16GB GDDR7 |
| 알고리즘 | PPO (RSL-RL) |
| 프로젝트 | `D:\project\spot_micro_rl` (branch: `develop`) |
| 병렬 환경 수 | 24,576 |

### 실행 전 필수 명령
```bash
conda activate env_isaaclab
cd D:\project\spot_micro_rl
pip install -e source/spot_micro_rl --quiet
```

### 중요 주의사항
- 백그라운드 터미널은 `(base)`로 시작됨 → 반드시 `conda activate env_isaaclab;` 선행
- `Select-Object -First N` 파이프를 훈련 프로세스에 걸면 프로세스가 죽음 → `isBackground: true` 사용
- 훈련 실행: `C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py ...`

---

## 3. 핵심 파일 위치

| 파일 | 역할 |
|------|------|
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py` | 환경 설정, 리워드 가중치 (V16 현재) |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py` | 커스텀 리워드 함수 25+ 개 (~920줄) |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/agents/rsl_rl_ppo_cfg.py` | PPO 하이퍼파라미터 |
| `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/__init__.py` | gym 환경 등록 (4개) |
| `source/spot_micro_rl/spot_micro_rl/robots/spot_micro.py` | 로봇 URDF, 모터 설정 |

---

## 4. 등록된 환경

| 환경 ID | 용도 |
|---------|------|
| `Isaac-Velocity-Flat-SpotMicro-v0` | Flat 학습/테스트 |
| `Isaac-Velocity-Rough-SpotMicro-v0` | Rough 학습 |
| `Isaac-Velocity-Rough-SpotMicro-Play-v0` | Rough 플레이 |
| `Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0` | Flat obs + 급경사 지형 플레이 |

---

## 5. 현재 상태 (V16)

### 5.1 V16 설계 의도
**문제**: V15d까지 뒷다리가 끌림 — 접촉 센서 기반 리워드로는 "미세 진동"으로 속임  
**해결**: **kinematic-based `diagonal_joint_coupling_reward`** 도입
- FL↔RR, FR↔RL 관절 속도 상관관계를 `tanh(v1*v2/deadzone²)`로 직접 측정
- 접촉 센서 없이 joint velocity 상관만으로 trot 강제
- weight=25.0

### 5.2 V16 리워드 가중치 변경 (vs V15d)

| 리워드 | V15d | V16 | 변화 이유 |
|--------|------|-----|----------|
| `standing_height` | 12 | **10** | diagonal coupling이 보완 |
| `foot_clearance` | 12 | **8** | diagonal coupling이 보완 |
| `trot_gait` | 30 | **40** | trot 패턴 강화 |
| `same_side_penalty` | -20 | **-30** | 비트로트 강력 억제 |
| `rear_swing` | 7 | **15** | 뒷발 리프트 강화 |
| `leg_lift` | 20 | **15** | 축소 (diagonal coupling 보완) |
| `rear_joint_velocity` | 15 | **20** | 뒷다리 활성화 강화 |
| `rear_joint_frozen` | -40 | **-60** | 뒷다리 동결 강력 처벌 |
| `rear_alternation` | 20 | **30** | 뒷다리 교대 강화 |
| `rear_both_ground` | -50 | **-80** | 뒷다리 고정 강력 처벌 |
| **`diagonal_coupling`** | - | **25** | **신규** (핵심) |

### 5.3 V16 PPO 하이퍼파라미터 (V15d와 동일)
```
gamma=0.97, clip_param=0.1, lr=1e-4, schedule=fixed
epochs=3, mini_batches=4, value_loss_coef=0.5, entropy=0.01
network: [512, 256, 128] ELU
```

### 5.4 V16 훈련 현황

| 항목 | 값 |
|------|-----|
| **상태** | ⏸️ play test를 위해 일시 중지 (2026-03-03) |
| **진행률** | iter **10800 / 22600** (48%) |
| **Mean Reward** | ~630 (안정적) |
| **Value Loss** | 1.6~2.1 (정상) |
| 체크포인트 위치 | `logs/rsl_rl/spot_micro_flat/2026-03-03_09-40-03/` (resume 이후) |
| 원본 체크포인트 | `logs/rsl_rl/spot_micro_flat/2026-02-27_09-12-43/` (iter 0~7600) |
| play test 결과 | **미확인** (사용자가 아직 피드백 안 줌) |

### 5.5 Resume 명령어
```bash
conda activate env_isaaclab
cd D:\project\spot_micro_rl
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 \
  --num_envs=24576 --headless --max_iterations=15000 \
  --resume --load_run=2026-03-03_09-40-03 --checkpoint=model_10800.pt
```
> 주의: `--max_iterations=15000` + resume offset 10800 = 총 25800까지 훈련됨

### 5.6 Play Test 명령어
```bash
# Flat 지형
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\play.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=50 \
  --checkpoint=D:\project\spot_micro_rl\logs\rsl_rl\spot_micro_flat\2026-03-03_09-40-03\model_10800.pt

# 급경사 지형
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\play.py \
  --task=Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0 --num_envs=50 \
  --checkpoint=D:\project\spot_micro_rl\logs\rsl_rl\spot_micro_flat\2026-03-03_09-40-03\model_10800.pt
```

---

## 6. 버전 히스토리 요약 (의사결정 이유 포함)

### V1~V8: 기본기 확립 (2026-02-17 ~ 2026-02-19)
- V1~V4: 서기→걷기 전환. 진동 해결(decimation 4→8), trot 보상 설계
- V5~V8: Flat 최적화. V8이 Flat 최종 모델 → Rough 전이학습 소스

### V9~V12: Rough 지형 도전 (2026-02-20 ~ 2026-02-23)
- V9: Flat→Rough 가중치 전이 (48→102 obs dim). 기본 보행 성공
- V10: `rear_alternation` 추가 → 뒷다리 토큰 교대만 (실제 보폭 없음)
- V11: `rear_both_ground` 페널티 → 뒷발을 들긴 하지만 제자리 들기
- **V12**: `rear_forward_stride` (높이×속도 곱) → 뒷다리 여전히 고정. **30K iter에서 포기**
  - **핵심 발견**: 접촉 센서 기반 리워드는 뒷다리가 "미세 진동"으로 속일 수 있음

### V13~V14b: Critic Reset 시도 (2026-02-24 ~ 2026-02-25)
- V12의 actor는 좋지만 critic이 오래된 리워드 구조에 갇힘
- Critic reset (Xavier init) + fine-tune → **3번 연속 발산**
- **교훈**: 리워드 가중치가 크게 바뀌면 critic reset만으로는 부족. from-scratch가 낫다

### V15 시리즈: From-Scratch Flat (2026-02-26)
- **전략 전환**: Rough에서 fine-tune 포기 → Flat에서 처음부터 뒷다리 보상 포함해서 학습
- V15a: 첫 시도 → 1600 iter에서 발 끌림 확인
- V15b: 보상 스케일 축소 → value_loss 발산 (gamma=0.99가 return을 키움)
- V15c: 더 축소 → 여전히 발산
- **V15d**: gamma=0.97, clip=0.1, lr=1e-4 → **안정화 성공!** 15000 iter, reward=559, value_loss=0.53
  - **핵심 교훈**: PPO 안정성은 gamma(return 크기)와 clip(업데이트 크기)에 좌우됨
  - 하지만 **뒷다리는 여전히 끌림** → 리워드 구조 자체의 문제

### V16: Diagonal Coupling (2026-02-27 ~ 현재)
- **핵심 인사이트**: 접촉 센서 기반 → 키네마틱(joint velocity) 기반으로 전환
- `diagonal_joint_coupling_reward`: FL↔RR, FR↔RL 관절 속도 상관 측정
- V15d의 안정된 PPO 하이퍼파라미터 유지
- 훈련 시작 (Feb 27) → iter 7600에서 중단 (이동) → 체크포인트 git commit
- 재개 (Mar 3) → iter 10800까지 진행 → play test를 위해 중단

---

## 7. 다음 할 일 (우선순위순)

1. **V16 Play Test 확인**: 사용자에게 뒷다리 trot 여부 피드백 받기
   - 성공 시 → 훈련 완료까지 재개 → Flat→Rough 전이
   - 실패 시 → `diagonal_coupling` weight 증가 또는 phase oscillator 도입 고려

2. **V16 훈련 재개**: iter 10800 → 완료 (예상 ~22600)
   - 리워드가 ~630에서 plateau → 추가 훈련이 quality를 개선하는지 지켜볼 것

3. **Flat→Rough 전이**: V16 trot 확인 후
   - `scripts/transfer_flat_to_rough.py` 사용 (48→102 obs dim, height_scan Xavier init)
   - Rough 환경: `Isaac-Velocity-Rough-SpotMicro-v0`

4. **PROJECT_HISTORY.md 갱신**: V15d~V16 내용 추가 (현재 V15까지만 기록됨)

---

## 8. 실패에서 배운 교훈

| 교훈 | 근거 |
|------|------|
| **접촉 센서 리워드는 뒷다리 "속임" 허용** | V10~V12에서 뒷다리가 미세 진동으로 접촉 리워드 획득 |
| **Critic reset + fine-tune은 큰 리워드 변경에 부적합** | V13, V14, V14b 3연속 발산 |
| **From-scratch가 fine-tune보다 안전** | V15d가 V13보다 훨씬 안정적 |
| **PPO 안정성 = gamma × reward_scale** | gamma 0.99→0.97로 return 3x 축소 → 발산 해결 |
| **clip_param이 작을수록 안정적** | 0.2→0.1로 줄이니 value_loss 안정화 |
| **키네마틱(joint vel) 리워드가 접촉 센서보다 속이기 어려움** | V16 diagonal_coupling 설계 근거 |
| **곱셈 리워드(A×B)로 "둘 다 해야"** 조건 표현 | rear_forward_stride = height × velocity |

---

## 9. 체크포인트 인벤토리

### Flat 모델 (중요한 것만)
| 폴더 | 버전 | 최종 iter | 비고 |
|-------|------|----------|------|
| `2026-02-26_16-08-11` | V15d | 14999 | reward=559, 뒷다리 끌림 |
| `2026-02-27_09-12-43` | V16 | 7600 | 중간 저장 (이동용) |
| `2026-03-03_09-40-03` | V16 resume | 10800 | **현재 최신**, play test 대기 |

### Rough 모델 (참고용)
| 폴더 | 버전 | 최종 iter | 비고 |
|-------|------|----------|------|
| `2026-02-23_19-41-20` | V12 | 30400 | 뒷다리 고정, 앞다리만 보행 |
| `2026-02-24_08-54-15` | V13 | 35000 | critic reset, 발산 |

---

## 10. Git 상태

| 항목 | 값 |
|------|-----|
| Branch | `develop` |
| 최신 커밋 | `adb3867` — V16: diagonal joint coupling reward |
| 원격 | `origin/develop` (pushed) |
| 비추적 파일 | `logs/` (체크포인트, tensorboard) |

---

*이 파일은 AI 세션 보조용입니다. 상세 프로젝트 히스토리는 `PROJECT_HISTORY.md`를 참고하세요.*
