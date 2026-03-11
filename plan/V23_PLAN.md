# V23 Plan — Training Strategy Reset on Top of V22 Observability

## 1. 목표

V23의 목표는 V22에서 정리된 운영/아티팩트 체계를 유지한 채, **실제 gait 품질을 끌어올리는 학습 전략 변경**을 정의하는 것이다.

## 2. 현재 출발점

- 학습 버전 태그: `V20`
- 운영/아티팩트 버전: `V22`
- 최종 검증 런: `logs/rsl_rl/spot_micro_flat/2026-03-11_02-39-01`
- 최종 checkpoint: `model_15000.pt`
- 최신 artifact: `clip_1005_iter15000_20260311_132732.zip`

## 3. V22 기준 핵심 문제

- 최종 판정은 여전히 `C (초기 보행 패턴)` 수준
- `gait_cycle_period = 0`
- `stride_length = 0`
- `standing_height`가 낮아 기립 안정성이 부족함
- 분석 리포트상 생존율/안정성은 아직 학습 목표 대비 부족함

## 4. V23에서 먼저 정해야 할 것

### 4.1 학습 시작 전략

둘 중 하나를 먼저 결정:

1. `model_9600.pt` 또는 `model_15000.pt` 기반 resume/fine-tune
2. from-scratch 재학습

판단 기준:

- V20이 이미 쓸 만한 gait seed를 갖고 있는가
- reward 구조 변경 폭이 critic을 다시 깨뜨릴 정도로 큰가

### 4.2 reward 변경 범위

우선 검토 후보:

- `standing_height`와 관련 posture 계열 재조정
- `gait_cycle_period`, `stride_length` 활성화 조건 완화 여부
- `forward_velocity`와 `diagonal_coupling`의 균형 재조정
- 과한 penalty가 다시 stillness trap을 만들지 않는지 점검

### 4.3 검증 기준

V23은 아래 지표 개선을 최소 기준으로 둔다:

- `standing_height` 유지
- `forward_velocity` 증가
- `diagonal_coupling` 유지 또는 개선
- `gait_cycle_period > 0`
- `stride_length > 0`
- `gait_score`와 `stability_score` 개선

## 5. 변경 금지선

- contact sensor 보상에 다시 과도하게 의존하지 않기
- 한 번에 너무 많은 reward를 동시에 증감하지 않기
- critic shock를 유발하는 hard switch를 다시 도입하지 않기

## 6. V23 착수 체크리스트

- [ ] resume vs from-scratch 결정
- [ ] 바꿀 reward 항목 3개 이하로 제한
- [ ] KPI 목표값 명시
- [ ] 비교 대상 checkpoint 지정
- [ ] 첫 2K iter 검증 계획 작성

## 7. 권장 첫 액션

가장 안전한 시작은 아래 순서다:

1. `model_9600.pt`와 `model_15000.pt` 중 어느 쪽이 gait seed가 더 나은지 V22 artifact 기준으로 비교
2. `standing_height / gait_cycle_period / stride_length` 세 축만 좁게 수정
3. 작은 범위 실험 후, V22 artifact 체계로 즉시 비교