# SpotMicro RL Training Project History

**Last Updated**: 2026-03-15
**Project Status**: V26.1 훈련 진행 중 — Symmetric Existence Floor + Load Sharing
**Current Active Run Snapshot**: V26.1 fresh run (2026-03-15 시작) / TRAIN_VERSION=”V26”

---

## 📌 Current Status Snapshot (V26.1 active)

### 2026-03-15 V26.1 훈련 시작

| 항목 | 값 |
|------|-----|
| TRAIN_VERSION | `”V26”` |
| 상태 | 훈련 진행 중 (fresh run) |
| 진입점 | `logs\_launch_supervisor.cmd` |
| supervisor PID | 18064 |
| 핵심 변경 | 8개 symmetric reward term (Existence Floor + Load Sharing) |
| 이전 버전 | V25 실패 (iter 400, RR collapse) |

최근 핵심 커밋:

- `346f674` Fix: add per-leg metrics to kpi_snapshot for video report
- `1c242fe` Add V26.1 reward implementation, docs, and RL/RR limb metrics
- `dc577ba` Fix /start fresh-start UX: confirmation flow

중요:

- 아래 역사 섹션은 프로젝트 전체 의사결정 배경을 보존하기 위한 연대기다.
- 가장 최신 active handoff는 `plan/MEMORY.md`, `plan/CURRENT_STATE_2026-03-15.md`를 먼저 본다.

### 학습 버전 요약 (V23~V26)

| 버전 | 판정 | 핵심 교훈 |
|------|------|-----------|
| V23 | 실패 | rear-left 3족 보행 exploit, contact sensor 오매핑 |
| V24 | 실패 | collapse 고착 후 패널티가 회피를 유도 |
| V25 | 실패 | 비대칭 패널티 → collapse 위치만 RL→RR 이동 |
| V26.1 | 훈련 중 | symmetric per-leg existence floor + load sharing |

- **현재 코드 기준 학습 버전 태그**: `TRAIN_VERSION = “V26”`
- **설계 철학 문서**: `plan/V26_ANALYSIS.md`
- **구현 계획 문서**: `plan/V26.1_PLAN.md` (active)

핵심 문서:

- `plan/V26_ANALYSIS.md`: V26 설계 철학 (부하 분산 + 파손 위험 최소화)
- `plan/V26.1_PLAN.md`: V26.1 구현 계획 + 판정 기준
- `plan/V25_ANALYSIS.md`: V25 실패 분석 (RR collapse)
- `plan/V24_ANALYSIS.md`: V24 실패 분석

### V22 핵심 변경

1. heartbeat를 gait-quality-first KPI 체계로 재정렬
2. supervisor가 heartbeat와 같은 KPI 언어로 영상 caption/요약을 생성
3. supervisor 멀티뷰 패키지를 `overview / side / front / rear / top`로 확장
4. artifact ZIP에 `heartbeat_history.xlsx`와 정지 프레임 묶음을 포함
5. 과거 런에도 TensorBoard fallback으로 workbook을 복구 가능하게 정리

### 2026-03-11 밤 운영 스크립트 단순화

- active 운영 파일은 `scripts/supervisor.py`, `scripts/heartbeat.py`, `scripts/common.py`
- 파일명 변경 기록
  - `scripts/training_supervisor.py` → `scripts/supervisor.py`
  - `scripts/training_heartbeat.py` → `scripts/heartbeat.py`
  - `scripts/training_common.py` / `scripts/v2/common.py` 계열 실험본 → `scripts/common.py`
- `scripts/legacy/supervisor.py`, `scripts/legacy/heartbeat.py`는 과거 V21/V22 운영 코드 참고용 보관본
- active 경로에서는 auto-resume / emergency resume / supervisor-heartbeat 상호복구 루프를 제거
- `start` / `stop`만 훈련 상태를 바꾸고, `report/front/rear/top/side`는 훈련 중이면 최신 산출물만 전송하고 정지 상태에서만 현재 checkpoint 기준으로 새로 생성
- 이후 2026-03-12에 same-run latest checkpoint 우선 선택, run-matched cache filtering, version/freshness status 표시가 추가됨

### Heartbeat / Supervisor 역할

| 컴포넌트 | 역할 | 출력 |
|----------|------|------|
| `heartbeat.py` | read-only 상태 감시, KPI 분류, 상세 heartbeat 전송 | 텍스트 |
| `supervisor.py` | Telegram 명령 처리, 훈련 시작/중단, 보고서/영상 전송 | 텍스트 + 비디오 + ZIP |

참고:

- 과거 V21/V22 문서의 `training_heartbeat.py`, `training_supervisor.py` 표기는 역사적 명칭이다
- 현재 active 파일은 `heartbeat.py`, `supervisor.py`
- 구 코드는 `scripts/legacy/` 아래에 참고용으로 남겨둔다
- `shutdown` 명령도 active supervisor 명령 셋에 포함된다

### V21에서 우선 보는 KPI

- `standing_height`
- `forward_velocity`
- `diagonal_coupling`
- `trot_gait`
- `rear_joint_velocity`
- `foot_clearance`

접촉 이벤트 기반 `stride_length`, `gait_cycle_period`는 참고 지표로 유지한다.

### 현재 운영 기준

- 실운영 검증 런: `2026-03-11_02-39-01`
- 최종 체크포인트: `model_15000.pt`
- 최신 검증 ZIP: `clip_1005_iter15000_20260311_132732.zip`
- V23 준비 문서: `plan/V23_ANALYSIS.md`

---

## 📋 Project Overview

### Objective
Train SpotMicro quadruped robot to perform stable walking from a crouched initial position using reinforcement learning (PPO algorithm via RSL-RL).

### Technical Stack
- **Isaac Lab**: v2.3.0
- **Isaac Sim**: 5.1.0.0
- **Python**: 3.10
- **Conda Environment**: env_isaaclab
- **GPU**: NVIDIA RTX 5080 Laptop 16GB
- **Algorithm**: PPO (Proximal Policy Optimization) via RSL-RL

### Project Structure Evolution
- **Phase 1**: In-tree development (C:\IsaacLab)
- **Phase 2**: Standalone extension (D:\project\spot_micro_rl\spot_micro_rl\)
- **Phase 3**: Simplified path structure (D:\project\spot_micro_rl\) ✅ **CURRENT**

---

## 🎯 Training Milestones

### Key Checkpoints

