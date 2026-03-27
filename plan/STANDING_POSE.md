# STANDING_POSE.md — SpotMicro 기본 서기 자세 분석

> 마지막 업데이트: 2026-03-27
> 상태: 보정 진행 중

---

## 1. 핵심 교훈

**FK 수식 계산을 믿지 말고, 반드시 시뮬레이터 실측 좌표로 검증해야 한다.**

이 URDF는 180° yaw 회전(base_rotate)이 있어서 수동 FK 계산이 틀리기 쉽다.
실제 시뮬레이터에서 body_pos_w를 읽어서 검증하는 것이 유일하게 신뢰할 수 있는 방법.

---

## 2. 실측 좌표 (leg=-0.68, foot=1.31)

시뮬레이터에서 `robot.data.body_pos_w`로 읽은 실제 world 좌표:

```
Front Left:  shoulder x=+0.093,  toe x=+0.129  → toe가 36mm 앞!
Front Right: shoulder x=+0.093,  toe x=+0.129  → toe가 36mm 앞!
Rear Left:   shoulder x=-0.093,  toe x=-0.057  → toe가 36mm 앞!
Rear Right:  shoulder x=-0.093,  toe x=-0.057  → toe가 36mm 앞!
```

**모든 발끝이 어깨보다 36mm 앞에 위치** → 뒤로 넘어지는 원인.

## 3. FK 계산 vs 실측 비교

```
FK 계산 (수동):  toe-shoulder = ±0.1mm (맞다고 주장)
시뮬레이터 실측:  toe-shoulder = +36mm (실제로 앞에 있음)

→ FK 계산이 36mm나 틀림!
→ 180° yaw 회전 체인에서 부호/방향 오류 발생
→ 수동 FK를 믿으면 안 됨
```

## 4. 다리 모양과 균형 원리

```
다리 모양 (옆에서 본 형태):

어깨(위) ─┐
           \
            > 무릎 (뒤로 뾰족)  ← < 모양
           /
발끝(아래) ┘

→ 어깨(위)와 발끝(아래)의 X좌표가 동일해야 안 넘어짐
→ 이것이 이 로봇의 기본 서기 자세의 핵심 조건
```

## 5. 보정 계산 (실측 기반)

```
현재 (leg=-0.68):    toe가 shoulder보다 +36mm 앞
FK 변화율:           ~13mm per 0.07rad (leg angle 변화)
필요한 보정:          -36mm → 약 -0.19rad 추가

보정된 leg angle:     -0.68 + (-0.19) = -0.87
```

## 6. 검증 방법

**반드시 시뮬레이터 실측으로 검증:**

1. deterministic_trot.py에서 `robot.data.body_pos_w`로 좌표 출력
2. `_trot_coords.txt` 파일에 기록됨
3. shoulder_link x와 toe_link x가 같은지 확인
4. FK 수식 계산 결과가 아닌 이 실측값이 ground truth

```python
# 시뮬레이터에서 좌표 읽는 코드
body_pos = robot.data.body_pos_w[0]
body_names = robot.body_names
for i, name in enumerate(body_names):
    if "shoulder" in name or "toe" in name:
        x, y, z = body_pos[i][0].item(), body_pos[i][1].item(), body_pos[i][2].item()
        print(f"{name}: x={x}, y={y}, z={z}")
```

## 7. 이것이 RL 훈련에 미치는 영향

standing pose가 물리적으로 불균형하면:
- RL이 불균형을 보상하기 위해 비자연스러운 자세를 학습
- V47에서 뒷발 위주 보행이 나온 원인 중 하나일 수 있음
- V47-B 자세 교정 실험 전에 이 기본 자세부터 올바르게 잡아야 함

## 8. Anymal-C vs SpotMicro 비교 (핵심 발견)

Anymal-C는 스폰 직후 안정적으로 서있음. SpotMicro와의 차이:

```
항목                   Anymal-C         SpotMicro        비율
effort_limit           80.0             15.0             5.3배!
saturation_effort      120.0            15.0             8배!
stiffness              40.0             15.0             2.7배
damping                5.0              1.5              3.3배
init height            0.6m             0.192m
앞뒤 init angle        다름(비대칭)      동일(4발 대칭)
```

**결정적 차이: effort_limit**
- stiffness 40에서 토크 = 40 × error → 하지만 effort_limit=15에서 잘림
- foot 관절이 중력을 못 이기고 처지는 진짜 원인
- Anymal은 effort 80이라 stiffness 40의 토크를 충분히 전달

**실측 증거 (fix_base=True, stiffness=40, effort=30)**
- foot: 설정 1.31 → 실측 1.56 (0.25 처짐)
- 토크 = 40 × 0.25 = 10 < effort_limit 30 → effort는 충분
- 그런데도 처지는 이유: DCMotor의 토크 계산이 단순 PD가 아님 (velocity term 포함)

## 9. URDF 특이사항

```
base_rotate: fixed joint, rpy=(0, 0, π) = 180° yaw
→ base_link의 모든 자식 링크가 180° 회전된 프레임에 있음
→ 수동 FK 계산 시 방향 오류 발생 가능
→ 시뮬레이터 실측이 유일한 신뢰 소스
```
