# SpotMicro RL — Quadruped Locomotion with Reinforcement Learning

강화학습(PPO)으로 **SpotMicro 4족 로봇**이 **trot 걸음걸이**(대각 교대보행)로 걷도록 훈련하는 프로젝트.

## Overview

NVIDIA Isaac Lab 위에서 병렬 환경으로 SpotMicro 로봇을 훈련합니다. V41 이하는 20,480개, V42 이후는 8,192개 환경을 사용합니다. Isaac Lab extension template 패턴을 따르며, Gymnasium 환경으로 등록되어 있습니다.

**현재 상태**: V47 훈련 중 (iter 5860). V38.3 순정(77 reward) + boot_standing/boot_contact만 추가. stride 6.29, coupling 0.46, shoulder 0.43 — V38.3 수준 재현 + shoulder 개선 + boot 2배 가속 달성. 한 달간 V42~V46에서 "reward 수를 줄이면 정답"이 아니라 "어떤 reward가 있는가가 핵심"이라는 결론에 도달.

### 기술 스택

| 항목 | 값 |
|------|-----|
| Isaac Lab | v2.3.0 |
| Isaac Sim | 5.1.0.0 |
| Python | 3.10 (conda env `env_isaaclab`) |
| 알고리즘 | PPO ([RSL-RL](https://github.com/leggedrobotics/rsl_rl)) |
| GPU | NVIDIA RTX 5080 Laptop 16GB |
| 병렬 환경 수 | 8,192 (V42+), 20,480 (V41 이하) |
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
- **영상 리포트 사용자 확인**: 영상 리포트 생성 전 Telegram으로 확인 요청 (훈련 중지 방지)
- **자동 run 감지**: CLI에서 새 훈련을 시작해도 listener가 자동으로 새 run/버전 인식
- **Note**: 구 `scripts/supervisor.py` + `scripts/heartbeat.py`는 `scripts/legacy/`로 이동됨. 현재는 `isaac_ops/listen.cmd`만 사용

**Telegram 명령** (listener가 실행 중일 때):
- `start` / `stop` / `resume` — 훈련 제어
- `status` — 현재 상태 조회
- `report` / `front` / `rear` / `top` / `side` — 영상 리포트
- `help` — 명령 목록

### 현재 운영 기준

- 학습 버전: `V47` 훈련 중 (V38.3 순정 + boot 가속)
- active 운영: `isaac_ops/listener.py`, `isaac_ops/common.py`, `isaac_ops/cli_send.py`
- 접촉 해석 기본값: `toe_link`
- 기능 플래그: `_CLEAN_REWARDS=False`, `_CONNECTED_TROT=False` (V47은 V38.3 구조 사용)
- 병렬 환경: 20,480 (V38.3 원래 값 복원)
- 참고 문서: `plan/V47_PLAN.md` (현재), `plan/HANDOFF.md`
- **주의**: listen.cmd는 Windows 터미널에서만 직접 실행 (WSL 금지)

---

## Reward Design

### V38.3 Soft CaT (현재 최종)

V37.2에서 L2 penalty의 구조적 한계 확인 후, **CaT → Soft CaT**로 발전:
- L2 penalty는 reward 채널 — agent가 다른 양의 보상으로 상쇄 가능
- CaT는 **discount factor 채널** — terminated=True면 미래 보상=0, 상쇄 불가
- **Soft CaT** (V38.2+): 종료 확률이 dev에 비례 → phase transition 제거

```
prob(dev) = base_prob × clamp((max_dev - threshold) / margin, 0, 1)
```

| 구간 | Iteration 범위 | 내용 |
|------|----------------|------|
| Boot Phase | 0 ~ 300 | alive_bonus(+10/step), undesired_contacts -20→-100 ramp, 저속 command |
| Velocity Restore | 0 ~ 500 | lin_vel_x (0.01,0.05) → (0.1,0.5) 선형 복원 |
| Splay L2 (고정) | 500+ | shoulder -6.0 고정 |
| **Soft CaT Ramp** | **800 ~ 3000** | **probability 0→0.0015 ramp (threshold 0.3, margin 0.3 고정)** |
| STAND→WALK Ramp | 1500 ~ 3000 | V32.1 soft-ramp 커리큘럼 |
| WALK→TROT Ramp | 5500 ~ 8000 | 전체 gait 보상 활성 |

**Soft CaT 결과** (V38.3): shoulder dev 0.54→0.45 (-16%), 0.45에서 local optimum 정체.

### V47 (현재)

V38.3 순정(77 reward) + boot_standing(+15) + boot_contact(+5)만 추가. "작동하는 시스템을 고치지 말고, 부족한 것만 더하자." V46에서 reward를 선별 복원하는 접근이 실패한 후, V38.3 전체를 살리고 boot만 가속하는 최소 변경 전략. 상세: `plan/V47_PLAN.md`

**부팅 안정화** (V35.5 검증 완료):
- `alive_bonus=10.0`: 매 step 생존 보상
- `undesired_contacts` 초기 완화: -100→-20 (iter 0~300 ramp)
- 초기 저속 command: (0.01, 0.05) → 서기 안정화 우선

**Anti-Shuffle** (V36 검증 완료):
- `stride_length` ramp 200~500, max 15.0
- `feet_air_time` threshold 0.25 (0.3에서 하향)
- `swing_stride` weight 4.0 (2.0에서 강화)

### Reward Architecture (V38.3)

V32.1 보상 구조 기반 + multi-layer 커리큘럼 + Soft CaT:

**부팅 안정화**: `alive_bonus(+10.0)`

**자세 제어**: `standing_height(+10)`, `base_height_l2(-15)`, `flat_orientation_l2(-7)`, `shoulder_neutral(-6.0)`, `stance_width(-3.0)`

**Soft CaT**: `shoulder_splay` DoneTerm — dev에 비례한 확률적 에피소드 종료 (prob 0.0015)

**Gait 패턴**: `feet_air_time(+20)`, `diagonal_coupling(+25)`, `gait_cycle_period(+15)`, `trot_gait(+15)`

**전진/보행**: `forward_velocity(+8)`, `stance_propulsion(+8)`, `rear_joint_velocity(+12)`, `stride_length(+15 ramp)`, `swing_stride(+4)`

**Multi-layer 커리큘럼**: boot_ramp → stride_ramp → **Soft CaT ramp** → STAND→WALK → WALK→TROT

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
| **V34** | **03-19** | **rel_standing_envs 기반 3-Phase Stand→Walk 커리큘럼** | ❌ 실패 (V33 기반) |
| **V35~V35.2** | **03-19~03-20** | **V32.1 복원 시도, anti-splay/anti-shuffle 수정** | ❌ 실패 (이모지 crash + 재현성 문제 발견) |
| **V35.3~V35.4** | **03-20** | **alive_bonus 도입 (2.0→10.0)** | ❌ 부분 효과 (부팅 불완전) |
| **V35.5** | **03-20** | **부팅 안정화 3가지 결합 (alive+contacts완화+저속)** | ✅ 부팅 성공 (iter 400 ep_len=234) |
| **V36** | **03-20** | **V35.5 + anti-splay(-6,-3,0.23) + anti-shuffle(stride ramp, swing_stride)** | 🟡 anti-shuffle 성공(stride +34%), anti-splay 실패(shoulder 0.54 고착) |
| **V37** | **03-20** | **Anti-splay 커리큘럼: shoulder -6→-15, stance -3→-8, height 0.23→0.22** | ❌ 실패 (iter 600에서 보행 붕괴, 리스크#1 적중) |
| **V37.2** | **03-20** | **V37 완화: shoulder만 -6→-10, ramp 500~1500, stance/height 변경 없음** | 🟡 L2 한계 확인 (splay 0.532, 행동 변화 없음) |
| **V38** | **03-21** | **CaT (Constraints as Terminations): shoulder splay → 확률적 종료** | ❌ 실패 (threshold 0.6 너무 타이트, iter 600 즉시 붕괴) |
| **V38.1** | **03-21** | **V38 완화: threshold 0.8→0.45, prob 0.03→0.15** | ❌ 실패 (phase transition, splay 57%) |
| **V38.2** | **03-21~03-22** | **Soft CaT: prob ∝ dev, phase transition 제거** | 🟡 안정적이나 prob 0.0004 너무 약함 (shoulder dev 0.52 정체) |
| **V38.3** | **03-22~03-23** | **Soft CaT prob 0.0015 (3.75x)** | 🟡 shoulder dev 0.54→0.45 (-16%, 역대 최대), 0.45 local optimum |
| **V38.3.1** | **03-23** | **CaT + L2 병행 (resume + weight -12)** | ❌ 실패 (critic 무효화 + curriculum 미복원) |
| **V39** | **03-23~03-24** | **CPG/Phase Clock + reward shape 실험** | 🟡 shape 교훈 획득, stride -39% 악화 |
| **V40-A** | **03-24** | **CaT prob 0.003 단일 변수 실험** | 🟡 0.45→0.384 달성, ep_len 170 (천장 확인) |
| **V41** | **03-24** | **Narrow-stance bootstrap 설계** | 미구현 (V42로 전환) |
| **V42** | **03-25** | **Clean Reward Restart: 50→16개, 8192 envs** | 설계 완료, exploit 발견 → V43 |
| **V43** | **03-25** | **15개 connected reward (per-leg propulsion gating)** | ❌ boot 실패 (ep_len=8, walking reward 충돌) |
| **V43-B** | **03-25** | **propulsion gate를 boot에서 OFF** | ❌ boot 실패 (gating ≠ 원인) |
| **V43-C** | **03-25** | **joint_default_pose -2.0→-0.3** | ❌ boot 실패 (pose ≠ 원인) |
| **V43-D** | **03-25** | **Walking reward boot gating (5-Phase 순차 활성화)** | 🟡 ep_len 10(+20%), fwd_vel 7x↑, positive 부족 |
| **V43-E** | **03-25** | **boot_standing + boot_foot_contact (V41 bootstrap 적용)** | ✅ **boot 성공 (ep_len 248, shoulder 0.40 역대 최고)**, stride 0.39 |
| **V44** | **03-26** | **diagonal_coupling 복원 + pose -0.5 + adaptive safety** | 🟡 stride 1.3~2.4↑, shoulder 0.53↑ (trade-off), coupling 0.0 |
| **V45** | **03-26** | **shoulder-leg 분리 + pair coupling + leg_lift** | 미구현 (V46으로 전략 전환) |
| **V46-A** | **03-26** | **V43-E + V38.3 gait reward 8개 추가** | 🟡 stride 1.45 (pose penalty 한계) |
| **V46-B** | **03-26** | **Run A + shoulder-leg 분리 (shoulder_neutral)** | 🟡 shoulder 0.44, stride 1.29 (여전히 부족) |
| **V47** | **03-26~** | **V38.3 순정(77 reward) + boot_standing + boot_contact** | ✅ **stride 6.29, coupling 0.46, shoulder 0.43 — V38.3 재현 + 개선** |

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
- **재현성 먼저 확인**: "성공한 버전"이라도 재현성 검증 필수 (V32.1은 25% 성공률)
- **alive_bonus는 locomotion RL의 기본**: 매 step 생존 보상이 없으면 초기 탐색 실패 시 local minimum에 갇힘
- **초기 harsh penalty는 탐색을 억제**: undesired_contacts=-100은 "시도하지 않는 게 최선"이라는 잘못된 학습 유도
- **Windows cp949 인코딩 주의**: print 문의 이모지(⏸🔄✅)가 UnicodeEncodeError로 훈련 crash 유발
- **penalty가 전체 reward의 1% 미만이면 무시됨**: V36에서 shoulder=-6.0이 reward 180 대비 0.6% → 행동 변경 없음. 5~10% 이상 필요
- **커리큘럼 적층이 안전**: boot_ramp → splay_ramp → stride_ramp를 순차 적용하면 각 단계가 안정된 후 다음 단계 시작
- **Barrier 함수, CaT(제약→종료) 등 최신 기법이 weight 커리큘럼보다 깔끔할 수 있음** (QUADRUPED_RL_RESEARCH.md 참조)
- **CaT threshold는 실측 dev에 충분한 여유 필요**: V38에서 dev 0.54 대비 threshold 0.6으로 즉시 붕괴. 초기 threshold는 실측의 1.5배 이상 권장
- **CaT probability는 극히 낮게 시작**: 0.1도 과도. 0.03~0.05에서 시작하여 점진 강화
- **DoneTerm은 매 step 호출**: probability 설계 시 `(1-p)^ep_len`으로 에피소드 생존율 역산 필수
- **Soft CaT는 phase transition 없이 안정적**: threshold 고정 + prob만 ramp → dev에 비례한 연속 압력
- **CaT에도 local optimum 한계**: 벌칙만으로는 0.45 이하 불가, positive incentive + 구조적 gait 유도 필요
- **resume 중 reward weight 변경 금지**: critic 무효화로 기존 성과 소실 (교훈 #4 재확인)
- **Isaac Lab resume은 curriculum 미복원**: CaT ramp 등 curriculum은 iter 0부터 재시작됨
- **walking reward가 boot에서 충돌**: feet_air_time(+20) "발 들어"가 alive_bonus(+10) "서있어"와 50:50 충돌 → boot gating 필수 (V43-D)
- **boot에 positive signal 필수**: reward를 끄는 것과 대체하는 것은 다름. penalty만 남으면 "빨리 죽는 게 이득" (V43-E)
- **net reward 부호가 학습 방향 결정**: net negative면 ep_len 감소가 최적해 (V43-D 분석)
- **reward 수를 줄이는 것 ≠ 정답**: 15개 clean → splay 해결(0.40) but 보행 부족(stride 0.39). 50개에서 stride 6.94. 핵심은 "어떤 reward" (V42~V44)
- **joint_default_pose는 shoulder와 leg를 분리해야 함**: 12개 관절 동일 penalty → stride↔splay trade-off (V44)
- **output=0 reward는 weight를 올려도 0**: coupling reward 1500+ iter 무효 (V44, 교훈#1 재확인)
- **구체적 보행 신호 없이 RL은 가장 쉬운 방법(종종걸음)을 찾음**: leg_lift, rear_alternation 등 필요 (V43-E vs V38.3)
- **reward 설계 시 phase별 상호작용/충돌 분석 필수**: 개별 reward는 합리적이어도 동시 작동 시 충돌 가능 (V43 boot 실패)
- **제거한 reward가 핵심 동력일 수 있음**: band/residency +37.56이 stride 6.79의 유력 동력. "복잡한 상호작용"으로 제거했지만 동시에 gait를 만드는 reward (V46-A/B)
- **작동하는 시스템을 고치지 말 것**: V38.3은 stride 6.79가 검증됨. 부족한 것(boot)만 더하는 V47이 정답 (V47)
- **listen.cmd는 Windows에서만 직접 실행**: WSL에서 실행 시 파일 핸들 잠금 발생, 리스너 재시작 불가

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
