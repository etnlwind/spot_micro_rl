# Run Version History

Generated: 2026-03-15, Updated: 2026-03-18

## 데이터 위치

- **런 디렉토리**: `logs/rsl_rl/spot_micro_flat/YYYY-MM-DD_HH-MM-SS/`
- **각 런 버전 파일**: `logs/rsl_rl/spot_micro_flat/<run_dir>/train_version.txt`
- **이 문서 원본**: `plan/RUN_VERSION_HISTORY.md` (V21~V26 이후 분석 문서들과 함께 관리)

## Background

All run Excel files were mislabeled as "v24" or "v23" due to a `V23_TRAIN_VERSION = "V24"` hardcoding
bug in `scripts/common.py`. The variable was renamed from `V23_TRAIN_VERSION` to `TRAIN_VERSION` and
its value was corrected on 2026-03-15 (commits 4b07453, f91513d, fe396d9).

The actual training version is determined by `TRAIN_VERSION` in
`source/spot_micro_rl/spot_micro_rl/tasks/manager_based/spot_micro_rl/spot_micro_rl_env_cfg.py`,
which controls the actual reward design used during training.

Two separate version variables existed during the V23–V24 era:
- `env_cfg.py` `TRAIN_VERSION`: the actual reward design version
- `common.py` `V23_TRAIN_VERSION`: the version label used for Excel/reporting (was hardcoded to "V24")

These were out of sync during V23 and V24, causing all Excel files from that era to say "v23" or "v24"
regardless of the actual reward design.

---

## Version Timeline (from git)

| Version | Commit | Date/Time (KST) | Key Change |
|---------|--------|-----------------|------------|
| V20 | `8e4eacd` | 2026-03-08 17:19 | Soft-ramp curriculum + enhanced logging; TRAIN_VERSION V19→V20 |
| V21 | `857b15e` | 2026-03-10 15:51 | Heartbeat KPI redesign (gait-quality-first), supervisor iteration-based cadence, toe contact reinterpretation, diagnostics tools; infra-only, TRAIN_VERSION unchanged (stays V20); validated on 03-10_07-43-51 model_10800.pt |
| V22 | (no commit) | ~2026-03-11 13:xx | Multiview video package (5-angle) + heartbeat workbook; infra-only, TRAIN_VERSION unchanged (stays V20); validated on 03-11_02-39-01 model_15000.pt; absorbed into V23 commit |
| V23 | `454082c` | 2026-03-11 14:18 | Posture-first refinement; TRAIN_VERSION V20→V23 (skipped separate V22 commit) |
| V24 | `d774e39` | 2026-03-13 15:05 | Add limb validity gating and run-scoped reporting; TRAIN_VERSION V23→V24 |
| V25 | `393e520` | 2026-03-14 21:53 | Direct RL penalty, diagonal gate, restart-on-collapse; TRAIN_VERSION V24→V25 |
| V26 | (no commit) | 2026-03-15 01:46 | First symmetric floor + load sharing experiment; uncommitted V26 changes in env_cfg.py + rewards.py (~201 lines); run 01-46-44 only; absorbed into V26.1 after analyzing results |
| V26.1 | `1c242fe` | 2026-03-15 03:13 | Refined symmetric existence floor + load sharing based on V26 experiment results; TRAIN_VERSION V25→V26 in env_cfg.py; +330 lines to rewards.py (vs +201 in V26); V26.1 label in common.py |
| V26.1 (common.py fix) | `4b07453` | 2026-03-15 08:33 | Fix V23_TRAIN_VERSION "V24"→"V26.1" in common.py; fixes Excel mislabeling |
| V26.1 (rename) | `f91513d` | 2026-03-15 08:53 | Rename V23_TRAIN_VERSION → TRAIN_VERSION in common.py |
| V26.1 (unified) | `fe396d9` | 2026-03-15 09:02 | Single-source TRAIN_VERSION = "V26.1" in common.py; TRAINING_CONFIG dict |
| V27 | (commit) | 2026-03-16 | contact residency EMA + propulsion/usage band reward 구조 도입; TRAIN_VERSION V26.1→V27 |
| V28 | (commit) | 2026-03-16 | V27 재기동 + hyperparameter 조정; TRAIN_VERSION V27→V28 |
| V28.2 | `745d7b6` | 2026-03-16 | rear pair 대칭 강제 (rear_pair_contact_diff_penalty); TRAIN_VERSION V28→V28.2 |
| V28.3 | `c50925f` | 2026-03-17 | front contact cap penalty 추가; TRAIN_VERSION V28.2→V28.3 |
| V29 | `0d57630` | 2026-03-17 | residency band_high=0.65 + stride_length + swing_gate_velocity; TRAIN_VERSION V28.3→V29 |
| V29 (reliability) | `f11242e` | 2026-03-17 | TRAIN_VERSION 단일 소스(env_cfg.py 권위), supervisor 중복 프로세스 자동 종료, 알림 버전 표시 |
| V29.2 | `483c627` | 2026-03-17 | residency band 교정 [0.20,0.85], target_band 0.75/w=3.0, front_rear_balance -4.0, enforce 800→ |
| V29.2 (docs) | `ff62aff` | 2026-03-17 | V29 analysis + V29.2 plan 문서 추가 |
| V30 | (uncommitted) | 2026-03-18 | 초기 자세 대칭 교정 (leg=-0.71, foot=1.31); TRAIN_VERSION V29.2→V30 |
| V31 | (uncommitted) | 2026-03-18 | front swing 강제 4함수 (front_swing_bonus, front_alternation, front_both_ground, min_swing_ratio); TRAIN_VERSION V30→V31 |
| V31.1 | (uncommitted) | 2026-03-18 | front_alternation 비활성화, front_both_ground -40→-15; TRAIN_VERSION V31→V31.1 |
| V31.2 | (uncommitted) | 2026-03-18 | front_both_ground/min_swing_ratio 비활성화, front_joint_velocity(+15)/front_joint_frozen(-40) 신규; TRAIN_VERSION V31.1→V31.2 |

