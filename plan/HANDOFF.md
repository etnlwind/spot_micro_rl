# HANDOFF.md

> 마지막 업데이트: 2026-03-17
> 이전 세션 커밋: `0d57630` (develop 브랜치)

---

## 1. 현재 목표

**V29 훈련 시작 및 모니터링**

V28 시리즈 → V29 진행 상황:
- V28: iter 1000 이후 RL collapse → 실패
- V28.1: run 재기동 후 RR collapse → 실패
- **V28.2: rear pair 대칭 완전 달성 (iter 1703: rear_usage_diff=0.012) → 성공**
- **V28.3: front contact cap(-10.0) 추가했으나 FL/FR contact 고착 미해결 → 실패**
- **V29: 구현 완료, 훈련 시작 대기 중** ← 현재 위치

V28.3 실패 근본 원인: contact_residency band_low만 존재(상한 없음) → FL 0.83도 최대 reward → 외부 패널티로는 한계.
V29 목표: reward 구조 내부 개혁 — band_high=0.65 추가 + stride_length + swing_gate_velocity.

---

## 2. 수정한 파일과 핵심 변경점

### V29 (커밋 `0d57630`) ← 최신

**`source/.../mdp/rewards.py`**
- `_update_v281_contact/prop/usage_ema`: band_high 파라미터 추가 (contact > band_high이면 in_band=0)
- `per_leg_contact/prop_band_residency_reward`: band_high=1.0 (default, cfg에서 0.65로 전달)
- `limb_usage_band_residency_reward`: band_high 추가
- `swing_quality_gated_velocity()` 신규:
  - 4발 swing ratio EMA를 계산하여 min()을 bottleneck으로 사용
  - min_swing_ratio(=0.15) 이상일 때만 heading_velocity를 보상
  - 앞발만 땅에 붙이고 뒷발만 스윙하는 벌레걸음 원천 차단
