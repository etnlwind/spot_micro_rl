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
import math

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
USER_STOP_FLAG = os.path.join(PROJECT_ROOT, "logs", "user_stop.flag")
MAX_ITERATIONS = int(_env.get("MAX_ITERATIONS", "15000"))

# TensorBoard remote access
TAILSCALE_IP = _env.get("TAILSCALE_IP", "")
TB_PORT = _env.get("TB_PORT", "6006")
TB_URL = f"http://{TAILSCALE_IP}:{TB_PORT}" if TAILSCALE_IP else ""
TB_CURRENT_LINK = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", f"{_log_subdir}_current")
FINAL_REPORT_MARKER_NAME = "heartbeat_final_report.sent"
HEARTBEAT_HISTORY_JSONL = "heartbeat_reports.jsonl"


def update_tb_junction(run_dir: str):
    """TensorBoard junction을 현재 런으로 업데이트."""
    target = os.path.abspath(run_dir)
    link = TB_CURRENT_LINK
    # 현재 junction이 이미 같은 대상을 가리키면 스킵
    if os.path.isdir(link):
        try:
            if os.path.realpath(link) == target:
                return
        except Exception:
            pass
        # 기존 junction 삭제
        try:
            os.rmdir(link)  # junction은 rmdir로 삭제 (내용물 삭제 안됨)
        except Exception:
            import shutil
            shutil.rmtree(link, ignore_errors=True)
    # 새 junction 생성
    try:
        import subprocess
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                       capture_output=True, check=True)
        print(f"[TB] Junction updated: {os.path.basename(target)}")
    except Exception as e:
        print(f"[TB] Junction update failed: {e}")


# ─── TensorBoard 프로세스 관리 ──────────────────────────────────

_tb_restart_count = 0

def _is_tb_alive() -> bool:
    """TB_PORT에 TCP 연결이 가능한지 확인."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(TB_PORT)), timeout=3):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def ensure_tensorboard() -> None:
    """TensorBoard가 죽었으면 자동 재시작. junction 경로 기준."""
    global _tb_restart_count

    if not TB_CURRENT_LINK or not os.path.isdir(TB_CURRENT_LINK):
        return  # junction이 아직 없으면 스킵

    if _is_tb_alive():
        return  # 정상 동작 중

    # 죽어 있음 — 재시작
    import subprocess
    _tb_restart_count += 1
    logdir = TB_CURRENT_LINK
    now = datetime.datetime.now().strftime("%H:%M:%S")

    try:
        # 이전 좀비 프로세스 정리
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = " ".join(p.info["cmdline"] or [])
                if "tensorboard" in cmdline.lower() and str(TB_PORT) in cmdline:
                    p.terminate()
                    print(f"[TB] Killed zombie TensorBoard PID {p.pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # 새 TensorBoard 시작
        cmd = [
            sys.executable, "-m", "tensorboard.main",
            f"--logdir={logdir}",
            "--host=0.0.0.0",
            f"--port={TB_PORT}",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        # 잠시 대기 후 확인
        time.sleep(3)
        if _is_tb_alive():
            print(f"[{now}] [TB] Restarted TensorBoard (PID {proc.pid}, restart #{_tb_restart_count})")
            if _tb_restart_count <= 3:  # 반복 알림 방지
                send_telegram(f"🔄 TensorBoard 자동 재시작 완료 (PID {proc.pid})\n🔗 {TB_URL}")
        else:
            print(f"[{now}] [TB] TensorBoard restart failed (PID {proc.pid} started but port not responding)")
            if _tb_restart_count <= 3:
                send_telegram(f"⚠️ TensorBoard 재시작 실패 — 포트 {TB_PORT} 응답 없음")
    except Exception as e:
        print(f"[{now}] [TB] TensorBoard restart error: {e}")


# Training / ops version tags
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


def _read_ops_version() -> str:
    for key in ("OPS_VERSION", "MONITOR_VERSION"):
        value = os.environ.get(key) or _env.get(key, "")
        if value:
            return value
    return "V22"


TRAIN_VERSION = _read_train_version()
OPS_VERSION = _read_ops_version()


def send_telegram(text):
    """텔레그램 메시지 전송 (최대 4096자 분할). OPS_VERSION 자동 prefix."""
    if OPS_VERSION:
        text = f"[{OPS_VERSION}] {text}"
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


def send_telegram_photo(photo_bytes: bytes, caption: str = ""):
    """텔레그램 이미지 전송 (PNG bytes, multipart/form-data)."""
    import uuid
    boundary = uuid.uuid4().hex
    if OPS_VERSION and caption:
        caption = f"[{OPS_VERSION}] {caption}"

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
    body += f"{TELEGRAM_CHAT_ID}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
    body += f"{caption}\r\n".encode("utf-8")
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="photo"; filename="graph.png"\r\n'
    body += b"Content-Type: image/png\r\n\r\n"
    body += photo_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"[TG PHOTO ERROR] {e}")


def generate_training_graphs(data, run_name: str) -> bytes | None:
    """핵심 훈련 지표 그래프를 생성하여 PNG bytes로 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("[GRAPH] matplotlib not available")
        return None

    # 그래프 설정: 2x2 레이아웃
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Training: {run_name}", fontsize=14, fontweight="bold")

    def plot_metric(ax, tags_labels, title, ylabel):
        for tag, label in tags_labels:
            if tag in data and data[tag]:
                steps = [s for s, v in data[tag]]
                vals = [v for s, v in data[tag]]
                ax.plot(steps, vals, label=label, linewidth=1.2)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Iteration")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8, loc="best")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k" if x >= 1000 else f"{x:.0f}"))

    # 1) Reward + Episode Length
    ax1 = axes[0, 0]
    plot_metric(ax1, [
        ("Train/mean_reward", "Mean Reward"),
    ], "Reward & Episode Length", "Reward")
    if "Train/mean_episode_length" in data:
        ax1b = ax1.twinx()
        steps = [s for s, v in data["Train/mean_episode_length"]]
        vals = [v for s, v in data["Train/mean_episode_length"]]
        ax1b.plot(steps, vals, color="orange", alpha=0.7, label="Ep Length", linewidth=1)
        ax1b.set_ylabel("Episode Length", color="orange")
        ax1b.legend(fontsize=8, loc="upper left")

    # 2) Primary gait KPIs
    plot_metric(axes[0, 1], [
        ("Episode_Reward/standing_height", "Standing Height"),
        ("Episode_Reward/forward_velocity", "Forward Velocity"),
        ("Episode_Reward/trot_gait", "Trot Gait"),
        ("Episode_Reward/diagonal_coupling", "Diagonal Coupling"),
    ], "Primary Gait KPIs", "Reward")

    # 3) Rear activation and clearance
    plot_metric(axes[1, 0], [
        ("Episode_Reward/rear_joint_velocity", "Rear Joint Velocity"),
        ("Episode_Reward/foot_clearance", "Foot Clearance"),
        ("Episode_Reward/leg_lift", "Leg Lift"),
        ("Episode_Reward/stride_length", "Stride Length [contact]"),
    ], "Rear Activation", "Reward")

    # 4) Stability and penalties
    ax4 = axes[1, 1]
    plot_metric(ax4, [
        ("Episode_Reward/undesired_contacts", "Undesired Contacts"),
        ("Episode_Reward/feet_below_knees", "Feet Below Knees"),
        ("Episode_Reward/flat_orientation_l2", "Orientation"),
        ("Episode_Reward/action_rate_l2", "Action Rate"),
    ], "Stability & Penalties", "Penalty (negative)")

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def find_latest_run():
    """가장 최신 훈련 런 디렉토리를 찾습니다."""
    if not os.path.isdir(LOG_BASE):
        return None
    runs = sorted([d for d in os.listdir(LOG_BASE)
                   if os.path.isdir(os.path.join(LOG_BASE, d))])
    return os.path.join(LOG_BASE, runs[-1]) if runs else None


