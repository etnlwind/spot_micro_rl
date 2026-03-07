"""Training Heartbeat - Iteration 100 배수마다 훈련 지표를 분석하여 텔레그램으로 전송
훈련을 중단하지 않고 TensorBoard 이벤트를 읽기 전용으로 분석합니다.

Usage: python scripts/training_heartbeat.py [--iter_step 100] [--poll 30] [--run_dir <path>]
"""

import argparse
import os
import re
import sys
import time
import datetime
import urllib.request
import urllib.parse
import json
import traceback
import io

# Windows cp949 콘솔에서 이모지 깨짐 방지
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Paths ──────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def _load_env(path):
    """Read .env file and return dict of key=value pairs."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


_env = _load_env(ENV_FILE)

# ─── Telegram Config ────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or _env.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _env.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not found in .env or environment")
    sys.exit(1)

# Paths & config from .env
_log_subdir = _env.get("LOG_SUBDIR", "spot_micro_flat")
LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", _log_subdir)
PID_FILE = os.path.join(PROJECT_ROOT, "logs", "training_heartbeat.pid")
MAINTENANCE_FLAG = os.path.join(PROJECT_ROOT, "logs", "maintenance.flag")
MAX_ITERATIONS = int(_env.get("MAX_ITERATIONS", "15000"))

# Training version tag (env_cfg.py에서 읽음)
def _read_train_version() -> str:
    cfg_path = os.path.join(
        PROJECT_ROOT, "source", "spot_micro_rl", "spot_micro_rl",
        "tasks", "manager_based", "spot_micro_rl", "spot_micro_rl_env_cfg.py"
    )
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^TRAIN_VERSION\s*=\s*["\'](.+?)["\']', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return _env.get("TRAIN_VERSION", "")

TRAIN_VERSION = _read_train_version()


def send_telegram(text):
    """텔레그램 메시지 전송 (최대 4096자 분할). TRAIN_VERSION 자동 prefix."""
    if TRAIN_VERSION:
        text = f"[{TRAIN_VERSION}] {text}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = []
    while len(text) > 4000:
        split_at = text[:4000].rfind("\n")
        if split_at < 100:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)

    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            print(f"[TG ERROR] {e}")
        time.sleep(0.3)


def find_latest_run():
    """가장 최신 훈련 런 디렉토리를 찾습니다."""
    if not os.path.isdir(LOG_BASE):
        return None
    runs = sorted([d for d in os.listdir(LOG_BASE)
                   if os.path.isdir(os.path.join(LOG_BASE, d))])
    return os.path.join(LOG_BASE, runs[-1]) if runs else None


def read_tfevents(run_dir, retries=3):
    """TensorBoard 이벤트 파일에서 스칼라 데이터를 읽습니다 (읽기 전용, 재시도)."""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    event_files = [f for f in os.listdir(run_dir) if f.startswith("events.out.tfevents")]
    if not event_files:
        return None

    event_path = os.path.join(run_dir, event_files[0])
    for attempt in range(retries):
        try:
            ea = EventAccumulator(event_path)
            ea.Reload()
            data = {}
            for tag in ea.Tags().get("scalars", []):
                events = ea.Scalars(tag)
                data[tag] = [(e.step, e.value) for e in events]
            return data
        except Exception as e:
            print(f"[TF READ] Attempt {attempt+1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None


def get_trend(values, window=50):
    """최근 추세를 계산합니다."""
    if len(values) < window * 2:
        if len(values) >= 10:
            mid = len(values) // 2
            first_half = values[:mid]
            second_half = values[mid:]
            avg_first = sum(v for _, v in first_half) / len(first_half)
            avg_second = sum(v for _, v in second_half) / len(second_half)
        else:
            return "📊", 0.0
    else:
        first_half = values[-(window * 2):-window]
        second_half = values[-window:]
        avg_first = sum(v for _, v in first_half) / len(first_half)
        avg_second = sum(v for _, v in second_half) / len(second_half)

    change = avg_second - avg_first
    pct = (change / abs(avg_first) * 100) if avg_first != 0 else 0

    if pct > 10:
        return "🔺", pct
    elif pct > 3:
        return "📈", pct
    elif pct < -10:
        return "🔻", pct
    elif pct < -3:
        return "📉", pct
    else:
        return "➡️", pct


def gait_quality_score(rewards):
    """걸음걸이 품질 종합 점수 (0-13)."""
    score = 0
    details = []

    # 1. 트로트 패턴 (0-3)
    trot = rewards.get("trot_gait", 0)
    if trot > 5.0:
        score += 3; details.append(f"트로트 ✅✅✅ ({trot:.2f})")
    elif trot > 1.0:
        score += 1; details.append(f"트로트 🟡 ({trot:.2f})")
    else:
        details.append(f"트로트 ❌ ({trot:.3f})")

    # 2. 대각선 커플링 (0-2)
    diag = rewards.get("diagonal_coupling", 0)
    if diag > 3.0:
        score += 2; details.append(f"대각선 ✅✅ ({diag:.2f})")
    elif diag > 0.5:
        score += 1; details.append(f"대각선 🟡 ({diag:.2f})")
    else:
        details.append(f"대각선 ❌ ({diag:.3f})")

    # 3. 걸음 주기 (0-2)
    cycle = rewards.get("gait_cycle_period", 0)
    if cycle > 2.0:
        score += 2; details.append(f"걸음주기 ✅✅ ({cycle:.2f})")
    elif cycle > 0.5:
        score += 1; details.append(f"걸음주기 🟡 ({cycle:.2f})")
    else:
        details.append(f"걸음주기 ❌ ({cycle:.4f})")

    # 4. 보폭 (0-2)
    stride = rewards.get("stride_length", 0)
    if stride > 2.0:
        score += 2; details.append(f"보폭 ✅✅ ({stride:.2f})")
    elif stride > 0.5:
        score += 1; details.append(f"보폭 🟡 ({stride:.2f})")
    else:
        details.append(f"보폭 ❌ ({stride:.4f})")

    # 5. 뒷다리 (0-2)
    rear_vel = rewards.get("rear_joint_velocity", 0)
    if rear_vel > 5.0:
        score += 2; details.append(f"뒷다리 ✅✅ ({rear_vel:.2f})")
    elif rear_vel > 1.0:
        score += 1; details.append(f"뒷다리 🟡 ({rear_vel:.2f})")
    else:
        details.append(f"뒷다리 ❌ ({rear_vel:.3f})")

    # 6. 기립 안정성 (0-2)
    height = rewards.get("standing_height", 0)
    if height > 5.0:
        score += 2; details.append(f"기립 ✅✅ ({height:.2f})")
    elif height > 1.0:
        score += 1; details.append(f"기립 🟡 ({height:.2f})")
    else:
        details.append(f"기립 ❌ ({height:.3f})")

    # 등급
    if score >= 10:
        grade = "🌟 A"
    elif score >= 7:
        grade = "⭐ B"
    elif score >= 4:
        grade = "🟡 C"
    elif score >= 2:
        grade = "🟠 D"
    else:
        grade = "🔴 F"

    return grade, score, details


def format_report(data, run_name, cycle_num):
    """상세 분석 리포트를 포맷합니다."""
    now = datetime.datetime.now().strftime("%H:%M:%S")

    # ── 기본 메트릭 ──
    reward_vals = data.get("Train/mean_reward", [])
    ep_len_vals = data.get("Train/mean_episode_length", [])

    if not reward_vals:
        return f"⚠️ [{now}] 아직 메트릭 데이터 없음"

    current_iter = reward_vals[-1][0]
    current_reward = reward_vals[-1][1]
    current_ep_len = ep_len_vals[-1][1] if ep_len_vals else 0

    max_iter = MAX_ITERATIONS
    progress_pct = current_iter / max_iter * 100

    # 보상 추세
    reward_icon, reward_pct = get_trend(reward_vals)

    # ep length 추세
    ep_icon, ep_pct = get_trend(ep_len_vals) if ep_len_vals else ("📊", 0)

    # 최근 10개 평균
    recent_rewards = reward_vals[-10:] if len(reward_vals) >= 10 else reward_vals
    avg_reward = sum(v for _, v in recent_rewards) / len(recent_rewards)

    # 최고/최저 보상
    all_reward_values = [v for _, v in reward_vals]
    best_reward = max(all_reward_values)
    worst_reward = min(all_reward_values)
    best_iter = reward_vals[all_reward_values.index(best_reward)][0]

    # 생존율
    max_ep = 10.0 * 50  # 10s × 50Hz
    survival_pct = (current_ep_len / max_ep) * 100

    # 종료 원인
    timeout_vals = data.get("Episode_Termination/time_out", [])
    bad_orient_vals = data.get("Episode_Termination/bad_orientation", [])
    timeout = timeout_vals[-1][1] if timeout_vals else 0
    bad_orient = bad_orient_vals[-1][1] if bad_orient_vals else 0
    total_term = timeout + bad_orient
    timeout_pct = (timeout / total_term * 100) if total_term > 0 else 0

    # ── 보상 분석 ──
    rewards = {}
    for tag, vals in data.items():
        if "Episode_Reward/" in tag and vals:
            name = tag.replace("Episode_Reward/", "")
            rewards[name] = vals[-1][1]

    positive = sorted([(k, v) for k, v in rewards.items() if v > 0.001], key=lambda x: x[1], reverse=True)
    negative = sorted([(k, v) for k, v in rewards.items() if v < -0.001], key=lambda x: x[1])

    # ── 걸음걸이 품질 ──
    grade, gait_score, gait_details = gait_quality_score(rewards)

    # ── 핵심 메트릭 추세 ──
    key_trends = []
    trend_metrics = [
        ("trot_gait", "트로트"),
        ("diagonal_coupling", "대각선"),
        ("leg_lift", "다리들기"),
        ("rear_joint_velocity", "뒷다리속도"),
        ("standing_height", "기립높이"),
        ("foot_clearance", "발들기"),
        ("forward_velocity", "전진속도"),
        ("stride_length", "보폭"),
        ("gait_cycle_period", "걸음주기"),
        ("rear_forward_stride", "뒷다리보폭"),
        ("rear_alternation", "뒷다리교대"),
        ("swing_stride", "스윙보폭"),
    ]
    for metric_name, label in trend_metrics:
        tag = f"Episode_Reward/{metric_name}"
        if tag in data and data[tag]:
            val = data[tag][-1][1]
            icon, pct = get_trend(data[tag])
            key_trends.append(f"  {icon} {label}: {val:+.4f} ({pct:+.1f}%)")

    penalty_trends = []
    penalty_metrics = [
        ("joint_vel_l2", "관절속도"),
        ("action_rate_l2", "행동변화"),
        ("dof_acc_l2", "관절가속"),
        ("ang_vel_xy_l2", "각속도"),
        ("same_side_penalty", "동측보행"),
        ("dof_pos_limits", "관절한계"),
        ("undesired_contacts", "불필요접촉"),
        ("flat_orientation_l2", "자세기울기"),
        ("shoulder_neutral", "어깨중립"),
        ("shoulder_symmetry", "어깨대칭"),
        ("foot_extension", "발뻗기"),
        ("feet_below_knees", "무릎아래발"),
    ]
    for metric_name, label in penalty_metrics:
        tag = f"Episode_Reward/{metric_name}"
        if tag in data and data[tag]:
            val = data[tag][-1][1]
            icon, pct = get_trend(data[tag])
            penalty_trends.append(f"  {icon} {label}: {val:+.4f} ({pct:+.1f}%)")

    # ── 학습 지표 ──
    vf_loss_vals = data.get("Loss/value_function", [])
    surr_loss_vals = data.get("Loss/surrogate", [])
    noise_vals = data.get("Policy/mean_noise_std", [])
    vf_loss = vf_loss_vals[-1][1] if vf_loss_vals else 0
    surr_loss = surr_loss_vals[-1][1] if surr_loss_vals else 0
    noise_std = noise_vals[-1][1] if noise_vals else 0

    # ── 속도 추적 ──
    vel_xy_err = data.get("Metrics/base_velocity/error_vel_xy", [])
    vel_yaw_err = data.get("Metrics/base_velocity/error_vel_yaw", [])
    vel_xy = vel_xy_err[-1][1] if vel_xy_err else 0
    vel_yaw = vel_yaw_err[-1][1] if vel_yaw_err else 0

    # ── 스무스니스 ──
    action_rate = abs(rewards.get("action_rate_l2", 0))
    joint_vel = abs(rewards.get("joint_vel_l2", 0))
    dof_acc = abs(rewards.get("dof_acc_l2", 0))
    smooth_total = action_rate + joint_vel + dof_acc
    if smooth_total < 10:
        smooth_label = "매우 부드러움 ✅"
    elif smooth_total < 30:
        smooth_label = "적당히 부드러움 🟡"
    elif smooth_total < 60:
        smooth_label = "거친 편 🟠"
    else:
        smooth_label = "매우 거침 🔴"

    # ── ETA 계산 ──
    remaining_iters = max_iter - current_iter
    if len(reward_vals) >= 2:
        steps_diff = reward_vals[-1][0] - reward_vals[-2][0]
        # 대략적 시간 추정 (134s/iter 기준)
        eta_min = remaining_iters * 134 / 60
        eta_hours = eta_min / 60
    else:
        eta_hours = 0

    # ════════════════════════════════════════════
    # 메시지 조립
    # ════════════════════════════════════════════
    lines = []
    lines.append(f"📊 <b>훈련 상태 리포트 #{cycle_num}</b>")
    lines.append(f"🕐 {now} | Run: {run_name}")
    lines.append("")

    # 진행 상황
    bar_len = 20
    filled = int(progress_pct / 100 * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    lines.append(f"<b>📈 진행</b>")
    lines.append(f"  [{bar}] {progress_pct:.1f}%")
    lines.append(f"  Iter: {current_iter:,} / {max_iter:,}")
    lines.append(f"  ETA: ~{eta_hours:.1f}h")
    lines.append("")

    # 핵심 지표
    lines.append(f"<b>🎯 핵심 지표</b>")
    lines.append(f"  {reward_icon} Reward: {current_reward:.1f} (avg10: {avg_reward:.1f})")
    lines.append(f"  {ep_icon} Episode: {current_ep_len:.1f} steps (생존 {survival_pct:.1f}%)")
    lines.append(f"  🏆 Best: {best_reward:.1f} @iter {best_iter}")
    lines.append(f"  📉 Worst: {worst_reward:.1f}")
    lines.append(f"  💀 종료: timeout {timeout_pct:.0f}% / fall {100-timeout_pct:.0f}%")
    lines.append("")

    # 걸음걸이 품질
    lines.append(f"<b>🦿 걸음걸이 {grade} ({gait_score}/13)</b>")
    for d in gait_details:
        lines.append(f"  {d}")
    lines.append("")

    # 보행 보상 추세 (양수)
    lines.append(f"<b>✅ 보행 보상 추세</b>")
    for t in key_trends:
        lines.append(t)
    lines.append("")

    # 페널티 추세 (음수)
    lines.append(f"<b>⛔ 페널티 추세</b>")
    for t in penalty_trends:
        lines.append(t)
    lines.append("")

    # 동작 부드러움
    lines.append(f"<b>🔧 동작 품질</b>")
    lines.append(f"  부드러움: {smooth_label} ({smooth_total:.1f})")
    lines.append(f"    action_rate: {action_rate:.2f}")
    lines.append(f"    joint_vel: {joint_vel:.2f}")
    lines.append(f"    dof_acc: {dof_acc:.2f}")
    lines.append("")

    # 학습 지표
    lines.append(f"<b>🧠 학습 지표</b>")
    lines.append(f"  VF Loss: {vf_loss:.1f}")
    lines.append(f"  Surrogate: {surr_loss:.5f}")
    lines.append(f"  Noise std: {noise_std:.3f}")
    lines.append(f"  Vel err (xy): {vel_xy:.4f}")
    lines.append(f"  Vel err (yaw): {vel_yaw:.4f}")
    lines.append("")

    # TOP5 양수/음수 보상
    lines.append(f"<b>🏅 TOP5 기여 보상</b>")
    for i, (name, val) in enumerate(positive[:5]):
        tag = f"Episode_Reward/{name}"
        icon, pct = get_trend(data.get(tag, []))
        lines.append(f"  {i+1}. {name}: {val:+.4f} {icon}")
    lines.append("")

    lines.append(f"<b>💣 TOP5 패널티</b>")
    for i, (name, val) in enumerate(negative[:5]):
        tag = f"Episode_Reward/{name}"
        icon, pct = get_trend(data.get(tag, []))
        lines.append(f"  {i+1}. {name}: {val:+.4f} {icon}")
    lines.append("")

    # ── 보상 궤적 테이블 (200 iter 간격) ──
    noise_vals = data.get("Policy/mean_noise_std", [])
    ep_len_all = data.get("Train/mean_episode_length", [])
    lines.append(f"<b>📉 보상 추이</b>")
    lines.append("  <code>Iter   | Reward  | EpLen | Noise</code>")
    # 200 iter 간격으로 스냅샷 + 마지막
    snap_iters = set()
    step = 200
    it = int(reward_vals[0][0])  # 시작 iter
    while it <= current_iter:
        snap_iters.add(it)
        it += step
    snap_iters.add(int(current_iter))
    for s, r in reward_vals:
        si = int(s)
        if si in snap_iters:
            snap_iters.discard(si)
            # 해당 step의 ep_len, noise 찾기
            el_v = next((v for st, v in ep_len_all if int(st) == si), None)
            if el_v is None:
                el_v = next((v for st, v in (ep_len_vals if ep_len_vals else [])), 0)
            ns_v = next((v for st, v in noise_vals if int(st) == si), None)
            el_str = f"{el_v:.1f}" if el_v else "?"
            ns_str = f"{ns_v:.3f}" if ns_v is not None else "?"
            lines.append(f"  <code>{si:>6} | {r:>7.1f} | {el_str:>5} | {ns_str}</code>")
    lines.append("")

    # ── 전체 개선량 ──
    early_n = min(20, len(reward_vals) // 3) or 1
    late_n = min(20, len(reward_vals) // 3) or 1
    early_avg = sum(v for _, v in reward_vals[:early_n]) / early_n
    late_avg = sum(v for _, v in reward_vals[-late_n:]) / late_n
    improvement = late_avg - early_avg

    # ── 핵심 보상 변화율 (last 100 vs prev 100) ──
    key_change_lines = []
    key_change_metrics = [
        ("trot_gait", "트로트"), ("diagonal_coupling", "대각선"),
        ("leg_lift", "다리들기"), ("rear_joint_velocity", "뒷다리"),
        ("standing_height", "기립"), ("foot_clearance", "발들기"),
        ("forward_velocity", "전진"),
    ]
    improving_keys = []
    declining_keys = []
    for mname, label in key_change_metrics:
        tag = f"Episode_Reward/{mname}"
        if tag in data and data[tag]:
            vals = data[tag]
            if len(vals) >= 40:
                half = len(vals) // 2
                old_avg = sum(v for _, v in vals[:half]) / half
                new_avg = sum(v for _, v in vals[half:]) / len(vals[half:])
                pct = ((new_avg - old_avg) / abs(old_avg) * 100) if old_avg != 0 else 0
                if pct > 5:
                    improving_keys.append((label, pct))
                elif pct < -5:
                    declining_keys.append((label, pct))

    # ── 학습 단계 판별 ──
    if survival_pct < 5:
        phase = "1단계: 기립 학습 초기"
        phase_icon = "🥚"
        phase_desc = "로봇이 즉시 넘어짐. 페널티 회피 학습 중"
    elif survival_pct < 20:
        phase = "2단계: 기립 시도"
        phase_icon = "🐣"
        phase_desc = "짧게 서있기 시작. 균형 학습 중"
    elif survival_pct < 50:
        phase = "3단계: 보행 출현"
        phase_icon = "🐥"
        phase_desc = "걸음걸이 패턴 형성 시작"
    elif survival_pct < 80:
        phase = "4단계: 보행 발달"
        phase_icon = "🐕"
        phase_desc = "트로트 패턴 발달, 속도 증가 중"
    else:
        phase = "5단계: 보행 안정화"
        phase_icon = "🦮"
        phase_desc = "안정적 보행, 미세 조정 단계"

    # ════════════════════════════════════════════
    # 종합 분석 섹션
    # ════════════════════════════════════════════
    lines.append(f"<b>{phase_icon} 학습 단계: {phase}</b>")
    lines.append(f"  {phase_desc}")
    lines.append("")

    # ✅ 좋은점
    lines.append(f"<b>✅ 좋은 점</b>")
    good_points = []
    if improvement > 0:
        good_points.append(f"보상 {improvement:+.1f} 개선 ({early_avg:.1f} → {late_avg:.1f})")
    if noise_vals:
        ns_first = noise_vals[0][1]
        ns_last = noise_vals[-1][1]
        if ns_last < ns_first * 0.95:
            good_points.append(f"탐색 안정화 (noise {ns_first:.3f} → {ns_last:.3f})")
    if timeout_pct > 0:
        good_points.append(f"timeout 비율 {timeout_pct:.0f}% (생존 개시)")
    if improving_keys:
        names = ", ".join(f"{n}({p:+.0f}%)" for n, p in improving_keys[:3])
        good_points.append(f"개선 중: {names}")
    if reward_pct > 3:
        good_points.append(f"최근 보상 추세 상승 ({reward_pct:+.1f}%)")
    if not good_points:
        good_points.append("아직 뚜렷한 개선 신호 없음 (초기 단계)")
    for g in good_points:
        lines.append(f"  👍 {g}")
    lines.append("")

    # ⚠️ 문제점
    lines.append(f"<b>⚠️ 문제점</b>")
    problems = []
    if survival_pct < 5:
        lines_surv = f"{current_ep_len:.1f}steps ({survival_pct:.1f}%)"
        problems.append(f"즉사 수준 생존율: {lines_surv}")
    elif survival_pct < 20:
        problems.append(f"낮은 생존율: {survival_pct:.1f}%")
    if bad_orient > 0.9:
        problems.append(f"bad_orientation {bad_orient*100:.0f}% — 거의 항상 넘어짐")
    if declining_keys:
        names = ", ".join(f"{n}({p:+.0f}%)" for n, p in declining_keys[:3])
        problems.append(f"하락 중: {names}")
    if improvement < 0:
        problems.append(f"보상 악화 ({improvement:+.1f})")
    if smooth_total > 40:
        problems.append(f"페널티 지배적 (smooth={smooth_total:.1f})")
    if gait_score < 2 and current_iter > 3000:
        problems.append(f"iter {int(current_iter):,}인데 걸음걸이 미형성")
    if not problems:
        problems.append("현재 특이 사항 없음")
    for p in problems:
        lines.append(f"  ❗ {p}")
    lines.append("")

    # 🔮 예상 타임라인
    lines.append(f"<b>🔮 예상 타임라인</b>")
    phases_timeline = [
        (2000, "기립 시작", "ep length 증가 시작"),
        (4000, "균형 학습", "넘어짐 비율 감소"),
        (7000, "보행 출현", "트로트 패턴 형성"),
        (10000, "보행 발달", "속도/보폭 증가"),
        (13000, "보행 안정화", "미세 조정"),
        (15600, "훈련 완료", "최종 모델"),
    ]
    for target_iter, label, desc in phases_timeline:
        if current_iter < target_iter:
            marker = "⬜"
        elif current_iter >= target_iter:
            marker = "✅"
        else:
            marker = "▶️"
        lines.append(f"  {marker} iter {target_iter:>6,}: {label} — {desc}")
    lines.append("")

    # 다음 리포트
    lines.append("")
    next_milestone = ((int(current_iter) // 100) + 1) * 100
    lines.append(f"⏰ 다음 리포트: iter {next_milestone:,}")

    return "\n".join(lines)


# ─── PID LOCK ───────────────────────────────────────────────────

def acquire_lock():
    """PID 잠금 파일로 중복 실행을 방지합니다."""
    import subprocess
    my_pid = os.getpid()

    if os.path.isfile(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            # 해당 PID가 살아있는지 확인
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {old_pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            if "python.exe" in result.stdout:
                print(f"ERROR: Another training_heartbeat is already running (PID {old_pid})")
                print(f"Kill it first: Stop-Process -Id {old_pid} -Force")
                sys.exit(1)
            else:
                print(f"Stale PID file found (PID {old_pid} dead), overwriting")
        except (ValueError, subprocess.TimeoutExpired):
            pass

    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(my_pid))
    print(f"Lock acquired: PID {my_pid}")


def release_lock():
    """잠금 파일 해제."""
    try:
        if os.path.isfile(PID_FILE):
            os.remove(PID_FILE)
    except Exception:
        pass


def check_maintenance_mode():
    """Supervisor 유지보수 중인지 확인 (maintenance.flag 존재 여부)."""
    return os.path.isfile(MAINTENANCE_FLAG)


def check_training_alive():
    """훈련 프로세스가 살아있는지 확인 (자기 자신 제외, training_heartbeat 제외)."""
    import subprocess
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Select-Object ProcessId,CommandLine | Format-List"],
            capture_output=True, text=True, timeout=15
        )
        # training 관련 python.exe가 있는지 확인 (heartbeat/monitor 제외)
        current_pid = None
        current_cmd = ""
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("ProcessId"):
                try:
                    current_pid = int(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    current_pid = None
            elif line.startswith("CommandLine"):
                current_cmd = line.split(":", 1)[1].strip() if ":" in line else ""
                # 이 PID+CommandLine 쌍을 판별
                if current_pid and current_pid != my_pid:
                    cmd_lower = current_cmd.lower()
                    # heartbeat/monitor 스크립트는 제외, 훈련 프로세스만 카운트
                    if "training_heartbeat" not in cmd_lower and "live_monitor" not in cmd_lower:
                        return True
                current_pid = None
                current_cmd = ""
        return False
    except Exception:
        # 오류 시 보수적으로 True 반환 (훈련 있다고 가정)
        return True


def check_supervisor_alive():
    """Training Supervisor (python) 프로세스가 살아있는지 확인."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["name"] and "python" in proc.info["name"].lower():
                    cmdline = " ".join(proc.info["cmdline"] or [])
                    if "training_supervisor" in cmdline.lower():
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False
    except ImportError:
        # psutil 없으면 보수적으로 alive 간주
        return True
    except Exception:
        return True  # 오류 시 보수적으로 alive 간주


