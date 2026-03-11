# V23 Plan — Phase 1 Style-Refinement Preparation

## 1. 목표

V23의 목적은 locomotion core를 유지한 채, **commercial-style quadruped posture/style 쪽으로 보수적으로 refinement**하는 것이다.

중요:

- V23 1차의 정체성은 style 완성 실험이 아니다.
- V23 1차는 style을 신뢰 가능하게 측정하고, posture-first 최소 refinement가 실제로 먹히는지 확인하는 실험이다.
- V23 1차에서는 instrumentation 변경과 reward refinement 변경을 동일 실험에 과도하게 혼합하지 말고, attribution 가능하도록 단계적으로 적용한다.

## 2. 현재 출발점

- 학습 버전 태그: `V20`
- 운영/아티팩트 버전: `V22`
- 최종 검증 런: `logs/rsl_rl/spot_micro_flat/2026-03-11_02-39-01`
- 최종 checkpoint: `model_15000.pt`
- 최신 artifact: `clip_1005_iter15000_20260311_132732.zip`

## 3. 이번 런에 대한 해석

### 3.1 확보된 것

- reward / episode length / timeout 기준으로 locomotion 자체는 성공적이다.
- forward velocity, diagonal coupling, trot-like motion은 실험적으로 유효하다.
- final checkpoint는 refinement 출발점으로 쓸 가치가 충분하다.

### 3.2 아직 남은 것

- front-view 기준 shoulder spread와 stance width가 commercial-style SpotMicro 인상과 다를 수 있다.
- distal foot jitter는 사용자 관찰상 존재 가능성이 있으나, 1차에서는 관측 우선이다.
- rear-driven bias는 아직 가설이며, penalty가 아니라 KPI 검증이 먼저다.
- contact 기반 stride/cycle은 핵심 style 판정 지표로 쓰기 어렵다.

## 4. V23 1차 범위

V23 1차의 진짜 목표는 아래 3개다.

1. instrumentation / export 신뢰도 복구
2. posture/style KPI를 신뢰 가능하게 추가
3. posture-first refinement를 매우 좁게 1차 적용

### 4.1 운영 레이어 전제 (2026-03-11 밤 정리)

- active 운영 엔트리포인트
  - `scripts/supervisor.py`
  - `scripts/heartbeat.py`
  - `scripts/common.py`
- 파일명 변경 기록
  - `scripts/training_supervisor.py` → `scripts/supervisor.py`
  - `scripts/training_heartbeat.py` → `scripts/heartbeat.py`
  - `scripts/training_common.py` / `scripts/v2/common.py` 계열 실험본 → `scripts/common.py`
- `scripts/legacy/supervisor.py`, `scripts/legacy/heartbeat.py`는 과거 운영 코드 참고용 보관본
- `supervisor.py` Telegram 명령
  - `start`
  - `stop`
  - `status`
  - `report`
  - `front`
  - `rear`
  - `top`
  - `side`
  - `help`
- 설계 원칙
  - `start` / `stop`만 훈련 상태를 바꾼다
  - `report/front/rear/top/side`는 훈련 중이면 최신 산출물만 전송한다
  - `report/front/rear/top/side`는 정지 상태에서만 현재 checkpoint 기준 산출물을 새로 생성한다
  - active 경로에서는 auto-resume / emergency resume / supervisor-heartbeat 상호복구 루프를 사용하지 않는다

이번 단계에서 하지 않을 것:

- distal jitter 본격 penalty 다중 추가
- front-rear balance penalty 대량 추가
- rear-specific reward 대규모 감쇄
- full retrain

## 5. 단계 분리

### 5.1 A0 — instrumentation / reporting only

변경 범위:

- heartbeat/history fallback export 개선
- `canonical / derived / estimated / fallback_source` 구분 추가
- `front / side / rear / top / overview` 저장 규칙 고정
- posture/style KPI 추가
- heartbeat 리포트에 Posture/Style 블록 추가

이 단계에서는 reward를 건드리지 않는다.

목표:

- 다음 실험부터 결과 해석이 가능하도록 계측 기반을 정비

### 5.2 A1 — posture-first refinement only

변경 범위:

- shoulder sign / pose convention 검증
- stance width body-frame metric 구현
- stance 결과 기반 항목 1개 내외 추가 또는 기존 항목 재가중치
- 필요 최소 수준의 posture-first refinement 적용

이 단계에서는 아래를 금지한다.

- distal jitter penalty 대량 추가
- front-rear balance penalty 대량 추가

목표:

- spider-like wide stance 인상을 줄이는 최소 변경이 실제로 통하는지 확인

### 5.3 이후 단계

- B: distal jitter refinement
- C: front-rear balance refinement

위 단계는 A1 결과를 보고 별도로 진행한다.

## 6. 핵심 guardrail

