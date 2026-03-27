# HANDOFF.md

> 마지막 업데이트: 2026-03-26
> 최신 커밋: develop 브랜치

---

## 1. 현재 목표

**자연스러운 Trot 보행 — V47: V38.3 순정 + Boot 가속 (훈련 중, stride 6.29 / shoulder 0.43)**

### 프로젝트 한 줄 요약

SpotMicro 4족 로봇이 PPO(Isaac Lab)로 자연스러운 trot 보행을 학습하는 프로젝트. 한 달간 V42~V44에서 reward 구조를 실험하여 boot 성공(V43-E)과 stride/splay trade-off(V44)를 확인. 현재 V43-E의 안정된 boot 위에 V38.3의 검증된 gait reward를 순차 추가하는 3-Run 실험 진행 예정.

---

## 2. 현재 위치 (2026-03-26)

### 검증된 성과

| 성과 | 버전 | 증거 |
|------|------|------|
| **Boot 성공** | V43-E | ep_len 248, bad_orientation 0.8% |
| **Shoulder 0.40** | V43-E | 15개 clean reward로 역대 최고 |
| **Boot gating 검증** | V43-D/E | walking reward OFF → boot 가능 |
| **Boot standing 검증** | V43-E | positive gradient → penalty 사막 해결 |
| **Pose↔stride trade-off 확인** | V44 | pose↓→stride↑+splay↑ (수학적 증명) |
| **Coupling reward 무효** | V44 | weight 10, 1500+ iter → coupling 0.0 |

### V46 실험 (3-Run)

| Run | 결과 | 교훈 |
|-----|------|------|
| V46-A | stride 1.45, shoulder 0.46 | gait reward 추가만으론 stride 2.0 미달 (pose 장벽) |
| V46-B | stride 1.29, shoulder 0.44 | shoulder 분리 OK, stride 여전히 부족 (제거한 reward가 동력) |

→ **전략 전환**: reward 선별이 아닌 V38.3 순정 + boot만 추가 (V47)

### V47 현재 상태 (iter 5860)

| 지표 | V47 | V38.3 | 비교 |
|------|:---:|:-----:|:----:|
| stride | **6.29** | 6.79 | 93% ✓ |
| coupling | **0.46** | 0.49 | 94% ✓ |
| shoulder | **0.43** | 0.45 | **V47 승** |
| ep_len | **195** | 207 | 94% ✓ |
| boot 속도 | **iter 300** | iter 500 | **2배** |

---

## 3. V47 실험 계획

### 전략 전환: V38.3 순정 + boot 가속만

V46 3-Run 실험(A/B/C)에서 확인: gait reward 추가(stride 1.45)와 shoulder 분리(0.44)로는 V38.3 수준(stride 6.79)에 도달 불가. 제거한 band/residency reward(+37.56)가 stride의 핵심 동력이었음.

**결론: 작동하는 시스템(V38.3)을 고치지 말고, 부족한 것(boot)만 더하자.**

### V47: V38.3 순정 + boot_standing + boot_contact — **성공**

```
유지: V38.3 reward 77개 전부, 기존 curriculum, CaT, shoulder -6.0
추가: boot_standing(+15), boot_contact(+5) — gait_gate 연동 ramp down
결과 (iter 5860):
  stride:    6.29  (V38.3: 6.79 — 93% 재현)
  coupling:  0.46  (V38.3: 0.49 — 94% 재현)
  shoulder:  0.43  (V38.3: 0.45 — V47이 더 좋음!)
  boot:      iter 300에서 ep_len 193 (V38.3: 86 — 2배 빠름)
```

### 이후 경로

```
V47.1: shoulder 개선 (shoulder_neutral -6→-3 등)
V47.2: coupling 추가 개선 (필요 시)
```

### 중단 기준 (전 Run 공통)

| iter | 조건 | 판정 |
|------|------|------|
| 300 | ep_len < 15 | boot 실패 → 중단 |
| 1000 | ep_len < 100 | boot 불안정 → 중단 |
| 3000 | stride < 2.0 OR coupling 0.0 | 가설 실패 → 분석 후 다음 Run |

### KPI 우선순위

```
1순위: ep_len / bad_orientation (boot 유지 — 잃으면 안 됨)
2순위: stride / coupling / leg_lift (gait 품질 — 주 목적)
3순위: shoulder_dev (splay — 제약조건, 0.45 이내면 OK)
```

---

## 4. V42~V44 시리즈 경과

| 버전 | 변경 | 결과 | 교훈 |
|------|------|------|------|
| V42 | 50→16개 reward | exploit 발견 | 독립 reward는 exploit 가능 |
| V43 | 15개 connected | boot 실패 (ep_len=8) | walking reward boot 충돌 |
| V43-B | gate_alpha ramp | boot 실패 | gating ≠ 원인 |
| V43-C | pose -0.3 | boot 실패 | pose ≠ 원인 |
| V43-D | Walking gating | ep_len 10, fwd 7x↑ | 방향 맞지만 positive 부족 |
| **V43-E** | **boot standing** | **ep_len 248, shoulder 0.40** | stride 0.39 (종종걸음) |
| V44 | coupling + pose↓ | stride 1.7↑, splay 0.53↑ | trade-off 미해결 |

### 핵심 교훈 (V42~V44)

1. walking reward가 boot에서 충돌 → boot gating 필수
2. boot에 positive signal 필수 (penalty만으로는 net negative)
3. reward 수를 줄이는 것 ≠ 정답. **어떤 reward가 있는가**가 핵심
4. joint_default_pose는 shoulder와 leg를 분리해야 함
5. output=0 reward는 weight를 올려도 0 (sparse gradient)
6. V38.3은 pose penalty -28.5에서도 stride 6.94 → 충분한 gait reward가 있으면 극복 가능

---

## 5. 주요 파일

| 파일 | 내용 |
|------|------|
| `source/.../spot_micro_rl_env_cfg.py` | 환경 설정 (기능 플래그 `_CLEAN_REWARDS`, `_CONNECTED_TROT`) |
| `source/.../mdp/rewards.py` | 보상 함수 (boot_standing, forward_velocity_gated, v42_boot_curriculum 등) |
| `plan/V46_PLAN.md` | V46 3-Run 실험 설계 |
| `plan/V43-E_PLAN.md` | V43-E boot 성공 + 종종걸음 분석 |
| `plan/V44_PLAN.md` | V44 stride/splay trade-off |

### 운영

- **listener**: `cmd.exe /c "cd /d D:\project\spot_micro_rl\isaac_ops && listen.cmd"`
- **CLI**: `cmd.exe /c "cd /d D:\project\spot_micro_rl\isaac_ops && cli.cmd /start"`
- **TensorBoard**: `cmd.exe /c "start /b ... --bind_all --port 6006"`
- **git push**: `cmd.exe /c "cd /d D:\project\spot_micro_rl && git push origin develop"`
