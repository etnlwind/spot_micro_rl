# 4족 보행 RL 연구 조사 및 프로젝트 비교 분석

**작성일**: 2026-03-18
**목적**: 주요 논문/프레임워크의 reward 설계를 조사하여 우리 프로젝트에서 놓친 부분 파악

---

## 1. 주요 프레임워크 조사

### 1a. legged_gym (ETH RSL) — 업계 표준

**출처**: https://github.com/leggedrobotics/legged_gym

ANYmal 시리즈 로봇에 사용되는 표준 reward 설계. 15개 항목으로 구성.

| 보상 항목 | 기본 weight | 역할 |
|-----------|------------|------|
| tracking_lin_vel | 1.0 | 속도 추적 (exp(-err²/σ)) |
| tracking_ang_vel | 0.5 | 회전 속도 추적 |
| lin_vel_z | -2.0 | 수직 속도 억제 |
| ang_vel_xy | -0.05 | 수평 각속도 억제 |
| orientation | -0.0 | 자세 수평 유지 |
| torques | -0.00001 | 토크 최소화 |
| dof_vel | -0.0 | 관절 속도 억제 |
| dof_acc | -2.5e-7 | 관절 가속도 억제 |
| base_height | -0.0 | 기립 높이 유지 |
| **feet_air_time** | **1.0** | **체공 시간 보상 (핵심)** |
| collision | -1.0 | 충돌 패널티 |
| feet_stumble | -0.0 | 발 걸림 패널티 |
| action_rate | -0.01 | 행동 변화율 억제 |
| stand_still | -0.0 | 정지 시 움직임 억제 |
| termination | -0.0 | 종료 패널티 |

**핵심 특징**: `only_positive_rewards=True` — 총 보상이 음수면 0으로 clip.

#### feet_air_time 구현 (핵심)

```python
def _reward_feet_air_time(self):
    contact = self.contact_forces[:, self.feet_indices, 2] > 1.
    contact_filt = torch.logical_or(contact, self.last_contacts)
    self.last_contacts = contact
    first_contact = (self.feet_air_time > 0.) * contact_filt
    self.feet_air_time += self.dt
    # 착지 순간: (체공시간 - 0.5초) 만큼 보상
    rew_airTime = torch.sum((self.feet_air_time - 0.5) * first_contact, dim=1)
    # 정지 명령이면 비활성
    rew_airTime *= torch.norm(self.commands[:, :2], dim=1) > 0.1
    self.feet_air_time *= ~contact_filt
    return rew_airTime
```

**동작 원리**:
- 각 발의 체공 시간을 추적
- 발이 착지하는 순간, `(체공시간 - 0.5초)` 만큼 보상/패널티
- 0.5초 이상 체공 → 양의 보상 / 0.5초 미만 → 음의 보상
- **4발 모두 동일 기준** → front/rear 구분 없이 균등하게 swing 유도
- 정지 명령(vel < 0.1)일 때는 비활성화

---

### 1b. Walk These Ways (CMU, Margolis 2023) — Gait Phase Clock

**출처**: https://github.com/Improbable-AI/walk-these-ways
**논문**: https://arxiv.org/abs/2212.03238

Unitree Go1에서 sim-to-real 검증된 프레임워크. **gait를 command로 파라미터화**.

#### Gait Command 구조

| 인덱스 | 파라미터 | 설명 |
|--------|---------|------|
| cmd[0:2] | x, y velocity | 이동 속도 |
| cmd[2] | yaw velocity | 회전 속도 |
| cmd[4] | frequency | 보행 주파수 (Hz) |
| cmd[5:9] | phase, offset, bound, duration | 4발 gait 타이밍 |
| cmd[9] | foot clearance height | 발 들기 높이 |
| cmd[12] | stance width | 보폭 너비 |
| cmd[13] | stance length | 보폭 길이 |

#### Contact Schedule 기반 보상

gait phase clock이 **desired_contact_states**를 생성하고, 이를 따르면 보상:

```python
# tracking_contacts_shaped_force: swing 상태에서 발에 힘이 가해지면 패널티
for i in range(4):
    reward += -(1 - desired_contact[:, i]) * (
        1 - torch.exp(-1 * foot_forces[:, i] ** 2 / gait_force_sigma))

# tracking_contacts_shaped_vel: stance 상태에서 발이 움직이면 패널티
for i in range(4):
    reward += -(desired_contact[:, i]) * (
        1 - torch.exp(-1 * foot_velocities[:, i] ** 2 / gait_vel_sigma))
```

