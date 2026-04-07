# V61 실험 보고서: Phase Clock Locomotion — From Scratch

> 작성: 2026-04-07
> 현재 코드 truth 기준 버전: `V61`
> 기반: V60.A~M 교훈 + phase clock observation

---

## 배경: 왜 V61이 필요한가

V60에서 13개 sub-version(A~M)을 거치며 약 35,000 iter를 소비했다.
그 과정에서 확인된 것은 명확하다:

1. **생존과 전진은 쉽다** — V60.A에서 1000 iter 만에 ep_len 1000 달성
2. **4발 swing도 만들 수 있다** — V60.G에서 4발 균형 swing 달성
3. **하지만 trot(대각선 교대)은 reward만으로 자연 발생하지 않는다**
4. **exploit을 하나씩 막으면 새 exploit이 생긴다** — 13버전 동안 반복

즉 V60의 핵심 결론은:

> **Policy가 "지금 어느 다리를 들어야 하는지"를 스스로 발명하지 못한다.**
> **시간 구조(phase)를 environment가 직접 제공해야 한다.**

V60.I에서 reward 내부에서만 phase를 계산했을 때 pde 0.86을 달성한 것이 이 가설을 지지한다.
하지만 policy가 phase를 직접 "볼" 수 없었기 때문에 대각선 교대까지는 도달하지 못했다.

따라서 V61은 **phase clock을 observation에 직접 넣고, from-scratch로 처음부터 학습**한다.

---

## V60에서 배운 핵심 교훈 13가지

V61의 모든 설계 결정은 아래 교훈에 기반한다.

| # | 교훈 | 발견 버전 | V61 반영 |
|---|------|----------|---------|
| 1 | feet_air_time이 1발만 들어도 보상 → 1발 exploit | V60.A | feet_air_time weight 낮춤 (+2), phase_contact가 주연 |
| 2 | penalty -3은 양수 15 대비 부족, -5~-10 필요 | V60.B→C | per_leg penalty -5로 설정 |
| 3 | curriculum 파일이 resume 시 env_cfg를 덮어씀 | V59.D | from-scratch라 해당 없음 |
| 4 | 서기→보행 resume 전환 비효율 | V59.D | from-scratch |
| 5 | 전역 gait incentive는 이미 움직이는 쪽만 강화 | V60.D | phase_contact가 4발 모두에 위상별 보상 |
| 6 | 한쪽 pair 전용 보상은 반대쪽 고착 유발 | V60.D/F | pair 전용 보상 없음 |
| 7 | 정적 접지 해는 lin_vel_x min 상향으로 깨짐 | V60.F | 초기엔 vel 0부터, phase_contact가 자연 유도 |
| 8 | balance penalty만으로는 교대 미발생 | V60.G | phase_contact + phase_clock obs로 대체 |
| 9 | standing_height/joint_default 복원은 자세 과교정 | V60.K | 둘 다 0 (넣지 않음) |
| 10 | non_toe_contact는 penalty보다 termination이 확실 | V60.K~M | termination으로 구현 |
| 11 | pair-lock은 penalty로 안 끊김, termination 필요 | V60.L~M | termination으로 구현 |
| 12 | reward가 많을수록 exploit 상호작용이 복잡 | V60.A~M | 10개로 최소화 |
| 13 | phase를 obs에 안 넣으면 policy가 타이밍을 발명 못 함 | V60.G~I | phase_clock obs 8차원 추가 |

---

## V61 설계 철학

### 핵심 원칙 3가지

**1. Phase clock이 observation에 있으면 reward가 많이 필요 없다**

Policy가 "지금 FL-RR이 swing할 차례"를 직접 보면,
별도의 diagonal_coupling, pair_separation, fr_balance 같은 보상이 불필요하다.
phase_contact_reward 하나가 "올바른 위상에 올바른 상태"를 보상하면 충분하다.

**2. Exploit 방지는 penalty가 아닌 termination**

V60에서 penalty(-3, -5, -6)를 여러 개 쌓았지만 exploit이 계속 나왔다.
Termination은 "그 행동을 하면 죽는다"이므로 훨씬 직접적이다.
V61에서는 비-toe 접촉, pair-lock을 termination으로 처리한다.

**3. Reward는 적을수록 좋다**

V60.M 시점에서 활성 reward가 15개 이상이었다.
서로 충돌하며 예측 불가능한 equilibrium을 만들었다.
V61은 10개로 시작한다. 필요하면 나중에 추가하되, 처음부터 많이 넣지 않는다.

---

## 쉽게 보는 V61 보상 구조

### 로봇에게 주는 정보

**"지금 어느 다리를 들 차례야"** — phase clock

