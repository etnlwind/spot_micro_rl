# SpotMicro RL — Quadruped Locomotion with Reinforcement Learning

강화학습(PPO)으로 **SpotMicro 4족 로봇**이 **trot 걸음걸이**(대각 교대보행)로 걷도록 훈련하는 프로젝트.

## Overview

NVIDIA Isaac Lab 위에서 24,576개 병렬 환경으로 SpotMicro 로봇을 훈련합니다. Isaac Lab extension template 패턴을 따르며, Gymnasium 환경으로 등록되어 있습니다.

**현재 상태**: V34 (rel_standing_envs 기반 3-Phase 커리큘럼: 서기→걷기) 훈련 준비

### 기술 스택

| 항목 | 값 |
|------|-----|
| Isaac Lab | v2.3.0 |
| Isaac Sim | 5.1.0.0 |
| Python | 3.10 (conda env `env_isaaclab`) |
| 알고리즘 | PPO ([RSL-RL](https://github.com/leggedrobotics/rsl_rl)) |
| GPU | NVIDIA RTX 5080 Laptop 16GB |
| 병렬 환경 수 | 20,480 |
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
│   │   │   ├── rewards.py              # 커스텀 리워드 함수 50+ 개
│   │   │   └── __init__.py             # MDP 모듈 re-export
│   │   └── agents/
│   │       └── rsl_rl_ppo_cfg.py       # PPO 하이퍼파라미터
│   └── robots/
│       └── spot_micro.py               # URDF articulation, DC motor 설정
├── isaac_ops/                          # ★ 독립 운영 패키지 (IsaacOps)
│   ├── common.py                       # Telegram, process, state, report/video helper, KPI 분석
│   ├── listener.py                     # 통합 Telegram listener (supervisor + heartbeat)
│   ├── cli_send.py                     # CLI에서 명령 실행 / 메시지 전송
│   ├── listen.cmd                      # Windows 런처 (listener)
│   └── cli.cmd                         # Windows 런처 (CLI)
├── scripts/
│   ├── rsl_rl/
│   │   ├── train.py                    # 훈련 entry point
│   │   └── play.py                     # 평가/비디오 entry point (카메라 preset, contact CSV 지원)
│   ├── common.py                       # scripts용 common (isaac_ops/common.py와 동기화)
│   ├── utils/
│   │   ├── evaluate_limb_gate_checkpoint.py  # checkpoint 단위 limb validity 수동 평가
│   │   └── analyze_training.py         # limb validity 열 추출, collapse 감지, workbook 기록
│   └── legacy/                         # 구 supervisor/heartbeat 코드 참고용 보관
├── plan/
│   ├── HANDOFF.md                      # AI 세션 핸드오프 (최신 상태 요약)
│   ├── QUADRUPED_RL_RESEARCH.md        # 4족 보행 RL 연구 조사 (legged_gym, Walk These Ways, AllGaits)
│   ├── V*_ANALYSIS.md / V*_PLAN.md    # 버전별 분석/계획 문서
│   └── archive/                        # 이전 상태 문서 보관
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

5. `.env` 생성:
    ```bash
    # PowerShell
    Copy-Item .env.example .env

    # bash/zsh
    cp .env.example .env
    ```

6. `.env` 보안 설정:
    ```env
    TELEGRAM_TOKEN=<bot token>
    TELEGRAM_CHAT_ID=<allowed chat id>
    TELEGRAM_ALLOWED_USER_IDS=<comma-separated user ids>
    TELEGRAM_VERBOSE_ERRORS=0
    ```
    `.env`는 직접 수정하지 말고 항상 `.env.example`을 복사해서 생성합니다.
    `TELEGRAM_ALLOWED_USER_IDS`를 설정하면 지정한 사용자만 `start/stop/report` 같은 명령을 실행할 수 있습니다. 설정하지 않으면 private chat에서 `chat_id == user_id`인 경우만 명령을 허용합니다.
    `TELEGRAM_VERBOSE_ERRORS=1`로 두면 `status`에 `last_error`를 표시하고, supervisor 예외 상세 문자열도 텔레그램으로 전송합니다. 기본값 `0`은 상세 에러를 서버 로그에만 남깁니다.

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
- `VIDEO_LENGTH`: report/video 생성 시 녹화 길이. 초가 아니라 simulation step 기준
- `VIDEO_FPS`: report/video ZIP에 넣기 전 재인코딩 fps. 낮출수록 같은 step 수라도 더 천천히 재생됨
- `VIDEO_CAPTURE_HEADLESS`: supervisor 리포트/멀티뷰 생성 시 `--headless` 사용 여부 (기본 1)
- `VIDEO_CAPTURE_FALLBACK_GUI`: headless 결과가 실패/중복이면 GUI 모드로 1회 재시도 (기본 1)
- `VIDEO_REQUIRE_DISTINCT_VIEWS`: 뷰별 영상 해시가 중복되면 실패 처리 (기본 1)
- `REPORT_REQUIRE_XLSX`: report ZIP에 `metrics/heartbeat_history.xlsx`를 반드시 포함 (기본 1)

### 모니터링 — IsaacOps

`isaac_ops/`는 Telegram 기반 훈련 모니터링 통합 패키지입니다. 기존 `supervisor.py` + `heartbeat.py`를 하나의 listener로 통합했습니다.

```bash
# IsaacOps listener 시작 (Telegram 명령 + 100 iter heartbeat + 자동 영상 리포트)
isaac_ops\listen.cmd

# CLI에서 직접 명령 실행
isaac_ops\cli.cmd status       # 훈련 상태 조회 → Telegram 전송
isaac_ops\cli.cmd hb           # heartbeat 리포트 → Telegram 전송
isaac_ops\cli.cmd stop         # 훈련 중지
isaac_ops\cli.cmd start        # 새 훈련 시작
isaac_ops\cli.cmd resume       # 이어서 훈련
isaac_ops\cli.cmd "메시지"     # 일반 텍스트 → Telegram 전송

# TensorBoard
python -m tensorboard.main --logdir=logs/rsl_rl/spot_micro_flat --port=6006
```

**IsaacOps 특징**:
- **통합 listener**: supervisor(Telegram 명령) + heartbeat(KPI 모니터링) + 자동 영상 리포트를 단일 프로세스로 처리
- **CLI 도구**: `cli.cmd`로 터미널에서 직접 명령 실행 (Telegram을 거치지 않음)
- **self-contained**: `isaac_ops/` 폴더만으로 독립 동작 가능, 다른 프로젝트에 재사용 가능
- **heartbeat 리포트**: raw metric 중심으로 간소화, 자동 판정은 iter 500 이후부터만 활성화

**Telegram 명령** (listener가 실행 중일 때):
- `start` / `stop` / `resume` — 훈련 제어
- `status` — 현재 상태 조회
- `report` / `front` / `rear` / `top` / `side` — 영상 리포트
- `help` — 명령 목록

### 현재 운영 기준

- 학습 버전: `V34` (rel_standing_envs 기반 3-Phase Stand→Walk 커리큘럼)
- active 운영: `isaac_ops/listener.py`, `isaac_ops/common.py`, `isaac_ops/cli_send.py`
- 접촉 해석 기본값: `toe_link`
- 참고 문서: `plan/V34_PLAN.md` (현재), `plan/HANDOFF.md`, `plan/QUADRUPED_RL_RESEARCH.md`

---

## Reward Design

### V34 Stand→Walk 커리큘럼 (현재)

Isaac Lab 내장 `rel_standing_envs` + command range 커리큘럼으로 **서기→걷기** 3-Phase 전환:

| 구간 | Iteration 범위 | 내용 |
|------|----------------|------|
| Phase 1 (STAND) | 0 ~ 200 | 80% env standing, 극저속 command, 자세 안정화 |
| Phase 2 (TRANSITION) | 200 ~ 500 | standing 비율/command range/reward weight 선형 ramp |
| Phase 3 (WALK) | 500+ | 10% standing, 본격 보행, 전체 reward 활성 |

**핵심 메커니즘**:
- `rel_standing_envs=0.8`: standing env에 command=0 자동 할당 (Isaac Lab 내장)
- `track_lin_vel_xy_exp=1.5` 처음부터 ON → standing env에서 "0 추적 성공" = 서기 보상
- Command range: (0.01, 0.15) → (0.1, 0.5) 점진 확대

### V34 Reward Architecture

V33 근본 재설계(122→28개) 기반, ~28개 핵심 보상:

**자세 제어** (처음부터 활성): `shoulder_neutral(-15)`, `joint_deviation(-1)`, `standing_height(+15)`, `base_height_l2(-15)`, `flat_orientation_l2(-5)`

**Gait 패턴** (4발 공통, 처음부터 활성): `feet_air_time(+20)`, `trot_gait(+40)`, `same_side_penalty(-30)`, `diagonal_coupling(+25)`

**전진/보행** (Phase 2 커리큘럼): `forward_velocity(0→5)`, `stationary_penalty(0→-3)`, `min_swing_ratio(0→-15)`, `rear_both_ground(0→-60)`

**Rear 부팅 신호** (처음부터 활성): `rear_joint_frozen(-60)`, `rear_joint_velocity(+10)`, `rear_alternation(+15)`

### 리워드 함수 패턴

```python
def my_reward(env: ManagerBasedRLEnv, asset_cfg: SceneEntityCfg, ...) -> torch.Tensor:
    """Per-environment scalar reward."""
    asset: Articulation = env.scene[asset_cfg.name]
    # ... compute reward
    return tensor  # shape: (num_envs,)
```

주요 리워드 카테고리:
- **양수**: `standing_height`, `forward_velocity`, `trot_gait`, `diagonal_joint_coupling`, `leg_lift`, `foot_clearance`, `stance_propulsion`, `rear_joint_velocity`, `rear_alternation`, `rear_forward_stride`
- **음수**: `undesired_contacts`, `feet_below_knees`, `dof_acc_l2`, `action_rate_l2`, `flat_orientation_l2`, `rear_joint_frozen`, `same_side_penalty`, `limb_usage_min_penalty`, `rear_left_right_usage_diff_penalty`

운영 해석 원칙:
- 운동학 KPI 우선 확인 (joint velocity 기반)
- flat 환경 contact 기준: `toe_link` 우선
- limb validity 4단계: observe(~500) → early_warning(500~800) → lock_warning(800~1200) → enforce(1200+)

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
| **V20** | **03-08~** | **Soft-ramp 선형 보간 커리큘럼** | ✅ 완료 |
| **V21** | **03-10~** | **gait-quality-first 모니터링, iter cadence supervisor, toe contact 진단** | ✅ 완료 |
| **V22** | **03-11~** | **멀티뷰 비디오 패키지, heartbeat workbook, ZIP artifact, top/front view 정리** | ✅ 완료 |
| **V23** | **03-12~** | **posture-first refinement, rear joint velocity 강화** | ✅ 완료 |
| **V24** | **03-13~** | **Limb Validity Gating: rear-left collapse 차단, 좌우 비대칭 페널티, 자동 영상 리포트** | ✅ 완료 |
| **V25** | **03-14~03-15** | **rear_left_contact_floor_penalty -60 직접 처방 (RL 회복, RR collapse 이동)** | ❌ 실패 (iter 400) |
| **V26.1** | **03-15** | **Symmetric Existence Floor + Load Sharing: 모든 다리 동일 기준, collapse 이동 차단** | ✅ 완료 |
| **V27** | **03-16** | **contact residency EMA + prop/usage band: 점진적 접촉 분포 유도** | ❌ 실패 (iter 1000 RL collapse) |
| **V28** | **03-16** | **V27 재기동 + 하이퍼파라미터 조정** | ❌ 실패 (RR collapse) |
| **V28.2** | **03-16** | **rear pair 대칭 강제 (rear_pair_contact_diff_penalty)** | ✅ 성공 (iter 1703 rear_usage_diff=0.012) |
| **V28.3** | **03-17** | **front contact cap(-10.0) 추가** | ❌ 실패 (FL/FR contact 0.83~0.88 고착) |
| **V29** | **03-17** | **Residency band_high=0.65 + stride_length + swing_gate_velocity** | ✅ 완료 |
| **V30** | **03-17** | **Symmetric init pose + supervisor reliability** | ✅ 완료 (FL/FR lock-in 미해결) |
| **V31** | **03-18** | **Front swing enforcement (mirror rear rewards)** | ❌ 실패 (역할 분리 유발) |
| **V31.1** | **03-18** | **front_both_ground + min_swing_ratio** | ❌ 실패 (역할 분리) |
| **V31.2** | **03-18** | **Joint-level front activation (front_joint_velocity/frozen)** | ✅ 완료 |
| **V32** | **03-18~03-19** | **feet_air_time core transition + rear bias reduction** | ✅ 완료 |
| **V33** | **03-19** | **근본 재설계 (122→28개, anti-splay, 4발 공통)** | ❌ 실패 (붕괴) |
| **V33.1** | **03-19** | **standing_height 강화** | ❌ 실패 (동일 붕괴) |
| **V33.2** | **03-19** | **rear 절반 복구 (부팅 신호)** | ❌ 실패 (3발 exploit) |
| **V33.3** | **03-19** | **per-limb penalty (min_swing, limb_usage, validity)** | ❌ 실패 (학습 억제) |
| **V34** | **03-19~** | **rel_standing_envs 기반 3-Phase Stand→Walk 커리큘럼** | 🔄 훈련 준비 |

### 핵심 교훈

- 접촉 센서 리워드는 미세 진동으로 속일 수 있음 → 키네마틱(joint velocity) 기반 권장
- 35개 리워드 동시 활성화 → "정지 함정" (페널티 합 > 보상 합)
- Hard phase switch → critic shock (value_loss 445x spike) → soft ramp 필요
- PPO 안정성은 `gamma × reward_scale`에 좌우됨 (gamma 0.99→0.97로 해결)
- Critic reset + fine-tune은 큰 리워드 변경에 부적합 → from-scratch 권장
- 곱셈 리워드 `(A × B)`로 "둘 다 해야" 조건 표현 가능
- **다리별 전용 보상(front_*, rear_*)은 역할 분리를 유발** → 4발 공통 보상(feet_air_time)이 더 안전
- **보상 50개+는 항목 간 상호작용 예측 불가** → 성공한 프레임워크는 15~20개 수준
- **Gait 패턴은 "발견"보다 "지시"가 안정적** → phase clock 또는 CPG 구조적 강제가 효과적
- **서기도 못 하는데 보행+전진 동시 요구는 불가** → 단계적 학습(서기→걷기) 필요
- **reward weight=0으로 Phase 분리하면 관측-보상 불일치** → Isaac Lab `rel_standing_envs` 사용이 정석

---

## Analysis

```bash
# V19 분석 (hard switch 문제 진단)
python scripts/analyze_v19.py

# V20 분석 (soft-ramp 효과 검증, iter 1500+ 권장)
python scripts/analyze_v20.py
```

분석/운영 문서:
- `plan/HANDOFF.md` — AI 세션 핸드오프 (최신 상태 요약)
- `plan/QUADRUPED_RL_RESEARCH.md` — 4족 보행 RL 연구 조사 (legged_gym, Walk These Ways, AllGaits 비교)
- `plan/V*_ANALYSIS.md` / `plan/V*_PLAN.md` — 버전별 분석/계획
- `plan/V01-V08_HISTORY.md` ~ `plan/V18_HISTORY.md` — 버전별 히스토리

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
