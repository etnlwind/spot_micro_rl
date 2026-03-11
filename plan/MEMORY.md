# MEMORY.md — AI Session Handoff Document
> **목적**: 새 세션에서 AI가 이 파일만 읽으면 프로젝트 컨텍스트를 즉시 복원할 수 있도록 작성.  
> **갱신 시점**: 매 세션 종료 시, 또는 중요 의사결정 발생 시.  
> **마지막 갱신**: 2026-03-11 (V22 운영/아티팩트 체계 완료, 운영 스크립트 단순화, V23 준비)

---

## 1. 프로젝트 한 줄 요약

SpotMicro 4족 로봇이 **trot 걸음걸이**(대각 교대보행)로 걷도록 강화학습(PPO)으로 훈련. 현재 학습 버전 태그는 **V20**이고, 운영/아티팩트 체계는 **V22**까지 정리됨. V22는 V21의 gait-quality-first 모니터링 위에 멀티뷰 영상, heartbeat workbook, ZIP artifact, front-view 포함 패키징을 얹은 운영 레이어다. 2026-03-11 밤에 운영 스크립트는 `scripts/supervisor.py` + `scripts/heartbeat.py` 중심의 단순 구조로 재정리됐고, 레거시 코드는 `scripts/legacy/`에 참고용으로 보관한다. 다음 작업은 **V23 학습 전략 준비**다.

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
| `scripts/common.py` | Telegram, process, state, report/video helper 공용 함수 |
| `scripts/supervisor.py` | Telegram 명령 루프 (`start/stop/status/report/front/rear/top/side/help`) |
| `scripts/heartbeat.py` | read-only heartbeat 전송 루프 |
| `scripts/legacy/` | 구 `training_supervisor.py` / `training_heartbeat.py` 참고용 보관 |

---

## 4. 등록된 환경

| 환경 ID | 용도 |
|---------|------|
| `Isaac-Velocity-Flat-SpotMicro-v0` | Flat 학습/테스트 |
| `Isaac-Velocity-Rough-SpotMicro-v0` | Rough 학습 |
| `Isaac-Velocity-Rough-SpotMicro-Play-v0` | Rough 플레이 |
| `Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0` | Flat obs + 급경사 지형 플레이 |

---

## 5. 현재 상태 (V20 학습 + V22 운영)

### 5.0 V22 운영 정리 (2026-03-11)

- 새 문서: `plan/V22_ANALYSIS.md`, `plan/V23_PLAN.md`
- supervisor 최종 패키지는 `overview / side / front / rear / top` 5개 시점을 전송
- top view에서는 command 화살표를 숨기고, side/front/rear/top 단일 로봇 시점을 일관되게 저장
- heartbeat는 `heartbeat_reports.jsonl`에 구조화 기록을 남김
- artifact ZIP은 `heartbeat_history.xlsx`를 포함하고, `Overview / Trends / RawData` 탭과 차트를 생성
- 과거 런에는 JSONL이 없을 수 있으므로 TensorBoard scalar fallback으로 workbook을 재구성
- 실전 검증 런: `logs/rsl_rl/spot_micro_flat/2026-03-11_02-39-01`
- 최신 검증 아티팩트: `clip_1005_iter15000_20260311_132732.zip`

### 5.0b 운영 스크립트 단순화 (2026-03-11 밤)

- active 운영 엔트리포인트는 `scripts/supervisor.py`, `scripts/heartbeat.py`, `scripts/common.py`
- 파일명 변경 기록
  - `scripts/training_supervisor.py` → `scripts/supervisor.py`
  - `scripts/training_heartbeat.py` → `scripts/heartbeat.py`
  - `scripts/training_common.py` / `scripts/v2/common.py` 계열 실험본 → `scripts/common.py`
  - `scripts/legacy/supervisor.py`, `scripts/legacy/heartbeat.py`는 과거 운영 코드 참고용 보관본
- `supervisor.py`가 Telegram 명령을 직접 처리
  - `start`
  - `stop`
  - `status`
  - `report`
  - `front`
  - `rear`
  - `top`
  - `side`
  - `help`
- `heartbeat.py`는 read-only 상태 감시 전용이며, 프로세스 kill/restart를 수행하지 않는다
- `start` / `stop`만 훈련 상태를 바꾸고, `report/front/rear/top/side`는 내부에서 훈련을 중단/재개하지 않는다
- `report/front/rear/top/side` 동작 원칙
  - 훈련 중이면 최신 기존 산출물만 전송
  - 훈련 정지 상태면 현재 active checkpoint 기준으로 새 산출물을 생성 후 전송
- 자동 재개 / emergency resume / supervisor-heartbeat 상호복구 루프는 active 경로에서 제거
- 구 운영 코드는 `scripts/legacy/` 아래에 참고용으로만 남긴다

### 5.1 V21 운영 정리 (2026-03-10)