```
시간 흐름 →

FL+RR:  ██████░░░░██████░░░░██████   (stance → swing → stance)
FR+RL:  ░░░░██████░░░░██████░░░░██   (swing → stance → swing)
```

로봇이 매 순간 이 리듬을 **직접 볼 수 있다** (sin/cos 8개 숫자).
V60에서는 이걸 안 줬기 때문에 로봇이 타이밍을 스스로 발명해야 했고, 결국 못 했다.

### 보상: "이렇게 하면 점수를 줄게"

**주연 1개 + 보조 4개 = 양수 5개**

| 보상 | 점수 | 쉬운 설명 |
|------|------|----------|
| **리듬에 맞춰 걸어** | +10 | 위 리듬대로 발을 딛고 들면 만점. 가장 중요한 점수. |
| 명령 속도를 따라가 | +4 | "0.2m/s로 가라"는 명령에 맞게 가면 점수 |
| 앞으로 나아가 | +3 | 실제로 전진하면 점수 |
| 수평을 유지해 | +3 | 몸이 기울지 않으면 점수 |
| 발을 들어 | +2 | 발을 들었다 놓으면 약간 점수 (백업용) |

### 벌칙: "이렇게 하면 점수를 깎을게"

**5개, 모두 exploit 방지용**

| 벌칙 | 감점 | 쉬운 설명 |
|------|------|----------|
| 한 다리 안 쓰기 금지 | -5 | RR만 뜨고 3발로 버티기 = 감점 |
| 한 다리 계속 뜨기 금지 | -5 | 발을 70% 이상 공중에 두면 감점 |
| 한 쌍만 쓰기 금지 | -5 | FL+RR만 흔들고 FR+RL 고정 = 감점 |
| 기울어지면 감점 | -2 | 몸이 기울면 감점 |
| 위아래 튀면 감점 | -2 | 바운싱 하면 감점 |

### 즉사: "이러면 바로 죽어"

벌칙이 아닌 **에피소드 종료**. 로봇이 "이건 절대 하면 안 된다"를 빠르게 배운다.

| 조건 | 쉬운 설명 |
|------|----------|
| 무릎이 바닥에 닿으면 | 발끝으로만 걸어야 해. 무릎으로 걸으면 죽어. |
| 한 쌍만 계속 들면 | FL+RR만 영원히 흔들고 FR+RL 고정? 죽어. |
| 몸통이 바닥에 닿으면 | 넘어지면 죽어. |
| 너무 기울면 | 30도 이상 기울면 죽어. |
| 너무 낮아지면 | 주저앉으면 죽어. |

### 명령

```
"0~0.25 m/s로 앞으로 가"     (처음엔 느리게)
"옆으로는 가지 마"            (직진만)
"회전하지 마"                (yaw OFF, 나중에 추가)
```

### 한 문장 요약

> **리듬표를 보여주고, 그 리듬대로 걸으면 큰 점수를 주고, 꼼수를 부리면 즉사시킨다.**

---

## 구현 상세

### Observation

기존 SpotMicro flat observation **48차원** + phase_clock **8차원** = **56차원**

```python
self.observations.policy.phase_clock = ObsTerm(
    func=custom_mdp.phase_clock_obs,
    params={"frequency": 2.0},
)
```

phase_clock_obs 함수 (rewards.py line 32):
- 4다리 각각의 trot phase를 sin/cos로 인코딩
- FL/RR = base phase, FR/RL = base + pi (trot 패턴)
- frequency=2.0Hz → 0.5초 주기
- 출력: `[sin_FL, sin_FR, sin_RL, sin_RR, cos_FL, cos_FR, cos_RL, cos_RR]`

**이것이 V60과의 가장 큰 차이.**
V60에서는 phase를 reward 함수 내부에서만 계산했고, policy는 볼 수 없었다.
V61에서는 policy가 매 step "지금이 어느 위상인지"를 직접 본다.

### Commands

```python
lin_vel_x = (0.0, 0.25)     # 0부터 자연스럽게 (V60.F의 0.12 최소값 없음)
lin_vel_y = (0.0, 0.0)      # 횡이동 없음
ang_vel_z = (0.0, 0.0)      # yaw OFF (직진부터)
standing_envs = 0.05         # 5%만 서기 (거의 전부 보행)
action_scale = 0.25          # Isaac Lab 표준
```

**왜 vel_x 최소값이 0인가:**
V60.F에서는 정적 해를 깨기 위해 min=0.12를 넣었다.
V61에서는 phase_contact가 "올바른 위상에 stance/swing"을 직접 요구하므로,
정적 해가 높은 reward를 받을 수 없다. 따라서 vel 최소값 강제가 불필요하다.

