# V25 Plan — Per-Limb Direct Gating + Collapse Prevention

> 작성: 2026-03-14
> 상태: **설계 중**
> 선행 버전: V24 (Limb Validity Gating) — 목표 미달성

---

## 1. V25 도입 배경

### 1.1 V24 실패 요약

V24는 rear-left collapse를 `limb_usage_min_penalty`와 `rear_left_right_usage_diff_penalty`라는 두 패널티로 차단하려 했다. 결과는 전 구간 `enforced_fail`. 실패 원인은 세 가지로 정리된다.

| 실패 원인 | 설명 |
|----------|------|
| **타이밍** | iter 0~200 observe 구간에 패널티 없음 → collapse가 이미 고착된 후 ramp 시작 |
| **간접 메커니즘** | `limb_usage_min`은 4개 사지 중 최솟값 → rear-left가 아닌 다른 사지가 collapse해도 동일하게 반응, rear-left만 선택적으로 차단 불가 |
| **가중치 부족** | 최종 weight -12.0은 총 reward(544) 대비 ~2% 수준 → 고착된 3다리 보행 경로의 이탈 비용보다 낮음 |

limb_usage_min이 iter 381에서 0.104였던 것이 iter 1900에서 0.000065로 **단조 감소**했다는 것은 패널티 ramp 이후에도 교정이 없었음을 증명한다. collapse가 패널티보다 먼저 안정화됐기 때문이다.

### 1.2 구조적 문제: 보상 경로 미차단

`diagonal_coupling` 보상은 FL+RR 쌍과 FR+RL 쌍의 관절 속도 상관으로 계산된다. rear-left가 항상 swing 상태이면 front-right(swing 시)와 rear-left(항상 swing)의 상관이 높아질 수 있어, **3다리 보행으로도 diagonal_coupling 보상을 상당 부분 획득**하는 경로가 열려 있다. V24는 이 경로를 차단하지 않았다.

---

## 2. V25 핵심 전략

V24 교훈에서 도출된 설계 원칙:

1. **직접(per-limb)**: rear-left contact_ratio에 직접 lower-bound penalty — 간접 proxy(min_usage) 방식 폐기
2. **즉시(iter 0부터)**: collapse 형성 전에 차단 — ramp 제거 또는 시작 iter를 0으로
3. **하드 리셋(restart-on-collapse)**: 조기 collapse 감지 시 run 즉시 종료 후 재시작
4. **경로 차단**: 3다리 보행으로 diagonal_coupling 보상을 얻지 못하도록 보상 구조 수정

---

## 3. V25 구현 변경

### 3.1 신규 Reward Term: `rear_left_contact_floor_penalty`

rear-left contact_ratio에 **직접** lower-bound penalty를 부여하는 term.

```python
def rear_left_contact_floor_penalty(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg = SceneEntityCfg("robot"),
    floor_target: float = 0.35,
    min_vel: float = 0.05,
) -> torch.Tensor:
    metrics = compute_v23_raw_metrics(env)
    if not metrics:
        return torch.zeros(env.num_envs, ...)
    gap = torch.clamp(floor_target - metrics["contact_ratio_rl"], min=0.0)
    return gap * _heading_velocity_gate(env, asset_cfg, min_vel)
```

- **weight**: -25.0 (iter 0부터 full weight, ramp 없음)
- **논리**: contact_ratio_rl < 0.35이면 gap에 비례 패널티. 완전 collapse 시(contact_ratio ~0.0003) gap ≈ 0.35 → step당 페널티 기여 ≈ 8.75 (총 reward 500 기준 ~1.75%)
- V24의 `limb_usage_min_penalty` / `rear_left_right_usage_diff_penalty`는 **유지** (보조 신호로 활용)

> **왜 -25.0인가?**
> V24 실패에서 -12.0이 총 reward의 ~2%였음. 직접 페널티는 gap이 최대 0.35이므로 실효 기여는 더 높다. 단, 너무 강하면 서기/전진 보상 자체를 압도할 위험이 있어 -25.0~-30.0 범위에서 시작한다.

---

### 3.2 `diagonal_coupling` 보상 경로 차단

`diagonal_joint_coupling_reward`에 **rear-left 활성도 게이트** 추가.