| Checkpoint | Iteration | Date | Achievement |
|------------|-----------|------|-------------|
| `2026-02-16_10-54-39` | 22,600 | 2026-02-16 | ⭐ **서기 성공** (Phase 1) |
| `2026-02-17_03-57-39` | 9,999 | 2026-02-17 | Baseline (서기만 함) |
| `2026-02-19_09-59-53` | 13,400 | 2026-02-19 | V4: 엄격한 트롯 (Flat) |
| `2026-02-19_20-40-30` | 900 | 2026-02-19 | V8: Flat 최종 (전이학습 소스) |
| `transferred_from_v8_flat` | 0 | 2026-02-20 | V8→Rough 가중치 전이 |
| `2026-02-21_08-43-40` | 1,000→9,900 | 2026-02-21 | V9: 첫 장기 러프 학습 (10K iters) |
| `2026-02-22_13-11-38` | 11,000→16,500 | 2026-02-22 | V10: rear_alternation 추가 |
| `2026-02-22_23-19-25` | 16,500→21,200 | 2026-02-22~23 | V11: rear_both_ground 페널티 |
| `2026-02-23_19-41-20` | 25,800→30,400 | 2026-02-23 | V12: rear_forward_stride (뒷다리 고정 발견) |
| `2026-02-24_08-54-15` | 30,400→47,360 | 2026-02-24 | V13: critic reset (발산) |
| `2026-02-25_16-34-32` | 35,000→35,005 | 2026-02-25 | V14: 접촉 독립 보상 (즉시 발산) |
| `2026-02-25_17-09-37` | 35,000→35,365 | 2026-02-25 | V14b: 축소 가중치 (발산) |
| `2026-02-26_??-??-??` | **0→???** | 2026-02-26 | 🔴 **V15: from-scratch Flat (현재)** |

### Training Statistics
- **Total Training Sessions**: 260+
- **Flat Terrain Iterations**: ~14,300 (Phase 1~4 + V5~V8) + V15 진행 중
- **Rough Terrain Iterations**: ~47,360 (V9~V13, V12 model_30400 기준)
- **Failed Fine-tune Attempts**: 4 (V13×2, V14, V14b — critic reset 발산)
- **Training Environments**: 24,576 parallel environments
- **Episode Length**: Flat 10s / Rough 20s

---

## 🔧 Technical Configuration

### Robot Configuration
**File**: `source/spot_micro_rl/spot_micro_rl/robots/spot_micro.py`

```python
# URDF Model (프로젝트 내 assets/ 폴더)
urdf_path = "assets/robots/spot_micro/spotmicroai_realistic_inertia.urdf"

# DC Motor Configuration
actuators = {
    "legs": DCMotorCfg(
        joint_names_expr=[".*shoulder", ".*leg", ".*foot"],
        effort_limit=10.0,
        saturation_effort=15.0,
        stiffness=10.0,
        damping=1.0,
        velocity_limit=10.0,
    )
}

# 서있는 초기 자세 (V6+)
init_state = {
    pos = (0.0, 0.0, 0.20),  # 높이 0.20m
    joint_pos = {
        ".*shoulder": 0.0,
        ".*leg": -0.5,       # upper leg 약간 기울임
        ".*foot": 1.2,       # 무릎 구부림
    }
}
soft_joint_pos_limit_factor = 0.7  # foot 관절 접힘 제한 (2.59×0.7=1.81rad)
```

### Environment Configuration
**File**: `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py`

#### 등록된 환경
- `Isaac-Velocity-Flat-SpotMicro-v0` — 평지 학습/테스트
- `Isaac-Velocity-Flat-SpotMicro-Play-v0` — 평지 플레이 (계단 지형 포함)
- `Isaac-Velocity-Rough-SpotMicro-v0` — 러프 지형 학습
- `Isaac-Velocity-Rough-SpotMicro-Play-v0` — 러프 지형 플레이

#### 현재 보상 항목 (V12, Rough Terrain)

| 보상 | 가중치 | 설명 |
|------|--------|------|
| **trot_gait** | **180.0** | 대각 페어 교대 (0.4×mean + 0.6×min) |
| **rear_forward_stride** | **250.0** | 뒷발 [높이 × 전방속도] 곱 |
| **same_side_penalty** | **-200.0** | 바운딩/페이싱 억제 |
| **rear_both_ground** | **-200.0** | 뒷다리 동시 접지 페널티 |
| **rear_alternation** | **150.0** | 뒷다리 교대 스윙 |
| rear_swing | 80.0 | 뒷발 스윙 높이 (target 12cm) |
| leg_lift | 60.0 | 스윙 시 힙 관절 들어올림 |
| swing_stride | 50.0 | 발의 전방 보폭 |
| terrain_progress | 50.0 | 지형 난이도 비례 보상 |
| foot_clearance | 35.0 | 스윙 시 발 높이 (target 10cm) |
| forward_velocity | 35.0 | 전진 보상 (target 0.5 m/s) |
| standing_height | 30.0 | 높이 0.22m × 수평 결합 |
| distance_walked | 30.0 | 원점 대비 이동 거리 |
| base_height_l2 | -30.0 | 높이 0.22m 기준 L2 |
| foot_extension | -30.0 | foot 관절 과신전 페널티 |
| knee_height | 20.0 | 무릎 높이 유지 |
| feet_air_time | 20.0 | 체공 시간 (150ms 이상) |
| flat_orientation_l2 | -15.0 | 수평 유지 |
| track_lin_vel_xy_exp | 10.0 | 속도 추적 |
| track_ang_vel_z_exp | 5.0 | 각속도 추적 |
| joint_deviation | -3.0 | 기본 자세 편차 |
| action_rate_l2 | -1.5 | 동작 부드러움 |
| undesired_contacts | -300.0 | 비정상 접촉 (base, shoulder, leg) |
| feet_below_knees | -500.0 | 발-무릎 역전 |

#### Rough Terrain 설정
```python
# 지형 종류: 계단, 역계단, 랜덤 박스, 울퉁불퉁, 경사(상/하)
terrain_size = (4.0, 4.0)  # 작은 지형 → 승급 기준 2m
curriculum = True           # 점진적 난이도 증가
step_height_range = (0.02, 0.08)  # SpotMicro 스케일

# 높이 스캐너: 0.1m 해상도, 0.8×0.5m 그리드
# 관측: 48차원(flat) + 54차원(height_scan) = 102차원

# 속도 명령
lin_vel_x = (0.2, 0.6)   # 러프 지형 속도 범위
episode_length_s = 20.0   # 긴 에피소드

# 외부 교란
push_robot = True          # 10~15초 간격, ±0.3 m/s
base_contact_termination = True  # 넘어짐 감지
```

#### PPO 설정 (Rough / V15 Flat)
```python
# 네트워크: [512, 256, 128] (actor = critic)
# V15 Flat:
learning_rate = 5e-4       # fixed schedule
entropy_coef = 0.01        # from-scratch 탐색
# V12 Rough (참고):
# learning_rate = 1e-3     # adaptive schedule
# entropy_coef = 0.005     # 안정성 우선
save_interval = 200        # V15: 세밀한 체크포인트
```

---

## 🚀 Training Evolution & Problem Solving

### Phase 1: Standing Achievement (Iter 0 → 22,600)
**Problem**: Robot couldn't stand up from crouch position
- Initial config had trembling/shaking behavior
- URDF joints not receiving motor torque

**Root Cause Identified**: 
```python
# WRONG: target_type="none" 
# → PhysX DriveAPI not created → DCMotor torque couldn't reach joints

# FIXED: target_type="position"
# → Enables PhysX drive interface → Motor control works correctly
```

**Result**: ✅ Stable standing achieved at iter 22,600

