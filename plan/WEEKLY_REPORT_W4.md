# 4주차 진행

- 4주차 훈련 리포트 (고용량 PT파일 제외)
    - V36 iter 800: Report_V35.5_iter800_20260320_125628.zip
    - V37 훈련 중 (iter ~100 / 15,000)

- **연구 목표**
    - V32.1 기반 보행 품질 개선 — 벌레보행(splay)과 셔플링(shuffle) 제거
    - 부팅 안정화 근본 해결 및 100% 재현성 확보
    - 최신 논문 조사를 통한 향후 기술 로드맵 수립

- **주요 수행 내용**
    - V24~V31.2: front lock-in 해소 실험 → 다리별 전용 보상의 역할 분리 문제 규명
    - V32~V34: 보상 구조 근본 재설계 시도 (122→28개) → 부팅 불가로 실패
    - V35~V35.5: 부팅 안정화 3결합(alive_bonus + contacts 램프 + 저속 command) 달성
    - V36~V37: anti-shuffle 성공, anti-splay 커리큘럼 설계 및 훈련 시작
    - IsaacOps 통합 패키지 완성 (supervisor + heartbeat + 영상 → 단일 listener)

- **핵심 분석 결과**
    - **V32.1이 25% 재현성**임을 발견 — 동일 코드 4회 중 1회만 성공, V33~V34 실패의 숨은 원인
    - alive_bonus=10.0 + contacts 초기 완화 + 저속 command **3결합으로 100% 부팅 달성** (V35.5)
    - V36에서 **stride +34%, swing +128% 개선**(anti-shuffle 성공), 그러나 shoulder_dev 0.54 고착(anti-splay 실패)
    - anti-splay 실패 원인: penalty가 전체 reward의 **0.6%에 불과** → 5~10% 이상이어야 행동 변경 유도 가능

- **기술적 의미**
    - 부팅 안정화가 보행 품질 개선의 **전제조건**임이 확인됨
    - penalty의 절대값이 아닌 **전체 reward 대비 비율**이 학습 행동을 결정함
    - 최신 논문 조사 결과, Barrier 함수(KAIST)·CaT(Solo-12) 등이 weight 커리큘럼보다 효과적인 anti-splay 해법으로 파악됨

- **금주 성과**
    - 부팅 안정화 근본 해결 — 재현성 25% → 100% (V35.5)
    - Anti-shuffle 성공 — stride +34%, swing +128% (V36)
    - IsaacOps 통합 패키지 완성 — 단일 listener, CLI, 자동 run 감지
    - V37 anti-splay 커리큘럼 설계 및 훈련 시작 (shoulder -6→-15, iter 500~1000)

- V37은 iter 700~1000에서 shoulder_dev < 0.3 달성 여부로 판정 예정
- 실패 시 V38에서 Barrier 함수 또는 CaT(Constraints as Terminations) 도입 예정