#### Raibert Heuristic 보상

발 배치 위치를 Raibert 공식으로 계산하고, 실제 위치와의 오차를 패널티:

```python
# 현재 속도와 gait phase를 기반으로 이상적 발 위치 계산
desired_xs = nominal_x + phase * x_vel * (0.5 / frequency)
desired_ys = nominal_y + phase * y_vel * (0.5 / frequency)
reward = -sum(square(desired - actual))
```

#### Foot Clearance (Phase 연동)

```python
# swing phase에서 발 높이가 명령값과 일치하면 보상
phases = 1 - abs(1 - clip((foot_indices * 2) - 1, 0, 1) * 2)
target_height = cmd_clearance * phases + 0.02
rew = -square(target_height - foot_height) * (1 - desired_contact)
```

**핵심**: gait를 "발견"하는 것이 아니라 **명시적으로 지시**. trot이면 `phase=[0,0.5,0.5,0]`.

---

### 1c. AllGaits (CPG 기반, 2024)

**출처**: https://arxiv.org/html/2411.04787v1

#### 보상 함수 (매우 단순)

| 항목 | weight | 비고 |
|------|--------|------|
| Linear velocity tracking | 3dt | exp(-‖err‖²/0.25) |
| Lateral/vertical velocity | -2dt | ‖v_yz‖² |
| Angular velocity | -0.1dt | ‖ω_xyz‖² |
| Power | -0.001dt | |τ·q̇| |

**총 4개 항목**. gait 패턴은 CPG(Central Pattern Generator) 커플링 매트릭스가 처리.

#### 커플링 매트릭스로 gait 강제

```
θ̇_i = ω_i + Σ_j r_j w_ij sin(θ_j - θ_i - φ_ij)
```

- trot: FL-RR 동위상, FR-RL 동위상 (φ 차이 = 0)
- 커플링 가중치 `w_ij = 10` (강한 결합)
- 훈련 중 3초마다 gait 매트릭스를 리샘플 → 단일 policy가 9종 gait 학습

**핵심**: reward를 복잡하게 만들지 않고, **gait 패턴을 구조적 레이어(CPG)로 분리**.

---

## 2. 우리 프로젝트와 비교

### 보유 vs 미보유 기능

| 기능 | legged_gym | Walk These Ways | AllGaits | 우리 (V31.2) |
|------|-----------|-----------------|----------|-------------|
| velocity tracking | ✅ | ✅ | ✅ | ✅ |
| **feet_air_time** | **✅ (w=1.0)** | — (phase clock 대체) | — (CPG 대체) | **❌ 없음** |
| **gait phase clock** | — | **✅** | — | **❌ 없음** |
| **CPG oscillator** | — | — | **✅** | **❌ 없음** |
| **foot clearance (phase 연동)** | — | **✅** | ✅ (g_c param) | **❌ 없음** |
| orientation | ✅ | ✅ | ✅ | ✅ |
| joint vel/acc penalty | ✅ | ✅ | ✅ (power) | ✅ |
| action rate | ✅ | ✅ | — | ✅ |
| base height | ✅ | ✅ | — | ✅ |
| collision | ✅ | ✅ | — | ✅ |
| torque penalty | ✅ | ✅ | ✅ | ❌ |
| **Raibert heuristic** | — | **✅** | — | **❌ 없음** |
| front/rear 전용 보상 | — | — | — | ✅ (5+개씩) |
| 보상 항목 수 | **15개** | **~28개** | **4개** | **50개+** |

### 핵심 차이점

#### A. 우리에게 없는 것: "모든 발에 공평한 swing 유도"

- **legged_gym**: `feet_air_time` 1개로 4발 공평 유도
- **Walk These Ways**: `desired_contact_states`로 명시적 trot 패턴
- **AllGaits**: CPG 커플링으로 gait 구조 강제
- **우리**: rear_swing_bonus, front_swing_bonus, rear_joint_velocity, front_joint_velocity... **다리별 보상을 개별 설계** → 복잡성 폭발 + 역할 분리 유발

#### B. 보상 복잡도

- 성공한 프레임워크: 4~28개 항목
- 우리: 50개+ → **항목 간 상호작용이 예측 불가능**
- 교훈 #7, #8 (역할 분리)이 발생하는 근본 원인일 수 있음

#### C. Gait 유도 방식