**왜 yaw가 OFF인가:**
From-scratch에서 yaw까지 넣으면 학습 난이도가 급증한다.
직진 trot이 안정적으로 나온 후 V61.B에서 yaw를 추가하면 된다.

### Rewards (10개)

#### 양수 reward (5개)

| reward | weight | 함수 | 역할 |
|--------|--------|------|------|
| `phase_contact` | **+10.0** | `phase_contact_reward` | **주연.** stance phase에 접지, swing phase에 이탈하면 보상. frequency=2.0Hz, duty_factor=0.55. standing command 시 all-stance. |
| `track_lin_vel_xy_exp` | +4.0 | Isaac Lab 표준 | 속도 추종 (std=0.15) |
| `forward_velocity` | +3.0 | `forward_velocity_reward` | 전진 직접 보상 (수평 유지 시에만) |
| `flat_orientation_bonus` | +3.0 | `flat_orientation_bonus` | 수평 유지 |
| `feet_air_time` | +2.0 | Isaac Lab 표준 | 발 들기 백업 (threshold=0.1s). phase_contact가 주연이므로 보조만. |

**왜 phase_contact가 +10인가:**

V60.I에서 reward-only phase(obs 없이)로 +3을 줬을 때 pde 0.86 달성.
V61에서는 policy가 phase를 직접 보므로 더 강한 신호를 줘도 안전하다.
+10이면 총 양수 budget ~22 중 45%를 차지 — 명확한 주연.

수치 검증:
- 완벽한 trot (4발 모두 phase 일치): phase_contact = 10.0/step
- 정적 접지 (standing vel일 때): phase_contact = 10.0/step (all-stance도 맞음)
- 정적 접지 (walking vel일 때): phase_contact = ~5.0/step (50% mismatch)
- 1발 exploit: phase_contact = ~7.5/step (3발 맞음 + 1발 틀림)

따라서 완벽한 trot이 정적 접지보다 ~5.0/step 이득 — per_leg_contact_min(-5)과 합치면 exploit보다 trot이 유리.

#### 음수 penalty (5개)

| penalty | weight | 함수 | 역할 |
|---------|--------|------|------|
| `per_leg_contact_min` | **-5.0** | `per_leg_contact_min_penalty` | 1발 비사용 exploit 방지 (min_ratio=0.15) |
| `per_leg_excess_swing` | **-5.0** | `per_leg_excess_swing_penalty` | 영구 공중 방지 (max_swing=0.70) |
| `pair_lock` | **-5.0** | `diagonal_pair_lock_penalty` | pair 고착 방지 (gap_threshold=0.45) |
| `flat_orientation_l2` | -2.0 | Isaac Lab 표준 | 수평 penalty |
| `lin_vel_z_l2` | -2.0 | Isaac Lab 표준 | 수직 바운싱 억제 |

추가 최소 항목:
- `ang_vel_xy_l2` = -1.0
- `action_rate_l2` = -0.05
- `dof_torques_l2` = -0.0001

**왜 penalty가 -5인가:**

V60.B에서 -3이 부족했다 (양수 ~15 대비 부족).
V61에서 양수 합계 ~22이므로, -5면 양수의 23% — 충분히 경쟁력 있다.
V60.C에서 -10으로 RR exploit을 100 iter 만에 교정한 경험상, -5는 적절한 시작점.

#### V60에서 썼지만 V61에서 뺀 것들

| reward | 왜 뺐는가 |
|--------|----------|
| `diagonal_coupling` | phase_contact가 대체. 별도 coupling reward는 reward 충돌 유발 |
| `foot_clearance` | phase_contact가 swing 타이밍을 유도하면 clearance는 자연 발생 |
| `rear_trailing` | termination(non_toe_contact)으로 대체 |
| `fr_swing_balance` | phase_contact가 4발 균형을 구조적으로 보장 |
| `fr_contact_balance` | 동일 이유 |
| `rear_lr_balance` | 동일 이유 |
| `pair_separation` | phase_contact가 대체 |
| `forward_step` | forward_velocity로 충분 |
| `rear_air_time` | pair 전용 보상 금지 (V60.F 교훈) |
| `rear_clearance` | 동일 이유 |
| `standing_height` | 자세 과교정 유발 (V60.K 교훈) |
| `joint_default_pos` | 동일 이유 |
| `contact_foot_velocity` | 불필요 |
| `non_toe_contact` (penalty) | termination으로 대체 |

### Terminations

