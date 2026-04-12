# V66 PLAN: Phase Randomization (부분 성공)

## 1. 배경

V64(mirror augmentation), V65(curriculum) 실패 후 데이터 재분석.
**V63.I 진단 데이터**에서 핵심 발견:

```
iter 300:  대각 diff 2.1%p  ← 대칭
iter 500:  대각 diff 11.1%p ← 여기서 갈라짐!
```

모든 4096 env가 **동일한 phase(FL=0, FR=π)**에서 시작 → FL+RR이 항상 "첫 stance" → gradient 일관 편향 → frozen diagonal.

## 2. 접근

Episode reset 시 env별 **random phase offset** 부여.
절반의 env가 FL first stance, 나머지가 FR first stance → policy gradient 평균 편향 0.

### V66 (binary offset: 0 또는 π)
- 대칭 5%p 달성 (V63.I 12.6%p 대비 개선)
- **GUI: double-step 부자연스러움** — 두 모드의 절충 궤적

### V66.1 (continuous offset: 0~2π)
- 대칭 2~6%p (역대 최고 당시)
- GUI: double-step 개선
- **iter 2500+에서 편향 재발** (3.5→15.2%p)

## 3. 결과

```
V66.1 대칭 추이:
  iter 398:  4.6%p  ← 초기 대칭 우수
  iter 766:  5.6%p
  iter 1114: 3.0%p  ← 최저!
  iter 1872: 2.0%p  ← 역대 최저!
  iter 2636: 15.2%p ← 급증 (true_trot exploit 재발견)
  iter 3034: 6.2%p  ← 우세 페어 전환
```

## 4. 한계

Phase randomization은 **"출발점 편향"을 제거**하지만, **"목적지 편향"(reward landscape)**은 해결 못 함.
true_trot_pattern이 편향 trot에 더 높은 reward를 주는 구조가 불변 → policy가 충분히 학습되면 exploit 재발견.

## 5. 교훈

1. Phase randomization은 초기 2000 iter 대칭 유지에 효과적
2. Binary(0/π)보다 continuous(0~2π)가 자연스러운 궤적 생성
3. **Phase randomization만으로는 근본 해결 불가** — reward landscape 수정 필요
4. 단, V68에서 reference tracking과 결합 시 **출발점+목적지 대칭 동시 확보**에 성공