| 방식 | 장점 | 단점 | 대표 |
|------|------|------|------|
| 암묵적 (emergent) | 유연, 보상만으로 가능 | 원하는 gait 보장 안 됨 | legged_gym |
| 명시적 (phase clock) | trot 패턴 직접 지정 | 경직적, command 구조 필요 | Walk These Ways |
| 구조적 (CPG) | gait를 레이어로 분리 | CPG 구현 필요 | AllGaits |
| **다리별 보상** | 세밀한 제어 가능 | **역할 분리 유발** | **우리 (실패 경험)** |

---

## 3. 구체적 개선 방안

### 방안 1: `feet_air_time` 도입 (최소 변경, 즉시 적용)

```python
def feet_air_time_reward(env, sensor_cfg, asset_cfg, target_air_time=0.4, min_vel=0.05):
    """4발 공통 체공시간 보상 — legged_gym 방식"""
    contact = contact_forces[:, feet_indices, 2] > 1.0
    first_contact = (feet_air_time > 0.) * contact
    reward = torch.sum((feet_air_time - target_air_time) * first_contact, dim=1)
    # 정지 시 비활성
    vel_gate = torch.clamp(root_vel_x / min_vel, 0, 1)
    feet_air_time += dt
    feet_air_time *= ~contact
    return reward * vel_gate
```

- weight: +5.0 ~ +10.0
- target_air_time: 0.4초 (trot의 50% duty cycle 기준)
- **rear_swing_bonus, front_swing_bonus, front_joint_frozen을 대체 가능**

### 방안 2: Contact Schedule (Gait Phase Clock) 도입

trot 패턴을 명시적으로 정의:

```python
# trot: FL-RR 동시, FR-RL 동시 (위상차 π)
phase = (iteration_count * dt * frequency) % (2π)
desired_contact = {
    'FL': phase < π,  # 0~π stance, π~2π swing
    'RR': phase < π,  # FL과 동위상
    'FR': phase >= π, # FL과 반대위상
    'RL': phase >= π, # FR과 동위상
}
# 실제 접촉과 desired 비교하여 보상/패널티
```

### 방안 3: 보상 항목 대폭 축소 (장기)

현재 50개+ 항목을 legged_gym 수준(15~20개)으로 정리:

**유지**: velocity tracking, orientation, joint penalties, action rate, base height, collision
**대체**: rear_*/front_* 10개+ → `feet_air_time` 1개
**대체**: trot_gait, diagonal_coupling → contact schedule 2개
**제거**: 중복/미미 효과 항목들

---

## 4. V31.2 이후 로드맵 제안

| 단계 | 버전 | 핵심 변경 | 목표 |
|------|------|----------|------|
| 현재 | V31.2 | front_joint_velocity/frozen 버그 수정 | joint-level 효과 검증 |
| 다음 | V32 | `feet_air_time` 추가 + front/rear 전용 보상 축소 | F-R gap < 0.20 |
| 중기 | V33 | contact schedule (trot phase clock) 도입 | 명시적 trot 강제 |
| 장기 | V34+ | 보상 항목 대폭 정리 (50개 → 20개) | 안정적 학습 구조 |

---

## 5. 프로젝트 교훈 추가

기존 교훈 #1~#8에 추가:

> **교훈 #9**: 다리별 전용 보상(front_*, rear_*)은 "어떤 다리를 희생할지" 최적화를 유발한다 — **4발 공통 보상**(feet_air_time)이 역할 분리를 방지한다.

> **교훈 #10**: 보상 항목 50개+는 항목 간 상호작용을 예측 불가능하게 만든다 — 성공한 프레임워크는 15~20개 수준이다.

> **교훈 #11**: Gait 패턴은 "발견"보다 "지시"가 안정적이다 — phase clock 또는 CPG로 구조적 강제가 더 효과적이다.

---

## 참고 자료

- [legged_gym (ETH RSL)](https://github.com/leggedrobotics/legged_gym)
- [Walk These Ways (CMU, Margolis 2023)](https://arxiv.org/abs/2212.03238) | [코드](https://github.com/Improbable-AI/walk-these-ways)
- [AllGaits: Learning All Quadruped Gaits and Transitions (2024)](https://arxiv.org/html/2411.04787v1)
- [NVIDIA Isaac Lab Spot Training](https://developer.nvidia.com/blog/closing-the-sim-to-real-gap-training-spot-quadruped-locomotion-with-nvidia-isaac-lab/)
- [Deep RL for Quadrupedal Locomotion Review](https://www.oaepublish.com/articles/ir.2022.20)
- [Footstep Reward for Energy-Efficient Gait](https://www.tandfonline.com/doi/full/10.1080/01691864.2024.2442718)