```python
# 현재: pair_b (FR+RL) 상관을 무조건 합산
# V25: RL contact_ratio < 0.15이면 pair_b 기여를 0으로 차단
rl_gate = (metrics["contact_ratio_rl"] > 0.15).float()  # shape: (num_envs,)
corr_b = corr_b * rl_gate  # pair_b(FR+RL) 기여 차단
```

- rear-left가 collapse 상태이면 FR+RL 대각 커플링 보상을 받지 못함
- 3다리 보행으로 `diagonal_coupling` 획득하는 경로를 직접 차단

---

### 3.3 Restart-on-Collapse 전략

`heartbeat.py`에 collapse 조기 감지 후 자동 run 종료 로직 추가.

#### 감지 조건 (모두 만족 시)

```
iter <= 300
AND contact_ratio_rl < 0.05 (3 consecutive heartbeat, ~30 iter)
AND swing_time_rl > 0.95
AND propulsion_rl < 0.01
```

#### 동작

1. collapse 감지 → Telegram 알림: `COLLAPSE DETECTED — iter N, restarting`
2. 현재 run 정지 (`common.stop_training()`)
3. from-scratch 재시작 (`common.launch_training()`, 체크포인트 없이)
4. `restart_count` 증가 (최대 5회 제한, 초과 시 알림 후 중단)

```python
# heartbeat.py 추가 변수
restart_count = 0
MAX_RESTARTS = 5
consecutive_collapse_count = 0
COLLAPSE_CONFIRM_STEPS = 3  # 3 heartbeat 연속 확인
```

> **왜 iter 300 이전인가?**
> iter 381에서 이미 contact_ratio_rl = 0.104로 하락 시작이 관측됐음. iter 300 이전에 개입하면 고착화 이전에 차단 가능.

---

### 3.4 V24 Validity Ramp 수정

| 항목 | V24 | V25 |
|------|-----|-----|
| `limb_usage_min_penalty` ramp 시작 | iter 200 | iter 0 |
| `rear_left_right_usage_diff_penalty` ramp 시작 | iter 200 | iter 0 |
| ramp 구간 | 200~600 | 0~200 (빠른 안정화) |
| `limb_usage_min_penalty` weight | -3.0 → -12.0 | -2.0 → -10.0 (직접 패널티 보조) |
| `rear_left_right_usage_diff_penalty` weight | -2.0 → -8.0 | -2.0 → -8.0 (유지) |

기존 `_crr_validity_ramp_start=200`을 `0`으로 변경, `_crr_validity_ramp_end=200`으로 단축.

---

### 3.5 변경 파일 요약

| 파일 | 변경 내용 |
|------|----------|
| `mdp/rewards.py` | `rear_left_contact_floor_penalty()` 추가; `diagonal_joint_coupling_reward()` RL gate 추가 |
| `spot_micro_rl_env_cfg.py` | `TRAIN_VERSION = "V25"`;  `rear_left_contact_floor_penalty` RewTerm 추가; validity ramp 파라미터 수정; `diagonal_coupling` 수정 반영 |
| `scripts/heartbeat.py` | restart-on-collapse 로직 추가: collapse 감지, run 종료, 재시작, 횟수 제한 |
| `scripts/common.py` | `LIMB_VALIDITY_THRESHOLDS` floor_target 추가; collapse 판정 조건 업데이트 |

---

## 4. 성공 기준

### 4.1 V25 Hard Safety Gate (V24와 동일)

| 기준 | 목표 |
|------|------|
| survival | iter 600+ ≥ 90% |
| ep_len | ≥ 200 |
| value_loss | < 150 (critic shock 없음) |

### 4.2 Collapse Prevention Gate (신규)

| iter | contact_ratio_rl 기준 | 판정 |
|------|----------------------|------|
| 200 | ≥ 0.10 | collapse_free_early |
| 300 | ≥ 0.15 | no_restart_triggered |
| 600 | ≥ 0.25 | limb_validity_early_pass |
| 1000+ | ≥ 0.35 | limb_validity_full_pass |

### 4.3 Limb Validity Gate (V24 대비 강화)

