# V68 PLAN: Reference Trajectory Tracking (성공)

> **한 줄 요약**: V63.I 실제 policy의 rollout 궤적을 녹화·좌우 대칭화해 reference trajectory로 삼고, RL이 이 궤적을 추적하게 만들어 **대칭 1.5%p + stride 4.40 + timeout 100% + GUI 긍정** 판정을 동시에 달성한 버전. V1~V67의 reward engineering 한계를 **policy trajectory mining**으로 돌파한 버전이며, 2026-04-12 기준 프로젝트의 최종 성공 checkpoint (`checkpoints/V68_model_2500_best.pt`)를 생성했다.

---

## 1. 배경과 문제 정의

### 1.1 V1~V67의 누적 실패 패턴

V63부터 V67까지 **10개 이상의 reward 구조**를 반복 실험하며 밝혀진 근본 문제는 다음과 같다.

| 버전 | 시도 | 결과 |
|------|------|------|
| V63.B~J | trot 유도 10+ 변형 | V63.I가 보행 품질 최고 (stride 4.35) — **대각 편향 12.6%p 잔존** |
| V64 | mirror symmetry augmentation (`RslRlSymmetryCfg`) | phase clock과 data augmentation 충돌, phantom 데이터, 학습 붕괴 |
| V65 | `true_trot → alternation` curriculum ramp | 부팅 전 curriculum 개입 → 서기 자체 실패 |
| V66 | per-env phase randomization | 초기 2000 iter 대칭 2~6%p (부분 성공), iter 2500+에서 true_trot exploit 재발견 |
| V67 | `balanced_true_trot = intra × inter × balance_factor` | **대칭 2.7%p** 역대 최고, 그러나 stride 2.23 (V63.I의 51%), GUI drift/slip |

V63~V67에서 반복적으로 확인된 **두 개의 축**:

1. **보행 품질 축 (stride, propulsion, GUI 자연스러움)** — V63.I에서 정점
2. **대칭성 축 (contact ratio L/R, propulsion L/R)** — V67에서 정점

두 축은 **항상 tradeoff 관계**였다. 한쪽을 올리면 반대쪽이 무너졌다.

### 1.2 `true_trot_pattern`의 구조적 결함

V63~V66 공통 주연 reward였던 `true_trot_pattern`은 실제로는 **특정 순간의 diagonal contact**를 보상한다. 즉 "FL+RR 동시 접지 → 다음 순간 FR+RL 동시 접지"라는 **시간축 교대**를 측정하지 않고, "지금 이 순간 대각이 맞는가"만 측정한다. 그래서 "FL+RR만 계속 접지, FR+RL은 공중에 띄운 채 frozen"인 비정상 자세가 **만점 reward**를 받는 frozen diagonal exploit이 자주 발생했다.

V67에서는 이를 `intra × inter × balance_factor`로 분해·완화했지만, **contact 대칭은 보행 품질 대칭이 아니었다**. 네 다리 접지 비율은 맞췄지만 실제 propulsion/stride가 무너졌다.

### 1.3 전환점 — "발견하게 하지 말고, 따라가게 하자"

V1~V67의 공통 전제는 **"적절한 reward를 설계하면 RL이 좋은 gait를 발견할 것이다"** 였다. 이 전제 자체가 한계였다.

> **V68의 핵심 아이디어**:
> 이미 V63.I가 **보행 품질 최고의 policy**를 학습했다. 단지 그 policy가 **L/R 편향**을 갖고 있을 뿐이다.
> 그렇다면 그 policy의 **rollout 궤적을 녹화한 뒤 대칭화**하면, **동역학적으로 유효하면서 좌우 대칭인 reference trajectory**를 얻을 수 있다.
> 그리고 RL은 이 reference를 **따라가도록** 학습시키면 된다.

이것이 V68의 전체 접근이다. 전통적 imitation learning과의 차이점:

- **Open-loop IK sweep 아님**: 단순 역기구학으로 다리 끝 경로를 생성하면 물리적 추진이 되지 않는다 (V68 이전에 실패 확인, `scripts/sweep_ideal_trot.py`에서 vel=-0.15 역방향 이동 확인)
- **외부 dataset 아님**: 별도 로봇이나 시뮬 궤적을 쓰지 않고, **자기 자신의 이전 policy**가 생성한 궤적을 쓴다
- **대칭화 후처리가 핵심**: 원본 V63.I policy의 편향을 수동 대칭화로 제거한다