**Note (V26 era)**: env_cfg.py had `TRAIN_VERSION = "V26"` (reward design V26.1 base), common.py had `TRAIN_VERSION = "V26.1"`.
V26 (01-46-44) and V26.1 (07-08-50) are **separate experiments**: V26 was an exploratory run with uncommitted code;
V26.1 was designed after analyzing V26 results and committed.

**Note (V29+ era)**: TRAIN_VERSION is now single-sourced from `env_cfg.py`. `common.py` imports it from there.

---

## Run Directory Mapping

| Run Dir | Version | Last Iter | Excel Label | Notes |
|---------|---------|-----------|-------------|-------|
| 2026-03-10_01-17-39 | **V20** | 8000 | none | V20 tooling + rewards |
| 2026-03-10_04-30-32 | **V20** | 9400 | none | V20 tooling + rewards |
| 2026-03-10_07-43-51 | **V20** | 10800 | none | V20 tooling + rewards; V21 validation target (heartbeat KPI + supervisor + toe contact tested on model_10800.pt after V21 commit) |
| 2026-03-10_10-58-10 | **V20** | 10800 | none | V20 tooling + rewards |
| 2026-03-10_15-56-10 | **V21** | 10400 | none | V21 tooling (after 03-10 15:51 commit); rewards V20 (TRAIN_VERSION unchanged) |
| 2026-03-10_18-02-00 | **V21** | 10600 | none | V21 tooling; rewards V20 |
| 2026-03-10_19-53-35 | **V21** | 12000 | none | V21 tooling; rewards V20 |
| 2026-03-10_23-02-43 | **V21** | 13600 | none | V21 tooling; rewards V20 |
| 2026-03-11_02-39-01 | **V22** | 15000 | v23 | V22 validation target (multiview + heartbeat workbook tested on model_15000.pt); ran with V21 committed code; rewards V20; Excel label "v23" due to later report regeneration |
| 2026-03-11_14-10-27 | **V23** | 0 | none | Started with V23 uncommitted changes active; only model_0.pt saved; aborted |
| 2026-03-11_14-32-22 | **V23** | 0 | v23 | Branch "ahead by 1 commit" = V23 committed; only model_0.pt saved |
| 2026-03-11_16-27-08 | **V23** | 600 | v23 | |
| 2026-03-11_22-13-01 | **V23** | 600 | none | Stopped early; no Excel generated |
| 2026-03-11_22-36-04 | **V23** | 600 | none | Stopped early; no Excel generated |
| 2026-03-11_22-38-08 | **V23** | 600 | v23 | |
| 2026-03-12_14-08-05 | **V23** | 1 | v23 | Barely started (model iter 1) |
| 2026-03-12_14-50-51 | **V23** | 1200 | v23 | |
| 2026-03-12_16-31-59 | **V23** | 2400 | v23 | |
| 2026-03-13_14-03-45 | **V24** | 200 | v23 | Started at 14:03 BEFORE d774e39 commit at 15:05, but env_cfg.py already had V24 uncommitted in working tree → actual reward design was V24. Excel "v23" because common.py still said "V23" at Excel generation time |
| 2026-03-13_18-53-26 | **V24** | 1800 | v24 | |
| 2026-03-14_17-46-10 | **V24** | 1800 | none | Continuation run; no Excel generated |
| 2026-03-14_17-52-38 | **V24** | 1800 | v24 | |
| 2026-03-14_18-00-08 | **V24** | 1800 | v24 | |
| 2026-03-14_18-12-32 | **V24** | 1800 | v24 | |
| 2026-03-14_18-29-12 | **V24** | 2000 | v24 | |
| 2026-03-14_19-05-50 | **V24** | 2000 | v24 | |
| 2026-03-14_21-59-46 | **V24** | 2000 | v24 | resume=true from V24 run 19-05-50 model_2000.pt; V25 코드로 시작했으나 즉시 붕괴 (reward 67), 실질 학습 0. model_2000.pt는 V24 가중치 그대로 → V24로 분류 |
| 2026-03-14_22-23-04 | **V25** | 400 | v24 | resume=false (fresh start); V25 리워드로 iter 400까지 진행 후 종료 |
| 2026-03-15_01-46-44 | **V26** | 1000 | v24 | Exploratory V26 run; env_cfg.py TRAIN_VERSION V25→V26 uncommitted (+201 lines to rewards.py); Excel "v24" mislabeled; results used to refine V26.1 |
| 2026-03-15_07-08-50 | **V26.1** | 1800 | V26.1 | First V26.1 run after 1c242fe commit (+330 lines to rewards.py); first run with correct Excel label |
| 2026-03-16_xx-xx-xx | **V27** | ~1000 | V27 | V27 run; iter 1000 이후 RL collapse → 실패 |
| 2026-03-16_xx-xx-xx | **V28** | ~? | V28 | V28 run (재기동 후 RR collapse) → 실패 |
| 2026-03-16_xx-xx-xx | **V28.2** | ~1703 | V28.2 | rear pair 대칭 달성 (rear_usage_diff=0.012 at iter 1703) → 성공 |
| 2026-03-17_xx-xx-xx | **V28.3** | ~2200 | V28.3 | front cap 추가; FL/FR contact 0.83~0.88 고착 → 실패 |
| 2026-03-17_18-01-05 | **V29** | ~1000 | V29 | residency band_high=0.65; 전체 4발 band 밖 → gradient 소멸 → 실패 |
| 2026-03-17_23-06-20 | **V29.2** | 201 | V29.2 | band 교정 [0.20,0.85]; supervisor silent crash로 iter 201 중단 |
| 2026-03-18_07-29-55 | **V30** | 724 | V30 | 초기 자세 대칭; reward 323 @644, FL/FR lock-in 불변; late_phase 급락으로 조기 종료 |
| 2026-03-18_11-13-18 | **V31** | ~421 | V31 | front swing 4함수; FL+RR만 접지, FR+RL 붕괴 (대각 2발 고착) → 실패 |
| 2026-03-18_13-11-59 | **V31.1** | 1001 | V31.1 | front_alternation 비활성화, front_both_ground -15; FL 0.874 lock-in + RL 0.027 붕괴 (대각 역할 분리) → 실패 |
| 2026-03-18_17-43-22 | **V31.2** | 훈련 중 | V31.2 | contact-level 패널티 전폐, front_joint_velocity(+15)/front_joint_frozen(-40) 신규; 🟡 훈련 진행 중 |

