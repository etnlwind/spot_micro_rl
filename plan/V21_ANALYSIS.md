# V21 Analysis — Gait-Quality-First Ops + Toe Contact Reinterpretation

> Log: `logs/rsl_rl/spot_micro_flat/2026-03-10_07-43-51`  
> 분석일: 2026-03-10  
> 상태: 운영/관측 체계 개편 완료, 재개 체크포인트는 `model_9600.pt` 우선 검토

---

## 1. V21 한 줄 요약

V21은 리워드 구조 자체를 크게 뒤엎은 버전이라기보다, **현재 V20 학습을 더 정확하게 읽고 더 안전하게 운영하기 위한 관측/운영 레이어 정비**에 가깝다.

핵심은 3가지다.

1. **Heartbeat를 gait-quality-first KPI 체계로 재정렬**
2. **Supervisor를 heartbeat와 같은 언어로 묶고, 영상 수집을 iteration 기준으로 운용**
3. **foot_link 중심 접촉 해석을 toe_link 중심으로 재정의하고, 진단/재생 도구를 추가**

---

## 2. 왜 V21이 필요했는가

V20 soft-ramp는 critic shock 완화 목적에는 맞았지만, 실제 운영에서는 아래 문제가 남아 있었다.

| 문제 | V20까지 상태 | V21에서 한 일 |
|------|--------------|---------------|
| 텔레그램 heartbeat가 reward 총합 중심으로 읽힘 | gait 품질보다 reward 숫자에 시선이 쏠림 | 기립/전진/대각커플링/트롯/뒷다리활성/발들기 중심 KPI 체계로 재배치 |
| supervisor와 heartbeat가 다른 언어를 사용 | 텍스트 판단과 영상 캡션이 분리됨 | supervisor가 heartbeat KPI snapshot을 직접 사용 |
| 영상 전송 주기가 시간 기반 | 훈련 중단 비용 대비 관측 효율이 떨어짐 | 초기 500 iter, 중기 1000 iter, 후기 1500 iter 기반으로 전환 |
| contact metric 해석이 foot_link 중심 | SpotMicro 소형 발 구조에서 접촉 이벤트가 불안정 | toe_link를 기본 접촉 해석으로 전환, 진단 CSV/JSON까지 추가 |

---

## 3. V21 변경 범위

### 3.1 Heartbeat 재설계

대상 파일: `scripts/training_heartbeat.py`

#### 핵심 변화

- Telegram 리포트 최상단에 **운영 판정**(`워밍업`, `계속 진행`, `계속 관찰`, `중단 검토`) 추가
- **우선 KPI** 6개를 별도 섹션으로 승격
  - `standing_height`
  - `forward_velocity`
  - `diagonal_coupling`
  - `trot_gait`
  - `rear_joint_velocity`
  - `foot_clearance`
- KPI별 상태를 `양호 / 형성중 / 미약`으로 분류
- stride/cycle 같은 **접촉 이벤트 기반 값은 참고 지표로 강등**
- survival rate 계산을 보정해서, timeout 기반 장수 에피소드가 과소평가되지 않도록 수정
- 그래프 패널도 gait-quality-first 기준으로 재배열

#### 운영 판단 함수

새 판단 로직은 `evaluate_training_window()`에 들어갔다.

- `iter <= 300`: 탐색 구간, KPI 출현 여부만 확인
- `300 < iter <= 1000`: 생존율 + bad orientation + KPI 형성 개수로 계속/관찰/중단 판단
- `iter > 1000`: 1k 이후에도 핵심 KPI가 안 보이면 중단 검토

즉, **reward 총합이 아니라 실제 gait 형성 여부를 보고 운영 결정을 내리게 변경**한 것이다.

---

### 3.2 Supervisor 재설계

대상 파일: `scripts/training_supervisor.py`

#### heartbeat와 언어 통합