---

## 2. 접근 단계별 상세

### Step 1 — V63.I Rollout 녹화

스크립트: `scripts/record_v63i_trajectory.py`

- 대상 policy: V63.I `model_4999.pt`
- 환경: Isaac-Velocity-Flat-SpotMicro-v0, 16 envs
- 길이: 1000 steps × 20 ms = **20초**
- 저장 변수:
  - `joint_pos`, `joint_vel` (12 DoF)
  - `action` (policy 출력)
  - `root_lin_vel_w`, `root_ang_vel_w`
  - `toe_pos_w` (4개 발끝 월드 좌표)
- 검증: `vx = 0.38 m/s` 안정 전진 확인, lateral drift 최소

이 단계에서는 **V63.I가 학습한 실제 dynamics-valid trajectory**를 디스크로 덤프하는 것만 한다.

### Step 2 — 궤적 분석과 주기 탐지

스크립트: `scripts/analyze_trajectory.py`

- FFT / autocorrelation으로 **주파수 탐지**: **2.0071 Hz** (25 steps/cycle)
- 1 cycle 추출 후 phase-normalized (0~1)
- L/R bias 정량화:
  - front leg bias: FL이 FR보다 +0.18 (앞쪽으로 치우침)
  - shoulder bias: FL/FR mean magnitude mismatch
- 총 L/R 비대칭 지표: 1.83 (raw)

### Step 3 — 좌우 대칭화

- **다리 역할 쌍**: FL/RR ↔ FR/RL (대각)
- 각 phase `t`에 대해:
  - `joint_sym[FL, t] = mean( joint[FL, t], joint[FR, t+0.5] )` (반대 다리 + phase shift)
  - shoulder는 magnitude 평균 후 좌우 부호 재적용
- 결과:
  - L/R 비대칭 **1.83 → 0.18** (**89.9% 감소**)
  - Phase 연속성 보존 (25 step cycle 유지)
- 저장 파일: **`logs/ideal_trot_reference.json`** (7.1 KB)
  - `joint_names`: 12개 joint 이름
  - `frequency_hz`: 2.0071138211382116
  - `cycle_steps`: 25
  - `dt`: 0.02
  - `phase_normalized_joint_pos`: (25, 12) 대칭화 후 궤적
  - `original_joint_pos`: (25, 12) 원본 V63.I 궤적 (비교용)

### Step 4 — Reference Tracking Reward 구현

파일: `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py:4391`

```python
def reference_trot_tracking_reward(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    frequency: float = 2.0,
    sigma: float = 1.5,
    ref_path: str = "logs/ideal_trot_reference.json",
) -> torch.Tensor:
    # --- Lazy load reference (첫 호출에만 disk 읽기) ---
    if not hasattr(env, "_v68_ref_loaded"):
        ref_jp = torch.tensor(json.load(open(ref_file))['phase_normalized_joint_pos'],
                              device=..., dtype=torch.float32)  # (25, 12)
        env._v68_ref_jp = ref_jp
        env._v68_ref_cycle = 25
        env._v68_ref_loaded = True

    # --- 현재 phase (V66+ per-env offset 반영) ---
    t = env.episode_length_buf.float() * env.step_dt
    base_phase = frequency * t
    if getattr(env, "_v66_phase_random_enabled", False):
        offset = _get_phase_offset(env)  # per-env random 0~2π
        base_phase = base_phase + offset / (2.0 * math.pi)
    phase_frac = base_phase % 1.0
    phase_idx = phase_frac * env._v68_ref_cycle

    # --- Linear interpolation 사이의 두 샘플 ---
    idx_low = phase_idx.long() % env._v68_ref_cycle
    idx_high = (idx_low + 1) % env._v68_ref_cycle
    frac = (phase_idx % 1.0).unsqueeze(-1)
    ref_target = env._v68_ref_jp[idx_low] + frac * (
        env._v68_ref_jp[idx_high] - env._v68_ref_jp[idx_low]
    )  # (N_envs, 12)

    # --- L1 error → exp(-err/sigma) ---
    err = (robot.data.joint_pos - ref_target).abs().sum(dim=-1)  # (N_envs,)
    reward = torch.exp(-err / sigma)
    return reward
```

핵심 설계 결정:

- **exp(-L1/sigma)**: L2 대신 L1 사용 → outlier joint에 덜 민감, sigma=1.5는 12 joint 전체 합산 기준 "평균 0.125 rad 이하이면 reward > 0.9"
- **Linear interpolation**: 25-step discrete reference를 연속 phase로 매핑 → 끊김 없음
- **V66+ phase randomization과 호환**: per-env random phase offset을 reference에도 적용 → 초기 대칭 효과 그대로 유지
- **Lazy load**: 훈련 시작 시 한 번만 디스크 접근, 이후 GPU tensor로 상주

---

## 3. V68 Reward 구조 전체

env config: `source/.../spot_micro_rl_env_cfg.py:6259` (`_IS_V68` 블록)

| Reward | Weight | 역할 | 비고 |
|--------|--------|------|------|
| **`ref_tracking`** | **+10.0** | **주연** — 대칭화 reference 궤적 추적 | V68 신설 |
| `true_trot_pattern` | +2.0 | 보조 — intra-pair sync 유지 | V63.I 재사용 (강도 낮춤) |
| `swing_body_forward` | +4.0 | 보조 — 전진 방향 body 이동 | V63.I 유지 |
| `effective_stride` | +5.0 | 보조 — 보폭 확보 | V63.I 유지 |
| `per_leg_contact_min` | −8.0 | 방어 — 다리 미사용 exploit 차단 | V63.I 유지 |
| `shoulder_neutral` | −4.0 | 방어 — 어깨 벌림(splay) 억제 | V63.I 유지 |
| `leg_lr_symmetry` | −2.0 | 방어 — 보조 대칭 안전장치 | V63.I 유지 |
| `anti_pace` | −3.0 | 방어 — pace(같은 쪽 동시 swing) 억제 | V67.1 −4 → 원상 복구 |
| `action_rate_l2` | −0.10 | 안정 — 부드러움 | 표준 |
| `+ phase randomization` | — | 초기화 — per-env 0~2π random offset | V66.1 유지 |
| **제거** | | |
| `alternation_trot` | **삭제** | V60~V63 유산 | ref_tracking이 대체 |
| `per_leg_role_variance` | **삭제** | V63 유산 | |
| `diagonal_pair_balance` | **삭제** | V63~V66 유산 | |
| `per_leg_contact_exp` | **삭제** | V66 유산 | |
| `stance_slip` | **삭제** | 초기 exploit 대응용 | 불필요 |
| `lateral_vel` | **삭제** | | |
| V65 `curriculum.reward_weights` | **전체 해제** | | |

Reward budget 대략 (per-step, 성공 정상 phase 기준):

- 주연 ref_tracking: `10.0 × exp(-0.3 / 1.5) ≈ 10.0 × 0.82 ≈ 8.2`
- 보조 합산 (trot+fwd+stride): `≈ 2~4`
- 방어 penalty 합산 (정상 보행): `≈ -1 ~ -2`
- **순 per-step reward**: **+9 ~ +12** → alive 보장, die-fast 불가능

이 budget 계산은 `feedback_penalty_alive_check` (per-step net reward 부호 검증) 원칙에 따라 설계 단계에서 검증되었다.

---

## 4. 훈련 설정

| 항목 | 값 |
|------|------|
| Run 이름 | `2026-04-12_12-26-08_V68` |
| Task | `Isaac-Velocity-Flat-SpotMicro-v0` |
| num_envs | 4096 |
| MAX_ITER | 5000 |
| dt | 0.02 s (50 Hz control) |
| episode length | 2000 steps (40초) |
| URDF | 실물 기준 질량, `merge_fixed_joints=False` |
| Actuator | ImplicitActuator (stiffness=20, damping=0.5) |
| Observation | 48-dim (표준 flat locomotion) |
| Action | 12-dim (joint position target) |
| Policy arch | rsl_rl MLP |
| Checkpoint 주기 | 매 100 iter |
| 커맨드 | `resume.cmd` 변형으로 from-scratch (not resume) |
| 훈련 시간 | 전체 5000 iter ≈ 4.5 시간 (RTX 5080) |

---

## 5. 결과

### 5.1 주요 지표 (iter 2500, 최적 구간)

