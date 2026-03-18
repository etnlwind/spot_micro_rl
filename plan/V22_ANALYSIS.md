# V22 Analysis — Multiview Media Package + Heartbeat Workbook

## 1. V22 한 줄 요약

V22는 V21의 gait-quality-first 운영 체계 위에, **최종 판단을 나중에 다시 검토할 수 있는 멀티뷰 영상 패키지와 workbook 기반 아티팩트 체계**를 얹은 버전이다.

## 2. 왜 V22가 필요했는가

- 텔레그램에 영상 1개만 보내면 순간 인상은 볼 수 있지만, 왜 그렇게 판단했는지 나중에 역추적하기 어려웠다.
- heartbeat 텍스트는 좋았지만, 장기 추세를 AI/사람이 바로 읽을 수 있는 표와 그래프가 부족했다.
- 완료된 런을 다시 검토할 때, side view만으로는 머리/상체/대각 리듬의 왜곡을 놓치기 쉬웠다.

## 3. V22 변경 범위

### 3.1 멀티뷰 영상 패키지

- supervisor가 `overview / side / front / rear / top` 5개 시점을 순차 녹화
- 텔레그램으로 5개 영상을 순서대로 전송
- ZIP artifact에 각 시점의 정지 프레임과 manifest를 포함

### 3.2 top view 정리

- top view에서는 command arrow debug visualization을 숨김
- top view는 보행 패턴 확인 전용 시점으로 유지
- 카메라는 원래 world-relative 동작으로 복원하고, top overlay만 정리함

### 3.3 heartbeat workbook

- `heartbeat_reports.jsonl`에 startup / milestone / final heartbeat를 구조화 저장
- ZIP 내부 `metrics/heartbeat_history.xlsx` 생성
- workbook 시트:
  - `Overview`: gait 핵심 지표 요약
  - `Trends`: 시간축 데이터 + 차트
  - `RawData`: 원본 heartbeat 레코드

### 3.4 legacy run fallback

- 오래된 런은 `heartbeat_reports.jsonl`이 없을 수 있음
- 이 경우 TensorBoard scalar를 읽어 workbook을 재구성
- 따라서 과거 최종 런도 같은 형식의 artifact로 다시 묶을 수 있음

## 4. 실전 검증 결과

검증 런:

- `logs/rsl_rl/spot_micro_flat/2026-03-11_02-39-01`
- checkpoint: `model_15000.pt`

검증 내용:

- 5개 시점 영상 생성 확인
- 텔레그램 비디오 전송 확인
- 분석 리포트 생성 확인
- ZIP artifact 생성 및 전송 확인
- workbook 포함 여부 확인

최신 검증 artifact:

- `clip_1005_iter15000_20260311_132732.zip`

## 5. V22의 핵심 판단

- V22는 학습 성능 자체를 끌어올린 버전이 아니다.
- 대신, **현재 학습이 왜 부족한지를 더 빠르고 더 안전하게 판단하는 운영 버전**이다.
- 특히 `front`와 `top`이 추가되면서, 상체 정렬과 대칭성/대각 리듬 확인이 쉬워졌다.

## 6. V22 이후 남은 과제

- 생존율과 실제 gait score를 올리는 것은 여전히 학습 설계 문제다.
- 현재 최종 분석에서 `gait_cycle_period=0`, `stride_length=0`, `height` 저하가 남아 있다.
- 따라서 다음 버전은 다시 **보상/커리큘럼/재개 전략** 쪽으로 돌아가야 한다.

## 7. 결론

> V22의 본질은 “더 잘 보게 만든 버전”이다.  
> V23은 이 관측 기반 위에서, 실제 gait 개선으로 다시 넘어가는 준비 단계다.