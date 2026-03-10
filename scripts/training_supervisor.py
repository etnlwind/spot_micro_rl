"""Training Supervisor — Python 통합판 (V17.1)
iteration milestone마다 훈련 중단 → 영상 녹화 → 상세 분석 → 텔레그램 보고/의사결정 → 훈련 재개

[T1] 텔레그램 양방향 통신 — 진행상황 알림 + 의사결정 요청
[T2] 10분 응답대기 → 타임아웃 시 자동 판단 (계속 진행)
[T3] 분석결과 파싱 (등급/점수/reward/trend) → 상황 판단
[T4] 등급 D/F 또는 점수 하락 시 사용자에게 선택지 제시

Phase별 try-except, GPU메모리기준 wait_gpu_free, 분석타임아웃 120s
Heartbeat 상호감시 (maintenance.flag 연동)

Usage: python scripts/training_supervisor.py [--interval 180] [--video_length 250]
"""

import argparse
import datetime
import glob
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request

import psutil

# Windows cp949 콘솔에서 이모지 깨짐 방지
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# .ENV CONFIG
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def _load_env(path: str) -> dict:
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

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or _env.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _env.get("TELEGRAM_CHAT_ID", "")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not found in .env or environment")
    sys.exit(1)

TG_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Paths
ISAAC_LAB = _env.get("ISAAC_LAB_PATH", r"C:\IsaacLab\isaaclab.bat")
TASK = _env.get("TASK", "Isaac-Velocity-Flat-SpotMicro-v0")
LOG_SUBDIR = _env.get("LOG_SUBDIR", "spot_micro_flat")

# Numeric config (defaults match .env)
INTERVAL_MINUTES = int(_env.get("INTERVAL_MINUTES", "180"))
VIDEO_LENGTH = int(_env.get("VIDEO_LENGTH", "250"))
PLAY_ENVS = int(_env.get("PLAY_ENVS", "50"))
TRAIN_ENVS = int(_env.get("TRAIN_ENVS", "24576"))
MAX_ITERATIONS = int(_env.get("MAX_ITERATIONS", "15000"))
VIDEO_FPS = int(_env.get("VIDEO_FPS", "15"))
DECISION_TIMEOUT_SEC = int(_env.get("DECISION_TIMEOUT_SEC", "600"))
SUPERVISOR_POLL_SECONDS = int(_env.get("SUPERVISOR_POLL_SECONDS", "60"))
VIDEO_INTERVAL_EARLY_ITER = int(_env.get("VIDEO_INTERVAL_EARLY_ITER", "500"))
VIDEO_INTERVAL_MID_ITER = int(_env.get("VIDEO_INTERVAL_MID_ITER", "1000"))
VIDEO_INTERVAL_LATE_ITER = int(_env.get("VIDEO_INTERVAL_LATE_ITER", "1500"))
VIDEO_INTERVAL_EARLY_END = int(_env.get("VIDEO_INTERVAL_EARLY_END", "1500"))
VIDEO_INTERVAL_MID_END = int(_env.get("VIDEO_INTERVAL_MID_END", "6000"))
URGENT_VIDEO_GAP_ITER = int(_env.get("URGENT_VIDEO_GAP_ITER", "400"))

# Video camera views for gait validation
VIDEO_VIEWS = ["side", "front", "rear", "top_oblique"]

# Training version tag (env_cfg.py에서 읽음 — 코드 변경 시 자동 반영)
def _read_train_version() -> str:
    """env_cfg.py에서 TRAIN_VERSION 상수를 파싱."""
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

# Curriculum Phase boundaries (must match rewards.py PHASE_WEIGHTS)
PHASE1_END_ITER = int(_env.get("PHASE1_END_ITER", "2000"))
PHASE2_END_ITER = int(_env.get("PHASE2_END_ITER", "6000"))

# Derived paths
LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", LOG_SUBDIR)
MONITOR_LOG = os.path.join(PROJECT_ROOT, "logs", "monitor_log.txt")
ANALYZE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "utils", "analyze_training.py")
MAINTENANCE_FLAG = os.path.join(PROJECT_ROOT, "logs", "maintenance.flag")
USER_STOP_FLAG = os.path.join(PROJECT_ROOT, "logs", "user_stop.flag")
HEARTBEAT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "training_heartbeat.pid")
HEARTBEAT_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "training_heartbeat.py")
SUPERVISOR_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "training_supervisor.pid")

# ── State ────────────────────────────────────────────────────────
_tg_offset = 0
_last_analysis_text = ""
_prev_score = -1
_heartbeat_alert_sent = False


def get_regular_video_interval(iteration: int) -> int:
    """iteration 구간별 정기 영상 간격(iter)을 반환."""
    if iteration < VIDEO_INTERVAL_EARLY_END:
        return VIDEO_INTERVAL_EARLY_ITER
    if iteration < VIDEO_INTERVAL_MID_END:
        return VIDEO_INTERVAL_MID_ITER
    return VIDEO_INTERVAL_LATE_ITER