| termination | 함수 | 조건 | V60 교훈 |
|-------------|------|------|---------|
| `base_contact` | `illegal_contact` | base_link 접촉 | 표준 |
| `bad_orientation` | `bad_orientation_grace` | 30deg, grace 150 step (3초) | 표준 |
| `min_height` | Isaac Lab 표준 | 0.14m | 표준 |
| **`non_toe_contact`** | `illegal_contact` | foot_link/leg_link 접촉 | V60.K: penalty보다 확실 |
| **`pair_lock`** | `prolonged_pair_lock_termination` | gap>0.50, 30연속, grace 100 | V60.L: penalty로 안 끊김 |
| `feet_lifted` | None | 제거 (자유) | 보행에 필요 |
| `shoulder_splay` | None | 제거 | 불필요 |
| `posture_violation` | None | 제거 | 불필요 |

**왜 non_toe_contact가 termination인가:**

V60.K에서 penalty(-5)로 넣었을 때 non_toe_contact=0으로 효과적이었다.
하지만 V61에서는 "무릎으로 걸으면 즉사"가 더 명확한 신호다.
Policy가 처음부터 "toe로만 접지해야 한다"를 배우게 된다.

**pair_lock termination 파라미터:**

```
gap_threshold: 0.50   — |pairA_swing - pairB_swing| 기준
grace_steps: 100      — 에피소드 시작 2초간 면제 (초기 관성)
consecutive_steps: 30  — 0.6초 연속이면 종료
```

V60.M에서 grace=50, consecutive=20으로 했을 때 한 번도 안 걸렸다.
V61에서는 grace를 100으로 늘려 초기 안정화 시간을 더 주고,
consecutive를 30으로 늘려 순간 변동은 무시한다.

### Events (초기 조건)

```python
position_range = (0.9, 1.1)   # 관절 초기값 ±10% 랜덤
velocity_range = (0.0, 0.0)   # 초기 속도 없음
pose_range x/y = (-0.1, 0.1)  # 위치 약간 랜덤
yaw = (0.0, 0.0)              # yaw 고정
add_base_mass = None           # 질량 변동 없음
push_robot = None              # 외력 없음
```

From-scratch이므로 도메인 랜덤화를 최소화한다.
Trot이 안정적으로 나온 후 V61.B에서 랜덤화를 추가한다.

---

## 실행 계획

### 실행 방법

```
train.cmd        # from-scratch (resume 아닌 새 학습)
train.cmd gui    # GUI로 확인하며 학습
```

런 폴더: `logs/rsl_rl/spot_micro_flat/YYYY-MM-DD_HH-MM-SS_V61/`

### 예상 학습 곡선

| 구간 | 예상 | 근거 |
|------|------|------|
| 0~500 iter | 생존 학습 (ep_len 상승) | V60.A에서 ~300 iter에 생존 달성 |
| 500~2000 iter | 전진 + phase matching 시작 | phase_contact가 강한 신호 |
| 2000~3000 iter | trot 구조 발현 여부 확인 | **1차 판정 시점** |
| 3000~5000 iter | trot 안정화 또는 exploit 확인 | 2차 판정 |

### 판정 기준

#### 1차 판정 (iter 2000~3000)

**Go 기준:**
- ep_len > 800
- phase_contact > 5.0 (50% 이상 phase match)
- 4발 swing_time 모두 > 0.05
- pair gap < 0.40 (pair-lock 아님)
- non_toe_contact termination < 10%
- **GUI에서 4발이 번갈아 움직이는 것이 보임**

**No-go 기준:**
- ep_len < 200 지속 (학습 안 됨)
- 1발 exploit 재발 (per_leg_contact_min 발동 지속)
- pair-lock termination 50%+ (pair gap을 줄이지 못함)
- phase_contact < 2.0 (phase를 무시하고 다른 해를 찾음)

#### 최종 목표

- 4발 trot 패턴 (대각 교대)
- clearance > 2cm
- ep_len > 950
- track_lin > 3.0
- **GUI에서 "정상 보행"으로 보임**
- **이상적 보행의 50%+ 품질** (V60.I 종료 시점 30~35%)

### 실패 시 다음 단계

| 실패 유형 | 대응 |
|----------|------|
| phase_contact 무시 | weight +10→+15 상향 |
| non_toe termination 과다 | grace 연장 또는 penalty로 전환 |
| pair-lock 재발 | gap_threshold 0.50→0.40 |
| 전체 학습 안 됨 | phase_clock frequency 2.0→1.5 검토 |
| trot은 나오지만 전진 안 됨 | forward_velocity weight 상향 |

---

## V60 vs V61 비교

