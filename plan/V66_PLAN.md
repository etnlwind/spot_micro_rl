# V66 PLAN: Phase Randomization (부분 성공)

## 1. 배경

V64(mirror), V65(curriculum) 실패 후 **V63.I 진단 데이터 재분석**으로 핵심 통찰 도출:

```
V63.I 대각 diff 추이:
  iter 300:  2.1%p  ← 대칭 (아직 쓰러지는 단계)
  iter 500:  11.1%p ← ★ 여기서 갈라짐!
  iter 3000: 0.5%p  ← 일시 수렴 (대칭 가능함 입증!)
  iter 3500: -0.4%p ← 거의 대칭
  iter 4000: 4.8%p  ← 다시 갈라짐
  iter 4999: 12.6%p ← 고착
```

**근본 원인**: 4096 env 모두 동일 phase(FL=0)에서 시작 → FL+RR이 항상 "첫 stance" → 초기 탐색에서 FL+RR 유리 → gradient 일관 편향 → frozen diagonal.

이 통찰은 V64의 mirror/penalty 접근이 아닌 **환경 초기화 자체를 바꾸는** 접근으로 이어짐.

## 2. 설계

### Phase offset randomization
```python
def _get_phase_offset(env):
    reset_mask = (env.episode_length_buf <= 1)
    if reset_mask.any():
        env._v66_phase_offset[reset_mask] = torch.rand(...) * 2 * math.pi
    return env._v66_phase_offset
```

- Episode reset 시 각 env에 random phase offset 부여
- `phase_clock_obs`와 `asymmetric_joint_target_reward` 양쪽에 적용
- ~50% env: FL first stance, ~50%: FR first stance → gradient 평균 편향 0

### Reward: V63.I 완전 동일
- true_trot_pattern: 7.0
- 모든 penalty 유지
- **mirror loss, curriculum, alternation 불필요**

## 3. 실험 과정

### V66 (binary offset: 0 또는 π)

| iter | FL | FR | RL | RR | diff | 해석 |
|------|------|------|------|------|------|------|
| 772 | 47.6 | 42.3 | 38.5 | 44.9 | 5.6%p | V63.I(130%p)의 1/23! |
| 1114 | 45.6 | 42.6 | 39.8 | 43.0 | **3.0%p** | 역대 최고 |
| 2212 | 44.1 | 40.5 | 39.9 | 41.7 | 3.5%p | 안정 유지 |
| 2636 | 46.2 | 37.4 | 37.5 | 43.9 | **15.2%p** | ★ 급증! |

**GUI 확인**: "한 걸음에서 다음 걸음으로 옮겨갈 때 부드럽지 않고 끊어짐" — **double-step**.
**원인**: Binary offset(0/π)은 두 모드의 절충 궤적 → 어느 쪽에도 완전 최적화 안 됨.

### V66.1 (continuous offset: 0~2π)

변경: `randint(0,2)*π` → `rand()*2π` (1줄 수정)

| iter | FL | FR | RL | RR | diff | stride |
|------|------|------|------|------|------|------|
| 398 | 43.8 | 42.8 | 28.7 | 29.0 | 4.6%p | — |
| 766 | 47.6 | 42.3 | 38.5 | 44.9 | 5.6%p | 4.40 |
| 1114 | 45.6 | 42.6 | 39.8 | 43.0 | **3.0%p** | 4.38 |
| 1872 | 44.5 | 42.7 | 40.3 | 42.2 | **2.0%p** | — |
| 2252 | 44.1 | 40.5 | 39.9 | 41.7 | 3.5%p | 4.38 |
| 2636 | 46.2 | 37.4 | 37.5 | 43.9 | **15.2%p** | — |

**iter 0~2000: 대칭 2~6%p** (역대 최고 당시), **iter 2500+: 15%p 급증** (true_trot exploit 재발견).

### V63.I GUI 비교
사용자 관찰:
- **V63.I model_2000**: "FR이 좀 이상한데 이게 훨씬 자연스럽다"
- **V66.1 model_2300**: "보폭을 두번에 나눠서 딛는 느낌"

## 4. 분석: 왜 후반에 편향 재발?

V66.1 iter 2252→2636에서 **reward가 363→386으로 상승하면서 diff가 3.5→15.2%p 급증**.
**편향이 커질 때 reward가 올랐다** = **reward landscape이 편향을 보상하는 구조**.

Phase randomization은 **초기 gradient 편향을 제거**하지만, policy가 충분히 학습되면 **reward landscape을 깊이 탐색** → "편향이 이득"임을 재발견 → 같은 곳에 수렴.

### true_trot_pattern의 구조적 결함
```
Balanced trot: inter_diff 교대 시 잠깐 떨어짐 → 평균 0.84
Frozen trot:   교대 없이 inter_diff 항상 ~1.0 → 평균 0.93
→ Frozen이 true_trot에서 0.09 더 높음
→ weight 7.0 × 0.09 = 0.63/step → 1000 step = 630 per episode
```

## 5. 한계

**Phase randomization = "출발점 편향" 해결 ✅, "목적지 편향"(reward landscape) 미해결 ❌**

## 6. 교훈

1. **Phase randomization은 초기 2000 iter 대칭 유지에 효과적** — V63.I 대비 대칭 5~8배 개선
2. **Binary(0/π)보다 continuous(0~2π)가 자연스러운 궤적** — double-step 방지
3. **단독으로는 근본 해결 불가** — true_trot reward landscape이 편향을 보상하는 한 결국 재발
4. **V68에서 reference tracking과 결합 시 출발점+목적지 대칭 동시 확보에 성공**
5. **사용자 GUI 관찰이 수치를 넘어서는 통찰 제공** — "FR 다쳤다", "double-step", "왼발 오래 닿음"