def get_final_report_marker_path(run_dir: str) -> str:
    """런별 최종 heartbeat 전송 마커 파일 경로를 반환합니다."""
    return os.path.join(run_dir, FINAL_REPORT_MARKER_NAME)


def has_final_report_marker(run_dir: str | None) -> bool:
    """런에 대한 최종 heartbeat 전송 여부를 반환합니다."""
    return bool(run_dir) and os.path.isfile(get_final_report_marker_path(run_dir))


def write_final_report_marker(run_dir: str, iteration: int):
    """최종 heartbeat 전송 마커를 기록합니다."""
    marker_path = get_final_report_marker_path(run_dir)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write(f"iter={iteration}\n")
        f.write(f"sent_at={timestamp}\n")


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


def get_heartbeat_history_path(run_dir: str) -> str:
    """Heartbeat 히스토리 JSONL 파일 경로를 반환합니다."""
    return os.path.join(run_dir, HEARTBEAT_HISTORY_JSONL)


def _safe_float(value, digits: int = 6):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return round(numeric, digits)


def _latest_scalar(data: dict, tag: str):
    values = data.get(tag, [])
    if not values:
        return None
    return _safe_float(values[-1][1])


def build_report_record(data: dict, run_name: str, cycle_num: int, report_kind: str = "milestone") -> dict | None:
    """텔레그램 리포트와 별개로 저장할 heartbeat 구조화 레코드를 생성합니다."""
    reward_vals = data.get("Train/mean_reward", [])
    if not reward_vals:
        return None

    ep_len_vals = data.get("Train/mean_episode_length", [])
    current_iter = int(reward_vals[-1][0])
    current_reward = _safe_float(reward_vals[-1][1])
    current_ep_len = _safe_float(ep_len_vals[-1][1]) if ep_len_vals else 0.0
    current_milestone = max(0, (current_iter // 100) * 100)

    timeout = _latest_scalar(data, "Episode_Termination/time_out") or 0.0
    bad_orient = _latest_scalar(data, "Episode_Termination/bad_orientation") or 0.0

    max_ep = 10.0 * 50
    if timeout > 0.95 and current_ep_len and current_ep_len > 1:
        max_ep = current_ep_len
    elif ep_len_vals:
        recent_max_ep = max(float(v) for _, v in ep_len_vals[-50:])
        if recent_max_ep > max_ep * 0.6:
            max_ep = recent_max_ep
    survival_pct = _safe_float((current_ep_len / max_ep) * 100 if max_ep > 0 else 0.0)

    rewards = {}
    for tag, vals in data.items():
        if tag.startswith("Episode_Reward/") and vals:
            rewards[tag.replace("Episode_Reward/", "")] = float(vals[-1][1])

    gait_grade, gait_score, _gait_details = gait_quality_score(rewards)
    stab_grade, stab_score, _stab_details, stab_valid = motion_stability_score(rewards, gait_score)
    posture_grade, posture_score, posture_details = posture_style_score(rewards)
    verdict, reasons, greens, yellows, reds = evaluate_training_window(current_iter, survival_pct or 0.0, bad_orient, rewards)

    primary_metrics = {}
    for metric_name in (
        "standing_height",
        "forward_velocity",
        "diagonal_coupling",
        "trot_gait",
        "rear_joint_velocity",
        "foot_clearance",
        "stride_length",
        "gait_cycle_period",
        "shoulder_neutral",
        "shoulder_symmetry",
        "stance_width_penalty",
    ):
        primary_metrics[metric_name] = _safe_float(rewards.get(metric_name, 0.0))

    penalties = {}
    for metric_name in (
        "joint_vel_l2",
        "action_rate_l2",
        "dof_acc_l2",
        "ang_vel_xy_l2",
        "flat_orientation_l2",
        "same_side_penalty",
    ):
        penalties[metric_name] = _safe_float(rewards.get(metric_name, 0.0))

    record = {
        "run_name": run_name,
        "report_kind": report_kind,
        "cycle_num": int(cycle_num),
        "iteration": current_iter,
        "milestone": current_milestone,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "mean_reward": current_reward,
        "mean_episode_length": current_ep_len,
        "survival_pct": survival_pct,
        "timeout": _safe_float(timeout),
        "bad_orientation": _safe_float(bad_orient),
        "value_function_loss": _latest_scalar(data, "Loss/value_function"),
        "surrogate_loss": _latest_scalar(data, "Loss/surrogate"),
        "noise_std": _latest_scalar(data, "Policy/mean_noise_std"),
        "vel_err_xy": _latest_scalar(data, "Metrics/base_velocity/error_vel_xy"),
        "vel_err_yaw": _latest_scalar(data, "Metrics/base_velocity/error_vel_yaw"),
        "gait_grade": gait_grade,
        "gait_score": int(gait_score),
        "gait_score_kind": "canonical",
        "gait_score_estimated": None,
        "stability_grade": stab_grade,
        "stability_score": int(stab_score),
        "stability_score_kind": "canonical",
        "stability_score_estimated": None,
        "stability_valid": bool(stab_valid),
        "posture_style_grade": posture_grade,
        "posture_style_score": int(posture_score),
        "posture_style_score_kind": "canonical",
        "posture_style_score_estimated": None,
        "posture_style_details": posture_details,
        "verdict": verdict,
        "reasons": reasons,
        "green_count": len(greens),
        "yellow_count": len(yellows),
        "red_count": len(reds),
        "survival_pct_kind": "canonical",
        "survival_pct_derived": None,
        "fallback_source": "heartbeat_jsonl",
        "primary_metrics": primary_metrics,
        "penalties": penalties,
    }
    return record


def append_report_record(run_dir: str, record: dict | None) -> None:
    """Heartbeat 레코드를 JSONL로 누적 저장합니다."""
    if not run_dir or not record:
        return
    history_path = get_heartbeat_history_path(run_dir)
    try:
        with open(history_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as err:
        print(f"[HEARTBEAT] Failed to append report history: {err}")


def load_report_history(run_dir: str) -> list[dict]:
    """저장된 heartbeat 레코드를 로드합니다."""
    history_path = get_heartbeat_history_path(run_dir)
    records = []
    if not os.path.isfile(history_path):
        return records
    try:
        with open(history_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as err:
        print(f"[HEARTBEAT] Failed to read report history: {err}")
    return records


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


# 현재 env_cfg 기준 활성/비활성 보상 항목 (weight=0이면 비활성)
# 접촉 이벤트 기반 메트릭은 소형 로봇에서 측정 불안정할 수 있음
INACTIVE_REWARDS = {"contact_count", "feet_on_ground", "forward_velocity_bootstrap",
                    "stationary_penalty", "leg_pose_symmetry"}
CONTACT_EVENT_METRICS = {"stride_length", "gait_cycle_period", "swing_stride",
                         "rear_alternation", "rear_both_ground", "rear_forward_stride"}
PRIMARY_KPI_THRESHOLDS = {
    "standing_height": (0.08, 0.16),
    "forward_velocity": (0.15, 0.45),
    "diagonal_coupling": (0.30, 1.00),
    "trot_gait": (0.10, 0.40),
    "rear_joint_velocity": (2.0, 8.0),
    "foot_clearance": (0.20, 0.80),
}


def classify_primary_kpi(metric_name, value):
    """주요 KPI를 3단계로 분류합니다."""
    warn_th, good_th = PRIMARY_KPI_THRESHOLDS[metric_name]
    if value >= good_th:
        return "🟢", "양호"
    if value >= warn_th:
        return "🟡", "형성중"
    return "🔴", "미약"


def classify_posture_metric(metric_name, value):
    """V23 posture-style 지표를 3단계로 분류합니다."""
    thresholds = {
        "shoulder_neutral": (-0.60, -0.20),
        "shoulder_symmetry": (-0.40, -0.10),
        "stance_width_penalty": (-0.60, -0.15),
        "standing_height": (0.10, 0.18),
        "flat_orientation_l2": (-0.04, -0.015),
    }
    warn_th, good_th = thresholds[metric_name]
    if value >= good_th:
        return "🟢", "양호"
    if value >= warn_th:
        return "🟡", "형성중"
    return "🔴", "미약"


def evaluate_training_window(current_iter, survival_pct, bad_orient, rewards):
    """초기 운영 판단용 verdict를 반환합니다."""
    watched_metrics = [
        "standing_height",
        "forward_velocity",
        "diagonal_coupling",
        "trot_gait",
        "rear_joint_velocity",
        "foot_clearance",
    ]
    greens = []
    yellows = []
    reds = []
    for metric_name in watched_metrics:
        value = rewards.get(metric_name, 0.0)
        _icon, status = classify_primary_kpi(metric_name, value)
        if status == "양호":
            greens.append(metric_name)
        elif status == "형성중":
            yellows.append(metric_name)
        else:
            reds.append(metric_name)

    reasons = []
    if current_iter <= 300:
        verdict = "🔵 워밍업"
        reasons.append("초기 탐색 구간이라 reward 총합보다 KPI 출현 여부만 확인")
    elif current_iter <= 1000:
        if survival_pct < 8 and bad_orient > 0.95 and len(greens) == 0 and len(yellows) < 2:
            verdict = "🔴 중단 검토"
            reasons.append(f"생존 {survival_pct:.1f}% / bad_orientation {bad_orient*100:.0f}%")
            reasons.append("기립·전진·대각선 패턴이 동시에 약함")
        elif survival_pct >= 15 and (len(greens) >= 1 or len(yellows) >= 3):
            verdict = "🟢 계속 진행"
            reasons.append(f"생존 {survival_pct:.1f}%로 초기 기준 통과")
            reasons.append(f"주요 KPI {len(greens) + len(yellows)}개가 형성중 이상")
        else:
            verdict = "🟡 계속 관찰"
            reasons.append(f"생존 {survival_pct:.1f}% / bad_orientation {bad_orient*100:.0f}%")
            reasons.append("추가 200~300 iter 관찰 후 재판정 권장")
    else:
        if survival_pct >= 25 and len(greens) >= 2 and bad_orient < 0.90:
            verdict = "🟢 계속 진행"
            reasons.append(f"생존 {survival_pct:.1f}% + 핵심 KPI {len(greens)}개 양호")
        elif survival_pct < 10 and len(greens) == 0 and len(yellows) < 2:
            verdict = "🔴 중단 검토"
            reasons.append("1k iter 이후에도 gait-quality KPI 형성이 부족")
        else:
            verdict = "🟡 계속 관찰"
            reasons.append("지표는 일부 형성됐지만 gait 품질 확정 전")

    if reds:
        reasons.append("미약: " + ", ".join(reds[:3]))
    if greens:
        reasons.append("양호: " + ", ".join(greens[:3]))

    return verdict, reasons, greens, yellows, reds


def gait_quality_score(rewards):
    """보행 품질 점수 (0-13).

    성숙 런 TensorBoard 값의 백분위 기준 threshold:
      80-90% → 2pt, 40-50% → 1pt (trot는 0-3)
    성숙 런 기준값: forward_velocity=1.87, foot_clearance=1.99,
      diagonal_coupling=3.33, trot_gait=1.0, rear_joint_velocity=19.9,
      standing_height=0.25
    접촉 이벤트(stride/cycle)는 점수 미반영, 참고만.
    """
    score = 0
    details = []

    # ── 핵심 보행 지표 (총 13점) ──

    # 1. 트로트 패턴 (0-3) — 성숙 ~1.0
    #    3pt: ≥0.9 (90%), 1pt: ≥0.4 (40%)
    trot = rewards.get("trot_gait", 0)
    if trot >= 0.9:
        score += 3
        details.append(f"트로트 ✅✅✅ ({trot:.3f})")
    elif trot >= 0.4:
        score += 1
        details.append(f"트로트 🟡 ({trot:.3f})")
    else:
        details.append(f"트로트 ❌ ({trot:.4f})")

    # 2. 관절 커플링 (0-2) — 성숙 ~3.3, joint-motion coupling
    #    2pt: ≥2.6 (80%), 1pt: ≥1.3 (40%)
    diag = rewards.get("diagonal_coupling", 0)
    if diag >= 2.6:
        score += 2
        details.append(f"관절커플링 ✅✅ ({diag:.2f}) [운동학적]")
    elif diag >= 1.3:
        score += 1
        details.append(f"관절커플링 🟡 ({diag:.2f}) [운동학적]")
    else:
        details.append(f"관절커플링 ❌ ({diag:.3f})")

    # 3. 뒷다리 활성화 (0-2) — 성숙 ~20
    #    2pt: ≥16 (80%), 1pt: ≥8 (40%)
    rear_vel = rewards.get("rear_joint_velocity", 0)
    if rear_vel >= 16.0:
        score += 2
        details.append(f"뒷다리 ✅✅ ({rear_vel:.1f})")
    elif rear_vel >= 8.0:
        score += 1
        details.append(f"뒷다리 🟡 ({rear_vel:.1f})")
    else:
        details.append(f"뒷다리 ❌ ({rear_vel:.2f})")

    # 4. 전진 속도 (0-2) — 성숙 ~1.87
    #    2pt: ≥1.5 (80%), 1pt: ≥0.75 (40%)
    fwd = rewards.get("forward_velocity", 0)
    if fwd >= 1.5:
        score += 2
        details.append(f"전진 ✅✅ ({fwd:.2f})")
    elif fwd >= 0.75:
        score += 1
        details.append(f"전진 🟡 ({fwd:.2f})")
    else:
        details.append(f"전진 ❌ ({fwd:.3f})")

    # 5. 발 들어올리기 (0-2) — 성숙 ~2.0
    #    2pt: ≥1.6 (80%), 1pt: ≥0.8 (40%)
    fc = rewards.get("foot_clearance", 0)
    if fc >= 1.6:
        score += 2
        details.append(f"발높이 ✅✅ ({fc:.2f})")
    elif fc >= 0.8:
        score += 1
        details.append(f"발높이 🟡 ({fc:.2f})")
    else:
        details.append(f"발높이 ❌ ({fc:.3f})")

    # 6. 기립 안정성 (0-2) — 성숙 ~0.25
    #    2pt: ≥0.20 (80%), 1pt: ≥0.10 (40%)
    height = rewards.get("standing_height", 0)
    if height >= 0.20:
        score += 2
        details.append(f"기립 ✅✅ ({height:.3f})")
    elif height >= 0.10:
        score += 1
        details.append(f"기립 🟡 ({height:.3f})")
    else:
        details.append(f"기립 ❌ ({height:.4f})")

    # ── 접촉 이벤트 참고 (점수 미반영) ──
    cycle = rewards.get("gait_cycle_period", 0)
    stride = rewards.get("stride_length", 0)
    if cycle > 0.01 or stride > 0.01:
        details.append(f"  📎 걸음주기 {cycle:.4f} / 보폭 {stride:.4f} [접촉·참고]")
    else:
        details.append(f"  📎 걸음주기·보폭 미감지 [접촉 이벤트 불안정]")

    # 등급
    if score >= 11:
        grade = "🌟 A"
    elif score >= 8:
        grade = "⭐ B"
    elif score >= 5:
        grade = "🟡 C"
    elif score >= 2:
        grade = "🟠 D"
    else:
        grade = "🔴 F"

    return grade, score, details


def motion_stability_score(rewards, gait_score):
    """동작 안정성 점수 (0-10).

    성숙 런 기준 penalty 크기로 평가. 값이 0에 가까울수록 안정.
    보행 미형성(gait_score<3)이면 측정 무의미 (정지 상태는 항상 안정).
    성숙 런 기준값: action_rate=-3.0, joint_vel=-4.8,
      flat_orientation=-0.008, ang_vel=-0.37, lin_vel_z=-0.009
    """
    if gait_score < 3:
        return "⚪ N/A", 0, ["보행 미형성 — 안정성 측정 무의미"], False

    score = 0
    details = []

    # 1. 액션 부드러움 (0-2) — 성숙 ~-3.0
    #    2pt: > -3.6 (120%), 1pt: > -6.0 (200%)
    ar = rewards.get("action_rate_l2", 0)
    if ar > -3.6:
        score += 2
        details.append(f"액션부드러움 ✅✅ ({ar:.2f})")
    elif ar > -6.0:
        score += 1
        details.append(f"액션부드러움 🟡 ({ar:.2f})")
    else:
        details.append(f"액션부드러움 ❌ ({ar:.2f})")

    # 2. 관절속도 억제 (0-2) — 성숙 ~-4.8
    #    2pt: > -6.0 (125%), 1pt: > -10.0 (208%)
    jv = rewards.get("joint_vel_l2", 0)
    if jv > -6.0:
        score += 2
        details.append(f"관절속도 ✅✅ ({jv:.2f})")
    elif jv > -10.0:
        score += 1
        details.append(f"관절속도 🟡 ({jv:.2f})")
    else:
        details.append(f"관절속도 ❌ ({jv:.2f})")

    # 3. 자세 수평 (0-2) — 성숙 ~-0.008
    #    2pt: > -0.015 (187%), 1pt: > -0.04 (500%)
    fo = rewards.get("flat_orientation_l2", 0)
    if fo > -0.015:
        score += 2
        details.append(f"자세수평 ✅✅ ({fo:.4f})")
    elif fo > -0.04:
        score += 1
        details.append(f"자세수평 🟡 ({fo:.4f})")
    else:
        details.append(f"자세수평 ❌ ({fo:.4f})")

    # 4. 각속도 안정 (0-2) — 성숙 ~-0.37
    #    2pt: > -0.5 (135%), 1pt: > -1.0 (270%)
    av = rewards.get("ang_vel_xy_l2", 0)
    if av > -0.5:
        score += 2
        details.append(f"각속도 ✅✅ ({av:.3f})")
    elif av > -1.0:
        score += 1
        details.append(f"각속도 🟡 ({av:.3f})")
    else:
        details.append(f"각속도 ❌ ({av:.3f})")

    # 5. 수직 진동 억제 (0-2) — 성숙 ~-0.009
    #    2pt: > -0.015 (167%), 1pt: > -0.03 (333%)
    lv = rewards.get("lin_vel_z_l2", 0)
    if lv > -0.015:
        score += 2
        details.append(f"수직진동 ✅✅ ({lv:.4f})")
    elif lv > -0.03:
        score += 1
        details.append(f"수직진동 🟡 ({lv:.4f})")
    else:
        details.append(f"수직진동 ❌ ({lv:.4f})")

    if score >= 8:
        grade = "🌟 A"
    elif score >= 6:
        grade = "⭐ B"
    elif score >= 4:
        grade = "🟡 C"
    elif score >= 2:
        grade = "🟠 D"
    else:
        grade = "🔴 F"

    return grade, score, details, True


def posture_style_score(rewards):
    """V23 phase-1 posture/style score (0-10)."""
    score = 0
    details = []

    metrics = [
        ("shoulder_neutral", "어깨중립"),
        ("shoulder_symmetry", "어깨대칭"),
        ("stance_width_penalty", "스탠스폭"),
        ("standing_height", "기립높이"),
        ("flat_orientation_l2", "자세수평"),
    ]
    for metric_name, label in metrics:
        value = rewards.get(metric_name, 0.0)
        icon, state = classify_posture_metric(metric_name, value)
        if state == "양호":
            score += 2
        elif state == "형성중":
            score += 1
        details.append(f"{label} {icon} ({value:+.4f})")

    if score >= 8:
        grade = "🌟 A"
    elif score >= 6:
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

    # 종료 원인
    timeout_vals = data.get("Episode_Termination/time_out", [])
    bad_orient_vals = data.get("Episode_Termination/bad_orientation", [])
    timeout = timeout_vals[-1][1] if timeout_vals else 0
    bad_orient = bad_orient_vals[-1][1] if bad_orient_vals else 0
    total_term = timeout + bad_orient
    timeout_pct = (timeout / total_term * 100) if total_term > 0 else 0

    # 생존율
    max_ep = 10.0 * 50  # 기본값: 10s × 50Hz
    if timeout > 0.95 and current_ep_len > 1:
        max_ep = current_ep_len
    elif ep_len_vals:
        recent_max_ep = max(v for _, v in ep_len_vals[-50:])
        if recent_max_ep > max_ep * 0.6:
            max_ep = recent_max_ep
    survival_pct = (current_ep_len / max_ep) * 100 if max_ep > 0 else 0

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

    # ── 동작 안정성 ──
    stab_grade, stab_score, stab_details, stab_valid = motion_stability_score(rewards, gait_score)

    # ── posture/style ──
    posture_grade, posture_score, posture_details = posture_style_score(rewards)

    # ── gait-quality-first 운영 KPI ──
    primary_kpi_defs = [
        ("standing_height", "기립높이"),
        ("forward_velocity", "전진속도"),
        ("diagonal_coupling", "대각커플링"),
        ("trot_gait", "트로트패턴"),
        ("rear_joint_velocity", "뒷다리활성"),
        ("foot_clearance", "발들기"),
    ]
    primary_kpi_lines = []
    for metric_name, label in primary_kpi_defs:
        tag = f"Episode_Reward/{metric_name}"
        val = rewards.get(metric_name, 0.0)
        icon, pct = get_trend(data.get(tag, [])) if tag in data else ("📊", 0.0)
        state_icon, state_label = classify_primary_kpi(metric_name, val)
        primary_kpi_lines.append(
            f"  {state_icon} {label}: {val:+.4f} {icon} ({pct:+.1f}%) [{state_label}]"
        )

    decision_verdict, decision_reasons, _decision_greens, _decision_yellows, _decision_reds = evaluate_training_window(
        current_iter, survival_pct, bad_orient, rewards
    )

    # ── 핵심 메트릭 추세 ──
    key_trends = []
    trend_metrics = [
        ("trot_gait", "트로트패턴", ""),
        ("diagonal_coupling", "관절커플링", "[운동학]"),  # joint-motion coupling, not footfall trot
        ("leg_lift", "다리들기", ""),
        ("rear_joint_velocity", "뒷다리속도", "[관절]"),
        ("standing_height", "기립높이", ""),
        ("foot_clearance", "발들기", ""),
        ("forward_velocity", "전진속도", ""),
        ("stride_length", "보폭", "[접촉]"),
        ("gait_cycle_period", "걸음주기", "[접촉]"),
        ("rear_forward_stride", "뒷다리보폭", "[접촉]"),
        ("rear_alternation", "뒷다리교대", "[접촉]"),
        ("swing_stride", "스윙보폭", "[접촉]"),
        ("stance_propulsion", "스탠스추진", "[접촉]"),
    ]
    for metric_name, label, tag_type in trend_metrics:
        tag = f"Episode_Reward/{metric_name}"
        if tag in data and data[tag]:
            val = data[tag][-1][1]
            # weight=0 비활성 항목은 건너뜀
            if metric_name in INACTIVE_REWARDS:
                continue
            icon, pct = get_trend(data[tag])
            suffix = f" {tag_type}" if tag_type else ""
            key_trends.append(f"  {icon} {label}: {val:+.4f} ({pct:+.1f}%){suffix}")

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
    lines.append(f"  {reward_icon} Reward: {current_reward:.1f} (avg10: {avg_reward:.1f}) [보조]")
    lines.append(f"  {ep_icon} Episode: {current_ep_len:.1f} steps (생존 {survival_pct:.1f}%)")
    lines.append(f"  🏆 Best: {best_reward:.1f} @iter {best_iter}")
    lines.append(f"  📉 Worst: {worst_reward:.1f}")
    lines.append(f"  💀 종료: timeout {timeout_pct:.0f}% / fall {100-timeout_pct:.0f}%")
    lines.append("")

    lines.append(f"<b>🚦 운영 판정</b>")
    lines.append(f"  {decision_verdict}")
    for reason in decision_reasons:
        lines.append(f"  - {reason}")
    lines.append("")

    lines.append(f"<b>🧭 우선 KPI (gait quality first)</b>")
    for kpi_line in primary_kpi_lines:
        lines.append(kpi_line)
    stride_val = rewards.get("stride_length", 0.0)
    cycle_val = rewards.get("gait_cycle_period", 0.0)
    lines.append(f"  📎 접촉참고: stride {stride_val:+.4f} / cycle {cycle_val:+.4f}")
    lines.append("")

    # ════════════════════════════════════════════
    # 3층 구조: 보행 품질 / 동작 안정성 / 접촉 참고
    # ════════════════════════════════════════════

    # 1층: 보행 품질
    lines.append(f"<b>🦿 보행 품질 {grade} ({gait_score}/13)</b>")
    for d in gait_details:
        lines.append(f"  {d}")
    lines.append("")

    # 2층: 동작 안정성
    if stab_valid:
        lines.append(f"<b>🛡️ 동작 안정성 {stab_grade} ({stab_score}/10)</b>")
        for d in stab_details:
            lines.append(f"  {d}")
    else:
        lines.append(f"<b>🛡️ 동작 안정성 {stab_grade}</b>")
        lines.append(f"  {stab_details[0]}")
    lines.append("")

    # 복합 요약 (Gait X / Stability Y)
    if stab_valid:
        lines.append(f"  📊 종합: Gait {grade} / Stability {stab_grade}")
    lines.append("")

    lines.append(f"<b>🧍 posture/style {posture_grade} ({posture_score}/10)</b>")
    for d in posture_details:
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

    # 동작 부드러움 (간략 — 상세는 안정성 점수에서)
    lines.append(f"<b>🔧 동작 품질</b>")
    lines.append(f"  {smooth_label} (action={action_rate:.1f} joint={joint_vel:.1f} acc={dof_acc:.1f})")
    lines.append("")

    # 학습 지표
    lines.append(f"<b>🧠 학습 지표</b>")
    lines.append(f"  VF Loss: {vf_loss:.1f}")
    lines.append(f"  Surrogate: {surr_loss:.5f}")
    lines.append(f"  Noise std: {noise_std:.3f}")
    lines.append(f"  Vel err (xy): {vel_xy:.4f}")
    lines.append(f"  Vel err (yaw): {vel_yaw:.4f}")
    lines.append("")

    # TOP5 양수/음수 보상 (weight=0 비활성 항목 제외)
    active_positive = [(k, v) for k, v in positive if k not in INACTIVE_REWARDS]
    active_negative = [(k, v) for k, v in negative if k not in INACTIVE_REWARDS]
    lines.append(f"<b>🏅 TOP5 기여 보상</b>")
    for i, (name, val) in enumerate(active_positive[:5]):
        tag = f"Episode_Reward/{name}"
        icon, pct = get_trend(data.get(tag, []))
        ct_mark = " [접촉]" if name in CONTACT_EVENT_METRICS else ""
        lines.append(f"  {i+1}. {name}: {val:+.4f} {icon}{ct_mark}")
    lines.append("")

    lines.append(f"<b>💣 TOP5 패널티</b>")
    for i, (name, val) in enumerate(active_negative[:5]):
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

    # ── 학습 단계 판별 (survival + 운동학 지표 결합) ──
    fwd_val = rewards.get("forward_velocity", 0)
    diag_val = rewards.get("diagonal_coupling", 0)
    fc_val = rewards.get("foot_clearance", 0)
    trot_val = rewards.get("trot_gait", 0)
    if survival_pct < 5:
        phase = "1단계: 기립 학습 초기"
        phase_icon = "🥚"
        phase_desc = "로봇이 즉시 넘어짐. 페널티 회피 학습 중"
    elif survival_pct < 20:
        phase = "2단계: 기립 시도"
        phase_icon = "🐣"
        phase_desc = "짧게 서있기 시작. 균형 학습 중"
    elif survival_pct < 50:
        phase = "3단계: 관절 패턴 형성"
        phase_icon = "🐥"
        extras = []
        if fc_val > 0.5:
            extras.append(f"발들기 {fc_val:.1f}")
        if trot_val > 0.3:
            extras.append(f"트로트 {trot_val:.2f}")
        if extras:
            phase_desc = f"관절 리듬 출현 ({', '.join(extras)}) — 실제 보행 여부는 영상 확인 필요"
        else:
            phase_desc = "관절 리듬 출현 (실제 보행 여부는 영상 확인 필요)"
    elif survival_pct >= 50 and diag_val > 1.0 and fwd_val > 0.5:
        kin_parts = [f"커플링 {diag_val:.1f}", f"전진 {fwd_val:.1f}"]
        if fc_val > 0.8:
            kin_parts.append(f"발들기 {fc_val:.1f}")
        if trot_val > 0.5:
            kin_parts.append(f"트로트 {trot_val:.2f}")
        kin_str = " + ".join(kin_parts)
        if survival_pct >= 80:
            phase = "5단계: 안정화 + 운동학 활성"
            phase_icon = "🦮"
            phase_desc = f"생존 {survival_pct:.0f}% + {kin_str} — 영상 최종 확인"
        else:
            phase = "4단계: 보행 발달 후보"
            phase_icon = "🐕"
            phase_desc = f"{kin_str} 활성 — rear-driven 가능성 있음 (영상 확인)"
    elif survival_pct >= 80:
        phase = "5단계: 생존 안정화 (운동학 미확인)"
        phase_icon = "🦮"
        phase_desc = "생존은 안정적이나 관절 커플링/전진 속도가 아직 약함"
    else:
        phase = "4단계: 보행 발달 후보"
        phase_icon = "🐕"
        phase_desc = "관절 커플링 발달 중 — rear-driven일 가능성 있음 (영상 확인)"

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

    # 🔮 예상 타임라인 (대략적 참고용, 학습마다 차이 큼)
    lines.append(f"<b>🔮 대략적 단계 참고</b>")
    lines.append(f"  ⚠️ 아래는 과거 학습 기준 참고치이며, 실제 진행은 다를 수 있음")
    phases_timeline = [
        (2000, "기립 시작", "ep length 증가 시작"),
        (4000, "균형 학습", "넘어짐 비율 감소"),
        (7000, "관절 패턴?", "커플링/리듬 발달 가능 (영상 확인)"),
        (10000, "보행 발달?", "stride/velocity 확인 필요"),
        (13000, "안정화", "미세 조정"),
        (15600, "훈련 종료", "최종 모델 (영상 검증 필수)"),
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

    # ════════════════════════════════════════════
    # 🧑‍🔬 AI 산문 분석
    # ════════════════════════════════════════════
    lines.append(f"<b>🧑‍🔬 AI 분석 의견</b>")
    prose_parts = []

    # 1) 전체 흐름 평가
    if current_iter < 500:
        prose_parts.append(
            f"아직 iter {int(current_iter):,}로 훈련 극초반입니다. "
            f"현재 평균 보상 {current_reward:.1f}은 초기 탐색 단계에서 전형적인 수치이며, "
            f"이 시점에서는 보상의 절대값보다 학습이 정상적으로 수렴 방향으로 움직이는지가 중요합니다."
        )
    elif current_iter < 3000:
        if improvement > 50:
            prose_parts.append(
                f"iter {int(current_iter):,} 기준, 보상이 {early_avg:.1f}에서 {late_avg:.1f}로 {improvement:+.1f} 개선되어 "
                f"빠른 학습 속도를 보이고 있습니다."
            )
        elif improvement > 0:
            prose_parts.append(
                f"iter {int(current_iter):,} 기준, 보상이 소폭({improvement:+.1f}) 개선 중입니다. "
                f"아직 본격적인 보행 학습 이전 단계로, 기립 및 균형 확보에 집중하는 시기입니다."
            )
        else:
            prose_parts.append(
                f"iter {int(current_iter):,}인데 보상이 {improvement:+.1f}로 정체 또는 하락 중입니다. "
                f"학습률이나 보상 가중치 재검토가 필요할 수 있습니다."
            )
    elif current_iter < 8000:
        stab_info = f", 안정성 {stab_grade}({stab_score}/10)" if stab_valid else ""
        if gait_score >= 8:
            prose_parts.append(
                f"중반부(iter {int(current_iter):,})에서 보행 {grade}({gait_score}/13){stab_info}로 "
                f"관절 패턴이 형성되고 있습니다. 단, 점수가 높아도 실제 footfall trot인지는 "
                f"영상으로 확인해야 합니다."
            )
        elif gait_score >= 5:
            prose_parts.append(
                f"중반부(iter {int(current_iter):,})에서 보행 {grade}({gait_score}/13){stab_info}입니다. "
                f"관절 리듬은 나타나고 있으나, 전진속도·발높이가 아직 약할 수 있어 "
                f"실제 보행 품질은 영상으로 판단해야 합니다."
            )
        else:
            prose_parts.append(
                f"iter {int(current_iter):,}까지 왔지만 보행 {grade}({gait_score}/13)로 "
                f"관절 패턴 형성이 더딥니다. 보상 구조 또는 커리큘럼 변경을 고려해볼 시점입니다."
            )
    else:
        stab_info = f", 안정성 {stab_grade}({stab_score}/10)" if stab_valid else ""
        if gait_score >= 11:
            prose_parts.append(
                f"후반부(iter {int(current_iter):,})에서 보행 {grade}({gait_score}/13){stab_info} — 운동학 지표 기준 우수합니다. "
                f"단, 이 점수는 관절·속도 수치 기반이며 실제 보행은 영상 확인 필수입니다."
            )
        elif gait_score >= 8:
            prose_parts.append(
                f"후반부(iter {int(current_iter):,})에서 보행 {grade}({gait_score}/13){stab_info}입니다. "
                f"양호하지만 전진속도 대비 뒷다리 활성이 지배적이라면 rear-driven 패턴일 가능성이 있습니다."
            )
        else:
            prose_parts.append(
                f"iter {int(current_iter):,}까지 왔음에도 보행 {grade}({gait_score}/13){stab_info}입니다. "
                f"현재 보상 구조로는 한계가 보이며, V20에서 근본적 접근 변경이 필요할 수 있습니다."
            )

    # 2) 생존/안정성 평가
    if survival_pct >= 80:
        prose_parts.append(
            f"생존율 {survival_pct:.0f}%로 매우 안정적이며, 대부분 timeout으로 에피소드가 종료됩니다."
        )
    elif survival_pct >= 40:
        prose_parts.append(
            f"생존율 {survival_pct:.0f}%로 어느 정도 버티고 있으나, "
            f"아직 넘어짐이 {100-timeout_pct:.0f}%를 차지합니다."
        )
    elif survival_pct >= 10:
        prose_parts.append(
            f"생존율 {survival_pct:.0f}%로 짧게 서있지만 금방 넘어집니다. "
            f"균형 및 자세 보상이 더 강화되어야 합니다."
        )

    # 3) 핵심 보상 동향
    if improving_keys and declining_keys:
        imp_names = ", ".join(n for n, _ in improving_keys[:3])
        dec_names = ", ".join(n for n, _ in declining_keys[:3])
        prose_parts.append(
            f"세부적으로, {imp_names}은(는) 개선 추세인 반면 {dec_names}은(는) 하락 중입니다. "
            f"하락 항목이 전체 보상에 미치는 영향을 모니터링해야 합니다."
        )
    elif improving_keys:
        imp_names = ", ".join(n for n, _ in improving_keys[:3])
        prose_parts.append(f"주요 보상 항목({imp_names}) 대부분이 개선 추세여서 긍정적입니다.")
    elif declining_keys:
        dec_names = ", ".join(n for n, _ in declining_keys[:3])
        prose_parts.append(f"경고: {dec_names}이(가) 하락 중으로, 보상 간 충돌 가능성을 점검해야 합니다.")

    # 4) 어깨 관련 (V19 핵심)
    shoulder_val = rewards.get("shoulder_neutral", 0)
    if abs(shoulder_val) < 0.2:
        prose_parts.append(
            f"V19의 핵심인 어깨 중립 페널티가 {shoulder_val:+.4f}로 매우 낮아, "
            f"목표 splay 각도에 잘 수렴하고 있습니다. V18.3 대비 큰 개선입니다."
        )
    elif abs(shoulder_val) < 1.0:
        prose_parts.append(
            f"어깨 중립 페널티가 {shoulder_val:+.4f}로 아직 약간의 편차가 있습니다. "
            f"학습이 진행되면 자연스럽게 줄어들 것으로 예상됩니다."
        )
    elif shoulder_val < -1.0:
        prose_parts.append(
            f"어깨 중립 페널티가 {shoulder_val:+.4f}로 여전히 큽니다. "
            f"타겟 splay 각도가 로봇 구조에 맞는지 재확인이 필요합니다."
        )

    # 5) 부드러움/에너지 효율 + 안정성 점수 연계
    if stab_valid and stab_score >= 8:
        prose_parts.append("동작 안정성이 우수합니다. 부드럽고 효율적인 보행입니다.")
    elif stab_valid and stab_score <= 4:
        prose_parts.append(
            f"동작 안정성 {stab_grade}({stab_score}/10)로 거칠어, "
            f"action_rate/joint_vel 페널티 강화를 고려해볼 만합니다."
        )
    elif smooth_total < 15:
        prose_parts.append("동작이 매우 부드러워 에너지 효율적인 학습이 진행되고 있습니다.")
    elif smooth_total > 50:
        prose_parts.append(
            f"동작 거칠기({smooth_total:.1f})가 높아 떨림이나 급격한 관절 변화가 의심됩니다. "
            f"action_rate 페널티 강화를 고려해볼 만합니다."
        )

    # 6) 학습 안정성 (VF loss)
    if vf_loss > 500:
        prose_parts.append(
            f"Value function loss가 {vf_loss:.1f}로 높습니다. "
            f"보상 스케일 과도, 보상 항목 간 불균형, 또는 gamma 조정이 필요할 수 있습니다."
        )
    elif vf_loss < 5 and current_iter > 1000:
        prose_parts.append(f"VF loss {vf_loss:.1f}로 안정적인 학습이 이루어지고 있습니다.")

    # 7) rear bias 경고
    rear_metrics = ["rear_joint_velocity", "rear_swing", "rear_forward_stride", "rear_alternation"]
    top5_names = [n for n, _ in active_positive[:5]]
    rear_in_top = [n for n in top5_names if any(rm in n for rm in rear_metrics)]
    if len(rear_in_top) >= 3:
        prose_parts.append(
            f"⚠️ TOP5 보상 중 {len(rear_in_top)}개가 뒷다리 계열입니다. "
            f"rear-driven locomotion precursor 상태일 가능성이 높으며, "
            f"실제 보행 여부는 영상으로 확인해야 합니다."
        )

    # 8) 접촉 이벤트 지표 신뢰성 경고
    contact_metrics_zero = []
    for cm in ["stride_length", "gait_cycle_period"]:
        cv = rewards.get(cm, 0)
        if abs(cv) < 0.001:
            contact_metrics_zero.append(cm)
    if contact_metrics_zero and current_iter > 2000:
        prose_parts.append(
            f"참고: {', '.join(contact_metrics_zero)}이(가) ~0입니다. "
            f"접촉 이벤트 측정이 불안정하거나, 실제 stride가 미형성일 수 있습니다."
        )

    # 산문 조합
    full_prose = " ".join(prose_parts)
    # 4096자 제한 대비 산문 길이 제한
    if len(full_prose) > 800:
        full_prose = full_prose[:797] + "..."
    lines.append(f"  {full_prose}")
    lines.append("")

    # 다음 리포트
    lines.append("")
    next_milestone = ((int(current_iter) // 100) + 1) * 100
    lines.append(f"⏰ 다음 리포트: iter {next_milestone:,}")

    # TensorBoard URL
    if TB_URL:
        lines.append(f"🔗 TensorBoard: {TB_URL}")

    return "\n".join(lines)


def send_final_heartbeat_report(run_dir: str, cycle_num: int = 0, force: bool = False) -> bool:
    """완료된 런의 최종 heartbeat 리포트를 한 번 전송합니다."""
    if not run_dir or not os.path.isdir(run_dir):
        print("[FINAL] Run dir missing, final heartbeat skipped")
        return False

    if not force and has_final_report_marker(run_dir):
        print(f"[FINAL] Marker exists, final heartbeat already sent: {run_dir}")
        return False

    data = read_tfevents(run_dir)
    if not data:
        print(f"[FINAL] No TensorBoard data for {run_dir}, final heartbeat skipped")
        return False

    reward_vals = data.get("Train/mean_reward", [])
    if not reward_vals:
        print(f"[FINAL] No reward scalars for {run_dir}, final heartbeat skipped")
        return False

    current_iter = int(reward_vals[-1][0])
    run_name = os.path.basename(run_dir)
    final_report = format_report(data, run_name, cycle_num)
    append_report_record(run_dir, build_report_record(data, run_name, cycle_num, report_kind="final"))
    final_header = (
        "🏁 <b>훈련 종료 Final Heartbeat</b>\n"
        f"📁 Run: <code>{run_name}</code>\n"
        f"🎯 최종 iter: <b>{current_iter:,}</b>\n"
        + "━" * 30
        + "\n\n"
    )
    send_telegram(final_header + final_report)

    graph_bytes = generate_training_graphs(data, run_name)
    if graph_bytes:
        send_telegram_photo(graph_bytes, f"🏁 Final Training Graphs (iter {current_iter:,})")

    write_final_report_marker(run_dir, current_iter)
    print(f"[FINAL] Final heartbeat report sent for {run_name} @ iter {current_iter}")
    return True


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


def check_user_stop():
    """사용자가 의도적으로 supervisor를 중단했는지 확인 (user_stop.flag 존재 여부)."""
    return os.path.isfile(USER_STOP_FLAG)


def is_run_complete(run_dir: str | None) -> bool:
    """주어진 런 디렉토리가 완료 상태인지 확인."""
    if not run_dir or not os.path.isdir(run_dir):
        return False

    model_iters = []
    try:
        for name in os.listdir(run_dir):
            if not (name.startswith("model_") and name.endswith(".pt")):
                continue
            match = re.match(r"model_(\d+)\.pt$", name)
            if match:
                model_iters.append(int(match.group(1)))
    except OSError:
        return False

    return bool(model_iters) and max(model_iters) >= MAX_ITERATIONS


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
    parser.add_argument("--send_final_now", action="store_true", help="Send final heartbeat report immediately for the target run")
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
    exit_notice = "👋 <b>Training Heartbeat 종료</b>"

    try:
        if args.send_final_now:
            target_run_dir = args.run_dir if args.run_dir else find_latest_run()
            if not send_final_heartbeat_report(target_run_dir, cycle_num=0, force=True):
                raise RuntimeError("Final heartbeat report was not sent")
            exit_notice = None
            return

        while True:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                # ── Supervisor 워치독 (자동 재시작) ──
                current_run_dir = args.run_dir if args.run_dir else find_latest_run()
                run_complete = is_run_complete(current_run_dir)
                if not check_supervisor_alive():
                    if check_user_stop():
                        print(f"[{now}] Supervisor stopped by user (user_stop.flag exists). Skipping auto-restart.")
                    elif run_complete:
                        print(f"[{now}] Completed run detected. Skipping supervisor auto-restart.")
                    elif not supervisor_alert_sent:
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
                        if run_complete:
                            final_report_sent = send_final_heartbeat_report(run_dir=current_run_dir, cycle_num=cycle + 1)
                            if final_report_sent:
                                print(f"[{now}] Final heartbeat delivered for completed run.")
                            else:
                                print(f"[{now}] Completed run already reported. Exiting quietly.")
                            exit_notice = None
                        else:
                            exit_notice = "🛑 <b>훈련 프로세스 없음!</b>\n훈련이 종료되었거나 크래시 발생"
                        print("No training process found!")
                        break
                else:
                    maintenance_logged = False  # 훈련 복귀 시 리셋

                # 런 디렉토리 찾기
                run_dir = current_run_dir
                if not run_dir or not os.path.isdir(run_dir):
                    print(f"Run dir not found: {run_dir}")
                    time.sleep(args.poll)
                    continue

                run_name = os.path.basename(run_dir)

                # TensorBoard junction 업데이트 (런 변경 시 자동 반영)
                update_tb_junction(run_dir)

                # TensorBoard 프로세스 상태 확인 및 자동 재시작
                ensure_tensorboard()

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
                    append_report_record(run_dir, build_report_record(data, run_name, cycle, report_kind="startup"))
                    header = f"🤖 <b>Training Heartbeat 시작</b> (PID {os.getpid()})\n"
                    header += f"📊 매 {args.iter_step} iter마다 리포트\n"
                    header += "━" * 30 + "\n\n"
                    report = header + report
                    print(f"\n[{now}] === Report #{cycle} (iter {current_iter}, milestone {current_milestone}) ===")
                    print(report)
                    send_telegram(report)
                    # 그래프 이미지 전송
                    graph_bytes = generate_training_graphs(data, run_name)
                    if graph_bytes:
                        send_telegram_photo(graph_bytes, f"📊 Training Graphs (iter {current_iter:,})")
                        print(f"Graph sent for iter {current_iter}")
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
                    append_report_record(run_dir, build_report_record(data, run_name, cycle, report_kind="milestone"))
                    print(report)
                    send_telegram(report)
                    # 그래프 이미지 전송
                    graph_bytes = generate_training_graphs(data, run_name)
                    if graph_bytes:
                        send_telegram_photo(graph_bytes, f"📊 Training Graphs (iter {current_iter:,})")
                        print(f"Graph sent for iter {current_iter}")
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

    if exit_notice:
        send_telegram(exit_notice)
    print("Heartbeat exited.")


if __name__ == "__main__":
    main()