| 지표 | V63.I | V67 | **V68 (iter 2500)** | V68 개선폭 |
|------|------|------|------|------|
| 대각 대칭 diff | 12.6 %p | 2.7 %p | **1.5 %p** | V63.I 대비 **8.4배 개선** |
| effective stride | 4.35 | 2.23 | **4.40** | V63.I 동등+, V67 대비 2배 |
| timeout (episode 완주) | 99.95 % | 98.9 % | **100.0 %** | |
| mean reward | 386 | 226 | **475** | V63.I 대비 +23% |
| GUI 판정 | FR/RR 이상 | drift/slip | **"보행 좋아 보인다"** | **V63~V68 시리즈 첫 긍정 판정** |

### 5.2 학습 추이 (iter별)

```
iter  550:  대칭 1.7%p, stride 3.58   (부팅 완료, 궤적 추적 시작)
iter  962:  대칭 2.3%p, stride 4.39   (V63.I stride 초과)
iter 1412:  대칭 2.0%p, stride 4.42   (안정 구간 진입)
iter 2000:  대칭 1.6%p, stride 4.40
iter 2236:  대칭 1.2%p, stride 4.38   (역대 최저 diff)
iter 2500:  대칭 1.5%p, stride 4.40   ← ★ BEST CHECKPOINT
iter 3000:  대칭 4.5%p, stride 4.35   (미세 상승 시작)
iter 3372:  대칭 9.8%p, stride 4.41
iter 4014:  대칭 12.7%p, stride 1.55  (후반 편향 재발 + stride 붕괴)
iter 4999:  완주 체크포인트 (최적 아님)
```

- **부팅 완료**: iter 500 부근 (ref_tracking이 충분히 학습됨)
- **최적 구간**: iter 2000~2700 (대칭 1~2%p + stride 4.4 안정)
- **후반 편향 재발**: iter 3500+ 에서 reward가 국소 최적으로 빠지며 편향 재출현
- **결론**: 완주(5000)가 아니라 **iter 2500이 최적**

### 5.3 GUI 정성 판정

- **model_2500**: 사용자 육안 판정 "보행 좋아 보인다" — V63~V68 시리즈 **첫 긍정 판정**
- V63.I model_2000과 병렬 비교:
  - V63.I: "FR/RR 이상, 몸 세우기 경향"
  - V68: "대칭 + stride + 자연스러움 동시"

### 5.4 Best Checkpoint 정량 리포트 (40초 rollout, 2000 steps, 77 gait cycles)

| 항목 | 값 | 판정 |
|------|------|------|
| Forward speed | 0.308 m/s | ✅ |
| Lateral drift | 0.003 m/s (forward의 1%) | ✅ 직진 |
| Body height | 0.240 m ±0.005 | ✅ 안정 |
| Roll rate std | 0.155 rad/s | ✅ |
| Pitch rate std | 0.264 rad/s | ✅ |
| Yaw rate std | 0.092 rad/s | ✅ |
| Cost of Transport | 6.97 | 기준값 (후속 버전 비교 기준) |
| L/R joint asymmetry | 0.338 | ✅ |
| Gait frequency | 2.00 Hz | ✅ 설계값 일치 |
| GUI 판정 | "보행 좋아 보인다" | ✅ |

---

## 6. 왜 V68이 성공했는가

### 6.1 Open-loop IK sweep 실패 → Policy trajectory mining

V68 이전에 이미 시도된 접근:

- **Open-loop IK**: foot trajectory를 수학적으로 정의 → joint space로 역기구학 변환 → reference로 사용
- **결과 실패**: 물리 시뮬에서 vel=-0.15 역방향 이동 (`scripts/sweep_ideal_trot.py` 실측)
- **원인**: IK 기반 궤적은 **정적 관점 최적**이지만, 접촉 시 push-off 타이밍과 발끝 속도 방향을 고려하지 않음 → 실제 추진력이 생기지 않음

V68의 차이:

- V63.I policy는 이미 **실제 dynamics에서 전진 가능한 궤적**을 학습했음
- 이 궤적은 정의상 **접촉 타이밍, push-off, 발끝 속도 방향**이 물리적으로 유효함
- 편향만 제거하면 즉시 사용 가능한 reference가 됨

### 6.2 V63.I의 장점만 추출

| 차원 | V63.I 원본 | V68 대칭화 후 | 획득 |
|------|------|------|------|
| 추진 역학 | ✅ (stride 4.35) | ✅ 그대로 보존 | V63.I의 핵심 자산 |
| 보행 품질 | ✅ | ✅ | |
| L/R 대칭 | ❌ (12.6%p) | ✅ (1.5%p) | **8.4배 개선** |

