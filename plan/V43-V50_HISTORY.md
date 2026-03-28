# V43~V50 History: Boot Stability → Standing Pose → Walking Baseline

## Summary

V43~V50은 **"로봇이 서서 걷게 만들기"**의 연속 실험.
V43~V46은 reward 구조 탐색, V47에서 성공 기반 확립, V48은 자세 보정, V49~V50은 인프라 정비 + 높이 유지.

---

## V43 시리즈 (3/25): Boot 실패 → Boot Gating 발견

**문제**: V42의 clean reward(15개)로 from-scratch 시 부팅 실패 (ep_len < 50)

| 버전 | 변경 | iter | 결과 |
|------|------|------|------|
| V43 | clean 15 reward baseline | 200 | 부팅 실패 |
| V43-B | gait_phase push_alpha ramp | 400 | 부팅 실패 |
| V43-C | per-leg propulsion gating | 800 | 부팅 실패 계속 |
| V43-D | walking reward OFF during boot (boot gating) | 600 | 부팅 성공 (ep_len 200+) |
| V43-E | + boot_standing + boot_contact | 800 | 부팅 안정 + stride 시작 |

**핵심 교훈**: Walking reward가 boot phase에서 conflicting signal → boot gating 필수.
`boot_standing_reward` (height x orientation gradient) + `boot_foot_contact` (4발 접지율)이 부팅의 핵심.

---

## V44~V46 (3/26): Stride 회복 실패 → V38.3 회귀

| 버전 | 변경 | iter | stride | coupling | 비고 |
|------|------|------|--------|----------|------|
| V44 | V43-E + adaptive pose safety | 800 | 0.65 | 0.11 | stride 부족 |
| V46-A | V44 + band reward 부활 시도 | 800 | 1.21 | 0.18 | 개선 미미 |
| V46-B | band + residency 부활 | 800 | 2.05 | 0.25 | 여전히 부족 |

**핵심 교훈**: Clean 15개 reward로는 stride engine이 없음.
V38.3의 band/residency reward(+37.56 weight)가 stride를 만드는 핵심 엔진.

---

## V47 (3/26~27): V38.3 순정 + boot_standing = 성공

**변경**: V38.3 77개 reward 그대로 + boot_standing(15.0) + boot_contact(5.0)만 추가

| 지표 | V47 (iter 800) |
|------|---------------|
| ep_len | 238 |
| stride | 6.29 |
| coupling | 0.46 |
| shoulder_dev | 0.43 |

**결론**: V38.3 순정이 최선. boot_standing만 추가하면 됨.

---

## V47-B ~ V48 시리즈 (3/27~28): 자세 보정

**문제**: V47 비디오에서 몸이 너무 낮고 다리가 과도하게 접힘

**원인 발견**: leg=-0.71에서 toe가 shoulder보다 33mm 앞에 위치 → 뒤로 기울어짐 → 낮은 자세로 보상
- FK 계산은 URDF 180도 yaw rotation 때문에 부정확
- **시뮬레이터 body_pos_w만 신뢰** (핵심 교훈)

**보정**: leg=-0.71 → leg=-0.97 (toe가 shoulder 수직선에 위치하도록)

---

## V48-C/D (3/27~28): 현실 질량/토크 실험 → 실패

| 버전 | 변경 | 결과 |
|------|------|------|
| V48-C | 현실 질량 분산 (5.3→6.54kg) | 보행 불안정 |
| V48-D | + 현실 토크 (effort 1.5~5.0) | 서기 불가 |

**결론**: 보행 기본이 안 잡힌 상태에서 realism 추가는 시기상조.
**Two-track 전략**: Walking baseline 먼저, Realism은 별도 트랙.

---

## V49 (3/28): Baseline 복원 + 인프라

**변경**: V48-B로 복귀 (원본 mass 5.3kg, effort 15.0, leg=-0.97)

**인프라 구현**:
- Curriculum state save/restore (checkpoint resume 지원)
- `_USE_BOOT_STANDING` feature flag (version 문자열 하드코딩 제거)

