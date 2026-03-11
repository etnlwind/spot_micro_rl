# SpotMicro RL — Quadruped Locomotion with Reinforcement Learning

강화학습(PPO)으로 **SpotMicro 4족 로봇**이 **trot 걸음걸이**(대각 교대보행)로 걷도록 훈련하는 프로젝트.

## Overview

NVIDIA Isaac Lab 위에서 24,576개 병렬 환경으로 SpotMicro 로봇을 훈련합니다. Isaac Lab extension template 패턴을 따르며, Gymnasium 환경으로 등록되어 있습니다.

**현재 상태**: V20 학습 커리큘럼 + V22 운영/아티팩트 체계, V23 준비 중

### 기술 스택

| 항목 | 값 |
|------|-----|
| Isaac Lab | v2.3.0 |
| Isaac Sim | 5.1.0.0 |
| Python | 3.10 (conda env `env_isaaclab`) |
| 알고리즘 | PPO ([RSL-RL](https://github.com/leggedrobotics/rsl_rl)) |
| GPU | NVIDIA RTX 5080 Laptop 16GB |
| 병렬 환경 수 | 24,576 |
| 최대 iteration | 15,000 |

### 등록된 환경

| 환경 ID | 용도 |
|---------|------|
| `Isaac-Velocity-Flat-SpotMicro-v0` | Flat 지형 학습 (주요) |
| `Isaac-Velocity-Rough-SpotMicro-v0` | Rough 지형 학습 |
| `Isaac-Velocity-Rough-SpotMicro-Play-v0` | Rough 지형 평가 |
| `Isaac-Velocity-Flat-SteepSlope-SpotMicro-Play-v0` | 급경사 지형 평가 |

---

## Project Structure

```
spot_micro_rl/
├── source/spot_micro_rl/spot_micro_rl/
│   ├── tasks/manager_based/spot_micro_rl/
│   │   ├── spot_micro_rl_env_cfg.py    # 환경 설정, 리워드 가중치, 커리큘럼
│   │   ├── __init__.py                 # Gymnasium 환경 등록 (4개)
│   │   ├── mdp/
│   │   │   ├── rewards.py              # 커스텀 리워드 함수 25+ 개
│   │   │   └── __init__.py             # MDP 모듈 re-export
│   │   └── agents/
│   │       └── rsl_rl_ppo_cfg.py       # PPO 하이퍼파라미터
│   └── robots/
│       └── spot_micro.py               # URDF articulation, DC motor 설정
├── scripts/
│   ├── rsl_rl/
│   │   ├── train.py                    # 훈련 entry point
│   │   └── play.py                     # 평가/비디오 entry point (카메라 preset, contact CSV 지원)
│   ├── training_supervisor.py          # iter milestone 기반 비디오 관리 + Telegram
│   ├── training_heartbeat.py           # gait-quality-first KPI 모니터링 + Telegram
│   ├── milestone_monitor.py            # V20 ramp milestone 자동 스냅샷/리포트
│   ├── collect_checkpoint_diagnostics.py    # foot/toe/aggregate contact 진단 패키지
│   ├── make_multiview_screenshot_pack.py    # 멀티뷰 스크린샷 ZIP 생성
│   ├── analyze_v19.py                  # V19 훈련 분석 스크립트
│   ├── analyze_v20.py                  # V20 훈련 분석 스크립트
│   └── transfer_flat_to_rough.py       # Flat→Rough 전이학습 (48→102 obs dim)
├── plan/
│   ├── MEMORY.md                       # AI 세션 핸드오프 문서
│   ├── V19_ANALYSIS.md                 # V19 분석 리포트
│   ├── V20_ANALYSIS.md                 # V20 분석 리포트
│   ├── V21_ANALYSIS.md                 # V21 운영/관측 체계 리포트
│   ├── V22_ANALYSIS.md                 # V22 멀티뷰/워크북/ZIP 아티팩트 리포트
│   ├── V23_PLAN.md                     # V23 준비 문서
│   └── V01-V08_HISTORY.md ~ V18_HISTORY.md  # 버전별 히스토리
├── assets/robots/spot_micro/           # SpotMicro URDF
├── logs/rsl_rl/spot_micro_flat/        # 훈련 로그 + 체크포인트
└── .env                                # Telegram 인증, 경로 설정
```

---

## Installation

1. [Isaac Lab v2.3.0 설치](https://isaac-sim.github.io/IsaacLab/main/source/setup/installation/index.html) (conda 권장)

2. 프로젝트 클론 (Isaac Lab 디렉토리 외부):
    ```bash
    git clone https://github.com/etnlwind/spot_micro_rl.git
    cd spot_micro_rl
    git checkout develop
    ```

3. 패키지 설치 (editable mode):
    ```bash
    conda activate env_isaaclab
    pip install -e source/spot_micro_rl
    ```

4. 환경 확인:
    ```bash
    # Windows
    C:\IsaacLab\isaaclab.bat -p scripts/list_envs.py

    # Linux
    ~/.local/share/ov/pkg/isaac-lab/isaaclab.sh -p scripts/list_envs.py
    ```

---

## Training

```bash
conda activate env_isaaclab
cd D:\project\spot_micro_rl

# 훈련 시작 (headless, 24,576 envs)
C:\IsaacLab\isaaclab.bat -p scripts/rsl_rl/train.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 \
  --num_envs=24576 --headless --max_iterations=15000

# 체크포인트에서 재개
C:\IsaacLab\isaaclab.bat -p scripts/rsl_rl/train.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 \
  --num_envs=24576 --headless --max_iterations=15000 \
  --resume --load_run=<TIMESTAMP>

# 예시: model_9600.pt 기준 재개
C:\IsaacLab\isaaclab.bat -p scripts/rsl_rl/train.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 \
  --num_envs=24576 --headless --max_iterations=15000 \
  --resume --load_run=2026-03-10_07-43-51 --checkpoint=model_9600.pt
```

### 평가 (Play)

```bash
C:\IsaacLab\isaaclab.bat -p scripts/rsl_rl/play.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=50 \
  --checkpoint=logs/rsl_rl/spot_micro_flat/<TIMESTAMP>/model_15000.pt

# 단일 로봇 멀티뷰/접촉 CSV 예시
C:\IsaacLab\isaaclab.bat -p scripts/rsl_rl/play.py \
  --task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=1 \
  --checkpoint=logs/rsl_rl/spot_micro_flat/<TIMESTAMP>/model_15000.pt \
  --video --video_length=120 --camera_view=rear \
  --save_contact_csv --contact_primary_mode=toe --headless
```

주요 play 옵션:
- `--camera_view`: `overview`, `side`, `front`, `rear`, `top`, `top_oblique`
- `--camera_zoom`: 단일 로봇 근접 촬영 거리 조정
- `--save_contact_csv`: LF/RF/LR/RR 접촉 상태와 force CSV 저장
- `--contact_primary_mode`: `foot`, `toe`, `aggregate`

### 모니터링

```bash
# TensorBoard
python -m tensorboard.main --logdir=logs/rsl_rl/spot_micro_flat_current --port=6006

# Heartbeat (gait-quality-first KPI를 100 iter마다 Telegram 리포트)
python scripts/training_heartbeat.py --iter_step 100 --poll 30

# Supervisor (iter milestone/판정 악화 시 비디오 녹화 → 분석 → Telegram)
python scripts/training_supervisor.py
```

### Heartbeat / Supervisor 역할 분담

- `training_heartbeat.py`: TensorBoard 기반 상태 감시, `standing_height`, `forward_velocity`, `diagonal_coupling`, `trot_gait`, `rear_joint_velocity`, `foot_clearance`를 우선 KPI로 판정
- `training_supervisor.py`: 훈련 일시중단, 멀티뷰 재생, 분석, Telegram 비디오 전송, 사용자 의사결정 처리
- supervisor 정기 cadence:
  - 초기 500 iter
  - 중기 1000 iter
  - 후기 1500 iter
  - verdict 악화 시 urgent clip 허용

### 현재 운영 기준

- 학습 버전: `V20`
- 운영/아티팩트 버전: `V22`
- 다음 준비 버전: `V23`
- 접촉 해석 기본값: `toe_link`
- 참고 문서: `plan/V21_ANALYSIS.md`
- 참고 문서: `plan/V22_ANALYSIS.md`
- 준비 문서: `plan/V23_PLAN.md`

---

## Reward Design

### V20: Soft-Ramp Curriculum (학습 버전)

하드 phase switch 대신 **선형 보간**으로 가중치를 점진적으로 전환:

| 전환 | Iteration 범위 | 내용 |
|------|----------------|------|
| Phase 1 (STAND) | 0 ~ 1,500 | 서기 안정화, 약한 페널티 |
| Ramp 1→2 | 1,500 ~ 3,000 | STAND→WALK 선형 보간 |
| Phase 2 (WALK) | 3,000 ~ 5,500 | 전진 보행, gait 도입 |
| Ramp 2→3 | 5,500 ~ 8,000 | WALK→TROT 선형 보간 |
| Phase 3 (TROT) | 8,000 ~ 15,000 | trot gait 완성 |

**안전장치**: ep_len < 200이면 ramp 일시 정지 (metric gating)

### 리워드 함수 패턴

```python
def my_reward(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg, ...) -> torch.Tensor:
    """Per-environment scalar reward."""
    asset: Articulation = env.scene[asset_cfg.name]
    # ... compute reward
    return tensor  # shape: (num_envs,)
```

주요 리워드 (25+ 개):
- **양수**: `standing_height`, `forward_velocity`, `trot_gait`, `diagonal_coupling`, `leg_lift`, `foot_clearance`, `stance_propulsion`
- **음수**: `undesired_contacts`, `feet_below_knees`, `joint_vel_l2`, `dof_acc_l2`, `action_rate_l2`, `flat_orientation_l2`
- **고정**: `leg_lift`, `rear_forward_stride` (phase 불변)

V21 이후 운영 해석 원칙:
- 운동학 KPI를 우선 확인
- `stride_length`, `gait_cycle_period` 같은 접촉 이벤트 메트릭은 참고 계층으로 사용
- flat 환경 contact 기준은 `foot_link`보다 `toe_link`를 우선 사용

### PPO 하이퍼파라미터

| 파라미터 | 값 |
|---------|-----|
| gamma | 0.97 |
| clip_param | 0.1 |
| learning_rate | 1e-4 (fixed) |
| epochs | 3 |
| mini_batches | 4 |
| network | [512, 256, 128] ELU |
| num_steps_per_env | 48 |

---

## Version History

| 버전 | 기간 | 핵심 내용 | 결과 |
|------|------|----------|------|
| V1~V8 | 02-17~02-19 | Flat 기본기 (서기→걷기, decimation 조정) | V8 = Flat 베이스라인 |
| V9~V12 | 02-20~02-23 | Rough 지형 도전, 뒷다리 끌림 문제 | 접촉 센서 리워드 한계 발견 |
| V13~V14 | 02-24~02-25 | Critic reset 시도 | 3연속 발산 → from-scratch 전환 |
| V15d | 02-26 | gamma=0.97, clip=0.1 PPO 안정화 | reward 559, value_loss 0.53 |
| V16 | 02-27~03-03 | Diagonal coupling (키네마틱 trot) | 접촉→관절속도 기반 전환 |
| V17.1 | 03-04~03-05 | Action rate + gait cycle + stride | ❌ 정지 함정 (35개 리워드 과부하) |
| V18~V18.3 | 03-06~03-07 | 3-Phase 커리큘럼 (hard switch) | Phase 2 데드락 → V19로 개선 |
| V19 | 03-08 | Phase 가중치 튜닝, hard switch | ❌ critic shock (value_loss 1000) |
| **V20** | **03-08~** | **Soft-ramp 선형 보간 커리큘럼** | 🔄 학습 운영 중 |
| **V21** | **03-10~** | **gait-quality-first 모니터링, iter cadence supervisor, toe contact 진단** | ✅ 운영 반영 |
| **V22** | **03-11~** | **멀티뷰 비디오 패키지, heartbeat workbook, ZIP artifact, top/front view 정리** | ✅ 검증 완료 |

### 핵심 교훈

- 접촉 센서 리워드는 미세 진동으로 속일 수 있음 → 키네마틱(joint velocity) 기반 권장
- 35개 리워드 동시 활성화 → "정지 함정" (페널티 합 > 보상 합)
- Hard phase switch → critic shock (value_loss 445x spike) → soft ramp 필요
- PPO 안정성은 `gamma × reward_scale`에 좌우됨 (gamma 0.99→0.97로 해결)
- Critic reset + fine-tune은 큰 리워드 변경에 부적합 → from-scratch 권장
- 곱셈 리워드 `(A × B)`로 "둘 다 해야" 조건 표현 가능

---

## Analysis

```bash
# V19 분석 (hard switch 문제 진단)
python scripts/analyze_v19.py

# V20 분석 (soft-ramp 효과 검증, iter 1500+ 권장)
python scripts/analyze_v20.py
```

분석/운영 문서:
- `plan/V19_ANALYSIS.md`
- `plan/V20_ANALYSIS.md`
- `plan/V21_ANALYSIS.md`
- `plan/V22_ANALYSIS.md`
- `plan/V23_PLAN.md`

---

## Robot Configuration

- **URDF**: `assets/robots/spot_micro/spotmicroai_realistic_inertia.urdf`
- **Joints**: 12개 (3 per leg × 4 legs) — `{front|rear}_{left|right}_{shoulder|leg|foot}`
- **Actuator**: DC Motor
- **Body ordering**: FL(0) / FR(1) / RL(2) / RR(3)
- **Base**: `base_link` (180° yaw via `base_rotate`)

---

## IDE Setup (Optional)

VSCode에서 `Ctrl+Shift+P` → `Tasks: Run Task` → `setup_python_env` 실행.
Isaac Sim 절대 경로 입력 시 `.vscode/.python.env` 자동 생성.

### Pylance 설정

```json
{
    "python.analysis.extraPaths": [
        "<path-to-project>/source/spot_micro_rl"
    ]
}
```