즉 V68은 **V63.I policy가 학습한 dynamics 지식 + 대칭화 후처리 = 새로운 reference**라는 구조를 만들었다.

### 6.3 Phase randomization 병행

V66.1에서 검증된 per-env random phase offset을 V68에서도 유지했다. 이유:

- 학습 초반 모든 env가 같은 phase에서 시작하면 gradient가 **초기 gait pattern에 편향**됨
- per-env random offset이면 네트워크가 **phase-invariant feature**를 먼저 학습하게 됨
- ref_tracking과 phase randomization은 독립적으로 결합 가능 (reward 수식에 offset 반영)

### 6.4 Reference tracking의 자체 최적화 효과

단순 imitation이 아닌 **"추적하면서 RL이 자체 최적화"** 구조다.

- reference는 V63.I 원본이므로 100% 완벽하지 않음 (CoT, 안정성 개선 여지 있음)
- RL은 reference 근처에서 움직이되, 나머지 보조 reward(swing_body_forward, effective_stride)가 "reference를 약간 벗어나더라도 더 좋은 gait"로 유도
- 결과적으로 **V68 > V63.I** (mean reward 475 vs 386)

---

## 7. Best Checkpoint 보존

### 7.1 왜 별도 보존이 필요한가

V68 훈련은 iter 3500+ 에서 편향이 재발하므로, **원본 run 디렉토리의 `model_4999.pt`는 사용 불가**다. 따라서 **중간 체크포인트 명시적 보존**이 필수다.

### 7.2 보존 방식

저장소 커밋: `252e981` "V68 best checkpoint 보존 + README/plan/README 업데이트"

- **경로**: `checkpoints/V68_model_2500_best.pt`
- **원본**: `logs/rsl_rl/spot_micro_flat/2026-04-12_12-26-08_V68/model_2500.pt`
- **크기**: 4,682,677 B (≈4.47 MB)
- **포맷**: rsl_rl PPO checkpoint
- **Reference 파일**: `logs/ideal_trot_reference.json` (7.1 KB)도 함께 커밋
- **Run 디렉토리 보존**: 원본 run 폴더 전체는 로컬에만 있음 (tfevents, 모든 iter 체크포인트). 저장소 용량 고려해 best 한 개만 커밋

### 7.3 재생 / resume

```cmd
:: 원본 run 경로에서 재생
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt

:: best 보존본을 원본 위치로 복구 후 재생
copy checkpoints\V68_model_2500_best.pt logs\rsl_rl\spot_micro_flat\2026-04-12_12-26-08_V68\model_2500.pt
play.cmd 2026-04-12_12-26-08_V68 model_2500.pt

:: resume 훈련 (V69.A 예시)
resume.cmd 2026-04-12_12-26-08_V68 model_2500.pt 5000 V69.A
```

---

## 8. 한계와 후속 과제

### 8.1 한계

1. **후반 편향 재발**: iter 3500+ 에서 대칭이 12.7%p로 회귀. 원인 미확정 (reference가 고정이므로 RL이 다른 local optimum을 재발견하는 것으로 추정)
2. **단일 속도 reference**: reference가 `vx ≈ 0.38 m/s` 고정 → 다른 명령 속도에서는 정확도 저하
3. **Flat terrain only**: height scanner 없이 평지 학습
4. **Domain randomization 미적용**: mass, friction, push 등 실물 편차 대응 부족
5. **Sim-to-real 미검증**: 실기체 배치 검증 단계 진입 전
6. **중간 체크포인트 선택이 수동**: 자동으로 best iter를 판정하는 체계 없음

### 8.2 후속 과제 (V69 이후)

| 과제 | 접근 | 기대 효과 |
|------|------|------|
| **Domain randomization** | mass ±20%, friction ±30%, external push | 실물 편차 흡수 |
| **Rough terrain** | heightfield / stair / random bumps | 지형 일반화 |
| **Height scanner** | observation 확장 (48 → 48 + scan) | 장애물 인식 |
| **Multi-speed reference** | 여러 속도 reference 병합 또는 interpolation | 명령 속도 추종 범위 확대 |
| **Sim-to-real** | 실기체 전개 (STS3215 서보, 실제 IMU) | 최종 배치 |
| **자동 best checkpoint 판정** | eval metric 기반 자동 저장 | 운영 자동화 |

