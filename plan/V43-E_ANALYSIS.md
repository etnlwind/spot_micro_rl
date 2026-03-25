V43-E Analysis

작성: 2026-03-26
기준 문서: plan/V43-E_PLAN.md
목적: V43-E의 설계 의도, 실제 결과, 수렴 패턴, 실패 원인, 다음 단계(V44) 권고안을 정리한다.

⸻

1. 한 줄 결론

V43-E는 boot 문제 해결에는 성공했지만, 정상 trot 형성에는 실패했다.
정확히는 “boot standing + walking gating”으로 서기/안정화/전진은 확보했으나, 최종적으로는 4발 균등 종종걸음(local optimum)에 수렴했다.

즉 V43-E는 실패한 실험이 아니라,
	•	부팅 복구 실험으로는 성공
	•	보행 품질 실험으로는 미완/실패
라고 평가하는 것이 가장 정확하다.

⸻

2. V43-E가 해결한 것

2.1 Boot 문제 해결

V43, V43-B, V43-C, V43-D에서 반복되던 핵심 문제는 boot 실패였다.

공통 패턴:
	•	ep_len ≈ 8~10
	•	bad_orientation ≈ 100%
	•	걷기 이전에 계속 넘어짐

V43-E는 여기서 벗어났다.

도달한 상태:
	•	ep_len ≈ 248
	•	bad_orientation ≈ 0.8%
	•	shoulder_dev ≈ 0.40
	•	forward_velocity ≈ 5.9

이는 V43-E의 핵심 추가 요소인 아래 두 reward가 boot phase에서 실제로 작동했다는 뜻이다.
	•	boot_standing_reward
	•	boot_foot_contact

즉 V43-D의 “penalty 사막” 문제를 메우는 데는 성공했다.

2.2 Positive/Negative 구조 복구

V43-D는 walking reward를 꺼서 충돌은 줄였지만, positive signal이 너무 약했다.
V43-E는 boot standing/bootstrap reward를 추가해 초기 학습 방향을 다시 만들었다.

이 점에서 V43-E는 “walking reward를 끈 것”이 아니라 “boot phase용 학습 신호를 재구성한 것” 이다.

⸻

3. V43-E가 실패한 것

3.1 stride 형성 실패

최종 수렴 상태에서:
	•	stride ≈ 0.39
	•	목표: > 6.0

이는 보폭이 거의 없는 수준이다.
즉 로봇은 앞으로는 가지만, 크게 내딛지 않는다.

3.2 diagonal coupling 형성 실패

최종 수렴 상태에서:
	•	diagonal_coupling = 0.0

이 값은 사실상 대각 교대 trot 패턴이 형성되지 않았음을 뜻한다.
로봇은 phase는 일부 따를 수 있지만, 실제 trot 구조는 만들지 못했다.

3.3 feet_air_time/보행 패턴 실패

문서 기준으로 V43-E는 결과적으로
	•	4발이 다 적당히 움직이고
	•	잘 안 넘어지고
	•	전진은 하지만
	•	보폭 없이 빠르게 짧게 움직이는
“4발 균등 종종걸음” 으로 수렴했다.

즉
	•	V38.3 = 비대칭이지만 효율적인 보행
	•	V43-E = 대칭적이지만 비효율적인 보행

이라는 차이가 생겼다.

⸻

4. 현재 local optimum의 성격

4.1 지금 로봇이 실제로 하고 있는 것

현재 로봇이 최적화한 전략은 다음과 같다.
	1.	넘어지지 않는다.
	2.	관절을 크게 움직이지 않는다.
	3.	4발을 조금씩 빠르게 움직인다.
	4.	전진 보상은 충분히 받는다.
	5.	대신 보폭은 거의 만들지 않는다.
	6.	대각 교대 trot는 만들지 않는다.

즉 현재 최적해는

“크게 걷지 않고, 짧고 빠르게 종종거리며 안정적으로 전진하는 것”

이다.

4.2 왜 이게 합리적인 최적해인가

현재 reward 구조에서는 이 전략이 수학적으로 합리적이다.
	•	forward_velocity 보상은 매우 큼
	•	stride 보상은 상대적으로 약함
	•	joint_default_pose penalty는 큼
	•	큰 보폭/큰 관절 움직임은 pose penalty를 유발함
	•	diagonal trot을 직접 강제하는 보상이 없음

그래서 로봇 입장에서는:
	•	큰 보폭을 만들면 손해
	•	대각 교대를 굳이 할 이유가 없음
	•	작은 걸음으로 빠르게 전진하는 편이 더 유리

즉 이건 로봇의 문제가 아니라,
reward 설계가 만든 최적해라고 보는 것이 맞다.

⸻

5. 근본 원인 3가지

5.1 forward_velocity >> stride 불균형

분석 결과상 현재는 forward_velocity 보상이 stride보다 훨씬 강하다.

의미:
	•	속도만 확보되면 됨
	•	보폭이 작아도 reward 총합은 충분히 좋음

결과:
	•	“보폭 없는 빠른 걸음”이 reward 상 유리

5.2 diagonal_coupling 직접 보상 부재

V43에서는 gait_phase가 diagonal_coupling을 대체할 것으로 기대했지만,
실제 결과는 그렇지 않았다.
	•	gait_phase: 타이밍 신호
	•	diagonal_coupling: 실제 대각 교대 패턴 신호

