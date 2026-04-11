# V65 PLAN: Curriculum Trot — true_trot → alternation 전환

## 1. 근본 원인 (V63~V64 시리즈 확정)

```
true_trot_pattern = intra_sync × inter_diff

문제: 매 순간의 contact 패턴만 측정, 시간축 역할 교대 미요구
→ FL+RR 영구 stance + FR+RL 영구 swing = "frozen diagonal"도 만점
→ 보조 penalty(leg_lr_symmetry, stance_ratio_balance, per_leg_contact_min)는
  true_trot의 exploit 보상을 이길 수 없음 (데이터로 확정)
```

### 증거
| Run | 상태 | true_trot_pattern | 대각 diff |
|---|---|---|---|
| V63.I | balanced | +6.51 | 12.6%p |
| V64 fail 1824 | frozen diagonal | +6.07 | 137.8%p |
| V64.2 restored | leg_lr 복원해도 frozen | +3.27 | 89.5%p |

## 2. 왜 단순 교체(V63.J)가 실패했는가

V63.J: `true_trot 7→2, alternation_trot +5` (from-scratch)
→ 부트스트랩 실패: alternation은 trot이 있어야 보상 → trot이 없으면 보상 0
→ true_trot 2.0만으론 trot 유도력 부족 → 보행 자체가 늦어짐

**닭-달걀 문제**: alternation은 trot 필요, trot 유도는 true_trot 필요, true_trot은 exploit 보상

## 3. V65 해결: Curriculum으로 닭-달걀 분리

### Phase 1: 부트스트랩 (iter 0~800)
- `true_trot_pattern` weight **4.0** → gait 형성 유도
  (코덱스 리뷰: 3.0은 V63.J(2.0) 부트스트랩 실패 데이터 기준 부족 위험)
- `alternation_trot` weight **0** → 아직 trot 없으니 측정 의미 없음
- `per_leg_contact_exp` threshold **0.30** (초기 완화)
- 목표: 서기 → 걷기 시작

### Phase 2: 전환 (iter 800~3000)
- `true_trot_pattern` weight **4.0 → 0.5** (linear ramp-down, 800~2500)
- `alternation_trot` weight **0 → 5.0** (linear ramp-up, 800~3000)
- `per_leg_contact_exp` threshold **0.30 → 0.40** (ramp, 1500~3000)
- 목표: 형성된 gait를 시간축 교대로 전환
- 핵심: V63.J 데이터에서 대각 편향 iter 2000~2500에 발생
  → alternation이 이 시점 전에 충분한 weight 확보 필요
  → iter 2000: alternation weight = (2000-800)/(3000-800)×5 = 2.73 (방어력 확보)

### Phase 3: 유지 (iter 3000+)
- `true_trot_pattern` weight **0.5** (보조, intra_sync 유지용)
- `alternation_trot` weight **5.0** (주연)
- `per_leg_contact_exp` threshold **0.40** (최종)
- 목표: 대칭 trot 고착

### Curriculum 시각화
```
Weight
  5│                           ╭──── alternation_trot (0→5)
  4│ ████╲                    ╱
  3│      ╲                  ╱
  2│       ╲                ╱
  1│        ╲              ╱
0.5│         ╲────────────╱──── true_trot_pattern (4→0.5)
  0│──────────╱────────────────── alternation_trot starts
   └────┬────┬────┬────┬────┬──
       500  1000 1500 2000 2500 3000  iter
```

### per_leg_contact_exp threshold ramp
```
Threshold
0.40│                    ╭────────
0.35│                   ╱
0.30│ ████████████████╱
   └────┬────┬────┬────┬──
       500  1000 1500 2000 3000  iter
```

## 4. per_leg_contact_min 강화

현재: `gap = clamp(0.40 - min_ratio, 0)`, weight -8
→ RL=4%에서도 gap=0.36 → -2.88/step, 감당 가능

### 변경: 지수 penalty (threshold 이하에서 급격히 증가)
```python
gap = clamp(threshold - min_ratio, 0)
penalty = exp(gap * sharpness) - 1  # gap 커질수록 기하급수적

# sharpness=10:
#   gap=0.05: exp(0.5)-1 = 0.65
#   gap=0.10: exp(1.0)-1 = 1.72
#   gap=0.20: exp(2.0)-1 = 6.39
#   gap=0.35: exp(3.5)-1 = 32.12  ← RL=5%면 penalty 32!
```

Weight -1.0 (지수라 자체 스케일 큼)

## 5. 기타 유지

- `leg_lr_symmetry` -2.0 (보조 안전장치)
- `mirror_loss` coeff 1.0 (soft constraint)
- `stance_ratio_balance` +5.0
- `swing_body_forward` +4.0, `effective_stride` +5.0
- `clearance_lift` +3.0, `base_height_target` +4.0
- `asymmetric_joint_target` +5.0

## 6. 수치 검증: Frozen Diagonal Budget (Phase 3 기준)

### Phase 3에서 frozen diagonal 시도 시:
```
true_trot_pattern(w=0.5):   +0.5 × 0.93 = +0.47  (대폭 축소!)
alternation_trot(w=5.0):    +5.0 × 0.0 = 0        (교대 없으므로 0)
leg_lr_symmetry(w=-2.0):    -2.0 × 2.0 = -4.00
per_leg_contact_exp(w=-1):  -1.0 × 32 = -32.0     (지수 penalty!)

NET frozen: 0.47 + 0 - 4.0 - 32.0 = -35.53  ← 강력 음수!
```

### Phase 3에서 balanced trot 시:
```
true_trot_pattern(w=0.5):   +0.5 × 0.93 = +0.47
alternation_trot(w=5.0):    +5.0 × 0.8 = +4.00    (교대 있으므로 높음)
leg_lr_symmetry(w=-2.0):    -2.0 × 1.0 = -2.00    (정상 trot도 순간 비대칭)
per_leg_contact_exp(w=-1):  -1.0 × 0.1 = -0.10    (모든 발 40%+ → 미미)

NET balanced: 0.47 + 4.0 - 2.0 - 0.1 = +2.37  ← 양수!
```

**Balanced trot(+2.37) vs Frozen diagonal(-35.53): 37.9점 차이!**

## 7. 리스크

| 리스크 | 대응 |
|---|---|
| Phase 1에서 true_trot 3.0이 부트스트랩에 부족 | V63.I에서 7.0으로 수렴 → 3.0도 가능성 높음 |
| Phase 2 전환 시 gait 붕괴 | linear ramp (1500 iter)으로 점진 전환 |
| alternation 부트스트랩 느림 (V63.J 재발) | Phase 1에서 true_trot이 gait 형성 → Phase 2 시작 시 이미 trot 있음 |
| per_leg_contact_exp가 정상 보행도 과도 penalty | threshold 0.35로 여유, sharpness 조절 가능 |
| curriculum iter 추정 (common_step_counter/24) | asymmetric_joint_target과 동일 방식, 검증됨 |

## 8. 구현 목록

1. `rewards.py`: `per_leg_contact_exponential_penalty` 신규
2. `rewards.py`: `v65_trot_curriculum` 커리큘럼 함수 신규
3. `env_cfg.py`: V65 블록 (curriculum 활성화, reward weight 초기화)
4. `train.cmd`: RUN_NAME=V65
5. 검증 스크립트