| 항목 | V60 시리즈 | V61 |
|------|-----------|-----|
| 총 버전 | 13 (A~M) | 1 (from-scratch) |
| 총 iter | ~35,000 | 목표 5,000 |
| phase 정보 | reward 내부 (policy 못 봄) | **observation으로 제공** |
| 활성 reward 수 | 15~20개 | **10개** |
| exploit 방지 | penalty 위주 | **termination 위주** |
| pair 전용 보상 | 있음 (V60.D~F) | **없음** |
| standing_height | 켰다 껐다 반복 | **없음** |
| diagonal_coupling | 별도 reward | **phase_contact가 대체** |
| 결과 | 30~35% 품질, trot 미달성 | ? |

---

## 실험에서 보는 핵심 지표

### 이번 버전의 핵심 지표

| 지표 | 의미 | 성공 기준 |
|------|------|----------|
| `phase_contact` | trot 위상 일치도 | > 5.0 (50%+) |
| `swing_time_*` | 각 발 공중 시간 | 4발 모두 > 0.05 |
| `pair gap` | \|pairA_sw - pairB_sw\| | < 0.40 |
| `ep_len` | 생존 | > 800 |
| `non_toe_contact termination` | 무릎 접지로 즉사 비율 | < 10% |
| `pair_lock termination` | pair 고착으로 즉사 비율 | < 10% |

### V60에서 쓰던 지표 중 V61에서 덜 중요한 것

| 지표 | 왜 덜 중요한가 |
|------|---------------|
| `diagonal_coupling_raw` | V27 함수 경로 전용, V61에서 측정 안 됨 |
| `rear_trailing` | termination으로 대체 |
| `stance_width` | V61에서 별도 제약 없음 |

---

## V61 초기 결과 및 수정

### V61 초기 결과 (iter 8000)

phase clock observation 덕분에 **phase timing 학습은 빠르게 성공**:
- iter 300에서 ep_len 56→937 폭발적 전환 (V60.A는 2000+ iter 소요)
- phase_contact 7.76 (높음)
- non_toe_contact termination 0.47%로 급감

**하지만 trot은 나오지 않았다:**
- anti_phase = 0.019 (trot 최소 0.3 필요)
- FL swing = 0.025 (사실상 안 듦)
- clearance = 1-2mm (보행 아님)

**원인 진단:** phase_contact_reward가 **"잘 맞으면 보상"만 있고 "swing phase에 붙어 있으면 손해"가 없었다.** duty_factor=0.55이면 4발 항상 접지해도 55%는 stance phase와 일치 → phase_contact ~5.5 기본 확보. 여기에 rear만 약간 들면 7+ 달성. "거의 안 움직이면서 7.76점"이 "제대로 걸으면서 10점"보다 안전하고 순이익이 높았다.

### V61 수정: swing violation penalty

**핵심 수정:** swing phase에 접지하면 적극적으로 감점.

```python
# 기존: match = (contact == expected), 0 or 1 → 정적 해도 55% 맞음
# 수정: swing violation = contact AND swing_phase → 감점
score = match - alpha * swing_violation
```

수치 검증:
```
정적 해 (4발 항상 접지):
  stance phase(55%): score = 1.0
  swing phase(45%): score = 0 - 1.5×1 = -1.5
  per-leg 평균 = 0.55 - 0.675 = -0.125 → 음수! (이전: +0.55)

완벽한 trot:
  stance phase: contact=1, score = 1.0
  swing phase: contact=0, score = 1.0 (violation 없음)
  per-leg 평균 = 1.0 → 양수
```

**정적 해가 이제 음수, trot이 양수.** 이전에는 둘 다 양수여서 정적 해가 유리했다.

변경 파라미터:
- `swing_penalty_alpha`: 0 → **1.5** (swing phase 접지 시 감점 1.5배)
- `aggregation_mode`: "mean" → **"mean_min"** (1발 희생 방지)

### 참고: diagonal_coupling_raw = 0은 측정 버그

`diagonal_coupling_raw`는 V27 함수(`diagonal_coupling_soft_gate_reward`) 경로에서만 업데이트됨.
V61은 `simple_diagonal_coupling_reward`를 사용하므로 이 값은 항상 0.
실제 교대 여부는 contact_ratio의 pair 분석(anti_phase)으로 판단해야 함.

---

## 한 줄 요약

V61은 **"policy에게 시간 구조를 직접 보여주고, swing phase 접지를 적극 감점하여 trot을 강제"**하는 설계이다.
V60에서 13버전 동안 배운 exploit 패턴 + V61 초기 8000 iter에서 발견한 phase-matched 정적 해 exploit까지 반영하여,
phase clock observation + swing violation penalty + mean_min aggregation으로 from-scratch trot 학습을 시도한다.
