# V35 Plan — V32.1 복원 + 부팅 안정성 근본 개선

**작성일**: 2026-03-20
**상태**: V35.5 훈련 중 (3가지 결합 부팅 안정화)

---

## 배경

### V33~V34 실패 원인
- V33: 보상 급진적 단순화 (122→28개) → "부팅 신호" 제거 → 붕괴
- V34: rel_standing_envs 3-Phase 커리큘럼 → 역시 실패
- 결론: V32.1 보상 구조 자체가 작동함, 문제는 다른 곳에 있음

### V32.1 재현성 분석 (핵심 발견)
V32.1 원본 코드로 4회 실행한 결과:

| Run | iter 100 ep_len | 결과 |
|-----|----------------|------|
| 07-13-40 | **90.05** | 성공 |
| 10-15-31 | N/A (crash) | 실패 |
| 11-19-04 | **10.84** | 실패 |
| 11-49-04 | **10.93** | 실패 |

**V32.1은 25% 성공률.** 랜덤 시드에 따라 부팅되거나 안 되는 불안정한 설정.

### 근본 원인: 초기 부팅 불안정
1. 랜덤 정책 → 12 step (~0.24초) 만에 낙하 → 에피소드 너무 짧음
2. 짧은 에피소드 → "서있는 게 좋다"는 학습 신호 부족
3. `undesired_contacts=-100` → 넘어지면 catastrophic penalty → 탐색 의지 억제
4. 결과: "빨리 넘어져서 penalty 최소화"라는 local minimum에 갇힘

---

## V35 시리즈 실험 경과

### V35 (실패) — Anti-Splay + Anti-Shuffle
V32.1 + 타겟 수정 6개. iter 300에서 ep_len=12.6, 100% fall.
→ **rewards.py 이모지 crash 발견** (cp949 인코딩 에러). 실제 원인 분리 불가.

| 변경 | V32.1 → V35 |
|------|-------------|
| shoulder_neutral | -4.0 → -8.0 |
| stance_width | -2.5 → -4.0 |
| height target | 0.24 → 0.22 |
| stride ramp | 400~700 → 200~500 |
| stride max | 12.0 → 15.0 |
| feet_air threshold | 0.3 → 0.25 |
| swing_stride | 2.0 → 4.0 |

### V35.1 (실패) — Anti-Splay 절반 완화
shoulder=-6.0, stance=-3.0, height=0.23. 동일 패턴 (ep_len=12.7).
→ Anti-splay가 주범이 아닌 것으로 판단.

### V35.2 (실패/crash) — 순수 V32.1 복원
V32.1 코드 100% 복원 (버전 태그만 V35.2).
→ **rewards.py `⏸` 이모지가 Windows cp949에서 UnicodeEncodeError 발생.**
→ gait_gate PAUSE 로그 출력 시 crash. 이모지를 ASCII로 교체하여 해결.
→ 이모지 수정 후 재실행: **ep_len=12~15로 정체 (iter 1700까지).**
→ V32.1 자체가 재현 불가 (25% 성공률) 확인.

### V35.3 (효과 미미) — alive_bonus=2.0
매 step +2.0 생존 보상 추가. ep_len=12.7 (iter 100) → 변화 없음.
→ penalty 총합(-100 등)에 비해 +2.0/step은 너무 약함.

### V35.4 (부분 효과) — alive_bonus=10.0
alive_bonus를 10.0으로 상향. iter 50에서 ep_len=31.9 달성 (역대 최고).
→ 하지만 iter 100 이후 다시 하락 (22.7→10.8).
→ 서기는 배우지만, 움직이려다 넘어지면 undesired_contacts=-100이 탐색 억제.

### V35.5 (현재 진행 중) — 3가지 결합
alive_bonus=10.0 + undesired_contacts 완화 + 초기 저속.

| 구성 | 상세 |
|------|------|
| alive_bonus | weight=10.0 (매 step 생존 보상) |
| undesired_contacts | iter 0~300: -20 → -100 램프 (초기 낙하 관용) |
| velocity command | iter 0~500: (0.01, 0.05) → (0.1, 0.5) 램프 (초기 저속) |

**초기 결과 (iter 118):**

| iter | ep_len | vs V35.4 | vs V32.1 실패 |
|------|--------|----------|--------------|
| 50 | **43.7** | 31.9 (+37%) | ~12 (+264%) |
| 100 | **40.6** | 22.7 (+79%) | ~11 (+269%) |

---

## 기술 이슈 해결