### Phase 2: Walking Transition (Iter 22,600 → 28,700)
**Problem**: Robot stood well but didn't walk forward
- Reward balance favored standing over movement
- Insufficient forward velocity incentive

**Solution**: Rebalanced reward weights
```python
# Before
"track_lin_vel_xy_exp": {weight: 1.0}
"standing_height": {weight: 5.0}

# After
"forward_velocity": {weight: 150.0}  # 150x increase!
"standing_height": {weight: 30.0}
```

**Result**: 🔄 Walking behavior emerging (training ongoing - iter 28,700)

### Phase 3: Configuration Adjustment (Iter 28,700+)
**Problem**: Configuration error during day training (discarded iter 30,200)
- Incorrect settings led to poor training results
- Reverted to iter 27,100 and restarted with corrected config

**Action Taken**: 
- Discarded session `2026-02-16_14-20-49` (iter 30,200)
- Adjusted configuration parameters
- Resumed from stable checkpoint iter 27,100
- Continued training: 27,100 → 28,300 → 28,700

**Current Status**: ⏸️ Ready to continue from iter 28,700

### Phase 4: Leg Dragging Prevention (Iter 26,600+)
**Problem**: Robot might drag legs instead of lifting them
- No incentive for leg clearance during gait
- Knee/shank contact not penalized

**Solution**: Added gait quality rewards
```python
"feet_air_time": {weight: 20.0}         # Reward leg lifting
"undesired_contacts": {weight: -100.0}  # Punish knee/shank contact
```

**Result**: ⏳ Under evaluation in current training

---

## 📦 Project Structure Updates

### Migration History

**Phase 1 → Phase 2**: In-Tree → Standalone Extension (2026-02-16 AM)
- Moved from `C:\IsaacLab\source\` to `D:\project\spot_micro_rl\spot_micro_rl\`
- All logs migrated (3.81 GB)

**Phase 2 → Phase 3**: Path Simplification (2026-02-16 PM)
- Simplified from `D:\project\spot_micro_rl\spot_micro_rl\` to `D:\project\spot_micro_rl\`
- Removed redundant nested directory structure
- Training continues seamlessly from iter 28,700

#### Old Structure (C:\IsaacLab)
```
C:\IsaacLab\
  ├── source/isaaclab_assets/isaaclab_assets/robots/spot_micro.py
  ├── source/isaaclab_tasks/.../spot_micro/flat_env_cfg.py
  └── logs/rsl_rl/spot_micro_flat/  (3.81 GB)
```

#### New Structure (Standalone Extension)
```
D:\project\spot_micro_rl\
  ├── source/spot_micro_rl/
  │   ├── setup.py
  │   ├── spot_micro_rl/
  │   │   ├── __init__.py
  │   │   ├── robots/
  │   │   │   └── spot_micro.py
  │   │   └── tasks/
  │   │       └── manager_based/
  │   │           └── spot_micro_rl/
  │   │               ├── __init__.py  (gym.register)
  │   │               ├── spot_micro_rl_env_cfg.py
  │   │               ├── agents/
  │   │               │   └── rsl_rl_ppo_cfg.py
  │   │               └── mdp/
  │   │                   └── rewards.py
  ├── scripts/
  │   └── rsl_rl/
  │       ├── train.py
  │       ├── play.py
  │       └── list_envs.py
  ├── logs/rsl_rl/spot_micro_flat/  (100+ training sessions)
  └── PROJECT_HISTORY.md  (this file)
```

#### Installation Status
```bash
# Extension installed via (updated for Phase 3):
cd D:\project\spot_micro_rl
pip install -e source/spot_micro_rl

# Verification:
✅ Extension loaded successfully
✅ Environment registered: Isaac-Velocity-Flat-SpotMicro-v0
✅ Training script functional
✅ Resumed training from iter 27,100 → 28,700
✅ Path simplified: D:\project\spot_micro_rl
```

---

## ⚠️ Important Notes & Known Issues

### Environment Registration
**Environment IDs**:
- `Isaac-Velocity-Flat-SpotMicro-v0` — Flat 학습
- `Isaac-Velocity-Flat-SpotMicro-Play-v0` — Flat 플레이
- `Isaac-Velocity-Rough-SpotMicro-v0` — Rough 학습 (현재 사용)
- `Isaac-Velocity-Rough-SpotMicro-Play-v0` — Rough 플레이

**Action Required** (import 문제 시): 
```bash
pip uninstall spot_micro_rl -y
pip install -e source/spot_micro_rl
```

### Training Resume Command
**Next Action**: V12 학습이 완료되면 결과 평가 후 V13 진행

```bash
# Rough terrain 학습 재개
conda activate env_isaaclab
cd D:\project\spot_micro_rl

python scripts/rsl_rl/train.py \
  --task=Isaac-Velocity-Rough-SpotMicro-v0 \
  --num_envs=24576 \
  --headless \
  --max_iterations=40000 \
  --resume \
  --load_run=2026-02-23_19-41-20
```

**Parameters**:
- **Current Iteration**: 27,100+
- **Parallel Envs**: 24,576
- **Resume From**: Latest checkpoint in `2026-02-23_19-41-20`

```bash
# 결과 시각화 (러프 지형)
python scripts/rsl_rl/play.py \
  --task=Isaac-Velocity-Rough-SpotMicro-Play-v0 \
  --num_envs=50 \
  --load_run=2026-02-23_19-41-20