### 8.3 후반 편향 재발 해결 후보

- **Reference update**: 학습 중간에 현재 policy의 궤적을 다시 대칭화해 reference 교체 (self-refinement)
- **Curriculum schedule**: ref_tracking weight를 iter에 따라 감쇠 (초반 강한 추적 → 후반 자율성)
- **Entropy bonus**: 후반 entropy 증가 방지를 위한 schedule 조정
- **Early stopping**: iter 2700 근처에서 자동 종료

---

## 9. 핵심 교훈

### 9.1 V68이 남긴 결정적 교훈

> **"RL이 발견하게"가 아니라 "검증된 궤적을 따라가게"가 정답이었다.**

- V1~V67은 "좋은 reward만 설계하면 RL이 좋은 gait를 발견할 것이다"를 전제로 했다
- 이 전제는 **충분조건이 아니었다**. Reward 하나를 막을 때마다 exploit은 새 path를 찾았다
- V68은 전제를 뒤집었다: **"이미 작동하는 policy에서 궤적을 뽑아내고, 대칭화 후처리로 결함만 제거한 뒤, RL이 그걸 따라가게 한다"**
- 이 접근은 **단순 imitation이 아니다**. RL이 reference 근처에서 보조 reward로 자체 최적화하기 때문이다

### 9.2 기술적 교훈

1. **Open-loop IK는 동역학을 모른다** → policy trajectory mining이 우위
2. **편향된 policy도 자산이다** → 대칭화 후처리로 구제 가능
3. **"최적 = 완주"가 아니다** → 중간 체크포인트 보존 필수
4. **Reference는 외부 데이터가 아니어도 된다** → 자기 policy rollout으로 충분
5. **Phase randomization은 reference tracking과 직교** → 함께 써도 충돌 없음
6. **V63.I의 12.6%p 편향은 policy의 결함이 아니라, gradient가 특정 초기 조건에 민감했기 때문** → reference + random phase로 동시 해결

### 9.3 방법론 교훈

- **"Reward를 더 추가하는 것"은 한계가 있다** — exploit은 항상 새 길을 찾는다
- **`true_trot_pattern`은 frozen diagonal을 보상한다** — 시간축 교대를 측정하지 않음
- **대칭은 reward가 아닌 구조로 해결해야 한다** — phase randomization + reference tracking
- **이미 작동하는 policy에서 reference를 추출**하면 동역학적으로 유효한 궤적을 얻을 수 있다
- **시뮬레이터를 적극 활용**하면 설계→검증→수정 사이클을 빠르게 돌릴 수 있다

---

## 10. 연결된 파일과 문서

### 10.1 코드
- `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py:4391` — `reference_trot_tracking_reward` 구현
- `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py:6259` — `_IS_V68` config 블록
- `scripts/record_v63i_trajectory.py` — rollout 녹화
- `scripts/analyze_trajectory.py` — 주기/대칭 분석
- `scripts/sweep_ideal_trot.py` — Open-loop IK 실패 실험 (V68 이전)

### 10.2 데이터
- **`checkpoints/V68_model_2500_best.pt`** — best checkpoint (4.47 MB)
- **`logs/ideal_trot_reference.json`** — 대칭화된 reference trajectory (7.1 KB)
- `logs/rsl_rl/spot_micro_flat/2026-04-12_12-26-08_V68/` — 전체 훈련 run (로컬)

### 10.3 관련 문서
- `plan/V63_PLAN.md` — V63 시리즈 (V64~V67 교훈 포함), Appendix J에 V64~V68 히스토리
- `plan/V66_PLAN.md` — phase randomization
- `plan/V67_PLAN.md` — balance-gated true_trot 실패
- `plan/README.md` — 전체 흐름 요약 (13기)
- `README.md` (루트) — Best Checkpoint 섹션에 .pt 파일 상세

---

## 11. V68 요약 한 문장

> **V68은 V1~V67의 reward engineering 한계를 policy trajectory mining으로 돌파한 버전이며, V63.I의 실제 rollout을 녹화·좌우 대칭화해 reference로 삼는 tracking reward(w=10)로 대칭 1.5%p + stride 4.40 + timeout 100% + GUI 긍정 판정을 iter 2500에서 동시에 달성했고, 그 결과물은 `checkpoints/V68_model_2500_best.pt`에 보존되어 이 프로젝트의 첫 deployable 보행 checkpoint가 되었다.**