- `_curriculum_apply_v281_weights`: V28.3 항목(#6 front_cap, #7 front_balance) → V29(#6 stride_length, #7 swing_gate)
- `reward_weight_curriculum`: V28.3 파라미터 전체 → V29(stride_length_ramp, swing_gate_ramp) 교체

**`source/.../spot_micro_rl_env_cfg.py`**
- `TRAIN_VERSION = "V29"`
- `lin_vel_z_l2`: -0.7 → **-2.0** (수직 진동 억제 강화)
- `ang_vel_xy_l2`: -0.2 → **-1.0** (몸통 흔들림 억제 강화)
- `contact_residency`: band_low 0.20→0.25, **band_high=0.65 추가**
- `prop_residency`: **band_high=0.65 추가**
- `usage_residency`: **band_high=0.65 추가**
- `front_pair_contact_cap` RewTerm **삭제** → `swing_gate_velocity` RewTerm **추가**
- `front_rear_support_balance_penalty` max_diff: 0.30 → 0.50 원복
- `stride_length`: target_stride 0.06→**0.10**, weight 12.0→**0.0** (curriculum 제어)
- TRAINING_CONFIG: front_cap/front_balance → stride_length(max=12.0, 400~700) + swing_gate(max=15.0, 600~900)

---

### 이전 버전 참고

**V28.3 (커밋 `c50925f`)**
- `front_pair_contact_cap_penalty()` 신규 (contact_cap=0.65, max=-10.0, ramp 700~1000)
- 결과: FL contact 0.83~0.88 고착 유지 → 실패

**V28.2 (커밋 `745d7b6`)**
- `rear_pair_contact_diff_penalty()` 신규 — rear 대칭 강제
- 결과: iter 1703 rear_usage_diff=0.012 → **성공**

---

## 3. 아직 안 끝난 작업

### 즉시 필요
- [ ] **V29 훈련 시작** — supervisor 재시작 후 `/start` 명령

### V29 훈련 중 모니터링

| 체크포인트 | 핵심 지표 |
|-----------|---------|
| iter 400 | stride ramp 시작 — FL/FR contact EMA 변화 방향 확인 |
| iter 600~700 | FL/FR contact < 0.75 (band_high 효과 발현) |
| iter 700 판정 | FL/FR contact < 0.75, rear_usage_diff < 0.10 |
| iter 900 판정 | FL/FR contact < 0.65, FL/FR swing > 0.25, front-rear diff < 0.25 |
| iter 1200 최종 | FL/FR contact 0.50~0.65, diagonal_coupling_raw > 0.70 |

### V29 경보 기준 (heartbeat)
| 지표 | 경보 기준 | 액션 |
|------|----------|------|
| rear_pair_residency_gap | > 0.15 ⚠️ | rear 불안정 감시 |
| contact_band_residency_rr | < 0.30 🔴 | 즉시 확인 |
| FL/FR contact (iter 700+) | 계속 증가 또는 > 0.80 | ramp 재검토 |
| rear_usage_diff (iter 700+) | > 0.20 | 즉시 중단 고려 |

### V29 결과에 따른 후속
- FL/FR contact < 0.65 달성 → V29 ANALYSIS 작성 후 V30 계획
- iter 900 swing < 0.25 미달 → **V29b: swing_gate min_swing_ratio 조정**
- rear 불안정 재발 → 즉시 중단, rear 우선 재검토

---

## 4. 다음 액션

### 즉시 (훈련 시작)
```
1. supervisor.cmd 실행 (supervisor 재시작)
2. Telegram /start 명령
3. heartbeat 확인 (iter 100, 200, 300 초기 상태)
```

### iter 600 체크포인트
heartbeat에서:
- FL/FR contact < 0.78 (band_high 효과 시작)
- rear_usage_diff < 0.10
- swing_gate reward 증가 방향 확인

### iter 900 핵심 판정
- FL/FR contact < 0.65 ✅
- FL swing > 0.25, FR swing > 0.25 ✅
- front-rear diff < 0.25 ✅
- diagonal_coupling_raw > 0.60 ✅

---

## 5. 실행/검증 명령

### heartbeat 로그 분석 (Python)
```bash
python3 -c "
import json, sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
path = 'logs/rsl_rl/spot_micro_flat/<RUN_NAME>/heartbeat_reports.jsonl'
with open(path, encoding='utf-8') as f:
    records = [json.loads(l) for l in f if l.strip()]
for r in records:
    k = r['kpi_snapshot']
    print(f'iter {k[\"iter\"]}: reward={k[\"reward\"]:.1f} FL={k.get(\"contact_ratio_fl\",0):.3f} FR={k.get(\"contact_ratio_fr\",0):.3f} RL={k.get(\"contact_ratio_rl\",0):.3f} RR={k.get(\"contact_ratio_rr\",0):.3f} fl_sw={k.get(\"swing_time_fl\",0):.3f} fr_sw={k.get(\"swing_time_fr\",0):.3f} rdiff={k.get(\"rear_left_right_usage_diff\",0):.3f} valid={k.get(\"limb_validity_pass\")}')
"
```

### 최신 run 디렉토리 확인
```bash
ls -lt logs/rsl_rl/spot_micro_flat/ | head -5
```

---

## 6. 주의사항

### 운영
- **supervisor는 반드시 프로젝트 루트의 `supervisor.cmd`로만 실행**
- **rewards.py / env_cfg.py 수정 시 supervisor 재시작 필수**
- **실행 중인 훈련은 명시적 요청 없이 중단/재시작 금지**

### 코드
- **버전별 상수는 TRAINING_CONFIG에서 읽어야 함** (rewards.py에 하드코딩 금지)
- **TRAIN_VERSION 동기화 항상 검증**

### V29 설계 원칙
- **band_high=0.65는 residency 내부 구조** — cap 패널티(외부)와 다름
  - FL contact 0.65 초과 시 residency reward 0 → 고착이 손해
- **swing_gate_max=15.0** (분석팀 제안 12.0보다 강하게, 20.0보다 약하게)
- **stride_length target=0.10m** (V17 0.06m 대비 보폭 목표 확대)
- **stability penalty 과강도 시 첫 조정 후보**: lin_vel_z_l2, ang_vel_xy_l2 모두 강화 — iter 500 전 reward 급락 시 -1.0/-0.5로 되돌릴 것

### 참고 문서
- `plan/V29_PLAN.md` — V29 설계 전체 **(필독)**
- `plan/V28.3_ANALYSIS.md` — V28.3 실패 분석 (band_high 부재 근본 원인)

---

## 현재 브랜치 상태

```
브랜치: develop
최신 커밋: 0d57630 — Implement V29: residency band_high + stride_length + swing_gate_velocity
원격 동기화: ✅ push 완료
```

### V28.3 실측 참고값 (iter 2200, 훈련 종료)
| 지표 | 값 |
|------|-----|
| reward | ~580 |
| FL contact / swing | 0.83~0.88 / 0.11~0.16 |
| FR contact / swing | 0.83~0.88 / 0.11~0.16 |
| RL contact / swing | ~0.50 / ~0.50 |
| RR contact / swing | ~0.49 / ~0.51 |
| rear_usage_diff | ~0.012 |
| front-rear diff | ~0.37 |
| 결과 | front 고착 미해결 → 실패 |