- 새 분석 문서: `plan/V21_ANALYSIS.md`
- heartbeat는 reward 총합보다 gait 품질 KPI를 먼저 보고 Telegram에 전송
- supervisor는 heartbeat와 같은 KPI 언어를 사용하고, 멀티뷰 영상(side/front/rear/top_oblique)을 전송
- 영상 수집 cadence는 시간 기반이 아니라 iteration 기반으로 전환 중
  - 초기 500 iter
  - 중기 1000 iter
  - 후기 1500 iter
  - verdict 악화 시 urgent clip 허용
- contact 해석은 flat 기준 `foot_link`에서 `toe_link`로 전환
- `play.py`는 contact CSV/JSON export와 카메라 preset을 지원
- 실운영 검증 런: `logs/rsl_rl/spot_micro_flat/2026-03-10_07-43-51`
- 재개 후보 체크포인트: `model_9600.pt` 우선

### 5.2 V17.1 훈련 분석 결과 (2026-03-06)

V17.1은 iter 5,104/15,000에서 **"정지 함정(stillness trap)"** 에 빠짐:

| 지표 | 값 | 판정 |
|------|-----|------|
| Mean Reward | -99.6 → **-54.2** (3,000+ iter plateau) | ❌ 음수 |
| bad_orientation 종료율 | **100%** (매 에피소드 넘어짐) | ❌ 치명적 |
| 전진 속도 | **0.009 m/s** (목표 0.5) | ❌ 사실상 정지 |
| 에피소드 길이 | **~1.5초** (최대 10초) | ❌ 즉사 |
| 보행 지표 (trot/stride/gait) | 전부 ~0 | ❌ 학습 안 됨 |

**근본 원인**: 35개 리워드 동시 활성화 → 페널티 합(-150 feet_below_knees, -100 undesired_contacts, -80 rear_both_ground)이 양수 보상 합보다 압도적 → 로봇이 "아무것도 안 하는 게 최선"이라 학습. 속도 게이팅된 양수 보상은 넘어지면 발동 불가 → 닭-달걀 문제.

### 5.3 V18 설계: 3-Phase Reward Curriculum

**핵심 전략**: Isaac Lab의 `CurriculumManager`를 이용해 훈련 단계별로 리워드 가중치를 동적으로 조절.

| Phase | 이름 | Iteration | 목표 |
|-------|------|-----------|------|
| 1 | **STAND** | 0 ~ 2,000 | 서기 안정화, 페널티 최소 |
| 2 | **WALK** | 2,000 ~ 6,000 | 전진 보행, 점진적 gait 도입 |
| 3 | **TROT** | 6,000 ~ 15,000 | V17.1 전체 가중치 복원 |

#### Phase별 주요 가중치 변화

| 리워드 | Phase 1 | Phase 2 | Phase 3 (V17.1) |
|--------|---------|---------|-----------------|
| `standing_height` | **40** | 20 | 10 |
| `height_bonus` | **25** | 15 | 7 |
| `forward_velocity_bootstrap` | **8** | 4 | 0 |
| `forward_velocity` | 2 | **8** | 8 |
| `same_side_penalty` | **0** | -10 | -30 |
| `rear_both_ground` | **0** | -30 | -80 |
| `undesired_contacts` | **-20** | -50 | -100 |
| `feet_below_knees` | **-30** | -80 | -150 |
| `trot_gait` | 5 | 20 | **40** |
| `rear_joint_frozen` | -10 | -30 | **-60** |
| `diagonal_coupling` | 5 | 15 | **25** |
| `gait_cycle_period` | 0 | 8 | **15** |
| `stride_length` | 0 | 6 | **12** |
| `foot_clearance` | 2 | 5 | **8** |

### 5.4 V18 구현 파일

| 파일 | 변경 내용 |
|------|----------|
| `mdp/rewards.py` | `reward_weight_curriculum()` 함수 추가 (~90줄) |
| `env_cfg.py` | `SpotMicroRewardCurriculumCfg` 클래스 + `self.curriculum` 설정 |

### 5.5 V18 PPO 하이퍼파라미터 (V15d와 동일)
```
gamma=0.97, clip_param=0.1, lr=1e-4, schedule=fixed
epochs=3, mini_batches=4, value_loss_coef=0.5, entropy=0.01
network: [512, 256, 128] ELU, num_steps_per_env=48
```

### 5.6 V18 훈련 명령어 (From Scratch)
```bash
conda activate env_isaaclab
cd D:\project\spot_micro_rl
pip install -e source/spot_micro_rl --quiet
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\train.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 \
  --num_envs=24576 --headless --max_iterations=15000
```
> **주의**: V18은 기존 체크포인트에서 resume 불가 — 반드시 from scratch 훈련.  
> `common_step_counter`가 0에서 시작하므로 resume 시 Phase가 리셋됨.