def restart_supervisor():
    """training_supervisor.py 자동 재시작. 성공 여부를 반환."""
    import subprocess as _sp
    supervisor_script = os.path.join(PROJECT_ROOT, "scripts", "training_supervisor.py")
    supervisor_pid_file = os.path.join(PROJECT_ROOT, "logs", "training_supervisor.pid")

    # 기존 PID 파일 제거
    try:
        os.remove(supervisor_pid_file)
    except OSError:
        pass

    sv_cmd = (
        f'conda activate env_isaaclab && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'python scripts/training_supervisor.py'
    )
    _sp.Popen(
        ["cmd", "/c", sv_cmd],
        cwd=PROJECT_ROOT,
        creationflags=_sp.CREATE_NEW_PROCESS_GROUP,
    )
    time.sleep(15)  # supervisor 초기화 대기 (heartbeat보다 느림)

    if check_supervisor_alive():
        new_pid = 0
        try:
            new_pid = int(open(supervisor_pid_file, "r").read().strip())
        except Exception:
            # PID 파일 없어도 프로세스가 살아있으면 OK
            try:
                import psutil
                for proc in psutil.process_iter(["pid", "cmdline"]):
                    try:
                        cmdline = " ".join(proc.info["cmdline"] or [])
                        if "training_supervisor" in cmdline.lower():
                            new_pid = proc.info["pid"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception:
                pass
        print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] Supervisor restarted OK (PID {new_pid})")
        send_telegram(f"✅ Training Supervisor 자동 재시작 완료 (PID {new_pid})")
        return True
    else:
        print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] WARNING: Supervisor restart FAILED")
        send_telegram("⚠️ Training Supervisor 재시작 실패! 수동 확인 필요\npython scripts/training_supervisor.py")
        return False