현재는 타이밍을 어느 정도 따라도,
실제 trot 구조를 만들 이유가 부족하다.

5.3 joint_default_pose penalty가 큰 움직임을 막음

현재 penalty 구조에서 joint_default_pose는 큰 보폭/큰 관절 각도를 사실상 억제한다.

결과:
	•	크게 내딛기보다
	•	default pose 근처에서
	•	작은 진폭으로 빠르게 움직이는 편이 유리

즉 stride를 억제하는 강한 숨은 제약으로 작동한다.

⸻

6. V38.3과 비교했을 때의 의미

6.1 V38.3이 더 나았던 것

V38.3은 비대칭 문제가 있었지만,
	•	stride가 컸고
	•	뒷발 lift가 강했고
	•	diagonal-ish 패턴이 일부라도 있었고
	•	실제로는 더 효율적인 보행에 가까웠다.

6.2 V43-E가 더 나았던 것

V43-E는
	•	boot가 안정적이고
	•	넘어지지 않고
	•	shoulder_dev가 더 좋고
	•	4발이 모두 고르게 참여한다.

6.3 결론

V43-E는
	•	stability / boot / posture 쪽은 V38.3보다 우수하지만,
	•	gait efficiency / stride / trot pattern 쪽은 V38.3보다 열세다.

즉 V43-E는

“더 안정적이지만, 덜 잘 걷는다”

라고 요약할 수 있다.

⸻

7. V43-E에 대한 최종 판정

성공한 축
	•	Boot recovery
	•	Stable standing
	•	Long episode length
	•	Low bad_orientation
	•	Good shoulder_dev
	•	Four-leg participation

실패한 축
	•	Stride formation
	•	Diagonal trot formation
	•	Efficient gait pattern
	•	Feet air / clear swing quality

최종 판정 문구

V43-E는 boot recovery 실험으로는 성공이다. 하지만 정상 trot 형성 실험으로는 실패이며, 4발 균등 종종걸음으로 수렴이 확정되었다.

⸻

8. 다음 단계: V44 설계 방향

현재 단계에서 더 오래 돌리는 것은 권장하지 않는다.
이미 수렴 형태가 분명하기 때문이다.

우선순위 1 — diagonal_coupling 복원

가장 중요함.

이유:
	•	현재 trot의 직접 신호가 없음
	•	gait_phase는 trot를 대체하지 못함
	•	diagonal_coupling 없이는 대각 교대를 기대하기 어려움

역할:
	•	패턴의 방향 제공
	•	“대각 교대를 해야 한다”는 명시적 유도

우선순위 2 — joint_default_pose 완화

두 번째로 중요함.

이유:
	•	큰 보폭 시도 자체가 penalty로 차단됨
	•	stride가 작은 이유 중 하나가 pose penalty 구조

역할:
	•	큰 움직임 허가
	•	“관절을 더 써도 된다”는 허용 신호

왜 둘을 같이 해야 하나
	•	coupling만 추가 → 작은 trot 가능성
	•	pose만 완화 → 큰 종종걸음 가능성
	•	둘 다 추가 → trot 방향 + 큰 보폭 허용

즉 V44는 최소 유효 변경으로 아래를 권장한다.
	1.	diagonal_coupling 복원
	2.	joint_default_pose 완화 (-2.0 → -0.5 수준 검토)
	3.	나머지 V43-E의 boot standing 구조는 유지

⸻

9. V44 예상 결과

보수적으로 예상하면:
	•	ep_len: 230+
	•	stride: 2.0 ~ 4.0
	•	diagonal_coupling: 0.2 ~ 0.4
	•	shoulder_dev: 0.40 ~ 0.45
	•	forward_velocity: 3.0 ~ 5.0

즉 V43-E보다 약간 덜 안정적일 수는 있지만,
대신 정상 보행 구조로 들어갈 가능성이 생긴다.

⸻

10. 실행 권고안

권고
	•	V43-E는 여기서 종료
	•	V44로 넘어감
	•	최소 유효 변경으로 시작

비권고
	•	V43-E를 더 오래 관찰
	•	stride weight만 단독 상향
	•	forward_velocity를 먼저 하향
	•	V38.3 reward를 대량 복원

이들은 현재 원인보다 결과를 때리는 방식이거나,
복잡도만 늘릴 위험이 있다.

⸻

11. 최종 요약

V43-E는 중요한 단계였다.
이 실험은 아래를 증명했다.
	1.	boot standing bootstrap은 실제로 boot 문제를 해결한다.
	2.	하지만 boot 성공이 곧 좋은 gait를 뜻하지는 않는다.
	3.	현재 reward 구조에서 로봇은 “4발 균등 종종걸음”을 합리적 최적해로 선택했다.
	4.	다음 단계는 stride를 세게 때리는 것이 아니라,
trot 패턴의 방향(diagonal coupling)과 큰 움직임의 허가(joint pose 완화)를 동시에 여는 것이다.

따라서 V43-E는 실패한 실험이 아니라,

“부팅은 해결했지만, 이제 진짜 gait 구조 문제로 넘어갈 때가 되었다”는 것을 분명히 보여준 성공적인 전환 실험

으로 평가할 수 있다.