### 5.7 Play Test 명령어
```bash
# 훈련 완료 후 (체크포인트 경로는 실제 타임스탬프로 교체)
C:\IsaacLab\isaaclab.bat -p scripts\rsl_rl\play.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=50 \
  --checkpoint=<logs/rsl_rl/spot_micro_flat/TIMESTAMP/model_15000.pt>
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

### V16: Diagonal Coupling (2026-02-27 ~ 2026-03-03)
- **핵심 인사이트**: 접촉 센서 기반 → 키네마틱(joint velocity) 기반으로 전환
- `diagonal_joint_coupling_reward`: FL↔RR, FR↔RL 관절 속도 상관 측정
- V15d의 안정된 PPO 하이퍼파라미터 유지
- 훈련 시작 (Feb 27) → iter 7600에서 중단 (이동) → 체크포인트 git commit
- 재개 (Mar 3) → iter 10800까지 진행 → play test를 위해 중단

### V17/V17.1: Action Rate + Gait Cycle + Stride Length (2026-03-04 ~ 2026-03-05)
- V17: `action_rate_l2_clamped` (weight -3.0), `gait_cycle_period_reward`, `stride_length_reward` 추가
- `dof_acc_l2` 강화 (-8e-8→-5e-6), `joint_vel_l2` 강화 (-0.02→-0.5)
- 속도 범위 확대 lin_vel_x (0.1, 0.5), 최소 속도 도입 (정지 방지)
- V17.1: `feet_air_time` threshold 완화 (0.25→0.1s, 솟구침 방지)
- **결과**: iter 5,104에서 "정지 함정" — reward -54.2 plateau, 100% bad_orientation, 전진 0.009 m/s
- **원인 분석**: 35개 리워드 동시 활성화, 페널티 합이 보상 합 압도, 닭-달걀 문제

### V18: 3-Phase Reward Curriculum (2026-03-06 ~ 현재)
- **전략**: Isaac Lab `CurriculumManager`로 STAND→WALK→TROT 단계적 리워드 가중치 변화
- Phase 1 (0~2K): 서기 집중, 페널티 최소화, bootstrap 활성화
- Phase 2 (2K~6K): 전진 유도, 점진적 gait 도입
- Phase 3 (6K~15K): V17.1 전체 가중치 복원
- `reward_weight_curriculum()` 함수 + `SpotMicroRewardCurriculumCfg` 구현
- **상태**: 코드 구현 완료, From-scratch 훈련 대기
- **참고**: Rough 환경은 terrain curriculum만 사용 (reward curriculum 미적용)
  - Flat 완료 후 Rough 전이 시 별도 처리 필요

---

## 7. 다음 할 일 (우선순위순)

1. **V18 From-Scratch 훈련 시작**: 3-Phase Curriculum으로 flat 환경에서 처음부터 학습
   - 예상 소요: ~4시간 (15,000 iter × 24,576 envs)
   - Phase 전환 로그 확인: "[Curriculum] Phase X (NAME) @ iter Y"

2. **TensorBoard 모니터링**: Phase별 학습 진행 확인
   - Phase 1 (0~2K): reward가 양수로 전환되는지?
   - Phase 2 (2K~6K): forward velocity가 증가하는지?
   - Phase 3 (6K~15K): trot gait 지표가 올라가는지?

3. **Play Test**: iter 15,000 완료 후 시각적 확인
   - 서기 → 걷기 → 트로트 패턴 달성 여부

4. **결과에 따른 후속 조치**:
   - 성공 시 → Flat→Rough 전이학습 (`transfer_flat_to_rough.py`)
   - 부분 성공 → Phase 경계 iteration 조정 (예: Phase 1 확장)
   - 실패 시 → Phase 1 가중치 추가 조정, 또는 explicit phase oscillator 도입

5. **PROJECT_HISTORY.md 갱신**: V16~V18 내용 추가

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
| **35개 리워드 동시 활성화 → 정지 함정** | V17.1: 페널티 합 > 보상 합 → 움직이지 않는 게 최적 |
| **Phase Curriculum로 닭-달걀 문제 해결** | V18: 서기→걷기→트로트 단계적 도입 |

---

## 9. 체크포인트 인벤토리

### Flat 모델 (중요한 것만)
| 폴더 | 버전 | 최종 iter | 비고 |
|-------|------|----------|------|
| `2026-02-26_16-08-11` | V15d | 14999 | reward=559, 뒷다리 끌림 |
| `2026-02-27_09-12-43` | V16 | 7600 | 중간 저장 (이동용) |
| `2026-03-03_09-40-03` | V16 resume | 10800 | play test 미확인 |
| (V17.1 run) | V17.1 | 5104 | **실패** — 정지 함정, reward -54.2 |
| (V18 예정) | V18 | - | **다음 훈련**, 3-Phase Curriculum |

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
| 최신 커밋 | V18: 3-Phase Curriculum 구현 (커밋 예정) |
| 원격 | `origin/develop` |
| 비추적 파일 | `logs/` (체크포인트, tensorboard) |
| 주요 변경 파일 | `mdp/rewards.py`, `env_cfg.py`, `plan/MEMORY.md` |

---

*이 파일은 AI 세션 보조용입니다. 상세 프로젝트 히스토리는 `PROJECT_HISTORY.md`를 참고하세요.*