### 1. rewards.py Unicode Crash
**증상**: 훈련이 iter 7~10에서 crash
**원인**: V32.1 rewards.py의 `⏸🔄✅` 이모지가 Windows cp949 콘솔에서 `UnicodeEncodeError`
**해결**: 이모지를 ASCII 텍스트로 교체 (`⏸`→`[PAUSED]`, `🔄`→`[>>]`, `✅`→`[OK]`)
**영향**: V35/V35.1의 실패는 이 crash가 아닌 보상 설정 문제. V35.2에서만 crash 발생 (V32.1 rewards.py 복원 시).

### 2. V32.1 재현성 문제
**증상**: 동일 코드, 4회 실행 중 1회만 성공 (25%)
**원인**: 초기 랜덤 정책의 운에 의존하는 불안정한 부팅 구조
**해결**: V35.5의 3가지 결합 부팅 안정화

### 3. 사전 검증 항목 (V35 시작 전 확인 완료)
- Forward axis: +X = 전방 (URDF π Z-rotation 확인)
- PD gains: stiffness=15.0, damping=1.5 (damping/mass=0.27, 적정)
- Contact sensing: `.*toe_link` (merge_fixed_joints=True에서도 존재 확인)
- Contact threshold: 1.0N (5.6kg 로봇의 7.3% static load, 적정)
- Termination: V32.1 유지 (bad_orientation=1.5rad, base_contact=None)

---

## 파일 변경 (V35.5 기준)

### `spot_micro_rl_env_cfg.py`
- Line 7: `TRAIN_VERSION = "V35.5"`
- Line 320-324: `alive_bonus` RewTerm 추가 (weight=10.0)
- Line 258-263: `boot_ramp` 커리큘럼 파라미터 추가
  - `boot_ramp_end=300`, `boot_undesired_contacts_floor=-20.0`
  - `boot_vel_x_min=0.01`, `boot_vel_x_max=0.05`, `boot_vel_restore_iter=500`

### `rewards.py`
- Line 22-24: `alive_bonus()` 함수 추가
- Line 3207-3211: `boot_ramp` 파라미터 시그니처 추가
- Line 3389-3411: boot stability ramp 로직 추가
- 이모지 → ASCII 교체 (7개소)

### `isaac_ops/listener.py`
- 영상 리포트 생성 전 Telegram 확인 요청 (훈련 중지 방지)
- mid-run 합류 시 마지막 마일스톤 보존 (리포트 누락 방지)
- 새 run 감지 시 train_version 자동 갱신 + version mismatch 알림

### 구조 정리
- `scripts/supervisor.py`, `scripts/heartbeat.py`, `scripts/supervisor.cmd` → `scripts/legacy/`로 이동
- `supervisor.cmd` (프로젝트 루트) → `scripts/legacy/supervisor_root.cmd`로 이동
- 현재 active: `isaac_ops/listen.cmd` → `isaac_ops/listener.py` (통합 listener)

### `.env`
- `TRAIN_VERSION=V35.5`

---

## 체크포인트 기준 (V35.5)

| iter | 확인 | 판정 |
|------|------|------|
| 100 | ep_len > 30 | 부팅 진행 확인 (달성: 40.6) |
| 300 | ep_len > 80, boot_ramp 완료 | undesired_contacts -100 복원 후 안정성 |
| 500 | ep_len > 150, vel 복원 완료 | 원래 속도에서 보행 유지 |
| 1000 | 4발 보행, trot 패턴 | V32.1 성공 run 수준 |
| 1500 | 보폭/자세 품질 | STAND→WALK ramp 시작 |

## 다음 단계

V35.5 성공 시:
1. **V36**: V35.5 기반 + anti-splay 수정 (shoulder=-6.0, stance=-3.0, height=0.23)
2. **V37**: V36 기반 + anti-shuffle 수정 (stride ramp 조기화, swing_stride 강화)

V35.5 실패 시:
1. alive_bonus 커리큘럼화 (iter 500 이후 감쇠) 검토
2. bad_orientation 임계값 초기 완화 (1.5→3.0 rad) 검토
3. undesired_contacts floor을 -10 또는 -5로 더 낮추기

---

## 교훈

1. **재현성 먼저 확인**: V32.1이 "성공"이라고 가정하기 전에 재현성을 검증해야 했음
2. **한 번에 하나씩**: V35에서 6개 변수를 동시에 바꾼 것이 원인 특정을 불가능하게 만듦
3. **환경 차이 점검**: 코드 동일해도 결과가 다르면 pyc 캐시, 인코딩, 시스템 변경 등 확인
4. **alive bonus의 중요성**: 대부분의 locomotion RL에서 기본 사용하는 보상이지만 누락되어 있었음
5. **penalty 스케일링**: 초기에 harsh penalty (-100)는 탐색을 억제하므로 커리큘럼 필요
