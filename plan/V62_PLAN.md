# V62 실험 계획: Phase-Gated Trot — drag/shuffle 해 약화 + 진짜 trot 유도

> 작성: 2026-04-08
> 현재 코드 truth 기준 버전: `V62`
> 기반: V61.C + Codex/Claude 공동 분석

---

## 배경: 왜 V62가 필요한가

V61.C (iter 1265)는 생존/안정성 완벽(ep_len=1000, reward=401, timeout=100%)이지만 **trot 실패**.

| 지표 | V61.C 실측 | trot 이론값 | 판정 |
|------|-----------|-----------|------|
| contact_ratio 평균 | 88% | ~50% | **1.8배 과다** |
| swing_time (FL) | 0.07 | ~0.45 | **사실상 안 뗌** |
| propulsion 분포 | 4발 균등 | 대각쌍 교대 | **drag 패턴** |
| feet_air_time | -0.019 | 양수 | **학습 실패** |

### 핵심 진단 (Codex + Claude 일치)

> "trot를 못 배우는 게 아니라, 현재 reward landscape에서 더 쉬운 drag/shuffle 해가 존재한다."

3가지 구조 원인:
1. **저속 정적 해**: `lin_vel_x=(0.0, 0.25)` + `standing_vel_threshold=0.08` → 32% 환경에서 서기=만점
2. **propulsion이 phase를 안 봄**: stance 중 아무 때나 밀면 보상 → drag/crawl도 보상
3. **swing 유도 약함**: feet_air_time weight=2.0 → phase_contact(10)+propulsion(8) 대비 너무 약

---

## V62 변경 사항 (3가지)

### 1. 저속 정적 해 제거

```
lin_vel_x = (0.08, 0.25)          # 0.0→0.08
standing_vel_threshold = 0.02      # 0.08→0.02 (이중 방어)
```

효과: 32% 환경에서 서기 최적해 → 0%

### 2. Phase-Gated Diagonal Propulsion (핵심 변경)

새 함수: `phase_gated_diagonal_propulsion_reward`

```
기존 V61.C: reward = push_pair × swing_pair                    (phase 무관)
V62:         reward = push_pair × swing_pair × late_stance_gate  (phase 연동)
```

**late_stance_gate:**
- stance의 마지막 ~25% (75%~100%)에서 gate가 0.5→1.0으로 상승
- stance 0~75%에서는 gate≈0 → 대부분의 접지 구간에서 보상 차단
- soft sigmoid (`gate_sharpness=5.0`) — 전환 폭 ≈ ±0.4 rad
- swing phase에서는 stance_mask=0이 이미 차단

**수치 검증:**
| 상태 | phase_contact (+10) | propulsion (+8, gated) | feet_air (+4) | 합산 |
|------|--------------------|-----------------------|---------------|------|
| drag/shuffle (88% contact) | ~7.5 | **~0.5** (gate 75%→ 차단 강화) | ~-0.5 | **~7.5** |
| trot (50% contact, 교대) | ~9.5 | **~6.0** (late-stance push-off) | ~+2.0 | **~17.5** |
| trot vs drag 차이 | | | | **+10.0** |

V61.C에서 차이 ≈ 0이었던 것이 V62에서 +10.0 → drag 대비 trot이 압도적으로 유리.
(gate가 75% onset으로 좁아져 drag 억제가 더 강력해짐)

### 3. Swing 품질 강화

```
feet_air_time weight = 4.0  (V61.C: 2.0)
```

---

## V62 전체 Reward 구조 (15개)

### 양수 (7개)

| reward | weight | 함수 | V61.C 대비 변경 |
|--------|--------|------|----------------|
| phase_contact | +10.0 | phase_contact_reward | standing_vel 0.02 |
| **propulsion** | **+8.0** | **phase_gated_diagonal_propulsion_reward** | **함수 교체 (핵심)** |
| track_lin_vel_xy_exp | +4.0 | Isaac Lab 표준 | 동일 |
| **feet_air_time** | **+4.0** | Isaac Lab 표준 | **2.0→4.0** |
| forward_velocity | +3.0 | forward_velocity_reward | 동일 |
| flat_orientation_bonus | +3.0 | flat_orientation_bonus | 동일 |
| track_ang_vel_z_exp | +1.0 | Isaac Lab 표준 | 동일 |

### 음수 (8개, V61.C와 동일)

| penalty | weight |
|---------|--------|
| per_leg_contact_min | -5.0 |
| per_leg_excess_swing | -5.0 |
| pair_lock | -5.0 |
| flat_orientation_l2 | -2.0 |
| lin_vel_z_l2 | -2.0 |
| ang_vel_xy_l2 | -1.0 |
| action_rate_l2 | -0.05 |
| dof_torques_l2 | -0.0001 |

---

## Trot 품질 KPI (새로 추가)

phase_gated_diagonal_propulsion_reward 내부에서 **에피소드별 누적 통계**로 로깅 (batch snapshot 아님):

| KPI | 의미 | trot 목표 |
|-----|------|----------|
| log_contact_ratio_fl/fr/rl/rr | per-leg 접지 비율 | ~0.55 |
| log_mean_swing_ratio | 4발 평균 swing 비율 | ~0.45 |
| log_pair_both_stance | 대각 쌍 동시 접지 비율 | < 0.2 (낮을수록 교대) |
| log_phase_gated_propulsion | phase window 내 propulsion | 상승 추세 |
| log_front_rear_prop_diff | 앞/뒤 propulsion 균형 | ~0 |
| log_swing_time_fl/fr/rl/rr | per-leg swing time | > 0.2 |

---

## 리스크

| 리스크 | 대응 |
|--------|------|
| phase gate가 너무 sparse → 초기 학습 실패 | `gate_sharpness=5.0` (soft sigmoid), 필요시 3.0으로 하향 |
| feet_air_time 강화 → "무작정 뛰기" | 기존 per_leg_excess_swing(-5)이 억제 |
| from-scratch 비용 | V61.C가 trot 실패 → resume 가치 없음 |

---

## 판정 기준

| iter | 기준 | Go/No-go |
|------|------|----------|
| 500 | ep_len > 500 + propulsion > 0 | 생존 + 기본 학습 |
| 1000 | mean_swing_ratio > 0.2 + log_pair_both_stance < 0.5 | trot 징후 |
| 2000 | contact_ratio < 0.7 + pair alternation 가시화 | trot 형성 |
| 3000 | GUI에서 대각 교대 육안 확인 | 최종 판정 |

---

## 실행

```
# V61.C 훈련 중지 후
# TRAIN_VERSION = "V62" (이미 설정됨)
train.cmd        # from-scratch
train.cmd gui    # GUI로 확인하며
```

---

## 수정 파일

1. `spot_micro_rl_env_cfg.py` line 7: `TRAIN_VERSION = "V62"`
2. `spot_micro_rl_env_cfg.py` line 33: `_IS_V62` 플래그 추가
3. `spot_micro_rl_env_cfg.py` line ~5003: V62 블록 신설
4. `rewards.py` line ~3858: `phase_gated_diagonal_propulsion_reward` 함수 신설 + 에피소드 누적 KPI
5. `train.cmd` line 7: `RUN_NAME=V62`
