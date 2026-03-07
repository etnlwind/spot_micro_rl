# V13~V15d: Critic Reset 실패와 From-Scratch 전략 전환
> **기간**: 2026-02-24 ~ 2026-02-26  
> **환경**: Rough (V13~V14b) → Flat (V15 시리즈)  
> **핵심 교훈**: 보상 구조가 크게 바뀌면 from scratch가 유일한 답

---

## 1. V13: Critic Reset 첫 시도 (2026-02-24)

### 배경
- V12의 actor는 합리적이었으나, critic이 오래된 보상 구조에 갇힘
- 새 보상 추가 시 value function의 추정이 완전히 틀림
- **아이디어**: V12 actor 유지 + critic만 Xavier init으로 초기화

### 시도
```python
# Critic 가중치만 초기화 (Xavier uniform)
for name, param in critic.named_parameters():
    if 'weight' in name:
        nn.init.xavier_uniform_(param)
    elif 'bias' in name:
        nn.init.zeros_(param)
```

### 학습 체인
| 폴더 | iter | 비고 |
|------|------|------|
| `2026-02-24_08-54-15` | 30,400→47,360 | V13 학습 (2회 시도) |

### 결과
- ❌ **value_loss 발산** — critic이 새 보상 landscape를 학습하지 못함
- actor 업데이트가 불안정해지면서 전체 정책 붕괴
- 2회 연속 실패

---

## 2. V14: 접촉 독립 보상 + Critic Reset (2026-02-25)

### 시도
- V12 기반에서 접촉 센서 의존도를 줄인 새 보상 설계
- 다시 critic reset 적용

### 학습 체인
| 폴더 | iter | 비고 |
|------|------|------|
| `2026-02-25_16-34-32` | 35,000→35,005 | V14 — **5 iter 만에 발산** |

### 결과
- ❌ **즉시 발산** — 보상 구조 변경 폭이 너무 커서 critic이 완전히 무력

---

## 3. V14b: 축소 가중치 + Critic Reset (2026-02-25)

### 시도
- V14의 새 보상을 유지하되 가중치를 대폭 축소
- "소프트" critic reset으로 발산 방지 시도

### 학습 체인
| 폴더 | iter | 비고 |
|------|------|------|
| `2026-02-25_17-09-37` | 35,000→35,365 | V14b — 365 iter에서 발산 |

### 결과
- ❌ **조금 버텼지만 결국 발산** (365 iter)
- 가중치를 줄여도 보상 구조 자체가 다르면 critic이 적응 불가

---

## 4. 결론: Critic Reset은 큰 보상 변경에 부적합

### 3연속 실패 분석

| 버전 | 보상 변경 폭 | 생존 iter | 결과 |
|------|:---:|:---:|------|
| V13 (1차) | 큼 | 수백 | 발산 |
| V13 (2차) | 큼 | 수백 | 발산 |
| V14 | 매우 큼 | **5** | 즉시 발산 |
| V14b | 중간 | 365 | 발산 |

### 근본 원인
```
보상 구조 크게 변경 
  → Critic의 value 추정이 현실과 완전히 괴리
  → Advantage estimate가 부정확
  → Policy gradient 방향이 잘못됨
  → Actor 업데이트가 엉뚱한 방향
  → 악순환 → 발산
```

Xavier init은 critic을 "무지 상태"로 만드는 것인데, 오래된 actor와 짝을 이루면 actor의 기존 행동에 대한 value를 전혀 추정할 수 없어서 오히려 더 불안정.

---

## 5. V15 시리즈: 전략 전환 — From-Scratch Flat (2026-02-26)

### 핵심 결정
> **"Rough에서 fine-tune 포기. Flat에서 처음부터 뒷다리 보상을 포함시켜 학습."**

- Rough 환경의 복잡성(height_scan, terrain curriculum) 없이
- Flat에서 순수하게 보행 품질에 집중
- 뒷다리 관련 보상을 처음부터 내장

### V15a: 첫 시도
- 보상 스케일이 V12 수준으로 큼 (trot_gait=180, forward_velocity=35 등)
- iter ~1600에서 발 끌림 확인

### V15b: 보상 스케일 축소
- 보상 가중치를 전반적으로 줄임
- ❌ **value_loss 발산** — gamma=0.99가 return을 키움

### V15c: 추가 축소
- ❌ **여전히 발산** — gamma=0.99 자체가 문제

### V15d: PPO 하이퍼파라미터 근본 수정 ★

#### 핵심 변경
```python
# Before (V15a~c)
gamma = 0.99       # return이 매우 큼
clip_param = 0.2   # 큰 업데이트 허용
learning_rate = 5e-4

# After (V15d) — 안정화 성공!
gamma = 0.97       # return 3x 축소
clip_param = 0.1   # 작은 업데이트만 허용
learning_rate = 1e-4  # 보수적 학습
```

#### 결과
- **15,000 iter, reward=559, value_loss=0.53** — 안정적 학습 완료!
- 체크포인트: `2026-02-26_16-08-11/model_14999.pt`
- 서기+앞다리 보행 정상
- **그러나 뒷다리는 여전히 끌림** → 보상 구조 자체의 문제

---

## 6. V15d PPO 설정 (이후 모든 버전의 기준)

```python
gamma = 0.97
clip_param = 0.1
learning_rate = 1e-4
schedule = "fixed"
epochs = 3
mini_batches = 4
value_loss_coef = 0.5
entropy_coef = 0.01
network = [512, 256, 128]  # actor = critic
activation = "ELU"
num_steps_per_env = 48
save_interval = 200
```

---

## 7. 이 시기의 핵심 교훈

| 교훈 | 근거 |
|------|------|
| **Critic reset + fine-tune은 큰 보상 변경에 부적합** | V13, V14, V14b 3연속 발산 |
| **From-scratch가 fine-tune보다 안전** | V15d가 V13보다 훨씬 안정적 |
| **PPO 안정성 = gamma × reward_scale** | gamma 0.99→0.97로 return 3× 축소 → 발산 해결 |
| **clip_param이 작을수록 안정적** | 0.2→0.1로 줄이니 value_loss 안정화 |
| **learning_rate도 보수적으로** | 5e-4→1e-4로 줄여서 안정성 확보 |