```

---

## 📊 Training Metrics to Monitor

### Primary Metrics (Rough Terrain)
1. **`Rewards/rear_forward_stride`**: 뒷발 실제 보폭 (V12 핵심)
2. **`Rewards/trot_gait`**: 트롯 걸음걸이 품질
3. **`Rewards/rear_alternation`**: 뒷다리 교대 비율
4. **`Rewards/rear_both_ground`**: 뒷다리 동시접지 (감소 필요)
5. **`Episode/terrain_levels`**: 커리큘럼 승급 레벨
6. **`Episode/time_out`**: 에피소드 끝까지 생존 비율
7. **`Episode/mean_reward`**: 전체 보상

### Secondary Metrics
- **`Rewards/forward_velocity`**: 전진 속도
- **`Rewards/distance_walked`**: 이동 거리
- **`Rewards/terrain_progress`**: 지형 난이도 보상
- **`Policy/mean_noise_std`**: 탐색 수준
- **`Loss/value_function`**: Critic 로스

### Success Criteria
- ✅ 서기 높이 유지 (~0.22m)
- ✅ 앞다리 트롯 교대
- ✅ 에피소드 생존율 >80%
- 🔄 뒷다리 실제 보폭 > 3cm
- 🔄 terrain_levels > 5.0
- ⬜ 전체 4족 자연스러운 트롯

---

## 🔄 Next Steps

### 현재 진행
1. **V12 학습 완료 대기**: rear_forward_stride 보상이 안정적으로 올라가는지 모니터
2. **Play 테스트**: 뒷다리 실제 보폭이 시각적으로 확인되면 성공

### 다음 단계 (V13+)
- **전체 4족 트롯 완성**: 앞/뒤 다리 모두 대각 교대로 자연스러운 보행
- **지형 일반화**: terrain_levels 최대치까지 커리큘럼 승급
- **속도 범위 확대**: lin_vel_x 범위를 (0.0, 1.0)까지 확장
- **외부 교란 강화**: push velocity 증가, 외력 추가
- **Sim-to-Real 전이**: 실제 SpotMicro 하드웨어에 배포

### 보상 설계 교훈
1. **단계적 접근이 핵심**: 교대(V10) → 동시접지 억제(V11) → 실제 보폭(V12)
2. **당근+채찍 병행**: 보상(alternation)만으로는 부족, 페널티(both_ground)도 필요
3. **곱셈 보상이 효과적**: height × velocity 곱으로 "둘 다 해야 보상" 구조
4. **min-heavy 결합**: 0.4*mean + 0.6*min으로 최악 성분을 견인
5. **전이학습 효과**: Flat에서 기본기를 배우고 Rough로 넘기면 학습 속도 향상

---

## 📝 Development Best Practices

### Code Organization
- ✅ Use standalone extension structure for portability
- ✅ Keep robot config separate from environment config
- ✅ Place custom rewards in dedicated `mdp/rewards.py`
- ✅ Version control with Git (recommended)

### Training Workflow
1. Test with small iteration count (10-100) after code changes
2. Use `--resume` to continue from checkpoints
3. Monitor logs regularly (TensorBoard recommended)
4. Keep multiple checkpoint backups (22600, 26600, 27100)
5. Document reward weight changes and results

### Debugging Tips
- **Robot trembling**: Check `target_type` in ArticulationCfg
- **No movement**: Verify actuator effort limits and stiffness
- **Unstable training**: Reduce action_scale or learning rate
- **Poor convergence**: Rebalance reward weights

---

## 📁 File Locations Reference

### Key Source Files
```
source/spot_micro_rl/spot_micro_rl/
├── robots/spot_micro.py                    # Robot config, URDF, motors
├── tasks/manager_based/spot_micro_rl/
│   ├── __init__.py                         # Environment registration
│   ├── spot_micro_rl_env_cfg.py           # Environment config, rewards
│   ├── agents/rsl_rl_ppo_cfg.py           # PPO hyperparameters
│   └── mdp/rewards.py                      # Custom reward functions
```

### Training Scripts
```
scripts/rsl_rl/
├── train.py          # Main training script
├── play.py           # Visualize trained policy
└── list_envs.py      # List registered environments
```

### Training Logs
```
logs/rsl_rl/
├── spot_micro_flat/          # Flat terrain (Phase 1~5, V1~V8)
│   ├── 2026-02-15_*/         # 초기 실험들
│   ├── 2026-02-17_*/         # Phase 4 (V1~V4)
│   └── 2026-02-19_20-40-30/  # V8 최종 Flat 모델
│
├── spot_micro_rough/         # Rough terrain (Phase 6, V9~V12)
│   ├── transferred_from_v8_flat/  # 전이학습 체크포인트
│   ├── 2026-02-20_*/         # V8 러프 초기 실험
│   ├── 2026-02-21_08-43-40/  # V9 장기 학습 (10K iters)
│   ├── 2026-02-22_13-11-38/  # V10 (rear_alternation)
│   ├── 2026-02-22_23-19-25/  # V11 (rear_both_ground)
│   └── 2026-02-23_19-41-20/  # V12 🔴 현재 학습 중
│
├── ant/                      # Ant 환경 테스트
├── anymal_c_flat/            # ANYmal C 참고
├── anymal_c_rough/           # ANYmal C Rough 참고
└── cartpole_direct/          # CartPole 테스트
```

---

## 🎓 Lessons Learned

### Critical Insights
1. **PhysX DriveAPI Requirement**: `target_type="position"` 필수 (DC 모터 제어)
2. **Reward Balance is Key**: 서기 우선 → 걷기 전환 시 보상 비율 조정 필수
3. **단계적 보상 추가**: 한번에 많은 보상을 넣으면 학습 불안정 → 순차 투입
4. **min-heavy 결합 (0.4mean + 0.6min)**: 약한 성분을 견인하는 효과
5. **곱셈 보상 (height × velocity)**: "둘 다 해야" 조건을 자연스럽게 표현
6. **전이학습 효과**: Flat→Rough 전이로 기본기를 보존하면서 새 능력 습득
7. **Local Minimum 탈출**: 보상(당근)만으로는 부족 → 페널티(채찍) 병행
8. **스케일 중요**: SpotMicro(24cm)는 ANYmal(55cm) 대비 1/2 스케일 — 지형/보상 모두 조정 필요
9. **Curriculum Learning**: 쉬운 지형부터 시작해서 점진적으로 어려운 지형으로 승급

### 뒷다리 문제 해결 과정 (V10→V12)
- ❌ V10: rear_alternation만으로는 "토큰 교대" (살짝 들었다 내려놓기)
- ❌ V11: + rear_both_ground 페널티 → 발을 들지만 제자리 들기
- 🔄 V12: + rear_forward_stride (높이×속도 곱) → 실제 보폭 학습 중

### Common Pitfalls Avoided
- ❌ `target_type="none"` with DC motors
- ❌ 안정성 과도 강조 → 움직임 억제
- ❌ 무릎/어깨 접촉 페널티 없이 학습
- ❌ 병렬 환경 부족 (4K→24K로 6배 증가)
- ❌ 코드 변경 후 대규모 테스트 (소규모 먼저)
- ❌ 한 커밋에 너무 많은 변경 (V5~V7은 커밋 없이 진행해서 추적 어려움)

---

## 📞 Support & Resources

### Documentation
- **Isaac Lab Docs**: [https://isaac-sim.github.io/IsaacLab](https://isaac-sim.github.io/IsaacLab)
- **RSL-RL GitHub**: [https://github.com/leggedrobotics/rsl_rl](https://github.com/leggedrobotics/rsl_rl)

### Troubleshooting Checklist
- [ ] Conda environment activated (`conda activate env_isaaclab`)
- [ ] Extension installed (`pip list | findstr spot_micro_rl`)
- [ ] URDF path correct (assets/robots/spot_micro/ 내)
- [ ] GPU available (check `nvidia-smi`)
- [ ] Sufficient disk space for logs (~8.3 GB)

---

## 🏁 Current Status Summary

**Training State**: 🟢 V12 학습 진행 중 (rough terrain, iter 27,100+)  
**Training Folder**: `logs/rsl_rl/spot_micro_rough/2026-02-23_19-41-20`  
**Environment**: ✅ Standalone extension (D:\project\spot_micro_rl)  
**Latest Model**: `model_27100.pt`  
**Terrain**: Rough (6종 지형, 커리큘럼 활성, terrain_levels ~2.6)  

**핵심 지표**:
- time_out 비율: ~0.90 (에피소드 끝까지 생존)
- rear_forward_stride: ~166 (뒷발 실제 보폭 신호)
- 24,576 환경, headless 모드, ~6.8s/iteration

**Resume Command**:
```bash
conda activate env_isaaclab
cd D:\project\spot_micro_rl
python scripts\rsl_rl\train.py --task Isaac-Velocity-Rough-SpotMicro-v0 --num_envs 24576 --headless --resume --load_run 2026-02-23_19-41-20 --max_iterations 40000
```

**뒷다리 문제 해결 진행도**:
- ✅ V9: 러프 지형 기본 보행
- ✅ V10: 뒷다리 교대 시작 (rear_alternation)
- ✅ V11: 뒷다리 동시접지 억제 (rear_both_ground)
- 🔄 V12: 뒷다리 실제 보폭 학습 중 (rear_forward_stride)
- ⬜ V13+: 전체 4족 트롯 완성, 지형 일반화

---

**Document Version**: 3.0  
**Generated**: 2026-02-23 22:00

### 개요
서있기만 하는 로봇을 실제 **강아지처럼 트롯 걸음걸이로 걷게** 만드는 과정.
baseline model_9999에서 시작하여 여러 보상 함수 설계/수정을 거쳐 V4까지 진화.

### 환경 최적화
- **병렬 환경**: 4,096 → **24,576** (GPU 13.2GB, 68% 활용)
- **제어 주파수**: 50Hz → **25Hz** (decimation 4→8, 진동 보행 물리적 차단)
- **학습 속도**: ~4.3s/iteration @ 24,576 envs

### 학습 체인 (Training Chain)

| 버전 | 폴더 | 체크포인트 | 보상 | 특징 |
|------|------|-----------|------|------|
| Baseline | `2026-02-17_03-57-39` | model_9999 | +273 | 서있기만 함 |
| Walking | `2026-02-17_19-39-15` | model_14998 | - | 첫 보행 (다리 떨림) |
| Smooth | `2026-02-18_12-21-30` | model_19997 | +37 | 떨림 제거 (발 끌기) |
| Clearance | `2026-02-18_16-40-58` | model_24996 | +248 | 발 높이 들기 (진동) |
| Trot-inplace | `2026-02-18_19-07-41` | - | - | 제자리 트롯 |
| Vel-gated | `2026-02-18_23-08-03` | - | - | 속도 게이팅 트롯 (작은 보폭) |
| Stride | `2026-02-19_00-31-13` | - | - | 보폭 확대 (벌레 기어다님) |
| **V1** | `2026-02-19_03-33-03` | model_11800 | ~870 | 높이↑, 24576 envs |
| **V2** | `2026-02-19_05-58-20` | model_12200 | ~986 | feet_air_time 완화 |
| **V3** | `2026-02-19_09-27-19` | model_12300 | ~1078 | standing_height 강화 |
| **V4** | `2026-02-19_09-59-53` | 학습 중... | 11→? | 엄격한 트롯 페어 |

### 주요 보상 함수 변경 이력

#### 문제→해결 과정
1. **서있기만 함** → `forward_velocity_reward` 정규화 + `stationary_penalty` 추가
2. **다리 떨림** → `action_rate_l2 = -0.5`
3. **발 끌기(셔플링)** → `foot_clearance_reward` 추가 (target 10cm)
4. **진동 보행** → `decimation 4→8` (50Hz→25Hz)
5. **제자리 트롯** → 모든 gait 보상에 `velocity gating` 추가
6. **작은 보폭** → `action_scale 0.5→1.0`, 관절 제약 완화
7. **벌레처럼 기어다님** → 높이 목표 0.21→0.24, 높이 페널티 강화

#### V4 핵심 변경 (현재)
- **`trot_gait_reward` 방식 변경**: 합산(OR) → **곱셈(AND)**
  - `pair_a_sync × pair_b_sync × anti_phase`
  - 세 조건 모두 충족해야 보상
  - 페어 A (왼앞+오른뒤) ↔ 페어 B (오른앞+왼뒤) 완벽 교대
- **trot_gait weight**: 25 → **50**
- **contact_count weight**: 10 → **20**

### 현재 보상 항목 (V4, 27개)

| 보상 | 가중치 | 설명 |
|------|--------|------|
| track_lin_vel_xy_exp | 25.0 | 속도 추적 |
| track_ang_vel_z_exp | 5.0 | 각속도 추적 |
| forward_velocity | 40.0 | 전진 보상 (target 0.5 m/s) |
| **trot_gait** | **50.0** | 대각 페어 교대 (곱셈 AND) |
| standing_height | 40.0 | 높이×수평 결합 |
| shoulder_neutral | -25.0 | 어깨 중립 |
| foot_clearance | 20.0 | 스윙 시 발 높이 (10cm) |
| **contact_count** | **20.0** | 2발 접촉 유지 |
| height_bonus | 20.0 | 높이 비례 보상 |
| flat_orientation_l2 | -20.0 | 수평 유지 |
| swing_stride | 15.0 | 보폭 보상 |
| stationary_penalty | -10.0 | 정지 페널티 |
| feet_air_time | 10.0 | 발 체공 시간 |
| shoulder_symmetry | -10.0 | 어깨 대칭 |
| knee_height | 5.0 | 무릎 높이 |
| base_height_l2 | -50.0 | 높이 (0.24m) |
| undesired_contacts | -100.0 | 비정상 접촉 |
| feet_below_knees | -500.0 | 발-무릎 역전 |

### 커밋 이력

| 커밋 | 해시 | 내용 |
|------|------|------|
| V4 | `44b46f0` | 엄격한 트롯 걸음걸이 (대각 페어 곱셈 AND 조건) |

---

## 🚀 Phase 5: Flat 지형 마무리 + 전이학습 준비 (2026-02-19 ~ 2026-02-20)

### 개요
V4까지 만든 트롯 걸음걸이를 **안정적으로 학습**시키고, Rough 지형으로의 **전이학습(Transfer Learning)** 준비.
V4의 곱셈 AND 방식 trot_gait가 너무 엄격해서 학습이 막히는 문제를 해결하고,
최종 Flat 모델을 만들어 Rough로 넘김.

### V5-V7: Flat 지형 보상 미세 조정

V4 이후 커밋 없이 다양한 보상 가중치를 시도하며 Flat에서 최적 걸음걸이를 찾는 과정.

#### 주요 변경점
- **trot_gait 방식**: 곱셈(AND) → **0.4×mean + 0.6×min** (min-heavy 결합)
  - 너무 엄격한 AND 조건이 학습을 막아서, 전체 평균은 유지하되 최악 성분을 더 중시하는 방식으로 변경
  - 4가지 성분: 대각A 동기화, 대각B 동기화, 반위상, 같은쪽 비동기
- **same_side_penalty** 신설: 바운딩(앞뒤 동기화) + 페이싱(좌우 동기화) 감지
- **trot_gait weight**: 50 → **150** (Flat 기준)
- **same_side_penalty weight**: **-80** (Flat 기준)
- **contact_count**: 통합 후 비활성화 (weight=0)
- **stationary_penalty**: 비활성화 (weight=0)

#### Flat 학습 체인 (post-V4)

| 폴더 | 이터레이션 범위 | 비고 |
|------|----------------|------|
| `2026-02-19_12-31-47` | 13,100→13,400 | V4 이어학습, 트롯 미세 조정 |
| `2026-02-19_13-49-17` | 0→600 | 새 시작, 보상 리밸런싱 |
| `2026-02-19_17-10-11` | 0→600 | 보상 재조정 |
| `2026-02-19_18-42-50` | 1,000→900 | 실험 |
| `2026-02-19_19-31-44` | 1,000→900 | 실험 |
| `2026-02-19_20-01-30` | 0→300 | 실험 |
| **`2026-02-19_20-40-30`** | **0→900** | **V8 최종 Flat 모델 (15 checkpoints)** |
| `2026-02-21_00-42-16` | 0→400 | 추가 Flat 실험 |

### V8: Flat→Rough 전이학습 (2026-02-20)

**커밋**: `c96d6d8` — "V8 flat + rough terrain transfer learning"

#### 전이학습 과정
1. **소스 모델**: `spot_micro_flat/2026-02-19_20-40-30/model_900.pt` (48차원 관측)
2. **전이 스크립트**: `scripts/transfer_flat_to_rough.py`
   - Flat 모델의 actor/critic 가중치 중 공통 48차원 부분을 유지
   - height_scan 54차원에 해당하는 가중치는 Xavier 초기화
   - 결과: Rough 모델(102차원) 생성
3. **전이된 체크포인트**: `spot_micro_rough/transferred_from_v8_flat/model_0.pt`

#### 주요 코드 변경 (V8 커밋)
- `SpotMicroRoughEnvCfg` 클래스 신설 (SpotMicroFlatEnvCfg 상속)
- Height scanner 추가 (RayCaster, 0.1m 해상도, 0.8×0.5m 그리드)
- 커리큘럼 활성화 (지형 난이도 점진적 증가)
- 러프 지형 생성기: 6종 (계단, 역계단, 랜덤 박스, 울퉁불퉁, 경사 상/하)
- 스케일: SpotMicro(24cm) 맞춤 — step_height 2~8cm, grid_height 2~6cm
- `PPORoughRunnerCfg` 신설 (entropy_coef=0.005, 탐색 줄임)
- 초기 자세 변경: 쪼그려앉기(0.13m) → **서있기(0.20m)** — leg=-0.5, foot=1.2
- `soft_joint_pos_limit_factor = 0.7` — foot 관절 과접힘 방지

#### Rough 지형 초기 실험 (V8 커밋 직후)

| 폴더 | 이터레이션 | 비고 |
|------|-----------|------|
| `2026-02-20_06-00-57` | 0→300 | 전이 모델 첫 러프 학습 (4 pts) |
| `2026-02-20_06-58-14` | 0→300 | 보상 조정 |
| `2026-02-20_08-54-38` | 300→900 | 이어학습 (7 pts) |
| `2026-02-20_10-47-37~12-38-23` | 500~600 | 보상 미세 조정 반복 (1~2 pts씩) |
| `2026-02-20_13-06-59` | 600→700 | |
| `2026-02-20_13-56-20` | 1,000→900 | 커리큘럼 실험 |
| `2026-02-20_14-58-25~22-39-59` | 1,000→3,500 | 점진적 이어학습 (여러 세션) |

이 시기에 러프 지형에서 서있기는 되지만 걸음걸이가 나오지 않는 문제가 있었음.
앞다리만 움직이고 뒷다리는 바닥에 고정하는 local minimum에 빠짐.

---

## 🚀 Phase 6: 러프 지형 마스터리 (2026-02-21 ~ 현재)

### 개요
러프 지형에서 **뒷다리까지 제대로 움직이는 트롯 걸음걸이**를 학습시키는 과정.
핵심 문제는 뒷다리가 앞다리의 안정적 지지대 역할만 하고 스윙을 안 하는 것.
V9에서 거리/난이도 보상을 추가하고, V10~V12에서 뒷다리 전용 보상 3종을 순차 투입.

### V9: 거리 보상 + 지형 난이도 보상 (2026-02-21)

#### 새로운 보상 함수
- **`terrain_progress_reward`**: 커리큘럼 레벨이 높을수록 보상 → 어려운 지형에서 생존 동기 강화
- **`distance_walked_reward`**: 원점에서 멀리 걸을수록 보상 (target 2.5m) → 커리큘럼 승급 유도

#### V9 학습 체인

| 폴더 | 이터레이션 | 특징 |
|------|-----------|------|
| `2026-02-21_05-36-45` | 0 | 새 시작 (1 pt) |
| **`2026-02-21_05-48-21`** | **0→900** | **핵심 seed 모델 (11 pts)** |
| `2026-02-21_08-08-10` | 0→100 | 실험 |
| `2026-02-21_08-29-55` | 0 | 실험 |
| **`2026-02-21_08-43-40`** | **1,000→9,900** | **V9 장기 학습 (101 pts, ~10K iters)** |

`2026-02-21_05-48-21`에서 900 이터까지 학습한 모델이 러프 지형에서 처음으로
제대로 걸었고, 이것을 seed로 `2026-02-21_08-43-40`에서 10K 이터까지 장기 학습.

이 런이 V9의 핵심 모델이 됨 — 이후 V10~V12 모두 이 체인에서 이어학습.

### V10: rear_alternation 추가 (2026-02-22)

#### 문제
V9 모델이 걷기는 하지만 **뒷다리 두 개가 동시에 바닥에 붙어 있는 시간이 80% 이상**.
앞다리가 교대하면서 뒷다리는 안정적 받침대 역할만 함 → 진정한 4족 트롯이 아님.

#### 해결: `rear_alternation_reward` 신설
- 뒷다리(RL, RR)의 접촉 상태가 다르면(하나는 접지, 하나는 스윙) 보상
- weight = **150.0**
- 전진 게이팅 적용 (서있을 때는 4발 접지 OK)

#### V10 학습 체인

| 폴더 | 이터레이션 | 특징 |
|------|-----------|------|
| **`2026-02-22_13-11-38`** | **11,000→16,500** | **V10 (56 pts, ~5.5K iters)** |

V9의 model_9900에서 이어학습. 뒷다리가 교대하기 시작하지만,
여전히 **토큰 교대 문제** 발생 — 뒷발을 살짝 들었다 내려놓기만 함.

### V11: rear_both_ground 페널티 (2026-02-22~23)

#### 문제
rear_alternation만으로는 뒷다리가 "최소한으로만" 교대함.
살짝 들었다 내려놓으면 보상은 받으면서 실제로는 보폭이 거의 0.

#### 해결: `rear_both_ground_penalty` 신설
- 두 뒷다리가 **동시에 접지**하면 직접 페널티
- rear_alternation의 보완재: 보상(당근) + 페널티(채찍) 동시 적용
- weight = **-200.0**

#### V11 학습 체인

| 폴더 | 이터레이션 | 특징 |
|------|-----------|------|
| **`2026-02-22_23-19-25`** | **16,500→21,200** | **V11 (48 pts, ~4.7K iters)** |

V10의 model_16500에서 이어학습. 뒷다리 동시 접지가 감소하지만
여전히 공중에서 제자리 들기만 하고 전방 보폭이 나오지 않음.

### V12: rear_forward_stride — 핵심 돌파구 (2026-02-23)

**커밋**: `cfd29a1` — "V12: rear_forward_stride reward + weight rebalance for actual rear leg stride"

#### 문제
V10(교대 보상)과 V11(동시접지 페널티)로 뒷다리가 교대는 하지만,
**발을 들어서 앞으로 내딛는 실제 보폭이 전무**. 센서상 접촉/비접촉만 교대하고
실제 이동이 없는 "토큰 교대" 상태.

#### 해결: `rear_forward_stride_reward` 신설
- **높이 × 전방속도** 곱으로 보상
  - 높이 점수: `clamp(rear_height / target_clearance, 0, 1)` (target 6cm)
  - 전방속도 점수: `clamp(rear_fwd_vel / 0.3, 0, 1)`
- 둘 다 있어야 보상이 나옴 → 제자리 들기(높이만 있음)나 바닥 끌기(속도만 있음)는 0점
- weight = **250.0** (전체 보상 중 최대)

#### 추가 변경
- **foot_extension_penalty** 신설: foot 관절이 1.5rad 초과 시 2차 페널티 (weight=-30)
  - 발바닥이 앞을 향하는 비자연스러운 과신전 자세 방지
- **전체 가중치 재밸런싱**: top5 보상 비중을 뒷다리 관련으로 집중

#### V12 학습 체인

| 폴더 | 이터레이션 | 특징 |
|------|-----------|------|
| `2026-02-23_08-56-41` | 21,200→22,200 | V12 초기 (보상 하락→회복) |
| `2026-02-23_10-54-50` | 22,200→24,500 | 이어학습 |
| `2026-02-23_15-05-53` | 24,500→25,300 | 이어학습 |
| `2026-02-23_16-52-22` | 25,300→25,800 | 이어학습 |
| **`2026-02-23_19-41-20`** | **25,800→27,100+** | 🔴 **현재 학습 중 (14+ pts)** |

#### V12 관찰 (iter 27,100 시점)
- terrain_levels: ~2.6 (커리큘럼 승급 진행 중)
- time_out 비율: ~0.90 (에피소드 끝까지 생존)
- rear_forward_stride: ~166 (뒷발의 실제 전방 보폭 신호 증가 중)
- 전체 보상: V12 전환 직후 하락 → 점진적 회복
- 이전 V11 대비 뒷다리 스트라이드가 실제로 나타나기 시작

### 전체 학습 체인 요약 (Flat → Rough)

```
[Flat 지형]
Phase 1~3: 서기 학습 (iter 0 → 22,600)
Phase 4, V1~V4: 트롯 걸음걸이 (iter 22,600 → 13,400)
Phase 5, V5~V8: Flat 최적화 (새 시작 → model_900)
    ↓
  전이학습 (transfer_flat_to_rough.py)
  48차원 → 102차원 (height_scan 54차원 Xavier 초기화)
    ↓
