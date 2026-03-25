# V43-B Plan: Boot Phase Propulsion Gate Ramp

> 작성: 2026-03-25
> 상태: **훈련 완료 — boot 실패 (V43과 동일)**

---

## 1. V43 실패 분석

V43에서 ep_len이 8로 고착. 분석팀 피드백: "propulsion_threshold=0.1이 boot phase에서 전진 신호를 차단"

### 가설

propulsion_threshold=0.1이 boot phase에서 너무 강한 gating → 전진 보상 신호 차단 → 전진 학습 불가 → ep_len 정체

### V43-B 핵심 변경

**Boot phase(iter 0~500)에서 propulsion gating 비활성, 이후 점진적 활성화**

---

## 2. 구현

### gate_alpha / push_alpha 파라미터 추가

```python
# forward_velocity_gated: gate_alpha 추가
effective_gate = (1.0 - gate_alpha) + gate_alpha * propulsion_gate
# alpha=0: no gating (V42 동작), alpha=1: full gating (V43 동작)

# gait_phase_contact_reward: push_alpha 추가
is_good_stance = push_alpha * is_pushing + (1 - push_alpha) * stance_mask
# alpha=0: contact only (V42), alpha=1: contact+push (V43)
```

### Curriculum ramp

| 구간 | gate_alpha | 동작 |
|------|-----------|------|
| iter 0~500 | 0.0 | gating 없음 |
| iter 500~1500 | 0→1 | 점진적 활성화 |
| iter 1500+ | 1.0 | V43 원래 동작 |

### 코드 변경

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | TRAIN_VERSION="V43-B", gate_alpha=0.0, push_alpha=0.0 초기값 |
| `rewards.py` | forward_velocity_gated에 gate_alpha, gait_phase_contact에 push_alpha 추가 |
| `rewards.py` | v42_boot_curriculum에 gate_ramp_start/end 추가 |

---

## 3. 리뷰 결과

코드 리뷰 에이전트: **8개 검증 항목 모두 PASS**
- gate_alpha=0 → effective_gate=1.0 (no gating) ✓
- gate_alpha=1 → effective_gate=propulsion_gate (full gating) ✓
- push_alpha=0 → contact only ✓
- push_alpha=1 → contact+push ✓
- Curriculum ramp 로직, term 이름 매칭, 초기값, 파라미터 모두 정상 ✓

---

## 4. 훈련 결과

- **Run**: `2026-03-25_17-07-55`
- **결과**: **boot 실패 — V43과 동일**

### V43 vs V43-B 비교

| iter | V43 ep_len | V43-B ep_len |
|------|-----------|-------------|
| 0 | 20.5 | 20.5 |
| 100 | 10.1 | 9.5 |
| 200 | 8.7 | 8.7 |
| 300 | 8.5 | 8.5 |

**차이 없음.** gate_alpha=0인데도 V43과 동일한 패턴.

---

## 5. 결론

**propulsion gating은 boot 실패의 원인이 아니었다.**

gate_alpha=0 (gating 완전 비활성)에서도 ep_len 8 고착 → 문제는 propulsion gating이 아닌 다른 곳.

→ V43-C에서 joint_default_pose 테스트