- V23 1차 reward 변경은 기존 항목 재가중치 또는 target 조정 우선이며, 완전 신규 항목 추가는 stance 결과를 직접 제어하는 항목 1개 내외로 제한한다.
- 기존 reward 축과 역할이 겹치는 신규 penalty는 추가하지 않는다.
- rear-driven bias는 KPI 검증 전까지 reward penalty로 직접 다루지 않는다.
- contact 신뢰도 검증 전까지 contact 기반 timing 지표는 핵심 style score에 직접 반영하지 않는다.

## 7. V23 1차 KPI

### 7.1 1차 핵심 raw KPI

Posture / Style:

- `stance_width_mean`
- `stance_width_front`
- `stance_width_rear`
- `front_rear_stance_width_diff`
- `shoulder_mean_abs_dev_from_target`
- `shoulder_left_right_diff`
- `shoulder_front_rear_diff`
- `base_height_raw`
- `body_roll_abs`
- `body_pitch_abs`

Distal Motion Quality:

- `foot_joint_action_rate_l2_mean`
- `foot_joint_vel_l2_mean`
- `stance_foot_jitter_score`

Front-Rear Balance:

- 1차에서는 기록 중심으로만 유지
- 실제 imbalance가 확인되면 2차에서 score 반영을 검토

### 7.2 1차 운영 score

- `PostureStyleScore`
	- `stance width` safe-band proximity
	- `shoulder deviation`
	- `body roll/pitch` 안정성
	- `base height raw` 범위 유지
- `FootJitterScore`
	- 1차에서는 예비 운영 score로만 사용
- `FrontRearBalanceScore`
	- 1차에서는 핵심 선택 기준이 아니라 기록 중심

## 8. stance width 원칙

- stance width는 body frame lateral distance 기준으로 계산한다.
- world 좌표 그대로 쓰지 않는다.
- yaw / drift / turning 영향을 줄여서 해석한다.
- 가능하면 contact 구간 또는 low-foot-height 구간 중심으로 집계한다.
- stance width는 1차에서 too-wide 억제가 목표이며, too-narrow 최적화는 목표로 두지 않는다.
- exact target보다 safe band 또는 target band proximity 개념을 우선한다.

## 9. fallback export 원칙

원래 canonical 필드는 유지한다.

- `gait_score`
- `stability_score`
- `survival_pct`

추가 필드:

- `gait_score_estimated`
- `stability_score_estimated`
- `survival_pct_derived`
- `fallback_source`

목표:

- fallback이 완성된 것처럼 보이게 하는 것이 아니라, fallback이 해석 가능하도록 만드는 것
- xlsx와 보고서 모두에서 `canonical / derived / estimated`를 시각적으로 구분

## 10. reward refinement 원칙

V23 1차는 posture-first 최소 변경만 허용한다.

우선 검토 항목:

- 기존 `shoulder_neutral` target / weight 재조정
- `stance_width_penalty` 또는 동등한 stance 결과 기반 항목 1개

shoulder target 관련:

- `-0.04 rad`는 candidate default일 뿐, 즉시 확정하지 않는다.
- 아래를 먼저 검증한다.
	- sign convention
	- 좌/우/전/후 shoulder convention 일관성
	- init pose와 target convention 일관성

## 11. 평가 순서

### 11.1 Hard Safety Gate

다음을 통과하지 못한 checkpoint는 style 후보에서 제외한다.

- fall 0 또는 매우 낮음
- ep_len 기준 유지
- critic / value function 안정
- locomotion core 유지

V23 1차의 style 평가는 hard safety gate 유지가 전제이며, gate를 통과하지 못한 checkpoint는 style 후보에서 제외한다.

### 11.2 Style Ranking

hard gate 통과 후 아래 순서로 해석한다.

1. posture/style KPI
2. front-view 영상 인상
3. reward / VF / ep_len 보조 해석

중요:

- V23 1차의 성공 기준은 style 완성이 아니라, posture KPI와 front-view 영상 인상이 같은 방향으로 개선되는지 확인하는 것이다.

### 11.3 Best Style Candidate 선정 규칙

1. hard safety gate 통과
2. `PostureStyleScore` 상위 checkpoint shortlist
3. `stance_width_mean` safe band 접근 여부 확인
4. `shoulder_mean_abs_dev_from_target` 개선 확인
5. shortlist에 대해 front-view 수동 리뷰 수행

## 12. contact 기반 보조 지표

다음 항목은 2차 보조 KPI로만 유지한다.

- `duty_factor`
- `contact_sequence_stability`
- `stance_time`
- `swing_time`
- `stride_length`
- `gait_cycle_period`

문서 원칙:

- contact 신뢰도 검증 전까지 위 항목은 보조 참고치로만 사용한다.
- V23 1차 핵심 style score에는 직접 반영하지 않는다.

## 13. 시작 전략

V23 첫 시도는 반드시 checkpoint refinement로 간다.

우선 후보:

- `model_9600.pt`
- `model_15000.pt`

추천 순서:

1. A0 완료
2. A1 minimal posture-first refinement 구현
3. `model_9600.pt` / `model_15000.pt` 중 seed 비교 후 refinement 시작
4. A1 결과 평가 후 B 또는 C 단계 진입 여부 결정