def get_next_regular_trigger(iteration: int) -> int:
    """현재 iteration 이후 다음 정기 영상 목표 iter를 계산."""
    if iteration < VIDEO_INTERVAL_EARLY_END:
        slot = (iteration // VIDEO_INTERVAL_EARLY_ITER) + 1
        candidate = slot * VIDEO_INTERVAL_EARLY_ITER
        if candidate <= VIDEO_INTERVAL_EARLY_END:
            return candidate
        iteration = VIDEO_INTERVAL_EARLY_END

    if iteration < VIDEO_INTERVAL_MID_END:
        slot = ((max(iteration, VIDEO_INTERVAL_EARLY_END) - VIDEO_INTERVAL_EARLY_END) // VIDEO_INTERVAL_MID_ITER) + 1
        candidate = VIDEO_INTERVAL_EARLY_END + slot * VIDEO_INTERVAL_MID_ITER
        if candidate <= VIDEO_INTERVAL_MID_END:
            return candidate
        iteration = VIDEO_INTERVAL_MID_END

    slot = ((max(iteration, VIDEO_INTERVAL_MID_END) - VIDEO_INTERVAL_MID_END) // VIDEO_INTERVAL_LATE_ITER) + 1
    return VIDEO_INTERVAL_MID_END + slot * VIDEO_INTERVAL_LATE_ITER


def verdict_severity(verdict: str) -> int:
    """운영 판정 문자열을 심각도로 변환."""
    if "중단 검토" in verdict:
        return 2
    if "계속 관찰" in verdict:
        return 1
    return 0


def should_capture_clip(current_iter: int, last_clip_iter: int, next_regular_iter: int, verdict: str, last_verdict: str) -> tuple[bool, str]:
    """정기 주기 또는 판정 악화 기준으로 clip 캡처 여부를 결정."""
    if current_iter >= next_regular_iter:
        return True, f"regular-{get_regular_video_interval(current_iter)}iter"

    current_severity = verdict_severity(verdict)
    last_severity = verdict_severity(last_verdict)
    if current_severity > last_severity and (current_iter - last_clip_iter) >= URGENT_VIDEO_GAP_ITER:
        return True, f"urgent-{verdict}"

    return False, ""


def format_trigger_status(next_regular_iter: int, last_clip_iter: int, verdict: str, last_verdict: str) -> str:
    """다음 정기/긴급 트리거 기준을 사람이 읽기 쉬운 문자열로 반환."""
    urgent_state = "enabled" if verdict_severity(verdict) > verdict_severity(last_verdict) else "standby"
    return (
        f"next regular @{next_regular_iter} iter | "
        f"urgent gap {URGENT_VIDEO_GAP_ITER} iter from last clip {last_clip_iter} ({urgent_state})"
    )


# ============================================================
# PID FILE — 자기 자신의 PID 기록 (Heartbeat에서 감시용)
# ============================================================

def write_pid_file():
    """Supervisor PID를 파일에 기록."""
    os.makedirs(os.path.dirname(SUPERVISOR_PID_FILE), exist_ok=True)
    with open(SUPERVISOR_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """Supervisor PID 파일 제거."""
    try:
        os.remove(SUPERVISOR_PID_FILE)
    except OSError:
        pass


# ============================================================
# UTILITY
# ============================================================

def write_log(msg: str):
    """로그를 콘솔과 파일에 동시 기록."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(MONITOR_LOG), exist_ok=True)
        with open(MONITOR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def send_telegram(msg: str):
    """텔레그램 메시지 전송 (UTF-8 명시). TRAIN_VERSION 자동 prefix."""
    if TRAIN_VERSION:
        msg = f"[{TRAIN_VERSION}] {msg}"
    try:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
        }).encode("utf-8")
        req = urllib.request.Request(f"{TG_BASE_URL}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=10)
        preview = msg[:60].replace("\n", " ")
        write_log(f"[TG] Sent: {preview}...")
    except Exception as e:
        write_log(f"[TG] Send failed: {e}")


def send_telegram_video(video_path: str, caption: str = ""):
    """텔레그램 영상 파일 전송 (multipart/form-data, UTF-8)."""
    if not video_path or not os.path.isfile(video_path):
        write_log(f"[TG] Video not found: {video_path} (skip)")
        return
    try:
        file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
        if file_size_mb > 50:
            write_log(f"[TG] Video too large: {file_size_mb:.2f}MB > 50MB limit (skip)")
            send_telegram(f"⚠️ 영상 파일 크기 초과: {file_size_mb:.2f}MB (50MB 제한)")
            return
        write_log(f"[TG] Sending video: {video_path} ({file_size_mb:.2f}MB)...")

        import uuid
        boundary = uuid.uuid4().hex
        filename = os.path.basename(video_path)

        with open(video_path, "rb") as vf:
            video_bytes = vf.read()

        # Build multipart body
        body = b""
        # chat_id
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
        body += f"{TELEGRAM_CHAT_ID}\r\n".encode()
        # caption
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
        body += f"{caption}\r\n".encode("utf-8")
        # video file
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="video"; filename="{filename}"\r\n'.encode()
        body += b"Content-Type: video/mp4\r\n\r\n"
        body += video_bytes
        body += f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{TG_BASE_URL}/sendVideo",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        urllib.request.urlopen(req, timeout=120)
        write_log(f"[TG] Video sent OK: {filename} ({file_size_mb:.2f}MB)")
    except Exception as e:
        write_log(f"[TG] Video send FAILED: {e} (skip)")
        send_telegram(f"⚠️ 영상 전송 실패: {e}")


def flush_telegram_updates():
    """이전 Telegram 메시지를 모두 소진하여 offset 갱신."""
    global _tg_offset
    try:
        url = f"{TG_BASE_URL}/getUpdates?timeout=0"
        resp = json.loads(urllib.request.urlopen(url, timeout=5).read().decode("utf-8"))
        if resp.get("ok") and resp.get("result"):
            _tg_offset = resp["result"][-1]["update_id"] + 1
    except Exception:
        pass


def get_telegram_reply(timeout_sec: int = 600) -> str | None:
    """텔레그램 사용자 응답 대기. timeout_sec 이내 응답 없으면 None."""
    global _tg_offset
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            url = f"{TG_BASE_URL}/getUpdates?offset={_tg_offset}&timeout=10"
            resp = json.loads(urllib.request.urlopen(url, timeout=15).read().decode("utf-8"))
            if resp.get("ok") and resp.get("result"):
                for update in resp["result"]:
                    _tg_offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text")
                    chat_id = msg.get("chat", {}).get("id")
                    if text and str(chat_id) == str(TELEGRAM_CHAT_ID):
                        write_log(f"[TG] Reply received: {text}")
                        return text.strip()
        except Exception:
            time.sleep(5)
        remaining = int(deadline - time.time())
        if remaining > 0 and remaining % 60 < 15:
            write_log(f"[TG] Waiting reply... {remaining}s left")
    write_log(f"[TG] Reply timeout ({timeout_sec}s)")
    return None


def ask_user_decision(situation: str, default: str = "continue") -> str:
    """사용자에게 Telegram으로 의사결정을 요청. timeout 시 default 반환."""
    flush_telegram_updates()
    auto_label = "1 (계속)" if default == "continue" else "2 (중단)"
    question = (
        f"{situation}\n\n"
        f"🤔 어떻게 할까요?\n"
        f"1️⃣ 계속 진행\n"
        f"2️⃣ 훈련 중단\n\n"
        f"⏰ {DECISION_TIMEOUT_SEC}초 내 응답 없으면 자동: {auto_label}\n"
        f"(숫자만 입력: 1 또는 2)"
    )
    send_telegram(question)
    write_log(f"Decision requested (timeout: {DECISION_TIMEOUT_SEC}s, default: {default})")

    reply = get_telegram_reply(timeout_sec=DECISION_TIMEOUT_SEC)
    if reply is None:
        auto_msg = "계속 진행" if default == "continue" else "중단"
        send_telegram(f"🤖 응답 없음 → 자동: {auto_msg}")
        write_log(f"No reply → default: {default}")
        return default

    if re.match(r"^1$|continue|go|yes|ok", reply, re.IGNORECASE):
        send_telegram("✅ 계속 진행합니다.")
        return "continue"
    elif re.match(r"^2$|stop|no|quit", reply, re.IGNORECASE):
        send_telegram("🛑 훈련을 중단합니다.")
        return "stop"
    else:
        def_label = "continue" if default == "continue" else "stop"
        send_telegram(f"❓ '{reply}' → 기본값: {def_label}")
        return default


# ============================================================
# ANALYSIS GRADE PARSING
# ============================================================

def parse_analysis_grade(text: str) -> dict:
    """분석 텍스트에서 종합 등급, 점수, Reward, Iteration, Trend 파싱."""
    result = {
        "Grade": "N/A", "Score": 0, "Reward": 0,
        "Iter": 0, "Trend": "N/A", "GradeLetter": "?"
    }
    if not text:
        return result
    # 종합 등급: X (label) (점수: N/13)
    m = re.search(r"종합\s+등급:\s*(\w)\s+\(([^)]+)\)\s+\(점수:\s*(\d+)/13\)", text)
    if not m:
        # 폴백: 점수만이라도 파싱 (깨진 한글 대응)
        m = re.search(r"(\w)\s+\(([^)]+)\)\s+\([^:]*:\s*(\d+)/13\)", text)
    if m:
        result["GradeLetter"] = m.group(1)
        result["Grade"] = f"{m.group(1)} ({m.group(2)})"
        result["Score"] = int(m.group(3))
    m = re.search(r"Mean Reward:\s*([-\d.]+)", text)
    if m:
        result["Reward"] = float(m.group(1))
    m = re.search(r"Current Iteration:\s*([\d,]+)", text)
    if m:
        result["Iter"] = int(m.group(1).replace(",", ""))
    m = re.search(r"Reward Trend:\s*(.+)", text)
    if m:
        # cp949 깨진 이모지 문자 제거 (예: IMPROVING 뒤의 깨진 📈)
        trend_raw = m.group(1).strip()
        trend_raw = re.sub(r"[^\x20-\x7E가-힣()%+\-.\d]+", "", trend_raw).strip()
        result["Trend"] = trend_raw
    return result


def build_supervisor_kpi_snapshot(run_dir: str) -> dict:
    """Heartbeat와 동일한 KPI 언어로 supervisor용 요약을 생성."""
    result = {
        "iter": 0,
        "reward": 0.0,
        "survival_pct": 0.0,
        "verdict": "⚪ KPI unavailable",
        "reason": "TensorBoard 데이터를 읽지 못함",
        "gait": "N/A",
        "gait_score": 0,
        "stability": "N/A",
        "stability_score": 0,
        "kpi_line": "기립높이 N/A | 전진속도 N/A | 대각커플링 N/A",
        "caption_suffix": "⚪ KPI unavailable",
    }
    try:
        try:
            import training_heartbeat as heartbeat
        except ImportError:
            from scripts import training_heartbeat as heartbeat

        data = heartbeat.read_tfevents(run_dir)
        if not data:
            return result

        reward_vals = data.get("Train/mean_reward", [])
        ep_len_vals = data.get("Train/mean_episode_length", [])
        if not reward_vals:
            return result

        current_iter = int(reward_vals[-1][0])
        current_reward = float(reward_vals[-1][1])
        current_ep_len = float(ep_len_vals[-1][1]) if ep_len_vals else 0.0

        timeout_vals = data.get("Episode_Termination/time_out", [])
        bad_orient_vals = data.get("Episode_Termination/bad_orientation", [])
        timeout = float(timeout_vals[-1][1]) if timeout_vals else 0.0
        bad_orient = float(bad_orient_vals[-1][1]) if bad_orient_vals else 0.0

        max_ep = 10.0 * 50
        if timeout > 0.95 and current_ep_len > 1:
            max_ep = current_ep_len
        elif ep_len_vals:
            recent_max_ep = max(v for _, v in ep_len_vals[-50:])
            if recent_max_ep > max_ep * 0.6:
                max_ep = recent_max_ep
        survival_pct = (current_ep_len / max_ep) * 100 if max_ep > 0 else 0.0

        rewards = {}
        for tag, vals in data.items():
            if tag.startswith("Episode_Reward/") and vals:
                rewards[tag.replace("Episode_Reward/", "")] = float(vals[-1][1])

        gait_grade, gait_score, _gait_details = heartbeat.gait_quality_score(rewards)
        stab_grade, stab_score, _stab_details, stab_valid = heartbeat.motion_stability_score(rewards, gait_score)
        verdict, reasons, _greens, _yellows, _reds = heartbeat.evaluate_training_window(
            current_iter, survival_pct, bad_orient, rewards
        )

        primary_items = []
        for metric_name, label in [
            ("standing_height", "기립"),
            ("forward_velocity", "전진"),
            ("diagonal_coupling", "대각"),
        ]:
            icon, state = heartbeat.classify_primary_kpi(metric_name, rewards.get(metric_name, 0.0))
            primary_items.append(f"{icon}{label} {state}")

        stability_label = f"{stab_grade} {stab_score}/10" if stab_valid else stab_grade
        result.update({
            "iter": current_iter,
            "reward": current_reward,
            "survival_pct": survival_pct,
            "verdict": verdict,
            "reason": reasons[0] if reasons else "",
            "gait": gait_grade,
            "gait_score": gait_score,
            "stability": stab_grade,
            "stability_score": stab_score,
            "kpi_line": " | ".join(primary_items),
            "caption_suffix": f"{verdict} | Gait {gait_grade} {gait_score}/13 | Stability {stability_label}",
        })
    except Exception as e:
        write_log(f"KPI snapshot err: {e}")
    return result


# ============================================================
# RUN / CHECKPOINT DISCOVERY
# ============================================================

def get_latest_run_dir() -> str | None:
    """LOG_BASE 아래 가장 최근 run 디렉터리 경로 반환."""
    if not os.path.isdir(LOG_BASE):
        return None
    dirs = sorted(
        [d for d in os.listdir(LOG_BASE) if os.path.isdir(os.path.join(LOG_BASE, d))],
    )
    return os.path.join(LOG_BASE, dirs[-1]) if dirs else None


def get_latest_checkpoint(run_dir: str) -> str | None:
    """run_dir 아래 model_*.pt 중 가장 높은 iteration 체크포인트 경로 반환."""
    pattern = os.path.join(run_dir, "model_*.pt")
    pts = [f for f in glob.glob(pattern) if re.match(r"model_\d+\.pt$", os.path.basename(f))]
    if not pts:
        return None
    pts.sort(key=lambda f: int(re.search(r"model_(\d+)", os.path.basename(f)).group(1)))
    return pts[-1]


def get_checkpoint_iter(checkpoint_path: str) -> int:
    """체크포인트 파일명에서 iteration 숫자 추출."""
    m = re.search(r"model_(\d+)", os.path.basename(checkpoint_path))
    return int(m.group(1)) if m else 0


def get_curriculum_phase(iteration: int) -> tuple[int, str]:
    """iteration 기반 예상 커리큘럼 Phase 및 이름 반환."""
    if iteration < PHASE1_END_ITER:
        return 1, "STAND"
    elif iteration < PHASE2_END_ITER:
        return 2, "WALK"
    else:
        return 3, "TROT"


# ============================================================
# RESOURCE CLEANUP — Process Management
# ============================================================

def get_heartbeat_pid() -> int:
    """training_heartbeat의 PID를 PID 파일에서 읽어 반환 (보호 대상). 없으면 0."""
    if not os.path.isfile(HEARTBEAT_PID_FILE):
        return 0
    try:
        pid = int(open(HEARTBEAT_PID_FILE, "r").read().strip())
        # PID가 살아있고 python인지 psutil로 확인
        proc = psutil.Process(pid)
        if proc.is_running() and "python" in proc.name().lower():
            return pid
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, OSError):
        pass
    return 0


def _get_python_pids_with_cmdline() -> list:
    """psutil로 모든 python.exe 프로세스의 (pid, cmdline_str) 리스트 반환."""
    result = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "python" in proc.info["name"].lower():
                cmdline = " ".join(proc.info["cmdline"] or [])
                result.append((proc.info["pid"], cmdline))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result


def kill_all_python(reason: str = "cleanup"):
    """heartbeat PID를 보호하면서 모든 python/Kit 프로세스 종료."""
    protected_pid = get_heartbeat_pid()
    my_pid = os.getpid()
    if protected_pid > 0:
        write_log(f"[{reason}] Heartbeat PID {protected_pid} 보호 (kill 제외)")
    write_log(f"[{reason}] Killing python/Kit processes (heartbeat/supervisor 제외)...")

    # Kit 프로세스 무조건 kill
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "kit.exe":
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # python.exe 프로세스 kill (heartbeat + supervisor 자신 제외)
    for pid, _cmdline in _get_python_pids_with_cmdline():
        if pid == protected_pid or pid == my_pid:
            continue
        try:
            psutil.Process(pid).kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(5)

    # 잔존 확인
    remaining = [
        pid for pid, _ in _get_python_pids_with_cmdline()
        if pid != protected_pid and pid != my_pid
    ]
    if remaining:
        write_log(f"[{reason}] {len(remaining)} python remaining → force kill")
        for pid in remaining:
            try:
                psutil.Process(pid).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        time.sleep(5)
        pass

    write_log(f"[{reason}] Process cleanup done.")


def get_gpu_memory_mb() -> int:
    """nvidia-smi로 현재 GPU 메모리 사용량(MB) 조회. 실패 시 0."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return int(result.stdout.strip())
    except Exception:
        return 0


def wait_gpu_free(max_wait_sec: int = 60, threshold_mb: int = 2000) -> bool:
    """GPU 메모리가 threshold_mb 미만이 될 때까지 대기."""
    for elapsed in range(0, max_wait_sec, 5):
        mem_mb = get_gpu_memory_mb()
        if mem_mb == 0:
            write_log("nvidia-smi failed, assuming clean.")
            return True
        if mem_mb < threshold_mb:
            write_log(f"GPU free: {mem_mb}MB (< {threshold_mb}MB). Ready.")
            return True
        write_log(f"GPU: {mem_mb}MB, waiting... ({elapsed}/{max_wait_sec}s)")
        time.sleep(5)
    write_log(f"WARNING: GPU still above {threshold_mb}MB after {max_wait_sec}s.")
    return False


def ensure_gpu_clean(reason: str = "cleanup"):
    """python 프로세스 kill + GPU 메모리 해제 대기."""
    kill_all_python(reason=reason)
    ok = wait_gpu_free(max_wait_sec=60, threshold_mb=2000)
    if not ok:
        write_log(f"[{reason}] Retry kill + wait...")
        kill_all_python(reason=f"{reason}-retry")
        time.sleep(10)
        wait_gpu_free(max_wait_sec=30, threshold_mb=2000)


# ============================================================
# MAINTENANCE FLAG — Heartbeat에게 유지보수 중임을 알림
# ============================================================

def set_maintenance_flag():
    """maintenance.flag 파일 생성 — heartbeat가 유지보수 모드를 인식."""
    os.makedirs(os.path.dirname(MAINTENANCE_FLAG), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MAINTENANCE_FLAG, "w", encoding="utf-8") as f:
        f.write(ts)
    write_log("Maintenance flag SET")


def remove_maintenance_flag():
    """maintenance.flag 파일 제거."""
    try:
        os.remove(MAINTENANCE_FLAG)
    except OSError:
        pass
    write_log("Maintenance flag REMOVED")


# ============================================================
# USER STOP FLAG — 사용자 중단 시 heartbeat 자동재시작 방지
# ============================================================

def set_user_stop_flag():
    """user_stop.flag 생성 — heartbeat가 supervisor를 재시작하지 않도록."""
    os.makedirs(os.path.dirname(USER_STOP_FLAG), exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(USER_STOP_FLAG, "w", encoding="utf-8") as f:
        f.write(ts)
    write_log("User stop flag SET")


def remove_user_stop_flag():
    """user_stop.flag 제거 (supervisor 시작 시 호출)."""
    try:
        os.remove(USER_STOP_FLAG)
    except OSError:
        pass


# ============================================================
# HEARTBEAT WATCHDOG — heartbeat 프로세스 감시 + 재시작
# ============================================================

def test_heartbeat_alive() -> bool:
    """training_heartbeat.py가 살아있는지 확인 (psutil CommandLine 검색)."""
    for _pid, cmdline in _get_python_pids_with_cmdline():
        if "training_heartbeat" in cmdline.lower():
            return True
    return False


def restart_heartbeat():
    """training_heartbeat.py 재시작 후 결과를 텔레그램으로 알림."""
    write_log("Restarting training_heartbeat...")
    # 기존 PID 파일 제거
    try:
        os.remove(HEARTBEAT_PID_FILE)
    except OSError:
        pass

    # 최신 run dir 찾기
    latest_run = get_latest_run_dir()
    run_arg = f'--run_dir "{latest_run}"' if latest_run else ""

    hb_cmd = (
        f'conda activate env_isaaclab && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'python "{HEARTBEAT_SCRIPT}" --iter_step 100 --poll 30 {run_arg}'
    )
    subprocess.Popen(
        ["cmd", "/c", hb_cmd],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    time.sleep(10)

    if test_heartbeat_alive():
        new_pid = 0
        try:
            new_pid = int(open(HEARTBEAT_PID_FILE, "r").read().strip())
        except Exception:
            pass
        write_log(f"Heartbeat restarted OK (PID {new_pid})")
        send_telegram(f"✅ Training Heartbeat 자동 재시작 완료 (PID {new_pid})")
        return True
    else:
        write_log("WARNING: Heartbeat restart FAILED")
        send_telegram("⚠️ Training Heartbeat 재시작 실패! 수동 확인 필요")
        return False


# ============================================================
# VIDEO RECORDING
# ============================================================

def record_video(checkpoint_path: str, run_dir: str, clip_num: int) -> str | None:
    """멀티뷰 영상 녹화: side/front/rear/top_oblique 순차 캡처.

    반환값은 side view 경로(기존 호출부 호환용).
    """
    cp_name = os.path.basename(checkpoint_path)
    iter_num = get_checkpoint_iter(checkpoint_path)
    write_log(f"Recording clip #{clip_num} from: {cp_name}")

    play_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "play.py")
    side_video_path = None
    any_video = False

    for view_name in VIDEO_VIEWS:
        write_log(f"Recording view: {view_name}")
        pre_videos = set(glob.glob(os.path.join(run_dir, "videos", "play", "*.mp4")))

        play_cmd = (
            f'conda activate env_isaaclab && '
            f'cd /d {PROJECT_ROOT} && '
            f'set PYTHONIOENCODING=utf-8 && '
            f'{ISAAC_LAB} -p {play_script} '
            f'--task={TASK} --num_envs={PLAY_ENVS} '
            f'--checkpoint={checkpoint_path} --video --video_length={VIDEO_LENGTH} '
            f'--camera_view={view_name}'
        )
        write_log(f"play_cmd({view_name}): {play_cmd}")
        proc = subprocess.Popen(["cmd", "/c", play_cmd])

        timeout = 480
        elapsed = 0
        while proc.poll() is None and elapsed < timeout:
            time.sleep(10)
            elapsed += 10
            if elapsed % 60 == 0:
                write_log(f"  Recording {view_name}... {elapsed}s")

        if proc.poll() is None:
            write_log(f"WARNING: Play timed out for {view_name} ({timeout}s), killing PID {proc.pid}")
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
            except Exception:
                pass

        ensure_gpu_clean(reason=f"post-recording-{view_name}")

        # 신규 생성 파일 우선 탐색
        post_videos = set(glob.glob(os.path.join(run_dir, "videos", "play", "*.mp4")))
        created = sorted(list(post_videos - pre_videos), key=os.path.getmtime)
        if created:
            latest_video = created[-1]
        else:
            # fallback: 최신 파일
            videos = sorted(list(post_videos), key=os.path.getmtime)
            latest_video = videos[-1] if videos else None

        if not latest_video:
            write_log(f"WARNING: No video file found for view={view_name}")
            continue

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"clip_{clip_num}_iter{iter_num}_{view_name}_{ts}.mp4"
        dest_path = os.path.join(run_dir, "videos", new_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(latest_video, dest_path)
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        write_log(f"Video saved: {new_name} ({size_mb:.1f}MB)")

        # 느린 재생 속도로 재인코딩
        reencoded = reencode_video(dest_path, VIDEO_FPS)
        if reencoded:
            dest_path = reencoded

        any_video = True
        if view_name == "side":
            side_video_path = dest_path

    if any_video:
        if side_video_path:
            return side_video_path
        # side 실패 시 첫 번째 view 파일을 반환하도록 최신 clip 파일 선택
        candidates = sorted(
            glob.glob(os.path.join(run_dir, "videos", f"clip_{clip_num}_iter{iter_num}_*.mp4")),
            key=os.path.getmtime,
        )
        return candidates[0] if candidates else None

    write_log("WARNING: No video file found across all views!")
    return None


def reencode_video(src_path: str, target_fps: int) -> str | None:
    """영상을 target_fps로 재인코딩 (원본 25fps → 15fps = ~0.6배속).
    PyAV H.264, CRF 18, medium preset. 성공 시 원본을 교체하고 경로 반환."""
    if not src_path or not os.path.isfile(src_path):
        return None
    if target_fps <= 0 or target_fps >= 25:
        write_log(f"VideoFps={target_fps}, skip re-encode (원본 25fps 유지)")
        return None

    out_path = re.sub(r"\.mp4$", f"_{target_fps}fps.mp4", src_path)
    write_log(f"Re-encoding video: {target_fps}fps (slowdown {25 / target_fps:.1f}x)...")

    py_code = f"""
import av, sys
from fractions import Fraction

src = r'{src_path}'
dst = r'{out_path}'
TARGET_FPS = {target_fps}

inp = av.open(src)
in_stream = inp.streams.video[0]

out = av.open(dst, mode='w')
out_stream = out.add_stream('h264', rate=TARGET_FPS)
out_stream.width = in_stream.width
out_stream.height = in_stream.height
out_stream.pix_fmt = 'yuv420p'
out_stream.time_base = Fraction(1, TARGET_FPS)
out_stream.options = {{'crf': '18', 'preset': 'medium'}}

count = 0
for frame in inp.decode(video=0):
    new_frame = frame.reformat(format='yuv420p')
    new_frame.pts = count
    new_frame.time_base = Fraction(1, TARGET_FPS)
    for packet in out_stream.encode(new_frame):
        out.mux(packet)
    count += 1

for packet in out_stream.encode():
    out.mux(packet)

out.close()
inp.close()
print(f'OK: {{count}} frames @ {{TARGET_FPS}}fps H.264 -> {{dst}}')
"""
    tmp_py = os.path.join(PROJECT_ROOT, "logs", "_reencode_tmp.py")
    try:
        with open(tmp_py, "w", encoding="utf-8") as f:
            f.write(py_code)

        reencode_cmd = f'conda activate env_isaaclab && set PYTHONIOENCODING=utf-8 && python "{tmp_py}"'
        proc = subprocess.run(
            ["cmd", "/c", reencode_cmd],
            capture_output=True, timeout=300,
        )
        try:
            os.remove(tmp_py)
        except OSError:
            pass

        if os.path.isfile(out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            write_log(f"Re-encoded OK: {os.path.basename(out_path)} ({size_mb:.1f}MB, {target_fps}fps)")
            # 원본 제거, 재인코딩본을 원본 이름으로 교체
            try:
                os.remove(src_path)
            except OSError:
                pass
            shutil.move(out_path, src_path)
            return src_path
        else:
            write_log("Re-encode failed: output not created")
            return None
    except Exception as e:
        write_log(f"Re-encode error: {e} (using original)")
        try:
            os.remove(tmp_py)
        except OSError:
            pass
        return None


# ============================================================
# ANALYSIS — conda activate + isaaclab.bat -p + 타임아웃 120s
# ============================================================

def write_basic_analysis(run_dir: str, iter_num: int):
    """분석 스크립트가 없을 때 기본 정보만 기록."""
    events = glob.glob(os.path.join(run_dir, "events*"))
    ev_kb = round(os.path.getsize(events[0]) / 1024) if events else 0
    cp_count = len(glob.glob(os.path.join(run_dir, "model_*.pt")))
    info = f"[Basic] Events: {ev_kb}KB | Checkpoints: {cp_count} | Iter: ~{iter_num}"
    write_log(info)


def run_detailed_analysis(run_dir: str, checkpoint_path: str, clip_num: int, video_path: str | None):
    """상세 분석 실행: analyze_training.py → stdout 캡처 → _last_analysis_text에 저장."""
    global _last_analysis_text
    iter_num = get_checkpoint_iter(checkpoint_path)
    write_log(f"Running analysis (iter {iter_num})...")

    header = (
        f"\n{'#' * 80}\n"
        f"#  CLIP #{clip_num} — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  model_{iter_num}.pt | {os.path.basename(run_dir)}\n"
        f"#  Video: {os.path.basename(video_path) if video_path else 'N/A'}\n"
        f"{'#' * 80}\n"
    )
    try:
        with open(MONITOR_LOG, "a", encoding="utf-8") as f:
            f.write(header)
    except Exception:
        pass

    if not os.path.isfile(ANALYZE_SCRIPT):
        write_log("analyze_training.py not found → basic analysis")
        write_basic_analysis(run_dir, iter_num)
        return

    analysis_cmd = (
        f'conda activate env_isaaclab && '
        f'cd /d {PROJECT_ROOT} && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'{ISAAC_LAB} -p {ANALYZE_SCRIPT} '
        f'--run_dir {run_dir} --clip_num {clip_num}'
    )
    write_log(f"analysis_cmd: {analysis_cmd}")

    try:
        proc = subprocess.Popen(
            ["cmd", "/c", analysis_cmd],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            write_log(f"WARNING: Analysis timed out (120s), killing PID {proc.pid}")
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
            except Exception:
                pass
            stdout_bytes, stderr_bytes = proc.communicate(timeout=5)

        text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        if text:
            print(text)
            try:
                with open(MONITOR_LOG, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except Exception:
                pass
            _last_analysis_text = text
        else:
            _last_analysis_text = ""

        err_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        if err_text.strip():
            write_log(f"Analysis stderr: {err_text[:500]}")

    except Exception as e:
        write_log(f"Analysis error: {e}")
        _last_analysis_text = ""

    write_log("Analysis complete.")

    # 분석용 python 잔존 시 정리
    time.sleep(2)
    my_pid = os.getpid()
    hb_pid = get_heartbeat_pid()
    for pid, cmdline in _get_python_pids_with_cmdline():
        if "analyze_training" in cmdline.lower():
            if pid != my_pid and pid != hb_pid:
                try:
                    psutil.Process(pid).kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    time.sleep(3)


# ============================================================
# TRAINING RESUME
# ============================================================

def resume_training(run_dir: str, checkpoint_path: str, next_regular_iter: int | None = None):
    """훈련을 재개: train.py 실행 → 프로세스 감지 확인."""
    run_name = os.path.basename(run_dir)
    cp_name = os.path.basename(checkpoint_path)
    iter_num = get_checkpoint_iter(checkpoint_path)

    write_log("Pre-resume cleanup...")
    ensure_gpu_clean(reason="pre-resume")

    phase_num, phase_name = get_curriculum_phase(iter_num)
    write_log(f"Resuming: {run_name} / {cp_name} (iter {iter_num}, Phase {phase_num}/{phase_name})")
    write_log(f"  common_step_counter will sync to iter {iter_num} × steps_per_env")
    train_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "train.py")
    train_cmd = (
        f'conda activate env_isaaclab && '
        f'cd /d {PROJECT_ROOT} && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'{ISAAC_LAB} -p {train_script} '
        f'--task={TASK} --num_envs={TRAIN_ENVS} --headless '
        f'--max_iterations={MAX_ITERATIONS} '
        f'--resume --load_run={run_name} --checkpoint={cp_name}'
    )
    write_log(f"train_cmd: {train_cmd}")
    subprocess.Popen(
        ["cmd", "/c", train_cmd],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    write_log("Waiting for init (60s)...")
    time.sleep(60)

    # python 프로세스 확인 (psutil)
    try:
        pids = []
        total_mem = 0
        my_pid = os.getpid()
        hb_pid = get_heartbeat_pid()
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                if proc.info["name"] and "python" in proc.info["name"].lower():
                    pid = proc.info["pid"]
                    if pid != my_pid and pid != hb_pid:
                        pids.append(pid)
                        mi = proc.info.get("memory_info")
                        if mi:
                            total_mem += mi.rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        mem_mb = round(total_mem / (1024 * 1024))
        if pids:
            write_log(f"Training running: PID={','.join(map(str, pids))}, Mem={mem_mb}MB")
        else:
            write_log("WARNING: Training process not detected!")
            send_telegram("⚠️ 훈련 프로세스 감지 실패! 확인 필요")
    except Exception:
        pass

    time.sleep(30)
    gpu_mem = get_gpu_memory_mb()
    if gpu_mem > 0:
        write_log(f"GPU after resume: {gpu_mem}MB")

    if next_regular_iter is not None:
        write_log(f"Next regular clip target: iter {next_regular_iter}")
    else:
        write_log(f"Supervisor poll active: every {SUPERVISOR_POLL_SECONDS}s")


# ============================================================
# MAIN LOOP — Phase별 try-except + 비상 훈련 재개
# ============================================================

def main():
    global _last_analysis_text, _prev_score, _heartbeat_alert_sent

    parser = argparse.ArgumentParser(description="Training Supervisor (Python)")
    parser.add_argument("--interval", type=int, default=0, help="Legacy override for INTERVAL_MINUTES (startup note only)")
    parser.add_argument("--video_length", type=int, default=0, help="Override VIDEO_LENGTH")
    parser.add_argument("--train_envs", type=int, default=0, help="Override TRAIN_ENVS")
    parser.add_argument("--play_envs", type=int, default=0, help="Override PLAY_ENVS")
    parser.add_argument("--max_iterations", type=int, default=0, help="Override MAX_ITERATIONS")
    args = parser.parse_args()

    # CLI override
    global INTERVAL_MINUTES, VIDEO_LENGTH, TRAIN_ENVS, PLAY_ENVS, MAX_ITERATIONS
    if args.interval > 0:
        INTERVAL_MINUTES = args.interval
    if args.video_length > 0:
        VIDEO_LENGTH = args.video_length
    if args.train_envs > 0:
        TRAIN_ENVS = args.train_envs
    if args.play_envs > 0:
        PLAY_ENVS = args.play_envs
    if args.max_iterations > 0:
        MAX_ITERATIONS = args.max_iterations

    # PID 기록
    write_pid_file()

    # 이전 user_stop.flag 제거 (재시작 시 정상 동작 보장)
    remove_user_stop_flag()

    write_log("=========================================")
    write_log("V17.1 Training Supervisor (Python, Telegram Interactive)")
    write_log("Phase에러격리 | GPU메모리기준 | 분석타임아웃")
    write_log(
        "Cadence: "
        f"{VIDEO_INTERVAL_EARLY_ITER} iter (<{VIDEO_INTERVAL_EARLY_END}), "
        f"{VIDEO_INTERVAL_MID_ITER} iter (<{VIDEO_INTERVAL_MID_END}), "
        f"{VIDEO_INTERVAL_LATE_ITER} iter (late)"
    )
    write_log(f"Poll: {SUPERVISOR_POLL_SECONDS}s | Video: {VIDEO_LENGTH}steps")
    write_log(f"Train: {TRAIN_ENVS} envs | Play: {PLAY_ENVS} envs")
    write_log("=========================================")

    flush_telegram_updates()
    send_telegram(
        f"🤖 SpotMicro Training Supervisor 시작\n\n"
        f"⚙️ 설정\n"
        f"├ Poll: {SUPERVISOR_POLL_SECONDS}초\n"
        f"├ Clip cadence: {VIDEO_INTERVAL_EARLY_ITER}/{VIDEO_INTERVAL_MID_ITER}/{VIDEO_INTERVAL_LATE_ITER} iter\n"
        f"├ Envs: {TRAIN_ENVS}\n"
        f"├ Video: {VIDEO_LENGTH}steps\n"
        f"├ Max: {MAX_ITERATIONS} iter\n"
        f"└ 의사결정 타임아웃: {DECISION_TIMEOUT_SEC}초\n\n"
        f"📢 등급 D/F 시 텔레그램으로 물어봅니다\n"
        f"10분 무응답 → 자동 계속"
    )

    clip_num = 0
    last_clip_iter = 0
    last_verdict = "🟢 계속 진행"
    next_regular_iter = VIDEO_INTERVAL_EARLY_ITER
    last_observed_checkpoint = ""

    try:
        while True:
            try:
                time.sleep(SUPERVISOR_POLL_SECONDS)

                # Heartbeat 워치독
                if not test_heartbeat_alive():
                    if not _heartbeat_alert_sent:
                        write_log("WARNING: Heartbeat not alive! Restarting...")
                        send_telegram("⚠️ Training Heartbeat 감지 불가! 자동 재시작 시도 중...")
                        restart_heartbeat()
                        _heartbeat_alert_sent = True
                else:
                    if _heartbeat_alert_sent:
                        write_log("Heartbeat recovered.")
                        _heartbeat_alert_sent = False

                run_dir = get_latest_run_dir()
                if not run_dir:
                    continue
                checkpoint = get_latest_checkpoint(run_dir)
                if not checkpoint:
                    continue

                iter_num = get_checkpoint_iter(checkpoint)
                kpi_snapshot = build_supervisor_kpi_snapshot(run_dir)
                if not last_observed_checkpoint:
                    last_observed_checkpoint = checkpoint
                    last_verdict = kpi_snapshot["verdict"]
                    next_regular_iter = get_next_regular_trigger(iter_num)
                    last_clip_iter = max(0, iter_num - get_regular_video_interval(iter_num))
                    write_log(
                        f"Supervisor armed at iter {iter_num} | "
                        f"{format_trigger_status(next_regular_iter, last_clip_iter, kpi_snapshot['verdict'], last_verdict)}"
                    )

                if iter_num >= MAX_ITERATIONS - 100:
                    trigger_clip, trigger_reason = True, "final"
                else:
                    trigger_clip, trigger_reason = should_capture_clip(
                        iter_num, last_clip_iter, next_regular_iter, kpi_snapshot["verdict"], last_verdict
                    )

                checkpoint_changed = checkpoint != last_observed_checkpoint
                if checkpoint_changed:
                    write_log(
                        f"Observed checkpoint: {os.path.basename(run_dir)} / {os.path.basename(checkpoint)} "
                        f"(iter {iter_num}) | verdict={kpi_snapshot['verdict']} | "
                        f"{format_trigger_status(next_regular_iter, last_clip_iter, kpi_snapshot['verdict'], last_verdict)}"
                    )
                    last_observed_checkpoint = checkpoint

                if not trigger_clip:
                    last_verdict = kpi_snapshot["verdict"]
                    continue

                clip_num += 1
                write_log("")
                write_log(f"########## CLIP #{clip_num} ##########")
                write_log(f"Trigger: {trigger_reason}")

                video_path = None
                progress_pct = round((iter_num / MAX_ITERATIONS) * 100, 1)
                send_telegram(
                    f"🎬 Clip #{clip_num} 시작\n"
                    f"├ 📍 Iter: {iter_num} / {MAX_ITERATIONS} ({progress_pct}%)\n"
                    f"├ Trigger: {trigger_reason}\n"
                    f"└ 📂 {os.path.basename(run_dir)} / {os.path.basename(checkpoint)}"
                )

                # 훈련 완료 체크
                if iter_num >= MAX_ITERATIONS - 100:
                    write_log(f"===== TRAINING COMPLETE (iter {iter_num}) =====")
                    send_telegram(f"🏆 훈련 완료! (iter {iter_num}/{MAX_ITERATIONS})\n최종 분석 진행합니다...")
                    try:
                        ensure_gpu_clean(reason="complete")
                    except Exception:
                        pass
                    try:
                        video_path = record_video(checkpoint, run_dir, clip_num)
                        if video_path and os.path.isfile(video_path):
                            send_telegram_video(
                                video_path,
                                f"🏆 최종 영상 | Iter {iter_num} / {MAX_ITERATIONS} | {kpi_snapshot['caption_suffix']}"
                            )
                    except Exception as e:
                        write_log(f"Video err: {e}")
                    _last_analysis_text = ""
                    try:
                        run_detailed_analysis(run_dir, checkpoint, clip_num, video_path)
                    except Exception as e:
                        write_log(f"Analysis err: {e}")
                    try:
                        ensure_gpu_clean(reason="final")
                    except Exception:
                        pass
                    try:
                        grade = parse_analysis_grade(_last_analysis_text)
                        send_telegram(
                            f"🏆 최종 결과\n\n"
                            f"📊 등급: {grade['Grade']}\n"
                            f"🎯 점수: {grade['Score']}/13\n"
                            f"💰 Reward: {grade['Reward']}\n"
                            f"📈 Trend: {grade['Trend']}\n"
                            f"🚦 운영 판정: {kpi_snapshot['verdict']}\n"
                            f"🧭 KPI: {kpi_snapshot['kpi_line']}\n"
                            f"🦿 Gait: {kpi_snapshot['gait']} ({kpi_snapshot['gait_score']}/13)\n"
                            f"🛡 Stability: {kpi_snapshot['stability']} ({kpi_snapshot['stability_score']}/10)\n\n"
                            f"✅ 모니터 종료"
                        )
                    except Exception:
                        send_telegram("✅ 훈련 완료. 모니터 종료.")
                    write_log("===== MONITOR FINISHED =====")
                    break

                last_clip_iter = iter_num
                next_regular_iter = get_next_regular_trigger(iter_num)

                # ── Maintenance Flag ON ──
                set_maintenance_flag()

                # Phase 1: 훈련 중단 + GPU 해제
                write_log("--- Phase 1/5: Stop Training ---")
                send_telegram("⏸️ P1/5: 훈련 중단 + GPU 해제")
                try:
                    ensure_gpu_clean(reason="stop-training")
                except Exception as e:
                    write_log(f"P1 err: {e} (fallback)")
                    kill_all_python(reason="p1-fb")
                    time.sleep(10)

                # Phase 2: 영상 녹화
                write_log("--- Phase 2/5: Record Video ---")
                send_telegram(f"🎥 P2/5: 영상 녹화 중... ({VIDEO_LENGTH} steps)")
                try:
                    video_path = record_video(checkpoint, run_dir, clip_num)
                    if video_path and os.path.isfile(video_path):
                        send_telegram_video(
                            video_path,
                            f"🎬 Clip #{clip_num} | Iter {iter_num} / {MAX_ITERATIONS} ({progress_pct}%) | {kpi_snapshot['caption_suffix']}"
                        )
                except Exception as e:
                    write_log(f"P2 err: {e} (skip)")
                    kill_all_python(reason="p2-fb")
                    wait_gpu_free(max_wait_sec=30)

                # Phase 3: 상세 분석
                write_log("--- Phase 3/5: Analysis ---")
                send_telegram("🔬 P3/5: 분석 중...")
                _last_analysis_text = ""
                try:
                    run_detailed_analysis(run_dir, checkpoint, clip_num, video_path)
                except Exception as e:
                    write_log(f"P3 err: {e} (skip)")

                # Telegram 보고 + 의사결정
                write_log("--- Telegram Report & Decision ---")
                try:
                    grade = parse_analysis_grade(_last_analysis_text)
                    grade_iter = grade["Iter"]
                    p_pct = round((grade_iter / MAX_ITERATIONS) * 100, 1) if grade_iter > 0 else "?"

                    grade_icons = {"A": "🌟", "B": "⭐", "C": "🟡", "D": "🟠", "F": "🔴"}
                    grade_icon = grade_icons.get(grade["GradeLetter"], "❓")

                    if re.search(r"↗|상승|\+", grade["Trend"]):
                        trend_icon = "📈"
                    elif re.search(r"↘|하락|-", grade["Trend"]):
                        trend_icon = "📉"
                    else:
                        trend_icon = "➖"

                    summary_msg = (
                        f"📊 Clip #{clip_num} 분석완료\n\n"
                        f"📍 Iter: {grade_iter} / {MAX_ITERATIONS} ({p_pct}%)\n"
                        f"💰 Reward: {grade['Reward']}\n"
                        f"{trend_icon} Trend: {grade['Trend']}\n"
                        f"{grade_icon} 등급: {grade['Grade']} ({grade['Score']}/13점)\n"
                        f"🚦 운영 판정: {kpi_snapshot['verdict']}\n"
                        f"🧭 KPI: {kpi_snapshot['kpi_line']}\n"
                        f"🦿 Gait: {kpi_snapshot['gait']} ({kpi_snapshot['gait_score']}/13)\n"
                        f"🛡 Stability: {kpi_snapshot['stability']} ({kpi_snapshot['stability_score']}/10)\n"
                        f"📝 핵심: {kpi_snapshot['reason']}"
                    )

                    # 등급 D/F → 사용자에게 결정 요청
                    if grade["GradeLetter"] in ("D", "F") and grade_iter > 500:
                        decision = ask_user_decision(
                            situation=f"⚠️ {summary_msg}\n\n🔴 등급 {grade['GradeLetter']} — 훈련 상태 좋지 않습니다."
                        )
                        if decision == "stop":
                            write_log("User requested STOP.")
                            send_telegram("🛑 사용자 요청으로 훈련 중단.")
                            ensure_gpu_clean(reason="user-stop")
                            set_user_stop_flag()
                            break

                    # 점수 하락 + 낮은 점수 → 사용자에게 결정 요청
                    elif _prev_score >= 0 and grade["Score"] < _prev_score and grade["Score"] < 4:
                        decision = ask_user_decision(
                            situation=f"⚠️ {summary_msg}\n\n📉 점수 하락 ({_prev_score} → {grade['Score']})"
                        )
                        if decision == "stop":
                            write_log("User requested STOP (score drop).")
                            send_telegram("🛑 사용자 요청으로 훈련 중단 (점수하락).")
                            ensure_gpu_clean(reason="user-stop")
                            set_user_stop_flag()
                            break

                    # 정상 → 알림만
                    else:
                        send_telegram(f"✅ {summary_msg}")

                    _prev_score = grade["Score"]
                except Exception as e:
                    write_log(f"Telegram report err: {e} (skip)")

                # Phase 4: 최종 정리
                write_log("--- Phase 4/5: Cleanup ---")
                send_telegram("🧹 P4/5: GPU 정리 중...")
                try:
                    ensure_gpu_clean(reason="pre-resume")
                except Exception as e:
                    write_log(f"P4 err: {e}")
                    kill_all_python(reason="p4-fb")
                    time.sleep(15)

                time.sleep(5)

                # Phase 5: 훈련 재개 (반드시 실행)
                write_log("--- Phase 5/5: Resume Training ---")
                phase_num, phase_name = get_curriculum_phase(iter_num)
                send_telegram(
                    f"▶️ P5/5: 훈련 재개 중... (iter {iter_num}~)\n"
                    f"📋 Curriculum Phase {phase_num} ({phase_name})\n"
                    f"다음 정기 clip 목표: iter {next_regular_iter}"
                )
                resume_training(run_dir, checkpoint, next_regular_iter=next_regular_iter)
                last_verdict = kpi_snapshot["verdict"]

                # ── Maintenance Flag OFF ──
                remove_maintenance_flag()

            except Exception as e:
                # 메인 루프 예외 → 비상 훈련 재개
                write_log(f"CRITICAL: {e}")
                write_log(traceback.format_exc())
                send_telegram(f"🚨 CRITICAL ERROR\n{e}\n\n비상 훈련 재개 시도 중...")
                write_log("Emergency resume...")
                try:
                    set_maintenance_flag()
                    kill_all_python(reason="emergency")
                    time.sleep(15)
                    er = run_dir if run_dir else get_latest_run_dir()
                    ec = checkpoint if checkpoint else (get_latest_checkpoint(er) if er else None)
                    if er and ec:
                        resume_training(er, ec)
                    else:
                        write_log("FATAL: Cannot find run/checkpoint for emergency resume!")
                    remove_maintenance_flag()
                except Exception as e2:
                    write_log(f"FATAL: Emergency resume failed: {e2}")
                    remove_maintenance_flag()

            write_log(f"########## CLIP #{clip_num} DONE ##########")
            write_log("")

    finally:
        remove_pid_file()

    send_telegram("👋 모니터 종료. 수고하셨습니다!")
    write_log("Monitor exiting.")


if __name__ == "__main__":
    main()