`build_supervisor_kpi_snapshot()`을 추가해 supervisor가 heartbeat와 같은 KPI/판정 로직을 재사용한다.

이 snapshot에는 아래 정보가 포함된다.

- 현재 iteration / reward / survival
- 운영 판정
- 핵심 사유 한 줄
- Gait grade / score
- Stability grade / score
- 캡션용 KPI 요약 문자열

그 결과 supervisor가 보내는 아래 메시지들이 모두 heartbeat와 같은 언어로 정렬됐다.

- clip 시작 알림
- 영상 caption
- clip 분석 완료 요약
- 최종 훈련 종료 요약

#### 영상 녹화 방식

기존 단일 시점에서, 아래 4개 시점을 순차 녹화하는 방식으로 바뀌었다.

- `side`
- `front`
- `rear`
- `top_oblique`

side view는 기존 호출부 호환을 위해 기본 반환값으로 유지하되, 실제 파일은 멀티뷰로 남긴다.

#### 시간 기반 → iteration 기반 cadence

V21에서 가장 중요한 운영 변경 중 하나다.

새 기본 규칙:

| 구간 | 정기 clip 간격 |
|------|----------------|
| 초기 | 500 iter |
| 중기 | 1000 iter |
| 후기 | 1500 iter |

추가로, **운영 판정이 악화될 때**는 `URGENT_VIDEO_GAP_ITER` 이상 떨어져 있으면 긴급 clip을 허용한다.

관련 함수:

- `get_regular_video_interval()`
- `get_next_regular_trigger()`
- `verdict_severity()`
- `should_capture_clip()`
- `format_trigger_status()`

이 변경으로 supervisor는 더 이상 “3시간마다 무조건 재생”하지 않고, **학습 진행량과 상태 악화에 반응하는 방식**으로 동작한다.

---

### 3.3 Contact 해석 재정의

대상 파일:

- `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py`
- `source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/mdp/rewards.py`

#### 핵심 변경

- Flat 환경의 contact sensor/body 기준을 **`.*foot_link`에서 `.*toe_link`로 전환**
- gait/stride/cycle 계열 리워드에 `contact_threshold` 파라미터를 명시적으로 전달
- rewards.py에 `_contact_force_peak()` / `_contact_state()` 헬퍼를 추가해 접촉 판별 코드를 공통화

#### 왜 toe로 바꿨는가

SpotMicro는 발 구조가 작고, foot_link 기준으로 보면 실제 지면 접촉보다 상위 링크/구조물 영향이 섞여 해석이 불안정할 수 있다.

V21은 contact 이벤트를 완전히 버리지는 않되,

- **운영판단에서는 참고 지표로만 사용**하고
- **측정 자체는 toe 기준으로 더 직접적으로 읽도록 전환**했다.

---

### 3.4 Play / Diagnostics 도구 추가

대상 파일:

- `scripts/rsl_rl/play.py`
- `scripts/collect_checkpoint_diagnostics.py`
- `scripts/make_multiview_screenshot_pack.py`
- `scripts/make_side_dense_pack.py`
- `scripts/make_screenshot_pack.py`

#### play.py 확장

새 옵션:

- `--camera_view`
- `--camera_zoom`
- `--save_contact_csv`
- `--contact_threshold`
- `--contact_primary_mode`

추가 기능:

- 단일 로봇 촬영 시 카메라 follow
- `foot / toe / aggregate` 3가지 contact mode를 동시에 CSV로 기록
- body mapping 메타데이터를 JSON으로 저장

#### 진단 스크립트 역할

- checkpoint 하나를 골라 contact mode별 차이를 비교
- multiview screenshot pack / dense side pack / GIF / ZIP 생성
- Telegram으로 패키지 전송 가능

즉, V21은 단순히 “영상 하나 보내기”가 아니라, **왜 그렇게 보였는지 나중에 역추적할 수 있는 진단 아티팩트 체계**를 추가한 버전이다.

---

## 4. Heartbeat와 Supervisor 역할 분담

