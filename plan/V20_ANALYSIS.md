# V20 Training Analysis — Soft-Ramp Curriculum

> **Log**: `logs/rsl_rl/spot_micro_flat/2026-03-08_17-34-49`  
> **분석일**: 2026-03-08  
> **상태**: 🔄 훈련 진행 중 (초기 단계)

---

## 설계 요약

V19의 **hard phase switch**에서 발생한 critic shock(value_loss 445x spike)를 해결하기 위해, **soft-ramp(선형 보간) curriculum**을 도입.

### Ramp 구간

| 전환 | 구간 | Alpha | 내용 |
|------|------|-------|------|
| Ramp 1 (STAND→WALK) | iter 1,500 ~ 3,000 | alpha12: 0→1 | Phase 1→2 가중치 선형 보간 |
| Ramp 2 (WALK→TROT) | iter 5,500 ~ 8,000 | alpha23: 0→1 | Phase 2→3 가중치 선형 보간 |

### 핵심 메커니즘

- **선형 보간**: `weight = w_prev + alpha × (w_next - w_prev)`
- **Metric gating**: ep_len < 200이면 ramp 일시 정지
- **Update interval**: 10 iter마다 가중치 갱신
- **Snapshot logging**: ramp 시작/완료 milestone + 100 iter 간격

---

## 현재 상태 (iter 17)

| 항목 | 값 |
|------|-----|
| 총 iteration | 17 |
| 현재 Phase | Phase 1 (STAND) — ramp 시작 전 |
| 최종 reward | -20.6 |
| 최종 ep_len | 23.3 |
| 최종 value_loss | 50.01 |
| noise_std | 1.00 (초기값) |

> ⚠️ 아직 초기 학습 단계. Phase 1 가중치로만 학습 중.

### 초기 Gait Metrics (iter 17 기준, weighted)

| Metric | Weighted Value |
|--------|---------------|
| forward_velocity | 0.037 |
| trot_gait | 0.075 |
| diagonal_coupling | 0.189 |
| leg_lift | 1.235 |
| foot_clearance | 0.141 |

---

## V19 대비 기대 효과

V20 soft-ramp의 목표는 다음 V19 문제점을 해결하는 것:

| 항목 | V19 (hard switch) | V20 기대 |
|------|-------------------|----------|
| value_loss spike | 1,000 (445x) @ iter 2000 | < 150 (점진적 증가) |
| reward 급락 | -828 (496→-332) | < V19의 50% |
| ep_len 하락 | 248→243 (98% 유지) | ≥ 200 유지 |
| 회복 시간 | 500+ iter (37% 회복) | 불필요 또는 < 100 iter |

---

## 리뷰어 성공 기준 (5개)

Ramp 1 통과 후 (`iter ≥ 1600`) 자동 검증 예정:

| # | 기준 | 판정 |
|---|------|------|
| ① | Ramp 구간 reward 급락폭 < V19의 50% | ⏳ 대기 |
| ② | value_loss spike < 150 | ⏳ 대기 |
| ③ | ep_len ≥ 200 유지 | ⏳ 대기 |
| ④ | Raw gait metrics 유지 (변화 < 10%) | ⏳ 대기 |
| ⑤ | Raw penalty metrics 점진 개선 | ⏳ 대기 |

---

## 핵심 모니터링 포인트

### Milestone별 체크 일정

| Iter | 이벤트 | 확인 사항 |
|------|--------|----------|
| ~500 | Phase 1 안정화 | reward 상승세, ep_len ≥ 200 도달 |
| 1,500 | Ramp 1 시작 | value_loss 변화, reward 변동폭 |
| 2,250 | Ramp 1 중간 (50%) | critic shock 여부, raw gait 유지 |
| 3,000 | Ramp 1 완료 | V19 대비 spike 비교 |
| 5,500 | Ramp 2 시작 | Phase 2 안정 상태 확인 |
| 6,750 | Ramp 2 중간 (50%) | trot 품질, penalty 적응 |
| 8,000 | Ramp 2 완료 | 최종 Phase 3 진입 |
| 15,000 | 훈련 종료 | 최종 성능 평가 |

---

## 다음 분석 시점

```bash
# iter 1500+ 도달 후 재분석 (Ramp 1 시작)
python scripts/analyze_v20.py

# iter 3000+ 도달 후 재분석 (Ramp 1 완료, V19 비교 가능)
python scripts/analyze_v20.py
```

> 이 문서는 V20 훈련 진행에 따라 업데이트 예정.