[Rough 지형]
V8 초기: 러프 실험 (iter 0 → 3,500, 여러 세션)
V9: 장기 학습 (iter 0 → 9,900) ← 핵심 seed 모델
V10: rear_alternation (iter 11,000 → 16,500)
V11: rear_both_ground (iter 16,500 → 21,200)
V12: rear_forward_stride (iter 21,200 → 27,100+) ← 현재
```

### 커밋 이력 (전체)

| 날짜 | 해시 | 내용 |
|------|------|------|
| 2026-02-16 21:45 | `3a9dee1` | Initial commit |
| 2026-02-16 23:55 | `ca5d6b1` | Add SpotMicro RL training project |
| 2026-02-17 00:07 | `37310ab` | Add URDF asset to project |
| 2026-02-17 00:24 | `c1eb35c` | Add mesh files, adjust training for stable standing |
| 2026-02-17 01:10 | `34c57c5` | Increase shoulder penalties |
| 2026-02-17 03:47 | `91a42e4` | Revert to successful configuration |
| 2026-02-19 09:58 | `44b46f0` | V4: 엄격한 트롯 걸음걸이 |
| 2026-02-19 10:39 | `fa5903b` | docs: PROJECT_HISTORY.md Phase 4 업데이트 |
| 2026-02-19 12:24 | `f28e6f4` | add joint limits check script |
| 2026-02-20 08:53 | `c96d6d8` | V8: flat + rough terrain transfer learning |
| 2026-02-23 17:55 | `cfd29a1` | V12: rear_forward_stride + weight rebalance || 2026-02-25 22:00 | `0e6b826` | docs: PROJECT_HISTORY.md Phase 5-6 update |

---

### Phase 7: V13~V14b — Critic Reset 발산 3연속 실패 (iter 30,400 → 47,360)

#### 핵심 문제
V12(model_30400)에서 **뒷다리가 바닥에 고정/끌림** 현상 발견. Flat 지형 Play 테스트에서 앞다리만 트로트하고 뒷다리는 미끄러지듯 끌림. V12의 aggressive 뒷다리 보상(rear_forward_stride=250, rear_alternation=150, rear_both_ground=-200)에도 불구하고 local minimum에 빠진 상태.

---

#### V13: Critic Reset + 기존 보상 재학습

**전략**: V12 model_30400에서 critic만 리셋하고 actor는 유지. 새 critic이 기존 보상 구조를 재학습.

**첫 시도** (2026-02-24_08-54-15):
- Critic reset from model_30400 (init_std=0.5)
- Iter 30,501→30,981에서 `action_rate_l2`가 10^15으로 폭발 → 발산

**해결**: `action_rate_l2_clamped()` 함수 신설 (max_value=50.0으로 클램핑)

**두번째 시도** (같은 폴더, 이어학습):
- Critic reset from model_30700 (init_std=0.5)
- Iter ~47,360에서 발산. value_loss → 3.48×10^17
- **원인**: adaptive LR schedule이 noise std를 0.5→1.33으로 끌어올림 → 정책 불안정

**Play 테스트 (model_35000)**: 뒷다리 여전히 끌림. 근본 문제 미해결.

---

#### V14: 접촉 독립 뒷다리 보상 + 고정 LR

**핵심 아이디어**: 접촉 센서에 의존하지 않고 뒷다리 관절 속도를 직접 측정하는 **3가지 새 보상 함수** 도입.

**신규 보상 함수** (rewards.py에 추가):
1. `rear_joint_velocity_reward` — 뒷다리 6개 관절의 절대 속도 합 보상
2. `rear_joint_frozen_penalty` — 관절 속도 합 < threshold이면 페널티 1.0
3. `forward_velocity_rear_gated` — 뒷다리 활동에 비례하는 전진 보상 게이트 **(V14 핵심)**

**PPO 변경**:
- `schedule`: adaptive → **fixed** (noise std 폭발 방지)
- `entropy_coef`: 0.005 유지

**V14 첫 시도** (2026-02-25_16-34-32):
- Critic reset from model_35000 (init_std=0.3)
- 가중치: rear_joint_velocity=200, rear_joint_frozen=-400, rear_both_ground=-800 등
- **5 iteration만에 발산** (35005→35009). value_loss → inf
- 원인: 총 보상 스케일이 fresh critic에 비해 너무 큼

---

#### V14b: 가중치 축소

**변경**: 모든 대형 가중치를 1/3~1/2로 축소
- rear_joint_velocity: 200→60, rear_joint_frozen: -400→-150
- rear_both_ground: -800→-250, same_side_penalty: -250→-120
- LR: 5e-4→1e-4

**V14b 시도** (2026-02-25_17-09-37):
- Critic reset, init_std=0.3
- 초기 5 iter 안정: value_loss=7,652, reward=656, noise_std=0.30
- **Iter ~35,365에서 발산**: value_loss → 7.8×10^18, reward → -1,243

---

#### V13~V14b 실패 분석

| 버전 | 원인 | 발산 이터 |
|------|------|-----------|
| V13-1 | action_rate_l2 폭발 | 30,981 |
| V13-2 | adaptive LR → noise std 1.33 | ~47,360 |
| V14 | 보상 스케일 과대 | 5 iter |
| V14b | 축소해도 critic reset 불안정 | ~35,365 |

**근본 원인**: Critic reset + pre-trained actor = 가치 추정 불일치. 
Fresh critic은 pre-trained actor의 행동 분포에 대한 가치를 전혀 모르고, 
새 보상 구조에서의 실제 리턴과 critic 예측 간 괴리가 기하급수적으로 확대.

---

### Phase 8: V15 — From-Scratch 학습 (2026-02-26~)

#### 전략 전환
3연속 fine-tune 실패 후, **처음부터 뒷다리 보상을 포함해 학습**으로 전환.
- Local minimum 탈출 불필요 (처음부터 뒷다리 보상 학습)
- Critic reset 불안정 없음 (critic이 V14 보상을 처음부터 학습)
- Flat → Rough 전이학습 경로 재사용 (V8에서 검증됨)

#### V15 보상 설계 (SpotMicroFlatEnvCfg)

**기존 Flat 보상 유지** + **V14 뒷다리 보상 추가 (보수적 가중치)**:

| 보상 | 가중치 | 변경 내용 |
|------|--------|----------|
| forward_velocity (rear_gated) | 8.0 | **신규**: 뒷다리 활동 게이팅 전진 (메인) |
| forward_velocity_bootstrap | 3.0 | **신규**: 기존 전진 보상 (초기 학습 보조) |
| rear_joint_velocity | 15.0 | **신규**: 뒷다리 관절 속도 보상 |
| rear_joint_frozen | -30.0 | **신규**: 뒷다리 동결 페널티 |
| rear_alternation | 30.0 | **신규**: 뒷다리 교대 보상 |
| rear_both_ground | -50.0 | **신규**: 뒷다리 동시 접지 페널티 |
| rear_forward_stride | 30.0 | **신규**: 뒷발 전방 보폭 |
| rear_swing | 20.0 | 0→20 (활성화) |
| foot_extension | -30.0 | **신규**: 과신전 페널티 |
| trot_gait | 100.0 | 150→100 (뒷다리 보상에 비중 분배) |
| same_side_penalty | -60.0 | -80→-60 |
| foot_clearance | 35.0 | 50→35 |
| lin_vel_x range | (0.0, 0.3) | (0.0, 0.15)→(0.0, 0.3) 확대 |

#### PPO 설정 (V15 Flat)
```python
learning_rate = 5e-4      # V12: 1e-3 → V15: 5e-4 (안정적)
schedule = "fixed"         # V12: adaptive → V15: fixed (noise std 제어)
max_iterations = 15000     # from-scratch 장기 학습
save_interval = 200        # 세밀한 체크포인트
entropy_coef = 0.01        # 충분한 탐색 (from-scratch)
```

#### V15 학습 경과 (진행 중)
- Iter 78: reward=366, value_loss=182, noise_std=0.64
- **안정적** — V14b 대비 value_loss가 10^18가 아닌 ~182로 안정
- ETA: ~19시간 (15K iter)

#### V15 다음 단계
1. Flat 학습 완료 후 Play 테스트 (뒷다리 활성 여부 확인)
2. `transfer_flat_to_rough.py`로 Rough 전이학습
3. Rough 지형에서 fine-tune

### 전체 학습 체인 요약 (Flat → Rough)

```
[Flat 지형]
Phase 1~3: 서기 학습 (iter 0 → 22,600)
Phase 4, V1~V4: 트롯 걸음걸이 (iter 22,600 → 13,400)
Phase 5, V5~V8: Flat 최적화 (새 시작 → model_900)
    ↓
  전이학습 (transfer_flat_to_rough.py)
  48차원 → 102차원 (height_scan 54차원 Xavier 초기화)
    ↓
