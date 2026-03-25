# V41-B Plan: Clean Reward Restart — 자연스러운 Trot

> 작성: 2026-03-25
> 상태: 설계 중

---

## 1. 왜 V42인가

### 1개월의 교훈

| 버전 | 접근 | 결과 | 교훈 |
|------|------|------|------|
| V35.5 | 부팅 안정화 3결합 | 서기+걷기 성공 | alive_bonus + contacts ramp + 저속 |
| V36~V37 | L2 penalty로 splay 공격 | 0.54 고착 | reward 채널로는 한계 |
| V38 | CaT로 splay 공격 | 0.45 정체 | discount 채널도 한계 |
| V39 | CPG로 gait 유도 | stride 악화 | 50개 reward 위에 CPG는 효과 없음 |
| V40-A | CaT prob 2배 | 0.384, ep_len 170 | 밀어넣을 수 있지만 보행 악화 |

**공통 패턴**: 50개 reward 구조 위에 무엇을 추가/조정해도 "splay 감소 ↔ 보행 악화" trade-off에서 벗어나지 못함.

### 근본 원인

**50개 reward의 복잡한 상호작용이 splay를 최적 전략으로 만들고 있음.**
성공한 quadruped 프로젝트(Solo-12, ANYmal, Walk These Ways)는 15~20개 reward로 splay 없이 자연스러운 trot을 달성.

### V42 목표

**reward를 15개로 줄이고, 자연스러운 trot으로 잘 걷는 로봇.**
splay를 직접 공격하지 않음. 깨끗한 reward로 trot이 학습되면 splay는 자연 해결.

---

## 2. V42 Reward 구조 (15개)

### 검증된 성공 패턴 기반

```
[생존/안정] 4개
  1. alive_bonus          (+10)     — 매 step 생존 보상 (V35.5 검증)
  2. base_height_l2       (-15)     — 목표 높이 유지
  3. flat_orientation_l2  (-7)      — 넘어짐 방지
  4. undesired_contacts   (ramp)    — body 접촉 방지 (boot ramp)

[전진/추진] 3개
  5. forward_velocity     (+8)      — 전진 보상 (핵심 목표)
  6. track_lin_vel_xy     (+1)      — 속도 추종
  7. track_ang_vel_z      (+0.5)    — 회전 추종

[Gait 패턴] 4개
  8. feet_air_time        (+20)     — 발 들기 (thr=0.25)
  9. gait_phase_reward    (+15)     — Phase clock trot 유도 (V39 교훈 반영, 강한 weight)
  10. diagonal_coupling   (+10)     — 대각 커플링
  11. stride_length       (+5)      — 보폭

[정규화] 4개
  12. action_rate_l2      (-0.5)    — 부드러운 동작
  13. dof_acc_l2          (-0.001)  — 관절 가속도 억제
  14. joint_vel_l2        (-0.05)   — 과도한 관절 속도 억제
  15. dof_pos_limits      (-5)      — 관절 한계 보호
```

### 제거 대상 (기존 50개에서 35개 제거)

