# V36 Plan — 부팅 안정화 + Anti-Splay/Anti-Shuffle

**작성일**: 2026-03-20
**상태**: 완료 (iter 800에서 종료 → V37로 전환)

---

## 배경

V35.5에서 부팅 안정화 3가지 결합이 성공:
- alive_bonus=10.0, undesired_contacts -20→-100 램프, 초기 저속 command
- iter 400에서 ep_len=234, iter 1200에서 ep_len=250 안정

하지만 V35.5 = V32.1 보상 구조이므로 **동일한 벌레보행 재발**:
- shoulder_mean_dev = 0.544 rad (31°) — 과도한 거미형 벌어짐
- stance_width = 0.320m — 기준(front 0.19m, rear 0.21m) 대비 60% 초과
- feet_air_time = -9.5 — threshold(0.3s) 미달 = 셔플링
- stride_length = 4.5 — 보폭 부족

## 전략

V35.5 (부팅 안정화) + V35 plan의 anti-splay/anti-shuffle 수정을 결합.

**핵심 가설**: V35/V35.1에서 anti-splay가 실패한 건 부팅 메커니즘 부재 때문이지, anti-splay 값 자체가 과도해서가 아니다. 부팅이 안정된 V35.5 위에서는 anti-splay가 정상 작동할 것.

**접근**: V35.1 수준(보수적 중간값)으로 시작. V35(-8.0)는 과도했을 수 있으므로.

---

## 변경 사항 (V35.5 → V36)

### Anti-Splay (거미형 벌어짐 방지)

| 파라미터 | V35.5 (V32.1) | V36 | 근거 |
|---------|--------------|-----|------|
| `shoulder_neutral.weight` | -4.0 | **-6.0** | V35.1 수준. V32.1(-4.0)은 약하고 V35(-8.0)는 미검증 |
| `stance_width_penalty.weight` | -2.5 | **-3.0** | V35.1 수준. 직접 폭 제한 소폭 강화 |
| `base_height_l2.target_height` | 0.24 | **0.23** | V35.1 수준. 높이 낮추면 splay 감소 (기하학적 효과) |
| `standing_height.target_height` | 0.24 | **0.23** | 일관성 (base_height와 동일) |

### Anti-Shuffle (셔플링/보폭 부족 방지)

| 파라미터 | V35.5 (V32.1) | V36 | 근거 |
|---------|--------------|-----|------|
| `stride_length_ramp_start` | 400 | **200** | 조기 보폭 신호. V32.1에서 400은 셔플링 고착 후 |
| `stride_length_ramp_end` | 700 | **500** | 더 빠르게 활성화 |
| `stride_length_max` | 12.0 | **15.0** | 보폭 보상 상한 강화 |
| `feet_air_time.threshold` | 0.3 | **0.25** | 약간 낮춰서 체공 달성 쉽게 (0.3은 포기 유발) |
| `swing_stride.weight` | 2.0 | **4.0** | 스윙 중 이동거리 보상 2배 |

### 부팅 안정화 (V35.5에서 유지)

| 파라미터 | 값 | 비고 |
|---------|-----|------|
| `alive_bonus` | 10.0 | 매 step 생존 보상 |
| `boot_ramp_end` | 300 | iter 0~300 부팅 구간 |
| `boot_undesired_contacts_floor` | -20.0 | 초기 낙하 관용 |
| `boot_vel_x_min/max` | 0.01 / 0.05 | 초기 저속 |
| `boot_vel_restore_iter` | 500 | iter 500에서 원래 속도 복원 |

---

## V36 vs 이전 시도 비교

| 버전 | anti-splay | anti-shuffle | 부팅 안정화 | 결과 |
|------|-----------|-------------|-----------|------|
| V32.1 | 없음 | 없음 | 없음 | 25% 성공, 벌레보행 |
| V35 | 강함(-8,-4,0.22) | 있음 | 없음 | 이모지 crash + 부팅 실패 |
| V35.1 | 중간(-6,-3,0.23) | 있음 | 없음 | 부팅 실패 (ep_len=12) |
| V35.5 | 없음 | 없음 | **있음** | 부팅 성공, 벌레보행 |
| **V36** | **중간(-6,-3,0.23)** | **있음** | **있음** | **?** |