[Rough 지형]
V8 초기: 러프 실험 (iter 0 → 3,500, 여러 세션)
V9: 장기 학습 (iter 0 → 9,900) ← 핵심 seed 모델
V10: rear_alternation (iter 11,000 → 16,500)
V11: rear_both_ground (iter 16,500 → 21,200)
V12: rear_forward_stride (iter 21,200 → 30,400) ← 뒷다리 고정 발견
V13: critic reset + 기존 보상 (iter 30,400 → 47,360) ← 발산
V14/V14b: 접촉 독립 보상 + critic reset (iter 35,000 → 35,365) ← 발산
    ↓
  전략 전환: from-scratch
    ↓
[Flat 지형, V15]
V15: from-scratch + V14 뒷다리 보상 (iter 0 → ???) ← 현재 진행 중
  → Flat 완료 후 Rough 전이학습 예정
```

### 커밋 이력 (전체)

| 날짜 | 해시 | 내용 |
|------|------|------|
| 2026-02-16 21:45 | `3a9dee1` | Initial commit |
| 2026-02-16 23:55 | `ca5d6b1` | Add SpotMicro RL training project |
| 2026-02-17 00:07 | `37310ab` | Add URDF asset to project |
| 2026-02-17 00:24 | `c1eb35c` | Add mesh files, adjust training for stable standing |
| 2026-02-17 01:10 | `34c57c5` | Increase shoulder penalties |
| 2026-02-17 03:47 | `91a42e4` | Revert to successful configuration |
| 2026-02-19 09:58 | `44b46f0` | V4: 엄격한 트롯 걸음걸이 |
| 2026-02-19 10:39 | `fa5903b` | docs: PROJECT_HISTORY.md Phase 4 업데이트 |
| 2026-02-19 12:24 | `f28e6f4` | add joint limits check script |
| 2026-02-20 08:53 | `c96d6d8` | V8: flat + rough terrain transfer learning |
| 2026-02-23 17:55 | `cfd29a1` | V12: rear_forward_stride + weight rebalance |
| 2026-02-25 22:00 | `0e6b826` | docs: PROJECT_HISTORY.md Phase 5-6 update |
| 2026-02-26 10:10 | — | V15: from-scratch + V14 rear-leg rewards (pending) |
