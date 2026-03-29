# V43~V53 History: Boot Stability → Standing Pose → Height Gate → Front Leg Lift

## Summary

V43~V46은 reward 구조 탐색, V47에서 성공 기반 확립, V48은 자세 보정,
V49~V50은 인프라 정비 + 높이 유지, V51은 soft height gate,
V52는 data-driven weight, V53은 앞다리 전용 reward.

---

## V43 (3/25): Boot 실패 → Boot Gating 발견

V42의 clean reward(15개)로 from-scratch 시 부팅 실패.
V43-D에서 boot gating(walking reward OFF during boot) 적용 → 부팅 성공.
V43-E에서 boot_standing + boot_contact 추가 → 부팅 안정 + stride 시작.
**교훈**: Walking reward가 boot phase에서 conflicting signal → boot gating 필수.

---

## V44~V46 (3/26): Stride 회복 실패

Clean 15개 reward로는 stride engine 부족. V38.3의 band/residency(+37.56 weight)가 핵심 엔진.
**교훈**: 기존 reward 체계를 대체하려면 동등한 driving force가 필요.

---

## V47 (3/26~27): V38.3 순정 + boot_standing = 성공

V38.3 77개 reward + boot_standing(15.0) + boot_contact(5.0)만 추가.
iter 800: stride 6.29, coupling 0.46 달성. V38.3 수준 복원.
**결론**: V38.3 순정이 최선. boot_standing만 추가하면 됨.

---

## V47-B ~ V48 (3/27~28): 자세 보정

V47 비디오에서 몸이 너무 낮고 다리 과접힘. leg=-0.71에서 toe가 shoulder보다 33mm 앞 위치.
leg=-0.97로 보정 (toe가 shoulder 수직선). init_height 0.30→0.22 복원.
**교훈**: FK 수식 대신 시뮬레이터 body_pos_w만 신뢰.
상세: V48_PLAN.md

---

## V48-C/D (3/27~28): 현실 질량/토크 → 실패

V48-C(6.54kg) 보행 불안정, V48-D(effort 1.5~5.0) 서기 불가.
**결론**: 보행 baseline 없이 realism 추가는 시기상조. Two-track 전략 결정.
상세: V48_PLAN.md

---

## V49 (3/28): Baseline 복원 + 인프라

V48-B 설정 복귀. curriculum state save/restore, `_USE_BOOT_STANDING` feature flag 구현.
iter 1140: stride 6.9 달성, but front_leg_lift 0.08 → **귀뚜라미 보행** 발견.
**원인**: boot_standing ramp-down(300 iter)이 너무 빠름 → "낮게 기기" 습관 고착.
상세: V49_PLAN.md

---

## V50 (3/28): Boot 연장 + 높이 강화

boot_ramp_down 300→1500, standing_height 10→15, base_height_l2 -15→-20.
iter 1030: front_lift 0.137 (V49: 0.08 → 70% 개선). 하지만 walking 활성화 후 하락 추세.
상세: V50_PLAN.md

---

## V50.1~V50.2 (3/28): Height Gradient 강화 → 실패

V50.1: height_k 500. 초반 0.228 달성 → walking 활성화 후 0.197 하락.
V50.2: boot_standing floor=10 유지. iter 1074에서 0.196 하락.
**결론**: reward weight 비율 조정(15:1)으로는 local optimum을 깰 수 없음. 구조 변경 필요.
상세: V50_PLAN.md

---

## V51 (3/28): Soft Height Gate Hybrid

Walking reward에 height 조건부 penalty. 3번 시행착오 (w=40 즉사 → w=15 수갑 → boot-gated 성공).
boot-gated iter 331: front_lift **0.257** (역대 최고). 하지만 iter 3300에서 0.035로 재하락.
**결론**: anti-crouch 성공, anti-cricket 실패. 적당히 낮은 자세에서 귀뚜라미 재발.
상세: V51_PLAN.md

---

## V52 (3/29): Height Gate + Min Height Termination

min_height_termination(0.15m, boot-gated) + front_rear_symmetry(w=8) 추가.
height 0.19 안정, but front_lift 여전히 하락 (iter 800: 0.156 → iter 3300: 0.035).
**실측 분석**: 앞다리 포기 순이익 +5.76/step — stance_width_penalty(+7.23) 하나가 순이익보다 큼.
상세: V52_PLAN.md

---

## V52.1 (3/29): 실측 기반 Weight 재설계

stance_width -3→-1.5, flc 8→16, leg_lift 15→20. 시나리오 A(마진 31%) 채택.
front_lift 0.13 유지(V52 대비 개선) but 장기 하락 동일.
**핵심 발견**: leg_lift_reward의 4발 평균이 앞다리 사용을 -5.7/step penalty화 (perverse incentive).
인프라: launch.lock, version-based snapshot, listen.cmd PID, stall detection /stop 대응.
상세: V52_PLAN.md

---

## V53 (3/29): 앞다리 전용 Front Leg Lift Reward

기존 leg_lift(4발, w=20) 유지 + front_leg_lift(FL/FR만, w=15) additive 추가.
수치 근거: V52.1 조정(-7.56) + V53 front_lift(-7.90) = **총 net -9.70/step** (앞다리 사용이 크게 유리).
from-scratch 훈련 예정. 핵심 판정: iter 1200 이후 front_lift > 0.10 유지 여부.
상세: V53_PLAN.md

---

## 핵심 교훈 (V43~V53)

| # | 교훈 | 출처 |
|---|------|------|
| 20 | boot_standing ramp-down이 너무 빠르면 "낮게 기기" 습관 고착 | V49 |
| 21 | 앞/뒷다리 비대칭은 boot phase 높이 습관 미각인 | V49→V50 |
| 22 | Version 하드코딩 대신 feature flag | V49 |
| 23 | CLI는 리스너 경유 통일 | V50 |
| 24 | WSL GUI 실행 불가 (세션 0 제한) | V50 |
| 25 | penalty > alive_bonus → 죽는게 이득 | V51 |
| 26 | height gate는 boot OFF, walking만 적용 | V51 |
| 27 | reward 변경 시 per-step net reward 부호 검증 | V51 |
| 28 | "잘 가라" > "앞으로 가라" — 품질 우선 | V49~V51 |
| 29 | 파라미터 설계: 추정 금지, 실측 먼저 | V52.1 |
| 30 | reward 평균 함수 → 다수파가 소수파 사용을 penalty화 | V52.1 |
| 31 | .cmd 파일 CRLF 필수 | V52.1 |
| 32 | launch_training 중복 실행 방지 lock | V52.1 |
| 33 | stall detection은 /stop 후 비활성화 | V52.1 |