---

## Evidence Sources

Each run directory contains `git/spot_micro_rl.diff` with:
- `--- git status ---`: shows whether branch was "up to date", "ahead", or had uncommitted changes
- `--- git diff ---`: shows uncommitted changes to source files at training start time

Key evidence used for version determination:

1. **2026-03-11_14-10-27**: diff shows `-TRAIN_VERSION = "V20"` / `+TRAIN_VERSION = "V23"` as
   uncommitted change -> V23 working tree was active when training started (before the commit)

2. **2026-03-13_14-03-45**: diff shows `-V23_TRAIN_VERSION = "V23"` / `+V23_TRAIN_VERSION = "V24"`
   as uncommitted in common.py, AND `-TRAIN_VERSION = "V23"` / `+TRAIN_VERSION = "V24"` as
   uncommitted in env_cfg.py. But the run started at 14:03 and V24 commit was at 15:05. The Excel
   filename is `spotmicro_v23_*` meaning common.py was still on "V23" when Excel was created ->
   confirmed V23 run despite pending uncommitted V24 changes.

3. **2026-03-14_21-59-46**: no TRAIN_VERSION changes in git diff, "up to date with origin/develop".
   V25 commit was at 21:53, run at 21:59 (6 min later) -> V25. Heartbeat contains
   `collapse_persistent` and `restart_recommended` fields which are V25 features.