| 기준 | V24 결과 | V25 목표 |
|------|---------|---------|
| `limb_validity_gate` 통과 checkpoint | 0개 | ≥ 1개 (iter 800+) |
| `contact_ratio_rl` at iter 1000 | 0.000065 | ≥ 0.30 |
| `rear_usage_diff` | 0.925 | ≤ 0.25 |
| restart-on-collapse 발동 횟수 | — | ≤ 2 (안정 수렴 지표) |

### 4.4 Gait 품질 (V24 수준 유지)

| 기준 | 목표 |
|------|------|
| gait score | ≥ A |
| posture score | ≥ B |
| reward (iter 1000+) | ≥ 400 |

---

## 5. 실험 전략

### 5.1 From-Scratch 재시작

V24 run에서 rear-left collapse가 iter 381 이전부터 진행 중이었으므로, V24 체크포인트에서 재개하는 것은 의미 없다. **from-scratch**로 시작한다.

### 5.2 Early Observation (iter 0~300)

- heartbeat를 50 iter 간격으로 강화 (기본 100 → 첫 300 iter는 50)
- contact_ratio_rl 추이를 조기에 확인
- iter 200 시점에 manual checkpoint 확인 권장

### 5.3 분기 시나리오

| iter 300 관측 | 대응 |
|--------------|------|
| contact_ratio_rl ≥ 0.10 | 계속 진행 (V25 전략 유효) |
| contact_ratio_rl < 0.05 + restart 미발동 | restart-on-collapse 로직 디버그 필요 |
| restart 3회 이상 발동 | rear_left_contact_floor_penalty weight 증가 (-30.0~-40.0) 검토 |
| restart 0회, contact_ratio_rl ≥ 0.20 | 이상적 경로 — iter 600까지 관찰 계속 |

---

## 6. 운영 주의사항

V24와 동일한 운영 구조 유지:

```
supervisor.cmd --listen    ← 유일한 진입점
    → heartbeat.py (50 iter: 초기 300 iter / 100 iter: 이후)
    → 1000 iter: 자동 영상 리포트
```

- `restart-on-collapse`는 heartbeat 프로세스 내에서 동작 — supervisor 재시작 불필요
- 재시작 후 새 run timestamp가 생성됨 — heartbeat가 `_get_resume_checkpoint_iter()` 로직으로 milestone skip 처리
- restart 알림 메시지 형식: `COLLAPSE RESTART (K/M) — iter N, c_rl=X.XXX`

---

## 7. V24 대비 변경 요약

| 항목 | V24 | V25 |
|------|-----|-----|
| 핵심 패널티 방식 | 간접 (min_usage proxy) | **직접** (contact_ratio_rl lower-bound) |
| 패널티 시작 시점 | iter 200 | **iter 0** |
| diagonal_coupling 경로 | 차단 없음 | **RL 비활성 시 pair_b 차단** |
| collapse 대응 | 패널티로 교정 시도 | **run 재시작 (hard reset)** |
| 기존 V24 term | — | 유지 (보조 신호) |

---

## 8. 위험 요소 및 대비

| 위험 | 가능성 | 대비 |
|------|--------|------|
| `rear_left_contact_floor_penalty`가 너무 강해 서기 학습 방해 | 중 | iter 300 ep_len 확인; 필요 시 weight -20.0으로 하향 |
| RL gate로 `diagonal_coupling`이 너무 약해져 gait 품질 저하 | 중 | gate threshold 0.15 → 0.08로 완화 가능 |
| restart-on-collapse가 정상 탐색 구간을 조기 종료 | 낮음 | 3 consecutive heartbeat 확인 조건으로 false positive 방지 |
| 5회 restart 후에도 collapse 지속 | 낮음 | weight -40.0으로 단계적 강화 |
| V24 indirect term과 V25 direct term 간 중복 패널티 과부하 | 낮음 | V24 `limb_usage_min_penalty` weight -12.0 → -8.0으로 소폭 감소 |

---

## 9. 참고 문서

- `plan/V24_ANALYSIS.md` — V24 실패 원인 상세 분석
- `plan/CURRENT_STATE_2026-03-15.md` — V24 최종 세션 상태
- `plan/MEMORY.md` — active handoff