V36은 V35.1과 동일한 anti-splay/shuffle이지만, V35.5의 부팅 안정화가 추가됨.

### V36 최종 결과 (iter 800)

| 지표 | V35.5 (기준) | V36 | 변화 | 판정 |
|------|-------------|-----|------|------|
| ep_len | 250 | 250 | 동일 | ✅ 부팅 완벽 |
| shoulder_dev | 0.544 rad | 0.543 | 0% | ❌ anti-splay 무효 |
| stance_width_front | 0.320m | 0.310 | -3% | 미미 |
| stride_length | 4.533 | 6.084 | +34% | ✅ anti-shuffle 성공 |
| swing_stride | 0.522 | 1.192 | +128% | ✅ 대폭 개선 |
| feet_air_time | -9.541 | -7.070 | +26% | ✅ 체공 개선 |

**결론**: Anti-shuffle은 성공. Anti-splay는 penalty(-6.0)가 전체 reward(+180)의 0.6%에 불과하여 무시됨. → **V37에서 penalty 2~3배 강화 + 커리큘럼 적용**.

---

## 파일 변경 목록

### `spot_micro_rl_env_cfg.py`
- Line 7: `TRAIN_VERSION = "V36"`
- `shoulder_neutral.weight`: -4.0 → -6.0
- `stance_width_penalty.weight`: -2.5 → -3.0
- `base_height_l2.target_height`: 0.24 → 0.23
- `standing_height.target_height`: 0.24 → 0.23
- `stride_length_ramp_start`: 400 → 200
- `stride_length_ramp_end`: 700 → 500
- `stride_length_max`: 12.0 → 15.0
- `feet_air_time.threshold`: 0.3 → 0.25
- `swing_stride.weight`: 2.0 → 4.0
- 부팅 안정화 파라미터 유지 (alive_bonus, boot_ramp 등)
- Rough env cfg: height target도 0.23으로 동기화

### `.env`
- `TRAIN_VERSION=V36`

---

## 체크포인트 기준

| iter | 확인 | 판정 |
|------|------|------|
| 100 | ep_len > 30 | 부팅 진행 (V35.5에서 40.6이었음) |
| 300 | ep_len > 80 | boot_ramp 완료 후 안정성 |
| 500 | ep_len > 150 | 속도 복원 후 보행 유지 |
| 800 | shoulder_mean_dev < 0.3 rad | anti-splay 효과 확인 |
| 1000 | stride > 8.0, feet_air > 0 | anti-shuffle 효과 확인 |
| 1500 | STAND→WALK ramp 시작 | 보행 전환 |

## 리스크

1. **Anti-splay가 부팅 안정성을 저해할 가능성** — V35.1에서 ep_len=12였지만, 그때는 부팅 메커니즘이 없었음. alive_bonus + contacts 램프가 이를 보상할 것으로 예상. 만약 iter 100에서 ep_len < 20이면 anti-splay가 부팅과 충돌하는 것이므로 V36.1에서 완화.

2. **Anti-shuffle 조기 활성화의 부작용** — stride_length ramp를 iter 200부터 시작하면 아직 보행이 불안정할 때 보폭을 강제. boot_ramp_end=300이므로 거의 동시에 활성화됨. 만약 충돌하면 stride_ramp_start를 400으로 복원.

3. **feet_air_time threshold 0.25 vs 0.3** — 0.25로 낮추면 달성이 쉬워지지만, 너무 낮으면 셔플링을 허용. 0.25는 0.3과 0.1의 중간으로 합리적.

## 성공 기준

V32.1 대비 개선:
- shoulder_mean_dev: 0.544 rad → **< 0.3 rad** (45% 감소)
- stance_width: 0.320m → **< 0.25m**
- feet_air_time: 음수 → **양수** (threshold 달성)
- stride_length: 4.5 → **> 8.0**
- ep_len: 250 유지 (부팅 안정성 보존)