V21 이후 운영 철학은 아래처럼 정리된다.

| 컴포넌트 | 주기 | 역할 | 출력 |
|----------|------|------|------|
| heartbeat | 자주 | TensorBoard 기반 상태 감시, KPI 판정, 그래프 전송 | 텍스트 + 그래프 |
| supervisor | 드물게 | 훈련 일시중단, 멀티뷰 재생, 상세 분석, 사용자 의사결정 | 비디오 + 분석 요약 |

### Heartbeat가 보는 것

- 지금 gait가 형성되고 있는가?
- 생존율과 bad orientation이 어느 수준인가?
- 지금은 계속 가도 되는가, 더 지켜봐야 하는가, 중단 검토인가?

### Supervisor가 보는 것

- 실제 영상에서 diagonal trot처럼 보이는가?
- rear usage가 살았는가?
- KPI가 나빠졌다면 영상을 남기고 사용자 결정을 받을 시점인가?

정리하면:

- **heartbeat = 자주 보는 계기판**
- **supervisor = 비싸지만 확실한 현장 점검**

---

## 5. V21 운영 결과

실제 운영 검증은 `logs/rsl_rl/spot_micro_flat/2026-03-10_07-43-51` 런에서 수행했다.

확인된 항목:

- heartbeat 샘플 메시지 Telegram 전송 완료
- supervisor KPI 테스트 메시지 Telegram 전송 완료
- side / rear / top_oblique / default multi-robot view 영상 전송 완료
- checkpoint `model_10800.pt` 기준 멀티뷰 재생 검증 완료

재개 체크포인트 선택은 **`model_9600.pt` 우선**으로 유지한다.

이유:

- 9800보다 gait 품질 관점에서 더 낫다고 판단
- V21 운영 체계는 “어느 체크포인트가 숫자상 조금 높냐”보다 “재개 후 gait 형성이 이어지느냐”를 더 중요하게 보기 때문

---

## 6. V21의 핵심 판단

### 성과

1. **운영 언어가 통일됐다**
   - heartbeat, supervisor, Telegram video caption이 같은 KPI 체계를 사용한다.

2. **reward 중심 모니터링에서 gait 중심 모니터링으로 바뀌었다**
   - 숫자 총합보다 기립/전진/대각커플링/트롯/rear usage를 먼저 본다.

3. **contact 지표를 더 정직하게 해석하게 됐다**
   - toe 기준으로 바꾸고, contact 이벤트는 참고 계층으로 낮췄다.

4. **운영 비용이 줄었다**
   - supervisor가 시간마다 무조건 재생하지 않고, iteration milestone과 verdict 악화에 반응한다.

### 아직 남은 것

1. V21은 **운영 체계 개선**이지, reward 자체의 최종 해법은 아니다.
2. toe contact 기준이 실제로 stride/cycle 신뢰도를 얼마나 높였는지는 장기 로그 비교가 더 필요하다.
3. iter 기반 supervisor cadence는 실제 장시간 재개 런에서 한 번 더 검증해야 한다.

---

## 7. 다음 액션

1. `model_9600.pt`에서 재개
2. heartbeat로 500/1000 iter 구간 KPI를 먼저 확인
3. supervisor는 iter milestone 기반으로 side/rear/top clip 수집
4. toe 기준 stride/cycle 값이 여전히 불안정하면 contact metric은 계속 참고 계층으로 유지

---

## 8. V21 결론

> V21의 본질은 “더 잘 학습시키는 버전”이라기보다, **무엇이 실제로 좋아지고 있는지 더 정확하게 보게 만든 버전**이다.

reward 총합이 아니라 gait 품질을 우선 KPI로 보고, heartbeat와 supervisor를 같은 판단 체계로 묶고, 영상 수집을 iteration 기반으로 바꾸면서, 앞으로의 재개/중단 결정이 훨씬 덜 흔들리게 됐다.