# ─── MAIN LOOP ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Training Heartbeat")
    parser.add_argument("--iter_step", type=int, default=100, help="Report every N iterations (default: 100)")
    parser.add_argument("--poll", type=int, default=30, help="Polling interval in seconds (default: 30)")
    parser.add_argument("--run_dir", type=str, default=None, help="Specific run dir (auto-detect if omitted)")
    args = parser.parse_args()

    # 중복 실행 방지
    acquire_lock()

    print(f"🤖 Training Heartbeat started | iter_step={args.iter_step} | poll={args.poll}s | PID={os.getpid()}")
    # 시작 알림은 첫 리포트에 포함 (별도 메시지 보내지 않음)

    cycle = 0
    last_reported_milestone = 0  # 마지막으로 리포트한 iter milestone
    first_check = True
    supervisor_alert_sent = False  # Supervisor 사망 알림 중복 방지
    maintenance_logged = False  # 유지보수 모드 로그 중복 방지

    try:
        while True:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                # ── Supervisor 워치독 (자동 재시작) ──
                if not check_supervisor_alive():
                    if not supervisor_alert_sent:
                        print(f"[{now}] WARNING: Supervisor not alive! Attempting auto-restart...")
                        send_telegram("⚠️ <b>Training Supervisor 감지 불가!</b>\n자동 재시작 시도 중...")
                        if restart_supervisor():
                            supervisor_alert_sent = False  # 재시작 성공 — 다음 사이클 정상 감시
                        else:
                            supervisor_alert_sent = True   # 재시작 실패 — 반복 알림 방지
                else:
                    if supervisor_alert_sent:
                        send_telegram("✅ <b>Training Supervisor 복구 확인</b>")
                        print(f"[{now}] Supervisor recovered.")
                    supervisor_alert_sent = False

                # ── 훈련 프로세스 확인 ──
                if not check_training_alive():
                    # 유지보수 모드인지 확인
                    if check_maintenance_mode():
                        if not maintenance_logged:
                            print(f"[{now}] Maintenance mode — Supervisor가 녹화/분석 중. 대기...")
                            maintenance_logged = True
                        time.sleep(args.poll)
                        continue
                    else:
                        send_telegram(f"🛑 <b>훈련 프로세스 없음!</b>\n훈련이 종료되었거나 크래시 발생")
                        print("No training process found!")
                        break
                else:
                    maintenance_logged = False  # 훈련 복귀 시 리셋

                # 런 디렉토리 찾기
                run_dir = args.run_dir if args.run_dir else find_latest_run()
                if not run_dir or not os.path.isdir(run_dir):
                    print(f"Run dir not found: {run_dir}")
                    time.sleep(args.poll)
                    continue

                run_name = os.path.basename(run_dir)

                # TensorBoard 읽기 (재시도 포함)
                data = read_tfevents(run_dir)
                if not data:
                    print(f"[{now}] No TF data yet, polling...")
                    time.sleep(args.poll)
                    continue

                # 현재 iter 확인
                reward_vals = data.get("Train/mean_reward", [])
                if not reward_vals:
                    time.sleep(args.poll)
                    continue

                current_iter = int(reward_vals[-1][0])
                current_milestone = (current_iter // args.iter_step) * args.iter_step

                # 첫 체크 시 현재 milestone을 기록 (시작 직후 즉시 리포트 방지)
                if first_check:
                    last_reported_milestone = current_milestone
                    first_check = False
                    # 첫 번째 리포트는 즉시 전송
                    cycle += 1
                    report = format_report(data, run_name, cycle)
                    header = f"🤖 <b>Training Heartbeat 시작</b> (PID {os.getpid()})\n"
                    header += f"📊 매 {args.iter_step} iter마다 리포트\n"
                    header += "━" * 30 + "\n\n"
                    report = header + report
                    print(f"\n[{now}] === Report #{cycle} (iter {current_iter}, milestone {current_milestone}) ===")
                    print(report)
                    send_telegram(report)
                    print(f"Report #{cycle} sent")
                    time.sleep(args.poll)
                    continue

                # 새 milestone에 도달했는지 확인
                if current_milestone > last_reported_milestone:
                    cycle += 1
                    last_reported_milestone = current_milestone

                    print(f"\n[{now}] === Report #{cycle} (iter {current_iter}, milestone {current_milestone}) ===")
                    print(f"Reading: {run_dir}")

                    # 리포트 생성 & 전송
                    report = format_report(data, run_name, cycle)
                    print(report)
                    send_telegram(report)
                    print(f"Report #{cycle} sent")
                else:
                    # milestone 미도달 → 조용히 대기
                    pass

            except Exception as e:
                err_msg = f"❌ Monitor error (cycle #{cycle}): {e}\n{traceback.format_exc()[-300:]}"
                print(err_msg)
                send_telegram(err_msg)

            time.sleep(args.poll)

    finally:
        release_lock()

    send_telegram("👋 <b>Training Heartbeat 종료</b>")
    print("Heartbeat exited.")


if __name__ == "__main__":
    main()
