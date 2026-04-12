# V67 PLAN: Balance-Gated True Trot (대칭 성공, 보행 품질 실패)

## 1. 배경

V66.1에서 phase randomization이 iter 2500+에서 편향 재발.
**데이터 분석으로 원인 확정**:

```
V66.1 iter 2252: diff 3.5%p, reward 363
V66.1 iter 2636: diff 15.2%p, reward 386 (+23!)
→ 편향이 커질 때 reward가 올랐다
→ true_trot_pattern이 편향 trot에 더 높은 reward 부여
```

### true_trot_pattern의 구조적 결함
```python
true_trot = intra_sync × inter_diff

# 이 수식의 문제:
# Frozen diagonal (FL+RR 고정 stance): intra=1, inter=1 → 1.0 (만점!)
# Balanced trot (교대 시 inter 잠깐 0): 평균 ~0.84
# → Frozen이 balanced보다 reward에서 유리
```

## 2. 설계

### Balance-gated true trot
```python
balanced_true_trot = intra × inter × balance_factor

# balance_factor:
ema = 0.95 * ema + 0.05 * contact_mask  # 20-step EMA
err = |ema_FL - mean| + |ema_FR - mean| + |ema_RL - mean| + |ema_RR - mean|
balance_factor = exp(-err / sigma)  # sigma=0.30
```

### 수치 검증
| 상태 | instant_trot | balance | **최종 reward** |
|------|------|------|------|
| Balanced (40~50%) | 0.84 | 0.51 | **0.43** |
| Frozen (5~85%) | 0.93 | 0.007 | **0.006** |
| → **72배 차이!** Frozen은 구조적으로 reward ≈ 0 |

### Phase randomization 병행
V66.1의 continuous offset(0~2π) 유지 → 초기 대칭 + balance gate가 후반 방어.

## 3. 실험 과정

### V67 from-scratch (5000 iter)

| iter | FL | FR | RL | RR | diff | stride | 특이사항 |
|------|------|------|------|------|------|------|------|
| 406 | 39.4 | 39.4 | 23.7 | 23.4 | **0.3%p** | — | 완벽 대칭 출발 |
| 784 | 45.1 | 44.4 | 33.5 | 33.8 | **1.0%p** | 4.09 | 서기+보행 시작 |
| 1164 | 35.3 | 37.9 | 34.8 | 36.1 | **1.3%p** | 4.38 | 역대 최균등 |
| 1542 | 34.1 | 34.4 | 33.5 | 35.2 | **0.8%p** | — | 4발 범위 1.7%p! |
| 1916 | 35.4 | 33.7 | 33.0 | 33.4 | 2.1%p | — | 안정 |
| 2272 | 36.2 | 32.9 | 31.6 | 32.8 | 5.7%p | 4.35 | 미세 상승 |
| 2652 | 36.8 | 35.5 | 31.3 | 32.9 | 8.0%p | — | Pair A 우세 |
| 3034 | 37.0 | 39.1 | 34.0 | 31.9 | 6.2%p | 4.41 | **Pair B로 전환!** |
| 3420 | 36.6 | 40.5 | 35.1 | 30.9 | 8.9%p | 4.23 | B 우세 지속 |
| 3816 | 40.4 | 45.6 | 33.4 | 32.3 | **19.3%p** | **1.26** | ★ 과도기! |
| 4196 | 40.2 | 43.1 | 35.2 | 34.5 | **7.9%p** | 3.62 | **자기 교정!** |
| 4578 | 40.6 | 40.6 | 35.0 | 39.0 | 3.2%p | 2.66 | FL=FR 완벽! |
| 4960 | 41.1 | 38.9 | 35.1 | 36.2 | 2.7%p | 1.81 | stride 하락 |

### 핵심 발견: 자기 교정 메커니즘
iter 3816에서 diff 19.3%p(과도기) → iter 4196에서 **7.9%p로 자동 복귀**.
V66.1에서는 15%p에서 돌아오지 않았는데, V67은 **balance gate가 편향 → reward 감소 → 교정 → 복귀** 피드백 루프 생성.

### 우세 페어 전환
iter 2652까지 Pair A(FL+RR) 우세 → iter 3034부터 **Pair B(FR+RL)로 전환**.
V63.I/V66.1에서는 한 방향 고착이었는데, V67은 **양방향 동등 경쟁** → frozen diagonal 아닌 동적 균형.

## 4. 보행 품질 문제

### V63.I vs V67 전체 비교
| Reward | V63.I | V67 | 판정 |
|------|------|------|------|
| **대칭 diff** | 12.6%p | **2.7%p** | V67 압승 |
| true_trot | +6.51 | +1.75 | *** V67 DOWN (balance gate 비용) |
| **effective_stride** | +4.35 | **+2.23** | *** V67 DOWN (−49%) |
| anti_pace | -0.06 | **-0.66** | V67 10배 악화 |
| ang_vel_xy | -0.22 | **-0.62** | 몸통 흔들림 3배 |
| lateral_balance | -0.50 | -0.84 | 횡방향 불안정 |
| propulsion RL | 0.435 | **0.286** | RL 최저 |

### GUI 관찰
- **"앞다리 2개가 동시에 오른쪽으로 미끄러지는 듯"** (사용자)
- **"RL이 심하게 뒤로 미끄러져"** (사용자, model_3000)
- stride 2.23 = V63.I의 51%

### 원인 분석
Balance gate가 **정상 trot에도 49% 세금** 부과 (sigma=0.30):
```
Balanced trot (err=0.20): balance_factor = exp(-0.67) = 0.51
→ true_trot reward의 49%를 잃음
→ push/stride gradient 약화 → 밀지 못함 → 미끄러짐
```

## 5. V67.1 보강 시도

코덱스 보수안 반영: sigma 0.30→0.40, stance_slip 복원, lateral_vel 추가, anti_pace -3→-4.
**결과**: 훈련 시작 전 "V67.1도 실패할 가능성 높음" 판단 → 중단.

코덱스 분석: "balance gate가 contact 비율 맞추도록 압박 → policy가 foot placement를 slip/drift로 우회 → penalty 추가로 고칠 수 있는 문제인지 불확실"

## 6. 판정: 대칭 3계층

| 계층 | V63.I | V67 | 해석 |
|------|------|------|------|
| Contact 시간 대칭 | ❌ 12.6%p | ✅ 2.7%p | V67 압승 |
| Propulsion 대칭 | ⚠️ | ❌ 전체 약화 | V67 실패 |
| Foot placement 대칭 | ⚠️ FR 약함 | ❌ drift/slip | V67 실패 |

**Contact ratio 균등 ≠ 좋은 보행** — V67의 핵심 교훈.

## 7. 교훈

1. **Balance gate의 자기 교정은 유효** — 편향 시 reward 감소 → 자동 복귀 (V66.1에서 없던 기능)
2. **하지만 보행 품질을 동시에 유지하는 것은 reward 구조만으로 불가능**
3. **"contact 대칭"과 "보행 품질 대칭"은 다른 문제** — 3계층으로 분리해 봐야 함
4. **정상 trot에 대한 "세금"이 너무 크면 stride/push가 붕괴**
5. → V68의 reference tracking 접근으로 해결: 대칭화된 **실제 추진 궤적**을 목표로 설정
