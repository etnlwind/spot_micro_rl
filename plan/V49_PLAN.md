# V49 Plan: Baseline Restore + Infrastructure

> 작성: 2026-03-28
> 상태: **완료 — stride 6.9 달성, 귀뚜라미 보행 발견 → V50으로 이관**

---

## 1. 왜 Baseline 복원이 필요한가

### V48-C/D 실패 후

V48-C(현실 질량 6.54kg)와 V48-D(현실 토크 1.5~5.0)가 모두 실패.
Two-track 전략에 따라 **V48-B 설정으로 복귀**하고, walking baseline 확보에 집중.

### V49 = V48-B + 인프라 정비

```
V49 설정:
  mass = 5.3 kg (원본 복원)
  effort = 15.0 Nm (원본 복원)
  leg_default = -0.97 (V48 보정 유지)
  init_height = 0.22m (V48-B)
  boot_standing = ON (V47)
```

---

## 2. Infrastructure 개선

### 2.1 Curriculum State Save/Restore

기존 문제: checkpoint에서 resume하면 curriculum이 iter 0부터 다시 시작.

```python
# curriculum state를 checkpoint와 함께 저장
curriculum_state = {
    "current_iter": iter,
    "reward_weights": current_weights,
    "phase": current_phase,
}
# checkpoint 로드 시 curriculum state도 복원
```

이로써 **resume 시 curriculum 진행 상태가 보존**됨.

### 2.2 `_USE_BOOT_STANDING` Feature Flag

기존 문제: `TRAIN_VERSION.startswith("V47")` 같은 버전 문자열 하드코딩으로 boot_standing 활성화 → **V49로 버전 올리면 boot_standing 누락**.

```python
# Before (V47):
if TRAIN_VERSION.startswith("V47"):
    # boot_standing 활성화

# After (V49):
_USE_BOOT_STANDING = True  # feature flag
if _USE_BOOT_STANDING:
    # boot_standing 활성화 — 버전과 무관
```

**실제 사고 발생**: 테스트 런 `07-49-43`에서 boot_standing 누락 → iter 0에서 진행 안 됨.
feature flag 도입 후 `08-08-39`에서 정상 작동.

### 2.3 CLI → Telegram → Listener 단일 실행 루트

```
기존: CLI에서 직접 python 실행 (세션 문제, PID 관리 불가)
변경: CLI → Telegram 메시지 → Listener가 수신 → 실행
```

모든 훈련 실행이 Listener 프로세스를 경유하도록 통일.

### 2.4 `/start gui` 옵션

```
/start         → headless 모드 (기본)
/start gui     → GUI 모드 (Listener Console 세션에서 실행)
```

WSL에서 GUI 프로세스는 세션 0 제한으로 직접 실행 불가 → Listener의 Console 세션을 활용.

### 2.5 Listener Stale Message Flush

```python
# Listener 시작 시 --resume 옵션으로 제어
# stale message (Listener 중단 동안 쌓인 Telegram 메시지) 처리
# --resume: stale message 무시하고 시작
# (없으면): stale message 처리 후 시작
```

### 2.6 버전 네이밍 규칙

```
Major (V50): from-scratch 훈련 필요 (reward 구조 변경 등)
Minor (V49.1): 기존 checkpoint에서 resume 가능 (weight 조정 등)
```

---

## 3. 테스트 런 이력

| Run | 시각 | 내용 | 결과 |
|-----|------|------|------|
| 06-23-30 | 06:23 | 이전 listener 자동 시작 (V49 이전 코드) | iter 0만 |
| 06-56-51 | 06:56 | listener 자동 시작 (V49 코드) | iter 200 |
| 07-49-43 | 07:49 | V49 수동 실행 (**boot_standing 누락!**) | iter 0만 |
| **08-08-39** | **08:08** | **V49 + _USE_BOOT_STANDING** | **iter 1140 진행** |

Run `07-49-43`의 실패가 feature flag 도입의 직접적 계기.

---

## 4. 결과: iter 1140

### 주요 지표

| 지표 | V49 (iter 1140) | V47 (iter 800) | 비교 |
|------|-----------------|----------------|------|
| ep_len | 234 | 238 | 유사 |
| stride | **6.9** | 6.29 | 개선 |
| coupling | **0.59** | 0.46 | 개선 |
| shoulder_dev | - | 0.43 | - |
| **front_leg_lift** | **0.08** | - | **심각하게 낮음** |
| **front_clearance** | **0.00** | - | **앞발 안 들림** |

### 귀뚜라미 보행 발견

stride 6.9로 수치상 우수하지만, **영상에서 뒷다리만 밀고 앞다리는 바닥에 고정**:

```
정상 보행:     귀뚜라미 보행:
  FL ↑↓           FL ── (고정)
  FR ↑↓           FR ── (고정)
  RL ↑↓           RL ↑↓ (밀기)
  RR ↑↓           RR ↑↓ (밀기)
```

front_leg_lift = 0.08, front_clearance = 0.00 → **앞다리가 전혀 들리지 않음**.

---

## 5. 원인 분석: 왜 귀뚜라미 보행인가

### boot_standing ramp-down이 너무 빠름

```
boot_standing ramp-down: 300 iter
  iter 0~300: boot_standing ON → "높이 서라" 신호
  iter 300~: boot_standing OFF → 높이 유지 신호 소멸
  iter 300~800: walking reward 활성화 → "앞으로 가면 보상"
```

300 iter 안에 "높게 서기" 습관이 충분히 각인되지 않음.

### "낮게 = 안전" 습관 고착

```
iter 0~300: 높이 서기 학습 (boot_standing)
iter 300~: boot_standing OFF + walking ON
  → "낮게 숙이면 넘어지지 않음" (alive_bonus 확보)
  → "낮은 자세에서 뒷다리만 밀면 stride 최대화"
  → 앞다리 불필요 → 귀뚜라미
```

낮은 자세에서 walking을 최적화하면 **앞다리가 구조적으로 불필요**해짐.

---

## 6. 핵심 교훈

| # | 교훈 | 출처 |
|---|------|------|
| 20 | boot_standing ramp-down이 너무 빠르면 "낮게 기기" 습관 고착 | V49 귀뚜라미 |
| 22 | Version 문자열 하드코딩 대신 feature flag 사용 | V49 boot_standing 누락 |
| 23 | CLI는 리스너 경유로 통일 (직접 실행 금지) | V49 실행 루트 통일 |

---

## 7. 다음 단계

V49의 귀뚜라미 보행 문제 → V50에서 boot 연장 + 높이 유지 강화 시도.

---

## 8. 파일 변경 요약

| 파일 | 변경 |
|------|------|
| `env_cfg.py` | mass 복원 5.3kg, effort 복원 15.0, `_USE_BOOT_STANDING` flag 추가 |
| `curriculum.py` | curriculum state save/restore 구현 |
| `listener.py` | CLI→Telegram→Listener 단일 루트, `/start gui`, stale message flush |
| `cli.py` | Telegram 경유 실행으로 변경 |