4. **2026-03-15_01-46-44**: diff shows `-TRAIN_VERSION = "V25"` / `+TRAIN_VERSION = "V26"` as
   uncommitted change in env_cfg.py, and +201 lines uncommitted in rewards.py -> V26 reward design
   was in working tree when training started (at 01:46). The 1c242fe "V26.1" commit at 03:13
   shows +330 lines to rewards.py from the same V25 base, confirming V26.1 is a refined version
   of V26 (not the same design). This run is V26, not V26.1.

---

## Analysis Notes

### Version jumps
- TRAIN_VERSION jumped from V20 to V23 (skipping V21, V22). V21 added monitoring/diagnostics
  without changing the reward design. V22 may have existed locally but was never committed.
- V26 (run 01-46-44) and V26.1 (run 07-08-50) are **separate experiments**. V26 was an
  exploratory run with uncommitted code (+201 lines in rewards.py). V26.1 was designed after
  analyzing V26 results and committed as 1c242fe (+330 lines). env_cfg.py retains
  `TRAIN_VERSION = "V26"` while common.py uses `"V26.1"` as the canonical reporting label.

### The Excel mislabeling bug
- `common.py` had `V23_TRAIN_VERSION = "V24"` hardcoded from the V23 era through all of V24 and V25
- This caused ALL Excel files from 03-11 to 03-15 07:08 to be named `spotmicro_v24_*` (or v23
  in very early runs when the value was still "V23")
- The actual training reward design is correctly determined by `env_cfg.py` `TRAIN_VERSION`
- Commits 4b07453, f91513d, fe396d9 on 03-15 morning fixed this for all future runs

### V20 runs with V21 monitoring
Runs from 2026-03-10_15-56-10 through 2026-03-11_02-39-01 used V20 rewards but V21-era monitoring
scripts (milestone_monitor.py, training_heartbeat.py with extended metrics). They are labeled V20
because the reward design did not change.

### Short/aborted runs
Several runs have very few checkpoints (model_0.pt only, or up to model_600.pt) indicating they
were test runs, crash restarts, or aborted early. These are included for completeness.

### train_version.txt files
All run directories now have `train_version.txt` written with the correct version string.
The file for `2026-03-15_07-08-50` was already present before this analysis.
