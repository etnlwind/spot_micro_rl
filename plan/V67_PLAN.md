# V67 PLAN: Balance-Gated True Trot (부분 성공 → 보행 품질 실패)

## 1. 배경

V66.1에서 phase randomization이 iter 2500+에서 편향 재발.
**원인 분석**: true_trot_pattern이 frozen diagonal에 더 높은 reward 부여.

```
Balanced trot: intra×inter 교대 시 inter 잠깐 떨어짐 → 평균 0.84
Frozen diagonal: 교대 없이 inter 항상 1.0 → 평균 0.93
→ Frozen이 reward에서 유리 → policy가 편향 선택
```

## 2. 접근

`balanced_true_trot = intra × inter × balance_factor`

- balance_factor: EMA(decay 0.95) 기반 4발 contact 균등도
- frozen diagonal: factor ≈ 0.007 → reward ≈ 0
- balanced trot: factor ≈ 0.51 → reward 유지
- **72배 차이**: frozen(0.006) vs balanced(0.43)

Phase randomization(V66.1 continuous) 병행.

## 3. 결과

### 대칭: 역대 최고
```
대칭 추이:
  iter 784:  1.0%p  ← 역대 최저!
  iter 1164: 1.3%p
  iter 1542: 0.8%p
  iter 1872: 2.0%p
  iter 3034: 6.2%p → 8.0%p → 19.3%p(과도기) → 4%p(자기 교정!)
→ 자기 교정 메커니즘 확인 (V66.1에서 없던 기능)
```

### 보행 품질: 실패
| 지표 | V63.I | V67 |
|------|------|------|
| stride | 4.35 | **2.23** (−49%) |
| anti_pace | -0.064 | **-0.656** (10배 악화) |
| lateral_balance | -0.502 | **-0.844** |
| propulsion RL | 0.435 | **0.286** |
| GUI | FR 약간 이상 | **앞다리 오른쪽 drift, RL 후방 slip** |

### V67.1: stance_slip + lateral_vel + anti_pace 보강
- 코덱스 권장 보수안: ang_vel_xy 유지, anti_pace -4(not -5)
- 결과 예측: balance gate가 근본 문제 → penalty 추가로 해결 어려움

## 4. 근본 원인

Balance gate가 **contact 시간 대칭은 강제**하지만:
- 발 배치(foot placement) 품질은 보지 않음
- Policy가 "slip/drift로 contact 시간 맞추기" exploit 발견
- 결과: contact 대칭 ✅ + 보행 품질 ❌

## 5. 교훈 (3계층 대칭)

| 계층 | V63.I | V67 |
|------|------|------|
| Contact 시간 대칭 | ❌ 12.6%p | ✅ 2.7%p |
| Propulsion 대칭 | ⚠️ | ❌ |
| Foot placement 대칭 | ⚠️ | ❌ (drift) |

1. **Contact ratio 균등 ≠ 좋은 보행** — V67의 핵심 교훈
2. Balance gate의 **자기 교정 메커니즘**은 유효 (19%p→4%p 복귀)
3. 하지만 보행 품질 유지와 동시에 대칭 강제는 **reward 구조만으로 불가능**
4. → V68의 reference tracking 접근으로 해결