**테스트 런 (3/28)**:

| Run | 내용 | 결과 |
|-----|------|------|
| 06-23-30 | 이전 listener 자동 시작 (V49 이전 코드) | iter 0만 |
| 06-56-51 | listener 자동 시작 (V49) | iter 200 |
| 07-49-43 | V49 수동 실행 (boot_standing 누락!) | iter 0만 |
| **08-08-39** | **V49 + _USE_BOOT_STANDING** | **iter 1140, 귀뚜라미 보행** |

**V49 iter 1140 결과**:
- ep_len 234, stride 6.9, coupling 0.59
- **front_leg_lift 0.08, front_clearance 0.00** → 앞발 안 들림
- 뒷다리만 밀고 앞다리는 바닥에 고정 = "귀뚜라미 보행"

**원인 분석**:
1. boot_standing ramp-down이 너무 빠름 (300 iter)
2. "낮게 = 안전" 습관이 굳은 후 walking reward 활성화
3. 낮은 자세에서 walking 최적화 → 앞다리 불필요

---

## V50 (3/28): Boot 연장 + 높이 유지 강화

**변경** (A+B 결합):

| 파라미터 | V49 | V50 | 이유 |
|---------|-----|-----|------|
| boot_standing_initial | 15.0 | 20.0 | 초기 "서기" 신호 강화 |
| boot_ramp_down_iters | 300 | 1500 | "서기" 습관 충분히 각인 |
| standing_height.weight | 10.0 | 15.0 | walking phase 높이 유지 |
| base_height_l2.weight | -15.0 | -20.0 | 높이 penalty 강화 |

**테스트 런 (3/28)**:

| Run | 내용 | 결과 |
|-----|------|------|
| 11-34-56 | V50 headless (cli 직접 실행) | iter 0만, GUI 테스트 |
| 11-38-07 | V50 GUI 시도 (hidden window) | iter 0만, 창 안 보임 |
| 11-41-31 | V50 GUI 시도 (CREATE_NEW_CONSOLE) | iter 0만, 세션 0 제한 |
| 11-44-19 | V50 GUI 시도 (같은 문제) | iter 0만 |
| **11-48-45** | **V50 GUI (listener Console 세션)** | **iter 200, GUI 성공** |
| 11-50-59 | V50 headless (이전 resume용) | iter 200 |
| **13-06-47** | **V50 resume from model_200** | **iter 1000+ 진행 중** |

**V50 iter 1030 중간 결과**:
- ep_len 243, stride 5.83, coupling 0.54
- **front_leg_lift 0.137** (V49: 0.08 → **70% 개선**)
- boot_standing 3.23 (V49: 2.05) — ramp-down 연장 효과
- shoulder_dev 0.515 — 아직 높음, 커리큘럼 후반 개선 기대

**인프라 개선**:
- CLI → Telegram → Listener 단일 실행 루트 통일
- `/start gui` 옵션 추가 (listener Console 세션에서 GUI 실행)
- Listener 시작 시 stale message flush (`--resume` 옵션으로 제어)
- 버전 네이밍: Major(V50)=from-scratch, Minor(V49.1)=resume 가능

---

## 핵심 교훈 추가

| # | 교훈 | 출처 |
|---|------|------|
| 20 | boot_standing의 ramp-down이 너무 빠르면 "낮게 기기" 습관이 굳음 | V49 귀뚜라미 |
| 21 | 앞/뒷다리 비대칭은 boot phase에서 높이 습관이 안 잡혀서 발생 | V49→V50 |
| 22 | Version 문자열 하드코딩 대신 feature flag 사용 | V49 boot_standing 누락 |
| 23 | CLI는 리스너 경유로 통일 (직접 실행 금지) | V50 GUI 세션 문제 |
| 24 | WSL에서 GUI 프로세스 실행 불가 (세션 0 제한) | V50 GUI 시도 |