| 카테고리 | 제거 항목 | 이유 |
|---------|----------|------|
| front/rear 개별 | rear_joint_velocity, rear_alternation, rear_swing, front_swing 등 ~10개 | 역할 분리 유발 (교훈 #9) |
| residency/band | contact_residency, prop_residency, usage_residency, contact_target_band, propulsion_target_band 등 ~8개 | 복잡한 상호작용 → splay 유지 인센티브 |
| validity/gate | limb_usage_min, single_limb_validity, late_phase_band_exit 등 ~5개 | 불필요한 제약 |
| stance 관련 | stance_width_penalty, stance_propulsion ~3개 | gait phase가 대체 |
| shoulder 직접 | shoulder_neutral, shoulder_symmetry ~2개 | trot이 자세를 자연 교정 |
| CaT | shoulder_splay termination | trot이 해결, 벌칙 불필요 |
| 기타 | foot_extension, knee_height, stationary 등 ~7개 | 불필요 |

### 추가: gait_phase_reward (V39 교훈 반영)

```python
def gait_phase_reward(env, frequency=2.0, duty_factor=0.5):
    """Phase clock trot: stance에서 접지, swing에서 이탈 시 보상.
    V39 교훈: match=+1/mismatch=-1 shape, 강한 weight(15+)."""
    # V39.1.1에서 검증된 +1/-1 shape 사용
    # weight 15 — 전체 reward의 ~15%, 충분한 신호
```

Phase clock observation 8차원도 포함 (V39에서 구현 완료).

---

## 3. 부팅 안정화 (V35.5 검증 사항 유지)

V35.5에서 검증된 3결합을 그대로 유지:

1. **alive_bonus = 10.0** — 매 step 생존 보상
2. **undesired_contacts ramp** — iter 0~300에서 -20→-100
3. **초기 저속 command** — (0.01, 0.05) → (0.1, 0.5)

V41에서 가져온 아이디어:
- **Phase 1 (iter 0~500)**: 직진 저속만, 서기+기본 걷기 형성
- **Phase 2 (iter 500~2000)**: 정상 command, gait phase 강화
- **Phase 3 (iter 2000+)**: 전체 안정화

---

## 4. 설계 원칙

1. **15개 이하 유지** — 추가하고 싶어도 참는다
2. **splay를 직접 공격하지 않음** — shoulder_neutral, CaT 없음
3. **gait phase가 자세를 교정** — trot이 되면 splay 자연 해결
4. **부팅 안정화는 검증된 것만** — V35.5 3결합
5. **from-scratch, 8192 envs** — 탐색 다양성 증가

---

## 5. Env 설정

- **num_envs: 8192** (기존 20480 → 축소)
  - 탐색 다양성 증가, entropy 오래 유지
  - 성공한 프로젝트들: 4096 사용
- **observation: 56차원** (48 + phase clock 8)
- **max_iterations: 15000**

---

## 6. 예상 결과

### 성공 시
- 자연스러운 trot 보행
- shoulder dev가 자연스럽게 0.30~0.40 범위 (직접 공격 없이)
- stride 6.0+, ep_len 230+
- splay 문제 자체가 발생하지 않음

### 부분 성공
- 보행은 되지만 trot이 불완전
- shoulder dev 0.40~0.45
- V38.3 수준이지만 보행 품질은 더 나음 (stride, ep_len)

### 실패
- 부팅 실패 또는 보행 붕괴
- 원인: reward가 너무 적어서 학습 신호 부족
- 대비: 핵심 reward 1~2개 추가 (최소 변경)

---

## 7. 판정 기준

**진짜 목표: 자연스러운 trot으로 잘 걷는 로봇**

주 지표:
1. **stride > 6.0** — 보폭 (보행 품질)
2. **ep_len > 230** — 에피소드 길이 (안정성)
3. **diagonal_coupling > 0.5** — trot 패턴

보조 지표:
4. shoulder dev — 직접 공격 안 했는데 얼마나 내려가는지 관찰
5. FL/FR contact ratio — 앞발 과고정 해결 여부
6. forward_velocity > 1.0

**성공 = stride + ep_len + diagonal 동시 달성.** shoulder dev는 관찰만.

---

## 8. 리스크

1. **부팅 실패** — reward 15개가 너무 적어서 학습 신호 부족
   - 완화: V35.5 부팅 3결합 유지
   - 대비: forward_velocity weight 올리기

2. **trot 학습 실패** — gait_phase_reward가 효과 없음
   - 완화: V39 교훈 (+1/-1 shape, weight 15)
   - 대비: weight 30으로 상향

3. **splay 여전히 발생** — 깨끗한 reward에서도 wide stance 선호
   - 이 경우 splay가 reward 문제가 아닌 기구학적 문제 확정
   - 대비: shoulder joint limit 축소 (V40-C)

---

## 9. 참고

- V35.5: 부팅 안정화 3결합 (검증됨)
- V38: CaT framework (필요 시 재사용 가능)
- V39: phase clock 구현 + reward shape 교훈
- V41: 초기 형성 커리큘럼 아이디어
- Solo-12, ANYmal, Walk These Ways: 15~20개 reward 구조 참고
