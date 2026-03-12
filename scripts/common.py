import contextlib
import datetime
import glob
import hashlib
import html
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
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

import psutil

if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
HEARTBEAT_HISTORY_JSONL = "heartbeat_reports.jsonl"
V23_TRAIN_VERSION = "V23"
V23_MASTER_LOG_FILENAME = "spotmicro_v23_training_master_log.xlsx"
V23_CHECKPOINT_REVIEW_FILENAME = "spotmicro_v23_checkpoint_review.xlsx"


def _load_env(path: str) -> dict:
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip().lstrip("\ufeff")] = value.strip()
    return env


def _parse_env_flag(raw_value, default: bool = False) -> bool:
    if raw_value is None:
        return default
    value = str(raw_value).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


_env = _load_env(ENV_FILE)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or _env.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _env.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ALLOWED_USER_IDS_RAW = os.environ.get("TELEGRAM_ALLOWED_USER_IDS") or _env.get("TELEGRAM_ALLOWED_USER_IDS", "")
TELEGRAM_VERBOSE_ERRORS = _parse_env_flag(
    os.environ.get("TELEGRAM_VERBOSE_ERRORS", _env.get("TELEGRAM_VERBOSE_ERRORS")),
    default=False,
)
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not found in .env or environment")
    sys.exit(1)

TG_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TASK = _env.get("TASK", "Isaac-Velocity-Flat-SpotMicro-v0")
LOG_SUBDIR = _env.get("LOG_SUBDIR", "spot_micro_flat")
ISAAC_LAB = _env.get("ISAAC_LAB_PATH", r"C:\IsaacLab\isaaclab.bat")
CONDA_ENV_NAME = _env.get("CONDA_ENV_NAME") or os.environ.get("CONDA_DEFAULT_ENV", "env_isaaclab")
TRAIN_ENVS = int(_env.get("TRAIN_ENVS", "24576"))
PLAY_ENVS = int(_env.get("PLAY_ENVS", "50"))
MAX_ITERATIONS = int(_env.get("MAX_ITERATIONS", "15000"))
VIDEO_LENGTH = int(_env.get("VIDEO_LENGTH", "250"))
VIDEO_FPS = int(_env.get("VIDEO_FPS", "15"))
VIDEO_CAPTURE_HEADLESS = _parse_env_flag(
    os.environ.get("VIDEO_CAPTURE_HEADLESS", _env.get("VIDEO_CAPTURE_HEADLESS")),
    default=True,
)
VIDEO_CAPTURE_FALLBACK_GUI = _parse_env_flag(
    os.environ.get("VIDEO_CAPTURE_FALLBACK_GUI", _env.get("VIDEO_CAPTURE_FALLBACK_GUI")),
    default=True,
)
VIDEO_REQUIRE_DISTINCT_VIEWS = _parse_env_flag(
    os.environ.get("VIDEO_REQUIRE_DISTINCT_VIEWS", _env.get("VIDEO_REQUIRE_DISTINCT_VIEWS")),
    default=True,
)
REPORT_REQUIRE_XLSX = _parse_env_flag(
    os.environ.get("REPORT_REQUIRE_XLSX", _env.get("REPORT_REQUIRE_XLSX")),
    default=True,
)
SUPERVISOR_POLL_SECONDS = int(_env.get("SUPERVISOR_POLL_SECONDS", "10"))
HEARTBEAT_POLL_SECONDS = int(_env.get("HEARTBEAT_POLL_SECONDS", _env.get("V2_HEARTBEAT_POLL_SECONDS", "30")))
HEARTBEAT_ITER_STEP = int(_env.get("HEARTBEAT_ITER_STEP", _env.get("V2_HEARTBEAT_ITER_STEP", "100")))
ZIP_FRAME_COUNT = int(_env.get("ZIP_FRAME_COUNT", "12"))
CACHE_SCHEMA_VERSION = 3

LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", LOG_SUBDIR)
STATE_FILE = os.path.join(PROJECT_ROOT, "logs", "state.json")
SUPERVISOR_LOG = os.path.join(PROJECT_ROOT, "logs", "supervisor.log")
HEARTBEAT_LOG = os.path.join(PROJECT_ROOT, "logs", "heartbeat.log")
SUPERVISOR_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "supervisor.pid")
HEARTBEAT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "heartbeat.pid")
SUPERVISOR_SHUTDOWN_FLAG = os.path.join(PROJECT_ROOT, "logs", "supervisor.shutdown.flag")
BUSY_LOCK_FILE = os.path.join(PROJECT_ROOT, "logs", "ops.lock")
TRAINING_LOG = os.path.join(PROJECT_ROOT, "logs", "training_launch.log")
ANALYZE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "utils", "analyze_training.py")
TG_OFFSET_FILE = os.path.join(PROJECT_ROOT, "logs", "telegram_offset.json")
HEARTBEAT_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "heartbeat.py")
SUPERVISOR_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "supervisor.py")

TELEGRAM_ALLOWED_USER_IDS = frozenset(
    token.strip()
    for token in re.split(r"[\s,]+", TELEGRAM_ALLOWED_USER_IDS_RAW)
    if token.strip()
)

PRIMARY_KPI_THRESHOLDS = {
    "standing_height": (0.08, 0.16),
    "forward_velocity": (0.15, 0.45),
    "diagonal_coupling": (0.30, 1.00),
    "trot_gait": (0.10, 0.40),
    "rear_joint_velocity": (2.0, 8.0),
    "foot_clearance": (0.20, 0.80),
}

V23_RUNLOG_COLUMNS = [
    "run_id", "train_version", "iter", "global_step", "timestamp", "elapsed_hours", "report_kind", "cycle_num", "log_source", "fallback_source",
    "mean_reward", "mean_reward_avg10", "mean_episode_length", "survival_pct", "timeout_pct", "fall_pct", "vf_loss", "surrogate_loss", "noise_std", "vel_err_xy", "vel_err_yaw",
    "survival_pct_derived", "gait_score_estimated", "stability_score_estimated",
    "forward_velocity_raw", "trot_gait_raw", "diagonal_coupling_raw", "leg_lift_raw", "foot_clearance_raw", "standing_height_raw",
    "forward_velocity_reward", "trot_gait_reward", "diagonal_coupling_reward", "leg_lift_reward", "foot_clearance_reward", "standing_height_reward",
    "stance_width_mean_raw", "stance_width_front_raw", "stance_width_rear_raw", "front_rear_stance_width_diff_raw", "shoulder_fl_raw", "shoulder_fr_raw", "shoulder_rl_raw", "shoulder_rr_raw", "shoulder_mean_abs_dev_from_target_raw", "shoulder_left_right_diff_raw", "shoulder_front_rear_diff_raw", "base_height_raw", "body_roll_abs_raw", "body_pitch_abs_raw",
    "action_rate_l2_raw", "joint_vel_l2_raw", "dof_acc_l2_raw", "joint_oscillation_raw", "foot_extension_raw", "foot_joint_action_rate_l2_raw", "foot_joint_vel_l2_raw", "stance_foot_jitter_score_raw", "foot_joint_acc_l2_raw", "contact_transition_oscillation_score_estimated",
    "front_leg_lift_mean_raw", "rear_leg_lift_mean_raw", "front_clearance_mean_raw", "rear_clearance_mean_raw", "front_propulsion_score_raw", "rear_propulsion_score_raw", "front_rear_propulsion_diff_raw", "front_rear_clearance_diff_raw", "front_rear_swing_diff_raw",
    "stride_length_raw", "gait_cycle_period_raw", "duty_factor_mean_raw", "duty_factor_front_raw", "duty_factor_rear_raw", "contact_sequence_stability_estimated", "stance_time_mean_estimated", "swing_time_mean_estimated",
    "gait_score_canonical", "stability_score_canonical", "posture_style_score", "foot_jitter_score", "front_rear_balance_score",
    "hard_safety_gate_pass", "style_shortlist_candidate", "best_reward_candidate", "best_style_candidate", "manual_front_review_rank", "manual_notes",
]

_tg_offset: int | None = None
_tg_poll_conflict_logged = False


def _normalize_windows_path(raw_path: str | None) -> str | None:
    if raw_path is None:
        return None
    candidate = str(raw_path).strip()
    if not candidate:
        return None
    candidate = candidate.replace('\\"', '"').replace("\\'", "'").strip()
    if (candidate.startswith('"') and candidate.endswith('"')) or (candidate.startswith("'") and candidate.endswith("'")):
        candidate = candidate[1:-1].strip()
    return os.path.abspath(candidate) if candidate else None


def _resolve_conda_activate_bat() -> str | None:
    conda_exe = os.environ.get("CONDA_EXE", "")
    conda_dir = os.path.dirname(conda_exe) if conda_exe else ""
    conda_root = os.path.dirname(conda_dir) if conda_dir else ""
    candidates = [
        _env.get("CONDA_ACTIVATE_BAT"),
        os.path.join(conda_dir, "activate.bat") if conda_dir else None,
        os.path.join(conda_root, "condabin", "activate.bat") if conda_root else None,
        os.path.join(conda_root, "condabin", "conda.bat") if conda_root else None,
    ]
    for raw_candidate in candidates:
        candidate = _normalize_windows_path(raw_candidate)
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


CONDA_ACTIVATE_BAT = _resolve_conda_activate_bat()


def _ensure_logs_dir() -> None:
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def write_log(message: str, log_path: str) -> None:
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
    print(line)
    _ensure_logs_dir()
    with open(log_path, "a", encoding="utf-8") as file:
        file.write(line + "\n")


def _read_text_tail(path: str, max_chars: int = 1200) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as file:
            text = file.read()
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text.strip()
    return text[-max_chars:].strip()


def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def write_json(path: str, data: dict) -> None:
    _ensure_logs_dir()
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def load_telegram_offset() -> int:
    payload = read_json(TG_OFFSET_FILE, {})
    if not isinstance(payload, dict):
        return 0
    try:
        return max(0, int(payload.get("offset", 0)))
    except (TypeError, ValueError):
        return 0


def save_telegram_offset(offset: int) -> None:
    write_json(TG_OFFSET_FILE, {"offset": max(0, int(offset))})


def default_state() -> dict:
    return {
        "updated_at": _now(),
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "mode": "idle",
        "active_run": "",
        "active_checkpoint": "",
        "last_command": "",
        "last_error": "",
        "last_report_zip": "",
        "last_report_checkpoint": "",
        "last_videos": {},
        "last_video_checkpoint": "",
    }


def load_state() -> dict:
    state = read_json(STATE_FILE, default_state())
    if not isinstance(state, dict):
        return default_state()
    merged = default_state()
    merged.update(state)
    return merged


def save_state(state: dict) -> dict:
    state = dict(state)
    state["updated_at"] = _now()
    state["cache_schema_version"] = CACHE_SCHEMA_VERSION
    write_json(STATE_FILE, state)
    return state


def update_state(**changes) -> dict:
    state = load_state()
    state.update(changes)
    return save_state(state)


def request_supervisor_shutdown(source: str) -> None:
    _ensure_logs_dir()
    with open(SUPERVISOR_SHUTDOWN_FLAG, "w", encoding="utf-8") as file:
        file.write(f"{source}\n{_now()}\n")


def clear_supervisor_shutdown_request() -> None:
    try:
        os.remove(SUPERVISOR_SHUTDOWN_FLAG)
    except OSError:
        pass


def consume_supervisor_shutdown_request() -> str:
    if not os.path.isfile(SUPERVISOR_SHUTDOWN_FLAG):
        return ""
    try:
        with open(SUPERVISOR_SHUTDOWN_FLAG, "r", encoding="utf-8", errors="replace") as file:
            source = file.readline().strip()
    except Exception:
        source = ""
    clear_supervisor_shutdown_request()
    return source or "external-request"


def acquire_pid_lock(pid_file: str, owner_name: str, log_path: str) -> None:
    _ensure_logs_dir()
    old_pid = 0
    try:
        if os.path.isfile(pid_file):
            with open(pid_file, "r", encoding="utf-8") as file:
                old_pid = int(file.read().strip())
    except Exception:
        old_pid = 0
    if old_pid and psutil.pid_exists(old_pid):
        raise RuntimeError(f"{owner_name} already running (PID {old_pid})")
    with open(pid_file, "w", encoding="utf-8") as file:
        file.write(str(os.getpid()))
    write_log(f"{owner_name} lock acquired (PID {os.getpid()})", log_path)


def release_pid_lock(pid_file: str) -> None:
    try:
        os.remove(pid_file)
    except OSError:
        pass


def _read_live_pid_lock(pid_file: str) -> int:
    try:
        with open(pid_file, "r", encoding="utf-8") as file:
            pid = int(file.read().strip())
    except Exception:
        return 0
    if pid > 0 and psutil.pid_exists(pid):
        return pid
    release_pid_lock(pid_file)
    return 0


@contextlib.contextmanager
def busy_lock(label: str):
    _ensure_logs_dir()
    try:
        fd = os.open(BUSY_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Another operation is already running.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(f"{label}\n{os.getpid()}\n{_now()}\n")
        yield
    finally:
        try:
            os.remove(BUSY_LOCK_FILE)
        except OSError:
            pass


def send_text(text: str, log_path: str, parse_mode: str | None = None) -> None:
    payload_dict = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if parse_mode:
        payload_dict["parse_mode"] = parse_mode
    payload = urllib.parse.urlencode(payload_dict).encode("utf-8")
    request = urllib.request.Request(f"{TG_BASE_URL}/sendMessage", data=payload)
    urllib.request.urlopen(request, timeout=15)
    write_log(f"[TG] Sent text: {text[:80].replace(chr(10), ' ')}", log_path)


def _multipart_request(url: str, fields: dict[str, str], file_field: str, filename: str, content_type: str, payload: bytes):
    boundary = uuid.uuid4().hex
    body = b""
    for key, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode("utf-8")
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode()
    body += f"Content-Type: {content_type}\r\n\r\n".encode()
    body += payload
    body += f"\r\n--{boundary}--\r\n".encode()
    return urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def send_video(video_path: str, caption: str, log_path: str) -> None:
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as file:
        request = _multipart_request(
            f"{TG_BASE_URL}/sendVideo",
            {"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            "video",
            os.path.basename(video_path),
            "video/mp4",
            file.read(),
        )
    urllib.request.urlopen(request, timeout=180)
    write_log(f"[TG] Sent video: {os.path.basename(video_path)}", log_path)


def send_document(file_path: str, caption: str, log_path: str) -> None:
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundError(f"Document not found: {file_path}")
    with open(file_path, "rb") as file:
        request = _multipart_request(
            f"{TG_BASE_URL}/sendDocument",
            {"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            "document",
            os.path.basename(file_path),
            "application/octet-stream",
            file.read(),
        )
    urllib.request.urlopen(request, timeout=180)
    write_log(f"[TG] Sent document: {os.path.basename(file_path)}", log_path)


def _telegram_get_updates(offset: int, timeout_sec: int = 0) -> list[dict] | None:
    query = urllib.parse.urlencode({"offset": offset, "timeout": timeout_sec})
    url = f"{TG_BASE_URL}/getUpdates?{query}"
    try:
        response = json.loads(urllib.request.urlopen(url, timeout=max(15, timeout_sec + 5)).read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 409:
            return None
        raise
    if not response.get("ok"):
        return []
    return response.get("result") or []


def _handle_telegram_poll_conflict(log_path: str | None) -> None:
    global _tg_poll_conflict_logged
    if _tg_poll_conflict_logged:
        return
    if log_path:
        write_log(
            "Telegram polling conflict detected (HTTP 409). Another client is using getUpdates; supervisor will retry.",
            log_path,
        )
    _tg_poll_conflict_logged = True


def _clear_telegram_poll_conflict(log_path: str | None) -> None:
    global _tg_poll_conflict_logged
    if not _tg_poll_conflict_logged:
        return
    if log_path:
        write_log("Telegram polling conflict cleared.", log_path)
    _tg_poll_conflict_logged = False


def prime_update_offset(log_path: str) -> int:
    global _tg_offset
    stored_offset = load_telegram_offset()
    if stored_offset > 0:
        _tg_offset = stored_offset
        write_log(f"Telegram offset restored: {stored_offset}", log_path)
        return stored_offset
    updates = _telegram_get_updates(0, timeout_sec=0)
    if updates is None:
        _tg_offset = 0
        _handle_telegram_poll_conflict(log_path)
        write_log("Telegram offset prime deferred until polling conflict clears.", log_path)
        return 0
    _clear_telegram_poll_conflict(log_path)
    next_offset = 0
    for update in updates:
        next_offset = max(next_offset, int(update.get("update_id", 0)) + 1)
    _tg_offset = next_offset
    save_telegram_offset(next_offset)
    write_log(f"Telegram offset primed: {next_offset}", log_path)
    return next_offset


def fetch_updates(timeout_sec: int = 0, log_path: str | None = None) -> list[dict]:
    global _tg_offset
    if _tg_offset is None:
        _tg_offset = load_telegram_offset()
    updates = _telegram_get_updates(_tg_offset, timeout_sec=timeout_sec)
    if updates is None:
        _handle_telegram_poll_conflict(log_path)
        return []
    _clear_telegram_poll_conflict(log_path)
    for update in updates:
        _tg_offset = max(_tg_offset, int(update.get("update_id", 0)) + 1)
    if updates:
        save_telegram_offset(_tg_offset)
    return updates


def extract_message(update: dict) -> tuple[str | None, str | None, str | None]:
    message = update.get("message") or {}
    text = message.get("text") or message.get("caption")
    chat_id = message.get("chat", {}).get("id")
    user_id = message.get("from", {}).get("id")
    return (
        text,
        str(chat_id) if chat_id is not None else None,
        str(user_id) if user_id is not None else None,
    )


def is_authorized_message(chat_id: str | None, user_id: str | None) -> bool:
    if chat_id != str(TELEGRAM_CHAT_ID):
        return False
    if TELEGRAM_ALLOWED_USER_IDS:
        return user_id in TELEGRAM_ALLOWED_USER_IDS
    return bool(user_id) and user_id == str(TELEGRAM_CHAT_ID)


def normalize_command(text: str) -> str:
    token = (text or "").strip().split()[0].lower() if text else ""
    if token.startswith("/"):
        token = token[1:]
    return token


def get_latest_run_dir() -> str | None:
    if not os.path.isdir(LOG_BASE):
        return None
    runs = sorted(d for d in os.listdir(LOG_BASE) if os.path.isdir(os.path.join(LOG_BASE, d)))
    return os.path.join(LOG_BASE, runs[-1]) if runs else None


def get_latest_checkpoint(run_dir: str | None) -> str | None:
    if not run_dir or not os.path.isdir(run_dir):
        return None
    pattern = os.path.join(run_dir, "model_*.pt")
    matches = [path for path in glob.glob(pattern) if re.match(r"model_\d+\.pt$", os.path.basename(path))]
    if not matches:
        return None
    matches.sort(key=lambda path: get_checkpoint_iter(path))
    return matches[-1]


def get_checkpoint_iter(checkpoint_path: str | None) -> int:
    if not checkpoint_path:
        return 0
    match = re.search(r"model_(\d+)", os.path.basename(checkpoint_path))
    return int(match.group(1)) if match else 0


def _extract_cmd_option(cmdline: str, option: str) -> str:
    pattern = rf"(?:^|\s)--{re.escape(option)}(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|(\S+))"
    match = re.search(pattern, cmdline)
    if not match:
        return ""
    for group in match.groups():
        if group:
            return str(group).strip()
    return ""


def _resolve_run_dir_from_arg(run_arg: str) -> str | None:
    if not run_arg:
        return None
    candidate = str(run_arg).strip().strip('"').strip("'")
    if not candidate:
        return None
    if os.path.isdir(candidate):
        return os.path.abspath(candidate)
    candidate_name = os.path.basename(candidate.rstrip("\\/"))
    run_dir = os.path.join(LOG_BASE, candidate_name)
    if os.path.isdir(run_dir):
        return run_dir
    return None


def _resolve_checkpoint_from_arg(run_dir: str | None, checkpoint_arg: str) -> str | None:
    if not checkpoint_arg:
        return get_latest_checkpoint(run_dir)
    candidate = str(checkpoint_arg).strip().strip('"').strip("'")
    if not candidate:
        return get_latest_checkpoint(run_dir)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    if run_dir:
        run_checkpoint = os.path.join(run_dir, os.path.basename(candidate))
        if os.path.isfile(run_checkpoint):
            return run_checkpoint
    return get_latest_checkpoint(run_dir)


def resolve_live_training_context() -> tuple[str | None, str | None]:
    processes = list_training_processes()
    if not processes:
        return None, None
    latest_run = get_latest_run_dir()
    for entry in sorted(processes, key=lambda item: item.get("pid", 0), reverse=True):
        cmdline = entry.get("cmdline") or ""
        run_dir = _resolve_run_dir_from_arg(_extract_cmd_option(cmdline, "load_run")) or latest_run
        checkpoint = _resolve_checkpoint_from_arg(run_dir, _extract_cmd_option(cmdline, "checkpoint"))
        if run_dir or checkpoint:
            return run_dir, checkpoint
    return latest_run, get_latest_checkpoint(latest_run)


def resolve_active_run_dir() -> str | None:
    live_run_dir, _ = resolve_live_training_context()
    if live_run_dir:
        return live_run_dir
    state = load_state()
    active_run = state.get("active_run") or ""
    if active_run:
        active_path = os.path.join(LOG_BASE, active_run)
        if os.path.isdir(active_path):
            return active_path
    return get_latest_run_dir()


def resolve_active_checkpoint(run_dir: str | None = None) -> str | None:
    live_run_dir, live_checkpoint = resolve_live_training_context()
    if live_checkpoint:
        if not run_dir or run_dir == live_run_dir:
            return live_checkpoint
    run_dir = run_dir or live_run_dir or resolve_active_run_dir()
    latest_checkpoint = get_latest_checkpoint(run_dir)
    state = load_state()
    checkpoint = state.get("active_checkpoint") or ""
    if checkpoint and os.path.isfile(checkpoint):
        checkpoint = os.path.abspath(checkpoint)
        if run_dir and os.path.dirname(checkpoint) == os.path.abspath(run_dir):
            if latest_checkpoint and get_checkpoint_iter(latest_checkpoint) > get_checkpoint_iter(checkpoint):
                return latest_checkpoint
            return checkpoint
    return latest_checkpoint


def get_display_iteration(run_dir: str | None, checkpoint_path: str | None = None) -> int:
    if run_dir and os.path.isdir(run_dir):
        live_iter = int(build_supervisor_kpi_snapshot(run_dir).get("iter") or 0)
        if live_iter > 0:
            return live_iter
    return get_checkpoint_iter(checkpoint_path)


def _path_matches_run(path: str | None, run_dir: str | None) -> bool:
    if not path or not run_dir:
        return False
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(run_dir)]) == os.path.abspath(run_dir)
    except Exception:
        return False


def _looks_like_training_command(name: str, cmdline: str) -> bool:
    cmdline_l = cmdline.lower()
    if (
        "scripts\\supervisor.py" in cmdline_l
        or "scripts/supervisor.py" in cmdline_l
        or "scripts\\heartbeat.py" in cmdline_l
        or "scripts/heartbeat.py" in cmdline_l
        or "scripts\\legacy\\supervisor.py" in cmdline_l
        or "scripts/legacy/supervisor.py" in cmdline_l
        or "scripts\\legacy\\heartbeat.py" in cmdline_l
        or "scripts/legacy/heartbeat.py" in cmdline_l
    ):
        return False
    if "powershell" in name.lower() and "get-ciminstance" in cmdline_l:
        return False
    return (
        "scripts\\rsl_rl\\train.py" in cmdline_l
        or "scripts/rsl_rl/train.py" in cmdline_l
        or ("isaaclab.bat" in cmdline_l and "train.py" in cmdline_l)
        or "_launch_resume_training.cmd" in cmdline_l
        or "_launch_fresh_training.cmd" in cmdline_l
    )


def list_training_processes() -> list[dict]:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if not cmdline:
                continue
            name = proc.info.get("name") or ""
            if _looks_like_training_command(name, cmdline):
                processes.append({"pid": proc.info["pid"], "name": name, "cmdline": cmdline})
        except (psutil.Error, PermissionError, OSError):
            pass
    deduped = {entry["pid"]: entry for entry in processes}
    return sorted(deduped.values(), key=lambda item: item["pid"])


def is_training_running() -> bool:
    return bool(list_training_processes())


def kill_training_processes(log_path: str) -> list[int]:
    killed = []
    for entry in list_training_processes():
        try:
            psutil.Process(entry["pid"]).kill()
            killed.append(entry["pid"])
            write_log(f"Killed training process PID {entry['pid']}: {entry['name']}", log_path)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed:
        time.sleep(3)
    return killed


def _hidden_creationflags(extra_flags: int = 0) -> int:
    if sys.platform == "win32":
        return extra_flags | subprocess.CREATE_NO_WINDOW
    return extra_flags


def _hidden_startupinfo():
    if sys.platform != "win32":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def _wrap_conda_command(command: str) -> str:
    if sys.platform != "win32":
        return command
    if CONDA_ACTIVATE_BAT:
        activate_cmd = f'"{CONDA_ACTIVATE_BAT}"'
        if os.path.basename(CONDA_ACTIVATE_BAT).lower() == "conda.bat":
            return f"call {activate_cmd} activate {CONDA_ENV_NAME} && {command}"
        return f"call {activate_cmd} && conda activate {CONDA_ENV_NAME} && {command}"
    return f"conda activate {CONDA_ENV_NAME} && {command}"


def _write_temp_cmd_script(command: str, prefix: str) -> str:
    logs_dir = os.path.join(PROJECT_ROOT, "logs", "_cmd_tmp")
    os.makedirs(logs_dir, exist_ok=True)
    script_path = os.path.join(
        logs_dir,
        f"{prefix}_{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.cmd",
    )
    with open(script_path, "w", encoding="utf-8", newline="\r\n") as file:
        file.write("@echo off\n")
        file.write(command + "\n")
    return script_path


def _escape_cmd_echo_text(text: str) -> str:
    escaped = str(text)
    escaped = escaped.replace("^", "^^")
    escaped = escaped.replace("&", "^&")
    escaped = escaped.replace("|", "^|")
    escaped = escaped.replace("<", "^<")
    escaped = escaped.replace(">", "^>")
    return escaped


def _popen_hidden_cmd(command: str, **kwargs):
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs.setdefault("creationflags", _hidden_creationflags(kwargs.pop("creationflags", 0)))
    kwargs.setdefault("startupinfo", kwargs.pop("startupinfo", _hidden_startupinfo()))
    kwargs["env"] = {**os.environ, "PYTHONIOENCODING": "utf-8", **kwargs.get("env", {})}
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    if sys.platform == "win32":
        script_path = _write_temp_cmd_script(command, "popen")
        return subprocess.Popen(["cmd", "/d", "/c", script_path], **kwargs)
    return subprocess.Popen(command, shell=True, **kwargs)


def _run_hidden_cmd(command: str, **kwargs):
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs.setdefault("creationflags", _hidden_creationflags(kwargs.pop("creationflags", 0)))
    kwargs.setdefault("startupinfo", kwargs.pop("startupinfo", _hidden_startupinfo()))
    kwargs["env"] = {**os.environ, "PYTHONIOENCODING": "utf-8", **kwargs.get("env", {})}
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    if sys.platform == "win32":
        script_path = _write_temp_cmd_script(command, "run")
        return subprocess.run(["cmd", "/d", "/c", script_path], **kwargs)
    return subprocess.run(command, shell=True, **kwargs)


def _launch_training_command(command: str, launcher_name: str) -> str:
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    launcher_path = os.path.join(logs_dir, launcher_name)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    command_for_echo = _escape_cmd_echo_text(command)
    with open(launcher_path, "w", encoding="utf-8", newline="\n") as file:
        file.write("@echo off\n")
        file.write(f'echo ===== [{timestamp}] training launch =====>> "{TRAINING_LOG}"\n')
        file.write(f'echo cmd: {command_for_echo}>> "{TRAINING_LOG}"\n')
        file.write(f'{command} >> "{TRAINING_LOG}" 2>&1\n')
    creationflags = 0
    if sys.platform == "win32":
        creationflags = _hidden_creationflags(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    subprocess.Popen(
        ["cmd", "/d", "/c", launcher_path],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=_hidden_startupinfo(),
        creationflags=creationflags,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return launcher_path


def _launch_background_command(command: str, launcher_name: str) -> str:
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    launcher_path = os.path.join(logs_dir, launcher_name)
    with open(launcher_path, "w", encoding="utf-8", newline="\n") as file:
        file.write("@echo off\n")
        file.write(command + "\n")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = _hidden_creationflags(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    subprocess.Popen(
        ["cmd", "/d", "/c", launcher_path],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=_hidden_startupinfo(),
        creationflags=creationflags,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return launcher_path


def _looks_like_heartbeat_command(name: str, cmdline: str) -> bool:
    cmdline_l = cmdline.lower()
    if "powershell" in name.lower() and "get-ciminstance" in cmdline_l:
        return False
    return (
        "scripts\\heartbeat.py" in cmdline_l
        or "scripts/heartbeat.py" in cmdline_l
        or "scripts\\legacy\\heartbeat.py" in cmdline_l
        or "scripts/legacy/heartbeat.py" in cmdline_l
        or "training_heartbeat.py" in cmdline_l
    )


def _looks_like_supervisor_command(name: str, cmdline: str) -> bool:
    cmdline_l = cmdline.lower()
    return "scripts\\supervisor.py" in cmdline_l or "scripts/supervisor.py" in cmdline_l


def _list_matching_processes(match_fn) -> list[dict]:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if not cmdline:
                continue
            name = proc.info.get("name") or ""
            if match_fn(name, cmdline):
                processes.append(
                    {
                        "pid": proc.info["pid"],
                        "name": name,
                        "cmdline": cmdline,
                        "create_time": float(proc.info.get("create_time") or 0.0),
                    }
                )
        except (psutil.Error, PermissionError, OSError):
            pass
    deduped = {entry["pid"]: entry for entry in processes}
    return sorted(deduped.values(), key=lambda item: item["pid"])


def list_heartbeat_processes() -> list[dict]:
    return _list_matching_processes(_looks_like_heartbeat_command)


def list_supervisor_processes() -> list[dict]:
    return _list_matching_processes(_looks_like_supervisor_command)


def is_heartbeat_running() -> bool:
    if _read_live_pid_lock(HEARTBEAT_PID_FILE):
        return True
    return bool(list_heartbeat_processes())


def _select_process_entry(processes: list[dict], pid_file: str | None = None) -> dict | None:
    preferred_pid = _read_live_pid_lock(pid_file) if pid_file else 0
    if preferred_pid:
        for entry in processes:
            if int(entry.get("pid") or 0) == preferred_pid:
                return entry
    if not processes:
        return None
    return max(processes, key=lambda item: (float(item.get("create_time") or 0.0), int(item.get("pid") or 0)))


def _process_status_version_text(processes: list[dict], watched_files: list[str], pid_file: str | None = None) -> str:
    repo_version = (_get_repo_git_commit() or "unknown")[:7]
    active_entry = _select_process_entry(processes, pid_file=pid_file)
    if not active_entry:
        return f"{repo_version} | stopped"
    latest_file_mtime = 0.0
    for path in watched_files:
        try:
            latest_file_mtime = max(latest_file_mtime, os.path.getmtime(path))
        except OSError:
            continue
    started_at = float(active_entry.get("create_time") or 0.0)
    freshness = "latest" if started_at >= latest_file_mtime else "stale"
    return f"{repo_version} | {freshness} | pid {int(active_entry.get('pid') or 0)}"


def build_heartbeat_command(iter_step: int | None = None, poll: int | None = None) -> str:
    heartbeat_script = HEARTBEAT_SCRIPT
    iter_step = int(iter_step or HEARTBEAT_ITER_STEP)
    poll = int(poll or HEARTBEAT_POLL_SECONDS)
    command = (
        f'cd /d "{PROJECT_ROOT}" && '
        'set PYTHONIOENCODING=utf-8 && '
        f'python "{heartbeat_script}" --iter_step={iter_step} --poll={poll}'
    )
    return _wrap_conda_command(command)


def launch_heartbeat(log_path: str, iter_step: int | None = None, poll: int | None = None) -> dict:
    if is_heartbeat_running():
        return {"mode": "already-running", "processes": list_heartbeat_processes()}
    command = build_heartbeat_command(iter_step=iter_step, poll=poll)
    write_log(f"Launching heartbeat: {command}", log_path)
    with open(HEARTBEAT_LOG, "ab") as heartbeat_log_file:
        proc = _popen_hidden_cmd(command, stdout=heartbeat_log_file, stderr=subprocess.STDOUT)
    write_log(f"Heartbeat launcher PID: {proc.pid}", log_path)
    deadline = time.time() + 15
    while time.time() < deadline:
        heartbeat_pid = _read_live_pid_lock(HEARTBEAT_PID_FILE)
        if heartbeat_pid:
            processes = list_heartbeat_processes()
            if not processes:
                processes = [{"pid": heartbeat_pid, "name": "python.exe", "cmdline": HEARTBEAT_SCRIPT}]
            write_log(f"Heartbeat active PID: {heartbeat_pid}", log_path)
            return {"mode": "started", "processes": processes}
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    log_tail = _read_text_tail(HEARTBEAT_LOG)
    raise RuntimeError(
        "Heartbeat failed to start"
        + (f" (launcher rc={proc.returncode})" if proc.poll() is not None else "")
        + (f"\n{log_tail}" if log_tail else "")
    )


def stop_heartbeat(log_path: str) -> list[int]:
    killed = []
    for entry in list_heartbeat_processes():
        try:
            psutil.Process(entry["pid"]).kill()
            killed.append(entry["pid"])
            write_log(f"Killed heartbeat process PID {entry['pid']}: {entry['name']}", log_path)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    release_pid_lock(HEARTBEAT_PID_FILE)
    return killed


def ensure_heartbeat_running(log_path: str, iter_step: int | None = None, poll: int | None = None) -> dict:
    if is_heartbeat_running():
        return {"mode": "already-running", "processes": list_heartbeat_processes()}
    return launch_heartbeat(log_path, iter_step=iter_step, poll=poll)


def build_train_command(resume_run_dir: str | None = None, checkpoint_path: str | None = None) -> str:
    train_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "train.py")
    parts = [
        f'cd /d "{PROJECT_ROOT}"',
        "set PYTHONIOENCODING=utf-8",
        f'"{ISAAC_LAB}" -p "{train_script}"',
        f"--task={TASK}",
        f"--num_envs={TRAIN_ENVS}",
        "--headless",
        f"--max_iterations={MAX_ITERATIONS}",
    ]
    if resume_run_dir and checkpoint_path:
        parts.extend([
            "--resume",
            f"--load_run={os.path.basename(resume_run_dir)}",
            f"--checkpoint={os.path.basename(checkpoint_path)}",
        ])
    return _wrap_conda_command(" && ".join(parts[:2]) + " && " + " ".join(parts[2:]))


def launch_training(log_path: str) -> dict:
    if is_training_running():
        return {"mode": "already-running", "run_dir": resolve_active_run_dir(), "checkpoint": resolve_active_checkpoint()}
    baseline_run = get_latest_run_dir()
    resume_run = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(resume_run)
    command = build_train_command(resume_run, checkpoint) if checkpoint else build_train_command()
    write_log(f"Launching training: {command}", log_path)
    launcher_path = _launch_training_command(command, "_launch_training.cmd")
    write_log(f"Training launcher: {launcher_path}", log_path)
    time.sleep(5)
    active_run = get_latest_run_dir()
    if baseline_run and active_run and os.path.basename(active_run) <= os.path.basename(baseline_run):
        active_run = resume_run or active_run
    active_checkpoint = resolve_active_checkpoint(active_run)
    update_state(
        mode="training",
        active_run=os.path.basename(active_run) if active_run else "",
        active_checkpoint=active_checkpoint or "",
        last_command="start",
        last_error="",
    )
    return {"mode": "started", "run_dir": active_run, "checkpoint": active_checkpoint}


def stop_training(log_path: str) -> dict:
    killed = kill_training_processes(log_path)
    active_run = resolve_active_run_dir()
    active_checkpoint = resolve_active_checkpoint(active_run)
    update_state(
        mode="stopped",
        active_run=os.path.basename(active_run) if active_run else "",
        active_checkpoint=active_checkpoint or "",
        last_command="stop",
        last_error="",
    )
    return {"killed": killed, "run_dir": active_run, "checkpoint": active_checkpoint}


def get_video_capture_specs(play_envs: int) -> list[dict]:
    return [
        {"key": "overview", "label": "overview", "camera_view": "overview", "num_envs": play_envs, "camera_zoom": 1.0},
        {"key": "side", "label": "side", "camera_view": "side", "num_envs": 1, "camera_zoom": 0.9},
        {"key": "front", "label": "front", "camera_view": "front", "num_envs": 1, "camera_zoom": 0.9},
        {"key": "rear", "label": "rear", "camera_view": "rear", "num_envs": 1, "camera_zoom": 0.9},
        {"key": "top", "label": "top", "camera_view": "top", "num_envs": 1, "camera_zoom": 0.85},
    ]


def _snapshot_play_videos(run_dir: str) -> dict[str, tuple[int, int]]:
    snapshot = {}
    for path in glob.glob(os.path.join(run_dir, "videos", "play", "*.mp4")):
        try:
            stat = os.stat(path)
        except OSError:
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _find_updated_play_video(run_dir: str, before_snapshot: dict[str, tuple[int, int]]) -> str | None:
    candidates: list[tuple[int, int, str]] = []
    for path in glob.glob(os.path.join(run_dir, "videos", "play", "*.mp4")):
        try:
            stat = os.stat(path)
        except OSError:
            continue
        current = (stat.st_mtime_ns, stat.st_size)
        previous = before_snapshot.get(path)
        if previous is None or current != previous:
            candidates.append((stat.st_mtime_ns, stat.st_size, path))
    candidates.sort()
    return candidates[-1][2] if candidates else None


def _sha256_file(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _find_duplicate_video_hashes(captured_videos: dict[str, str]) -> dict[str, list[str]]:
    hash_to_views: dict[str, list[str]] = {}
    for view_key, path in captured_videos.items():
        if not path or not os.path.isfile(path):
            continue
        digest = _sha256_file(path)
        hash_to_views.setdefault(digest, []).append(view_key)
    return {digest: sorted(views) for digest, views in hash_to_views.items() if len(views) > 1}


def find_latest_video(view_key: str, run_dir: str | None = None) -> str | None:
    search_roots = [run_dir] if run_dir else []
    if LOG_BASE not in search_roots:
        search_roots.append(LOG_BASE)
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        matches = glob.glob(os.path.join(root, "**", f"*{view_key}*.mp4"), recursive=True)
        matches = [path for path in matches if os.path.isfile(path)]
        if matches:
            matches.sort(key=lambda path: os.path.getmtime(path), reverse=True)
            return matches[0]
    return None


def find_latest_report_zip(run_dir: str | None = None) -> str | None:
    search_roots = [run_dir] if run_dir else []
    if LOG_BASE not in search_roots:
        search_roots.append(LOG_BASE)
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        matches = glob.glob(os.path.join(root, "**", "*.zip"), recursive=True)
        matches = [path for path in matches if os.path.isfile(path)]
        if matches:
            matches.sort(key=lambda path: os.path.getmtime(path), reverse=True)
            return matches[0]
    return None


def find_latest_report_xlsx(run_dir: str | None = None) -> str | None:
    search_roots = [run_dir] if run_dir else []
    if LOG_BASE not in search_roots:
        search_roots.append(LOG_BASE)
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        matches = glob.glob(os.path.join(root, "**", "clip_*_heartbeat_history.xlsx"), recursive=True)
        matches = [path for path in matches if os.path.isfile(path)]
        if matches:
            matches.sort(key=lambda path: os.path.getmtime(path), reverse=True)
            return matches[0]
    return None


def read_tfevents(run_dir: str, retries: int = 3):
    try:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    except ImportError:
        return None
    event_files = [name for name in os.listdir(run_dir) if name.startswith("events.out.tfevents")]
    if not event_files:
        return None
    event_path = os.path.join(run_dir, event_files[0])
    for attempt in range(retries):
        try:
            accumulator = EventAccumulator(event_path)
            accumulator.Reload()
            data = {}
            for tag in accumulator.Tags().get("scalars", []):
                events = accumulator.Scalars(tag)
                data[tag] = [(event.step, event.value) for event in events]
            return data
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return None


def get_heartbeat_history_path(run_dir: str) -> str:
    return os.path.join(run_dir, HEARTBEAT_HISTORY_JSONL)


def load_report_history(run_dir: str) -> list[dict]:
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
        write_log(f"Failed to read heartbeat history: {err}", SUPERVISOR_LOG)
    return records


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


def classify_primary_kpi(metric_name: str, value: float):
    warn_th, good_th = PRIMARY_KPI_THRESHOLDS[metric_name]
    if value >= good_th:
        return "🟢", "양호"
    if value >= warn_th:
        return "🟡", "형성중"
    return "🔴", "미약"


def classify_posture_metric(metric_name: str, value: float):
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
    watched_metrics = [
        "standing_height",
        "forward_velocity",
        "diagonal_coupling",
        "trot_gait",
        "rear_joint_velocity",
        "foot_clearance",
    ]
    greens, yellows, reds = [], [], []
    for metric_name in watched_metrics:
        _, state = classify_primary_kpi(metric_name, rewards.get(metric_name, 0.0))
        if state == "양호":
            greens.append(metric_name)
        elif state == "형성중":
            yellows.append(metric_name)
        else:
            reds.append(metric_name)
    reasons = []
    if current_iter <= 300:
        verdict = "🔵 워밍업"
        reasons.append("초기 탐색 구간")
    elif current_iter <= 1000:
        if survival_pct < 8 and bad_orient > 0.95 and len(greens) == 0 and len(yellows) < 2:
            verdict = "🔴 중단 검토"
            reasons.append(f"생존 {survival_pct:.1f}% / bad_orientation {bad_orient*100:.0f}%")
        elif survival_pct >= 15 and (len(greens) >= 1 or len(yellows) >= 3):
            verdict = "🟢 계속 진행"
            reasons.append(f"생존 {survival_pct:.1f}%로 초기 기준 통과")
        else:
            verdict = "🟡 계속 관찰"
            reasons.append(f"생존 {survival_pct:.1f}% / bad_orientation {bad_orient*100:.0f}%")
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
    score = 0
    trot = rewards.get("trot_gait", 0.0)
    diag = rewards.get("diagonal_coupling", 0.0)
    rear_vel = rewards.get("rear_joint_velocity", 0.0)
    fwd = rewards.get("forward_velocity", 0.0)
    foot = rewards.get("foot_clearance", 0.0)
    height = rewards.get("standing_height", 0.0)
    score += 3 if trot >= 0.9 else 1 if trot >= 0.4 else 0
    score += 2 if diag >= 2.6 else 1 if diag >= 1.3 else 0
    score += 2 if rear_vel >= 16 else 1 if rear_vel >= 8 else 0
    score += 2 if fwd >= 1.5 else 1 if fwd >= 0.75 else 0
    score += 2 if foot >= 1.6 else 1 if foot >= 0.8 else 0
    score += 2 if height >= 0.20 else 1 if height >= 0.10 else 0
    if score >= 11:
        return "🌟 A", score, []
    if score >= 8:
        return "⭐ B", score, []
    if score >= 5:
        return "🟡 C", score, []
    if score >= 2:
        return "🟠 D", score, []
    return "🔴 F", score, []


def motion_stability_score(rewards, gait_score):
    if gait_score < 3:
        return "⚪ N/A", 0, ["보행 미형성"], False
    score = 0
    metrics = [
        ("action_rate_l2", -6.0, -3.6),
        ("joint_vel_l2", -10.0, -6.0),
        ("flat_orientation_l2", -0.04, -0.015),
        ("ang_vel_xy_l2", -1.0, -0.5),
        ("lin_vel_z_l2", -0.03, -0.015),
    ]
    for name, warn_th, good_th in metrics:
        value = rewards.get(name, 0.0)
        if value > good_th:
            score += 2
        elif value > warn_th:
            score += 1
    if score >= 8:
        return "🌟 A", score, [], True
    if score >= 6:
        return "⭐ B", score, [], True
    if score >= 4:
        return "🟡 C", score, [], True
    if score >= 2:
        return "🟠 D", score, [], True
    return "🔴 F", score, [], True


def posture_style_score(rewards):
    score = 0
    for metric_name in ("shoulder_neutral", "shoulder_symmetry", "stance_width_penalty", "standing_height", "flat_orientation_l2"):
        _, state = classify_posture_metric(metric_name, rewards.get(metric_name, 0.0))
        if state == "양호":
            score += 2
        elif state == "형성중":
            score += 1
    if score >= 8:
        return "🌟 A", score, []
    if score >= 6:
        return "⭐ B", score, []
    if score >= 4:
        return "🟡 C", score, []
    if score >= 2:
        return "🟠 D", score, []
    return "🔴 F", score, []


def jitter_quality_score(rewards):
    score = 0.0
    metrics = [
        ("action_rate_l2", -3.6, -6.0),
        ("joint_vel_l2", -6.0, -10.0),
        ("dof_acc_l2", -6.0, -12.0),
        ("joint_oscillation", -0.20, -0.50),
        ("foot_extension", -0.20, -0.50),
    ]
    count = 0
    for name, good_th, warn_th in metrics:
        value = rewards.get(name)
        numeric = _safe_float(value)
        if numeric is None:
            continue
        count += 1
        if numeric >= good_th:
            score += 100.0
        elif numeric >= warn_th:
            score += 65.0
        else:
            score += 20.0
    if count == 0:
        return None
    return round(score / count, 1)


def _trend_icon_and_pct(values, window: int = 20) -> tuple[str, float]:
    if len(values) < 2:
        return "📊", 0.0
    if len(values) < window * 2:
        if len(values) < 10:
            return "📊", 0.0
        split = len(values) // 2
        first_half = values[:split]
        second_half = values[split:]
    else:
        first_half = values[-(window * 2):-window]
        second_half = values[-window:]
    avg_first = sum(value for _, value in first_half) / len(first_half)
    avg_second = sum(value for _, value in second_half) / len(second_half)
    change = avg_second - avg_first
    pct = (change / abs(avg_first) * 100.0) if avg_first not in (0, 0.0) else 0.0
    if pct > 10.0:
        return "📈", round(pct, 1)
    if pct > 3.0:
        return "↗️", round(pct, 1)
    if pct < -10.0:
        return "📉", round(pct, 1)
    if pct < -3.0:
        return "↘️", round(pct, 1)
    return "➡️", round(pct, 1)


def _build_heartbeat_summary(current_iter: int, rewards: dict, survival_pct: float, timeout_pct: float, fall_pct: float, gait_grade: str, gait_score: int, stab_grade: str, stab_score: int, stab_valid: bool, posture_grade: str, posture_score: int) -> list[str]:
    summary = []
    forward_velocity = rewards.get("forward_velocity", 0.0)
    foot_clearance = rewards.get("foot_clearance", 0.0)
    diagonal_coupling = rewards.get("diagonal_coupling", 0.0)
    if current_iter < 1000:
        if forward_velocity >= 0.75 and diagonal_coupling >= 1.3:
            summary.append("초반 구간에서 관절 리듬과 전진 반응이 함께 나타나고 있습니다.")
        elif forward_velocity < 0.3:
            summary.append("초반 구간이지만 아직 전진보다 자세 유지 쪽이 우세합니다.")
        else:
            summary.append("초반 구간에서 locomotion 신호는 보이지만 아직 gait 품질 확정 전입니다.")
    else:
        if gait_score >= 8 and forward_velocity >= 0.75:
            summary.append("관절 리듬은 형성됐고 전진도 동반되어, 단순 정지 패턴은 지난 상태입니다.")
        elif gait_score >= 5:
            summary.append("관절 리듬은 형성되고 있지만 전진속도와 발들기가 아직 충분히 따라오지 않습니다.")
        else:
            summary.append("현재까지는 gait 품질 형성이 약해 보상 구조 또는 커리큘럼 재검토가 필요할 수 있습니다.")
    if survival_pct >= 70.0:
        summary.append(f"생존률 {survival_pct:.1f}%로 비교적 안정적이며 종료는 timeout 비중이 높습니다.")
    elif survival_pct >= 30.0:
        summary.append(f"생존률 {survival_pct:.1f}% 수준으로 버티고 있으나 fall 비중 {fall_pct:.0f}%가 아직 큽니다.")
    else:
        summary.append(f"생존률 {survival_pct:.1f}%로 낮아 자세 안정화가 우선입니다.")
    if stab_valid and stab_score >= 6 and posture_score >= 6:
        summary.append("stability와 posture는 양호한 편이라, 다음 관전 포인트는 forward_velocity와 foot_clearance의 동반 상승입니다.")
    elif foot_clearance < 0.8:
        summary.append("발들기 신호가 약해 실제 trot이라기보다 낮은 진폭 패턴일 가능성을 열어둬야 합니다.")
    rear_bias_signals = 0
    if rewards.get("rear_joint_velocity", 0.0) >= 8.0:
        rear_bias_signals += 1
    if rewards.get("rear_forward_stride", 0.0) >= 0.2:
        rear_bias_signals += 1
    if rear_bias_signals >= 2:
        summary.append("rear-driven bias 가능성은 남아 있으므로 최종 판정은 계속 영상과 함께 봐야 합니다.")
    return summary[:3]


def build_supervisor_kpi_snapshot(run_dir: str) -> dict:
    result = {
        "iter": 0,
        "reward": 0.0,
        "reward_avg10": 0.0,
        "ep_len": 0.0,
        "survival_pct": 0.0,
        "timeout_pct": 0.0,
        "fall_pct": 0.0,
        "verdict": "⚪ KPI unavailable",
        "reason": "TensorBoard 데이터를 읽지 못함",
        "reasons": [],
        "gait": "N/A",
        "gait_score": 0,
        "stability": "N/A",
        "stability_score": 0,
        "stability_valid": False,
        "posture": "N/A",
        "posture_score": 0,
        "foot_jitter_score": None,
        "kpi_line": "기립 N/A | 전진 N/A | 대각 N/A",
        "caption_suffix": "⚪ KPI unavailable",
    }
    data = read_tfevents(run_dir)
    if not data:
        return result
    reward_vals = data.get("Train/mean_reward", [])
    ep_len_vals = data.get("Train/mean_episode_length", [])
    if not reward_vals:
        return result
    current_iter = int(reward_vals[-1][0])
    current_reward = float(reward_vals[-1][1])
    reward_window = reward_vals[-10:] if len(reward_vals) >= 10 else reward_vals
    reward_avg10 = sum(v for _, v in reward_window) / len(reward_window) if reward_window else current_reward
    current_ep_len = float(ep_len_vals[-1][1]) if ep_len_vals else 0.0
    timeout = float(_latest_scalar(data, "Episode_Termination/time_out") or 0.0)
    bad_orient = float(_latest_scalar(data, "Episode_Termination/bad_orientation") or 0.0)
    total_term = timeout + bad_orient
    timeout_pct = (timeout / total_term * 100.0) if total_term > 0 else 0.0
    fall_pct = (bad_orient / total_term * 100.0) if total_term > 0 else 0.0
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
    gait_grade, gait_score, _ = gait_quality_score(rewards)
    stab_grade, stab_score, _details, stab_valid = motion_stability_score(rewards, gait_score)
    posture_grade, posture_score, _ = posture_style_score(rewards)
    foot_jitter_score = jitter_quality_score(rewards)
    verdict, reasons, _greens, _yellows, _reds = evaluate_training_window(current_iter, survival_pct, bad_orient, rewards)
    primary_items = []
    for metric_name, label in [("standing_height", "기립"), ("forward_velocity", "전진"), ("diagonal_coupling", "대각")]:
        icon, state = classify_primary_kpi(metric_name, rewards.get(metric_name, 0.0))
        primary_items.append(f"{icon}{label} {state}")
    stability_label = f"{stab_grade} {stab_score}/10" if stab_valid else stab_grade
    result.update(
        {
            "iter": current_iter,
            "reward": current_reward,
            "reward_avg10": reward_avg10,
            "ep_len": current_ep_len,
            "survival_pct": survival_pct,
            "timeout_pct": timeout_pct,
            "fall_pct": fall_pct,
            "verdict": verdict,
            "reason": reasons[0] if reasons else "",
            "reasons": reasons,
            "gait": gait_grade,
            "gait_score": gait_score,
            "stability": stab_grade,
            "stability_score": stab_score,
            "stability_valid": stab_valid,
            "posture": posture_grade,
            "posture_score": posture_score,
            "foot_jitter_score": foot_jitter_score,
            "kpi_line": " | ".join(primary_items + [f"🧍포즈 {posture_grade} {posture_score}/10"]),
            "caption_suffix": f"{verdict} | Gait {gait_grade} {gait_score}/13 | Stability {stability_label} | Posture {posture_grade} {posture_score}/10",
        }
    )
    return result


def build_report_record(data: dict, run_name: str, cycle_num: int, report_kind: str = "heartbeat") -> dict | None:
    reward_vals = data.get("Train/mean_reward", [])
    if not reward_vals:
        return None
    run_dir = os.path.join(LOG_BASE, run_name)
    kpi = build_supervisor_kpi_snapshot(run_dir) if os.path.isdir(run_dir) else {}
    ep_len_vals = data.get("Train/mean_episode_length", [])
    current_iter = int(reward_vals[-1][0])
    return {
        "run_name": run_name,
        "report_kind": report_kind,
        "cycle_num": int(cycle_num),
        "iteration": current_iter,
        "timestamp": _now(),
        "mean_reward": _safe_float(reward_vals[-1][1]),
        "mean_episode_length": _safe_float(ep_len_vals[-1][1]) if ep_len_vals else 0.0,
        "kpi_snapshot": kpi,
    }


def append_report_record(run_dir: str, record: dict | None) -> None:
    if not run_dir or not record:
        return
    history_path = get_heartbeat_history_path(run_dir)
    try:
        with open(history_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        refresh_v23_training_logs(run_dir, SUPERVISOR_LOG)
    except Exception as err:
        write_log(f"V23 workbook refresh failed: {err}", SUPERVISOR_LOG)


def _format_relative_age(timestamp_text: str | None) -> str:
    if not timestamp_text:
        return "N/A"
    try:
        target = datetime.datetime.fromisoformat(str(timestamp_text))
    except (TypeError, ValueError):
        return "N/A"
    delta = datetime.datetime.now() - target
    total_seconds = max(int(delta.total_seconds()), 0)
    if total_seconds < 60:
        return "just now"
    if total_seconds < 3600:
        return f"{total_seconds // 60}m ago"
    if total_seconds < 86400:
        return f"{total_seconds // 3600}h ago"
    return f"{total_seconds // 86400}d ago"


def _get_last_heartbeat_age(run_dir: str | None) -> str:
    if not run_dir or not os.path.isdir(run_dir):
        return "N/A"
    records = load_report_history(run_dir)
    for record in reversed(records):
        timestamp_text = record.get("timestamp")
        if timestamp_text:
            return _format_relative_age(timestamp_text)
    history_path = get_heartbeat_history_path(run_dir)
    if os.path.isfile(history_path):
        history_updated_at = datetime.datetime.fromtimestamp(os.path.getmtime(history_path)).isoformat(timespec="seconds")
        return _format_relative_age(history_updated_at)
    return "N/A"


def _build_status_snapshot() -> dict:
    state = load_state()
    run_dir = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(run_dir)
    kpi_snapshot = build_supervisor_kpi_snapshot(run_dir) if run_dir and os.path.isdir(run_dir) else {}
    iter_num = int(kpi_snapshot.get("iter") or 0) or get_checkpoint_iter(checkpoint)
    progress_pct = (iter_num / MAX_ITERATIONS * 100.0) if MAX_ITERATIONS > 0 else 0.0
    last_videos = state.get("last_videos") or {}
    available_views = [
        key
        for key, path in sorted(last_videos.items())
        if path and os.path.isfile(path) and _path_matches_run(path, run_dir)
    ]
    if not available_views and run_dir:
        available_views = [key for key in ("front", "overview", "rear", "side", "top") if find_latest_video(key, run_dir)]
    last_report_zip = state.get("last_report_zip") or ""
    if not _path_matches_run(last_report_zip, run_dir):
        last_report_zip = find_latest_report_zip(run_dir) or ""
    heartbeat_alive = is_heartbeat_running()
    last_heartbeat_report_text = _get_last_heartbeat_age(run_dir)
    if heartbeat_alive:
        last_heartbeat_text = f"alive | report {last_heartbeat_report_text}"
    elif last_heartbeat_report_text != "N/A":
        last_heartbeat_text = f"stopped | report {last_heartbeat_report_text}"
    else:
        last_heartbeat_text = "stopped"
    supervisor_version_text = _process_status_version_text(
        list_supervisor_processes(),
        [SUPERVISOR_SCRIPT, __file__],
        pid_file=SUPERVISOR_PID_FILE,
    )
    heartbeat_version_text = _process_status_version_text(
        list_heartbeat_processes(),
        [HEARTBEAT_SCRIPT, __file__],
        pid_file=HEARTBEAT_PID_FILE,
    )
    return {
        "state": state,
        "run_dir": run_dir,
        "checkpoint": checkpoint,
        "iter_num": iter_num,
        "training_alive": is_training_running(),
        "heartbeat_alive": heartbeat_alive,
        "mode": str(state.get("mode", "idle")),
        "progress_text": f"{iter_num:,}/{MAX_ITERATIONS:,} ({progress_pct:.1f}%)",
        "reward_text": f"{float(kpi_snapshot.get('reward') or 0.0):.3f}" if kpi_snapshot else "N/A",
        "ep_len_text": f"{float(kpi_snapshot.get('ep_len') or 0.0):.1f}" if kpi_snapshot else "N/A",
        "verdict_text": str(kpi_snapshot.get("verdict") or "N/A") if kpi_snapshot else "N/A",
        "kpi_text": str(kpi_snapshot.get("kpi_line") or "N/A") if kpi_snapshot else "N/A",
        "last_heartbeat_text": last_heartbeat_text,
        "last_report_zip_name": os.path.basename(last_report_zip) if last_report_zip else "N/A",
        "available_views": available_views,
        "supervisor_version_text": supervisor_version_text,
        "heartbeat_version_text": heartbeat_version_text,
    }


def get_v23_master_log_path() -> str:
    return os.path.join(LOG_BASE, V23_MASTER_LOG_FILENAME)


def get_v23_checkpoint_review_path() -> str:
    return os.path.join(LOG_BASE, V23_CHECKPOINT_REVIEW_FILENAME)


def get_v23_run_log_path(run_dir: str) -> str:
    run_id = os.path.basename(run_dir.rstrip("\\/"))
    return os.path.join(run_dir, f"spotmicro_v23_run_{run_id}_training_log.xlsx")


def _scalar_value_at_or_before(data: dict, tag: str, iteration: int):
    values = data.get(tag, [])
    for step, value in reversed(values):
        if int(step) <= int(iteration):
            return _safe_float(value)
    return None


def _normalize_pct(value):
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if abs(numeric) <= 1.0:
        return round(numeric * 100.0, 4)
    return numeric


def _compute_elapsed_hours(run_dir: str, timestamp_text: str) -> float | None:
    try:
        started_at = datetime.datetime.fromtimestamp(os.path.getctime(run_dir))
        current_at = datetime.datetime.fromisoformat(timestamp_text)
        return round((current_at - started_at).total_seconds() / 3600.0, 4)
    except Exception:
        return None


def _score_band(value, warn_low: float, good_low: float, good_high: float | None = None, warn_high: float | None = None) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    good_high = good_low if good_high is None else good_high
    warn_high = good_high if warn_high is None else warn_high
    if good_low <= numeric <= good_high:
        return 100.0
    if warn_low <= numeric <= warn_high:
        return 65.0
    return 20.0


def _score_penalty(value, good_threshold: float, warn_threshold: float) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if numeric >= good_threshold:
        return 100.0
    if numeric >= warn_threshold:
        return 65.0
    return 20.0


def _load_yaml_config(file_path: str):
    if not os.path.isfile(file_path):
        return {}
    try:
        import yaml

        with open(file_path, "r", encoding="utf-8") as file:
            try:
                return yaml.safe_load(file) or {}
            except Exception:
                file.seek(0)
                return yaml.unsafe_load(file) or {}
    except Exception:
        return {}


def _get_repo_git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        pass
    return ""


def _build_v23_row(record: dict, run_dir: str, data: dict, reward_window: list[float]) -> dict:
    run_id = os.path.basename(run_dir)
    iteration = int(record.get("iteration") or 0)
    timestamp_text = str(record.get("timestamp") or _now())
    rewards = {tag.replace("Episode_Reward/", ""): _scalar_value_at_or_before(data, tag, iteration) for tag in data if tag.startswith("Episode_Reward/")}
    kpi = build_supervisor_kpi_snapshot(run_dir)
    timeout_pct = _normalize_pct(_scalar_value_at_or_before(data, "Episode_Termination/time_out", iteration))
    fall_pct = _normalize_pct(_scalar_value_at_or_before(data, "Episode_Termination/bad_orientation", iteration))
    mean_reward = _scalar_value_at_or_before(data, "Train/mean_reward", iteration) or _safe_float(record.get("mean_reward"))
    mean_ep_len = _scalar_value_at_or_before(data, "Train/mean_episode_length", iteration) or _safe_float(record.get("mean_episode_length"))
    if mean_reward is not None:
        reward_window.append(mean_reward)
    mean_reward_avg10 = round(sum(reward_window[-10:]) / len(reward_window[-10:]), 6) if reward_window else None
    survival_pct_derived = _normalize_pct(record.get("kpi_snapshot", {}).get("survival_pct") or record.get("survival_pct") or kpi.get("survival_pct"))

    posture_components = [
        _score_penalty(rewards.get("stance_width_penalty"), -0.15, -0.60),
        _score_penalty(rewards.get("shoulder_neutral"), -0.20, -0.60),
        _score_penalty(rewards.get("shoulder_symmetry"), -0.10, -0.40),
        _score_band(rewards.get("standing_height"), 0.10, 0.18, 0.24, 0.30),
        _score_penalty(rewards.get("flat_orientation_l2"), -0.015, -0.04),
        _score_penalty(rewards.get("base_height_l2"), -0.015, -0.04),
    ]
    posture_values = [value for value in posture_components if value is not None]
    posture_style_score = round(sum(posture_values) / len(posture_values), 3) if posture_values else None

    jitter_components = [
        _score_penalty(rewards.get("action_rate_l2"), -3.6, -6.0),
        _score_penalty(rewards.get("joint_vel_l2"), -6.0, -10.0),
        _score_penalty(rewards.get("dof_acc_l2"), -6.0, -12.0),
        _score_penalty(rewards.get("joint_oscillation"), -0.20, -0.50),
        _score_penalty(rewards.get("foot_extension"), -0.20, -0.50),
    ]
    jitter_values = [value for value in jitter_components if value is not None]
    foot_jitter_score = round(sum(jitter_values) / len(jitter_values), 3) if jitter_values else None
    stance_foot_jitter_score_raw = foot_jitter_score

    balance_components = [
        _score_band(rewards.get("leg_pose_symmetry"), 0.0, 0.3, 1.5, 2.5),
        _score_band(rewards.get("rear_alternation"), 0.0, 0.2, 2.0, 3.0),
        _score_band(rewards.get("rear_forward_stride"), 0.0, 0.2, 2.0, 3.0),
        _score_penalty(rewards.get("same_side_penalty"), -0.05, -0.25),
    ]
    balance_values = [value for value in balance_components if value is not None]
    front_rear_balance_score = round(sum(balance_values) / len(balance_values), 3) if balance_values else None

    gate_pass = bool(
        (survival_pct_derived or 0.0) >= 70.0
        and (fall_pct is None or fall_pct <= 10.0)
        and (_safe_float(_scalar_value_at_or_before(data, "Loss/value_function", iteration)) or 0.0) <= 5.0
        and (kpi.get("gait_score") or 0) >= 5
    )

    has_posture_raw = any(
        rewards.get(name) is not None
        for name in (
            "stance_width_mean_raw",
            "stance_width_front_raw",
            "stance_width_rear_raw",
            "shoulder_fl_raw",
            "shoulder_fr_raw",
            "shoulder_rl_raw",
            "shoulder_rr_raw",
            "shoulder_mean_abs_dev_from_target_raw",
            "shoulder_left_right_diff_raw",
            "shoulder_front_rear_diff_raw",
        )
    )
    has_front_rear_raw = any(
        rewards.get(name) is not None
        for name in (
            "front_leg_lift_mean_raw",
            "rear_leg_lift_mean_raw",
            "front_clearance_mean_raw",
            "rear_clearance_mean_raw",
            "front_propulsion_score_raw",
            "rear_propulsion_score_raw",
            "front_rear_propulsion_diff_raw",
            "front_rear_clearance_diff_raw",
            "front_rear_swing_diff_raw",
        )
    )

    fallback_parts = [
        "locomotion_raw=reward_proxy",
        "posture_score=proxy_reward_terms",
        "foot_jitter_score=proxy_reward_terms",
        "front_rear_balance_score=proxy_reward_terms",
        f"posture_raw={'env_export' if has_posture_raw else 'not_exported'}",
        f"front_rear_raw={'env_export' if has_front_rear_raw else 'not_exported'}",
    ]

    row = {column: None for column in V23_RUNLOG_COLUMNS}
    row.update(
        {
            "run_id": run_id,
            "train_version": V23_TRAIN_VERSION,
            "iter": iteration,
            "global_step": iteration,
            "timestamp": timestamp_text,
            "elapsed_hours": _compute_elapsed_hours(run_dir, timestamp_text),
            "report_kind": record.get("report_kind") or "heartbeat",
            "cycle_num": int(record.get("cycle_num") or 0),
            "log_source": "heartbeat_jsonl+tfevents",
            "fallback_source": "; ".join(fallback_parts),
            "mean_reward": mean_reward,
            "mean_reward_avg10": mean_reward_avg10,
            "mean_episode_length": mean_ep_len,
            "survival_pct": survival_pct_derived,
            "timeout_pct": timeout_pct,
            "fall_pct": fall_pct,
            "vf_loss": _scalar_value_at_or_before(data, "Loss/value_function", iteration),
            "surrogate_loss": _scalar_value_at_or_before(data, "Loss/surrogate", iteration),
            "noise_std": _scalar_value_at_or_before(data, "Policy/mean_noise_std", iteration),
            "vel_err_xy": _scalar_value_at_or_before(data, "Metrics/base_velocity/error_vel_xy", iteration),
            "vel_err_yaw": _scalar_value_at_or_before(data, "Metrics/base_velocity/error_vel_yaw", iteration),
            "survival_pct_derived": survival_pct_derived,
            "gait_score_estimated": kpi.get("gait_score"),
            "stability_score_estimated": kpi.get("stability_score"),
            "forward_velocity_raw": rewards.get("forward_velocity"),
            "trot_gait_raw": rewards.get("trot_gait"),
            "diagonal_coupling_raw": rewards.get("diagonal_coupling"),
            "leg_lift_raw": rewards.get("leg_lift"),
            "foot_clearance_raw": rewards.get("foot_clearance"),
            "standing_height_raw": rewards.get("standing_height"),
            "forward_velocity_reward": rewards.get("forward_velocity"),
            "trot_gait_reward": rewards.get("trot_gait"),
            "diagonal_coupling_reward": rewards.get("diagonal_coupling"),
            "leg_lift_reward": rewards.get("leg_lift"),
            "foot_clearance_reward": rewards.get("foot_clearance"),
            "standing_height_reward": rewards.get("standing_height"),
            "stance_width_mean_raw": rewards.get("stance_width_mean_raw"),
            "stance_width_front_raw": rewards.get("stance_width_front_raw"),
            "stance_width_rear_raw": rewards.get("stance_width_rear_raw"),
            "front_rear_stance_width_diff_raw": rewards.get("front_rear_stance_width_diff_raw"),
            "shoulder_fl_raw": rewards.get("shoulder_fl_raw"),
            "shoulder_fr_raw": rewards.get("shoulder_fr_raw"),
            "shoulder_rl_raw": rewards.get("shoulder_rl_raw"),
            "shoulder_rr_raw": rewards.get("shoulder_rr_raw"),
            "shoulder_mean_abs_dev_from_target_raw": rewards.get("shoulder_mean_abs_dev_from_target_raw") or rewards.get("shoulder_neutral"),
            "shoulder_left_right_diff_raw": rewards.get("shoulder_left_right_diff_raw") or rewards.get("shoulder_symmetry"),
            "shoulder_front_rear_diff_raw": rewards.get("shoulder_front_rear_diff_raw"),
            "base_height_raw": rewards.get("standing_height"),
            "body_roll_abs_raw": rewards.get("flat_orientation_l2"),
            "body_pitch_abs_raw": rewards.get("flat_orientation_l2"),
            "action_rate_l2_raw": rewards.get("action_rate_l2"),
            "joint_vel_l2_raw": rewards.get("joint_vel_l2"),
            "dof_acc_l2_raw": rewards.get("dof_acc_l2"),
            "joint_oscillation_raw": rewards.get("joint_oscillation"),
            "foot_extension_raw": rewards.get("foot_extension"),
            "stance_foot_jitter_score_raw": stance_foot_jitter_score_raw,
            "contact_transition_oscillation_score_estimated": rewards.get("joint_oscillation"),
            "front_leg_lift_mean_raw": rewards.get("front_leg_lift_mean_raw"),
            "rear_leg_lift_mean_raw": rewards.get("rear_leg_lift_mean_raw") or rewards.get("leg_lift"),
            "front_clearance_mean_raw": rewards.get("front_clearance_mean_raw"),
            "rear_clearance_mean_raw": rewards.get("rear_clearance_mean_raw") or rewards.get("foot_clearance"),
            "front_propulsion_score_raw": rewards.get("front_propulsion_score_raw"),
            "rear_propulsion_score_raw": rewards.get("rear_propulsion_score_raw") or rewards.get("rear_forward_stride"),
            "front_rear_propulsion_diff_raw": rewards.get("front_rear_propulsion_diff_raw"),
            "front_rear_clearance_diff_raw": rewards.get("front_rear_clearance_diff_raw"),
            "front_rear_swing_diff_raw": rewards.get("front_rear_swing_diff_raw"),
            "stride_length_raw": rewards.get("stride_length"),
            "gait_cycle_period_raw": rewards.get("gait_cycle_period"),
            "gait_score_canonical": kpi.get("gait_score"),
            "stability_score_canonical": kpi.get("stability_score"),
            "posture_style_score": posture_style_score,
            "foot_jitter_score": foot_jitter_score,
            "front_rear_balance_score": front_rear_balance_score,
            "hard_safety_gate_pass": gate_pass,
            "style_shortlist_candidate": False,
            "best_reward_candidate": False,
            "best_style_candidate": False,
            "manual_front_review_rank": None,
            "manual_notes": "",
        }
    )
    return row


def _build_v23_run_rows(run_dir: str) -> tuple[list[dict], dict, list[dict], list[dict]]:
    records = load_report_history(run_dir)
    data = read_tfevents(run_dir) or {}
    env_cfg = _load_yaml_config(os.path.join(run_dir, "params", "env.yaml"))
    agent_cfg = _load_yaml_config(os.path.join(run_dir, "params", "agent.yaml"))
    run_id = os.path.basename(run_dir)
    rows: list[dict] = []
    reward_window: list[float] = []
    for record in sorted(records, key=lambda item: int(item.get("iteration") or 0)):
        rows.append(_build_v23_row(record, run_dir, data, reward_window))
    if rows:
        best_reward_row = max(rows, key=lambda item: item.get("mean_reward") if item.get("mean_reward") is not None else float("-inf"))
        best_reward_row["best_reward_candidate"] = True
        style_rows = [row for row in rows if row.get("hard_safety_gate_pass")]
        for row in style_rows:
            row["style_shortlist_candidate"] = (row.get("posture_style_score") or 0.0) >= 65.0
        if style_rows:
            best_style_row = max(style_rows, key=lambda item: item.get("posture_style_score") if item.get("posture_style_score") is not None else float("-inf"))
            best_style_row["best_style_candidate"] = True
    meta = {
        "run_id": run_id,
        "train_version": V23_TRAIN_VERSION,
        "git_commit": _get_repo_git_commit(),
        "task_name": env_cfg.get("task_name") or TASK,
        "checkpoint_source": f"{agent_cfg.get('load_run') or 'fresh'}:{agent_cfg.get('load_checkpoint') or ''}" if agent_cfg.get("resume") else "fresh",
        "note": "V23 dedicated style/logging workbook",
        "resume": agent_cfg.get("resume"),
        "seed": agent_cfg.get("seed") or env_cfg.get("seed"),
        "num_envs": env_cfg.get("scene", {}).get("num_envs") if isinstance(env_cfg.get("scene"), dict) else None,
        "max_iterations": agent_cfg.get("max_iterations"),
    }
    events = []
    if agent_cfg.get("resume"):
        events.append({"timestamp": rows[0]["timestamp"] if rows else _now(), "event_type": "resume", "detail": meta["checkpoint_source"]})
    events.append({"timestamp": _now(), "event_type": "workbook_refresh", "detail": "V23 workbook refreshed"})
    review_rows = []
    for row in rows:
        if row.get("best_reward_candidate") or row.get("best_style_candidate") or row == rows[-1]:
            review_rows.append({
                "run_id": row["run_id"],
                "iter": row["iter"],
                "mean_reward": row["mean_reward"],
                "survival_pct": row["survival_pct"],
                "vf_loss": row["vf_loss"],
                "gait_score_canonical": row["gait_score_canonical"],
                "stability_score_canonical": row["stability_score_canonical"],
                "posture_style_score": row["posture_style_score"],
                "foot_jitter_score": row["foot_jitter_score"],
                "front_rear_balance_score": row["front_rear_balance_score"],
                "hard_safety_gate_pass": row["hard_safety_gate_pass"],
                "style_shortlist_candidate": row["style_shortlist_candidate"],
                "best_reward_candidate": row["best_reward_candidate"],
                "best_style_candidate": row["best_style_candidate"],
                "manual_front_review_rank": row["manual_front_review_rank"],
                "manual_notes": row["manual_notes"],
            })
    return rows, meta, events, review_rows


def _load_v23_rows_from_workbook(workbook_path: str) -> tuple[list[dict], list[dict]]:
    try:
        from openpyxl import load_workbook
    except Exception:
        return [], []
    if not os.path.isfile(workbook_path):
        return [], []
    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        run_rows: list[dict] = []
        review_rows: list[dict] = []
        if "RunLog_100iter" in wb.sheetnames:
            ws_run = wb["RunLog_100iter"]
            rows_iter = ws_run.iter_rows(values_only=True)
            headers = next(rows_iter, None)
            if headers:
                for values in rows_iter:
                    if values is None or not any(value is not None for value in values):
                        continue
                    run_rows.append({str(header): value for header, value in zip(headers, values) if header})
        if "CheckpointReview" in wb.sheetnames:
            ws_review = wb["CheckpointReview"]
            rows_iter = ws_review.iter_rows(values_only=True)
            headers = next(rows_iter, None)
            if headers:
                for values in rows_iter:
                    if values is None or not any(value is not None for value in values):
                        continue
                    review_rows.append({str(header): value for header, value in zip(headers, values) if header})
        return run_rows, review_rows
    finally:
        wb.close()


def _format_v23_run_list(run_names: list[str], limit: int = 5) -> str:
    if not run_names:
        return ""
    visible = run_names[:limit]
    suffix = ""
    if len(run_names) > limit:
        suffix = f" ... +{len(run_names) - limit} more"
    return ", ".join(visible) + suffix


def _export_v23_run_workbook(run_dir: str, log_path: str) -> tuple[str | None, list[dict], list[dict]]:
    rows, meta, events, review_rows = _build_v23_run_rows(run_dir)
    if not rows:
        return None, [], []
    workbook_path = export_v23_training_workbook(get_v23_run_log_path(run_dir), rows, meta, events, review_rows, log_path)
    return workbook_path, rows, review_rows


def backfill_v23_run_workbooks(log_path: str, max_runs: int | None = None, overwrite: bool = False) -> dict:
    created_runs: list[str] = []
    skipped_runs: list[str] = []
    failed_runs: list[str] = []
    processed = 0
    if not os.path.isdir(LOG_BASE):
        return {"created_runs": created_runs, "skipped_runs": skipped_runs, "failed_runs": failed_runs}
    candidate_run_names = []
    for run_name in sorted(os.listdir(LOG_BASE), reverse=True):
        candidate_run_dir = os.path.join(LOG_BASE, run_name)
        if not os.path.isdir(candidate_run_dir):
            continue
        if not os.path.isfile(get_heartbeat_history_path(candidate_run_dir)):
            continue
        candidate_run_names.append(run_name)
    for run_name in candidate_run_names:
        if max_runs is not None and processed >= max_runs:
            break
        processed += 1
        candidate_run_dir = os.path.join(LOG_BASE, run_name)
        workbook_path = get_v23_run_log_path(candidate_run_dir)
        if os.path.isfile(workbook_path) and not overwrite:
            skipped_runs.append(run_name)
            continue
        try:
            exported_path, rows, _review_rows = _export_v23_run_workbook(candidate_run_dir, log_path)
            if exported_path and rows:
                created_runs.append(run_name)
            else:
                skipped_runs.append(run_name)
        except Exception as err:
            failed_runs.append(run_name)
            write_log(f"V23 backfill failed for {run_name}: {err}", log_path)
    if created_runs:
        write_log(f"V23 backfill created {len(created_runs)} run workbooks: {_format_v23_run_list(created_runs)}", log_path)
    if failed_runs:
        write_log(f"V23 backfill failed for {len(failed_runs)} runs: {_format_v23_run_list(failed_runs)}", log_path)
    if skipped_runs:
        write_log(f"V23 backfill skipped {len(skipped_runs)} runs: {_format_v23_run_list(skipped_runs)}", log_path)
    return {
        "created_runs": created_runs,
        "skipped_runs": skipped_runs,
        "failed_runs": failed_runs,
        "processed_runs": processed,
    }


def _collect_v23_master_rows(current_run_dir: str, current_rows: list[dict], current_review_rows: list[dict], log_path: str) -> tuple[list[dict], list[dict], int, list[str]]:
    master_rows = list(current_rows)
    master_review_rows = list(current_review_rows)
    run_count = 1 if current_rows else 0
    skipped_runs: list[str] = []
    if not os.path.isdir(LOG_BASE):
        return master_rows, master_review_rows, run_count, skipped_runs
    current_run_id = os.path.basename(current_run_dir.rstrip("\\/"))
    for run_name in sorted(os.listdir(LOG_BASE)):
        candidate_run_dir = os.path.join(LOG_BASE, run_name)
        if not os.path.isdir(candidate_run_dir) or run_name == current_run_id:
            continue
        if not os.path.isfile(get_heartbeat_history_path(candidate_run_dir)):
            continue
        workbook_path = get_v23_run_log_path(candidate_run_dir)
        run_rows, run_review_rows = _load_v23_rows_from_workbook(workbook_path)
        if not run_rows:
            skipped_runs.append(run_name)
            continue
        run_count += 1
        master_rows.extend(run_rows)
        master_review_rows.extend(run_review_rows)
    return master_rows, master_review_rows, run_count, skipped_runs


def _write_v23_meta_sheet(ws, meta: dict, header_font) -> None:
    ws.title = "Meta"
    ws.append(["key", "value"])
    for cell in ws[1]:
        cell.font = header_font
    for key, value in meta.items():
        ws.append([key, value])
    ws.freeze_panes = "A2"


def _write_v23_events_sheet(ws, events: list[dict], header_font) -> None:
    ws.title = "Events"
    headers = ["timestamp", "event_type", "detail"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = header_font
    for event in events:
        ws.append([event.get("timestamp"), event.get("event_type"), event.get("detail")])
    ws.freeze_panes = "A2"


def _write_v23_review_sheet(ws, review_rows: list[dict], header_font) -> None:
    ws.title = "CheckpointReview"
    headers = [
        "run_id", "iter", "mean_reward", "survival_pct", "vf_loss", "gait_score_canonical", "stability_score_canonical",
        "posture_style_score", "foot_jitter_score", "front_rear_balance_score", "hard_safety_gate_pass",
        "style_shortlist_candidate", "best_reward_candidate", "best_style_candidate", "manual_front_review_rank", "manual_notes",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = header_font
    for row in review_rows:
        ws.append([row.get(header) for header in headers])
    ws.freeze_panes = "A2"


def _add_v23_chart_sheet(wb, runlog_headers: list[str], runlog_rows: list[dict], header_font) -> None:
    from openpyxl.chart import LineChart, Reference

    ws_chart = wb.create_sheet("Charts")
    ws_chart.append(runlog_headers)
    for cell in ws_chart[1]:
        cell.font = header_font
    for row in runlog_rows:
        ws_chart.append([row.get(header) for header in runlog_headers])
    ws_chart.freeze_panes = "A2"
    chart_groups = [
        ("CoreTraining", ["mean_reward", "mean_episode_length", "survival_pct", "fall_pct", "vf_loss"]),
        ("LocomotionCore", ["forward_velocity_raw", "trot_gait_raw", "diagonal_coupling_raw", "leg_lift_raw", "foot_clearance_raw", "standing_height_raw"]),
        ("PostureStyle", ["stance_width_mean_raw", "stance_width_front_raw", "stance_width_rear_raw", "shoulder_mean_abs_dev_from_target_raw", "body_roll_abs_raw", "body_pitch_abs_raw", "posture_style_score"]),
        ("MotionJitter", ["action_rate_l2_raw", "joint_vel_l2_raw", "dof_acc_l2_raw", "foot_joint_action_rate_l2_raw", "foot_joint_vel_l2_raw", "stance_foot_jitter_score_raw"]),
        ("FrontRearBalance", ["front_leg_lift_mean_raw", "rear_leg_lift_mean_raw", "front_clearance_mean_raw", "rear_clearance_mean_raw", "front_propulsion_score_raw", "rear_propulsion_score_raw", "front_rear_balance_score"]),
    ]
    if ws_chart.max_row < 2:
        return
    categories = Reference(ws_chart, min_col=runlog_headers.index("iter") + 1, min_row=2, max_row=ws_chart.max_row)
    for chart_index, (title, metric_names) in enumerate(chart_groups, start=1):
        available = [name for name in metric_names if name in runlog_headers]
        chart = LineChart()
        chart.title = title
        chart.style = 2
        chart.y_axis.title = "value"
        chart.x_axis.title = "iter"
        added = False
        for metric_name in available:
            col_idx = runlog_headers.index(metric_name) + 1
            has_value = any(isinstance(ws_chart.cell(row=row_idx, column=col_idx).value, (int, float)) for row_idx in range(2, ws_chart.max_row + 1))
            if not has_value:
                continue
            data_ref = Reference(ws_chart, min_col=col_idx, min_row=1, max_row=ws_chart.max_row)
            chart.add_data(data_ref, titles_from_data=True)
            added = True
        if not added:
            continue
        chart.set_categories(categories)
        ws_chart.add_chart(chart, f"A{1 + (chart_index - 1) * 18}")


def export_v23_training_workbook(out_path: str, rows: list[dict], meta: dict, events: list[dict], review_rows: list[dict], log_path: str) -> str | None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except Exception as err:
        write_log(f"V23 workbook skipped (openpyxl unavailable): {err}", log_path)
        return None
    wb = Workbook()
    ws_run = wb.active
    ws_run.title = "RunLog_100iter"
    header_font = Font(bold=True)
    ws_run.append(V23_RUNLOG_COLUMNS)
    for cell in ws_run[1]:
        cell.font = header_font
    for row in rows:
        ws_run.append([row.get(column) for column in V23_RUNLOG_COLUMNS])
    ws_run.freeze_panes = "A2"
    _write_v23_meta_sheet(wb.create_sheet("Meta"), meta, header_font)
    _write_v23_events_sheet(wb.create_sheet("Events"), events, header_font)
    _write_v23_review_sheet(wb.create_sheet("CheckpointReview"), review_rows, header_font)
    _add_v23_chart_sheet(wb, V23_RUNLOG_COLUMNS, rows, header_font)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    write_log(f"V23 workbook exported: {out_path}", log_path)
    return out_path


def export_v23_checkpoint_review_workbook(out_path: str, review_rows: list[dict], log_path: str) -> str | None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except Exception as err:
        write_log(f"V23 checkpoint review skipped (openpyxl unavailable): {err}", log_path)
        return None
    wb = Workbook()
    header_font = Font(bold=True)
    _write_v23_review_sheet(wb.active, review_rows, header_font)
    wb.active.title = "CheckpointReview"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    write_log(f"V23 checkpoint review exported: {out_path}", log_path)
    return out_path


def refresh_v23_training_logs(run_dir: str, log_path: str) -> dict:
    run_log_path, rows, review_rows = _export_v23_run_workbook(run_dir, log_path)
    if not run_log_path or not rows:
        return {}
    master_rows, master_review_rows, run_count, skipped_runs = _collect_v23_master_rows(run_dir, rows, review_rows, log_path)
    master_rows.sort(key=lambda item: (str(item.get("run_id") or ""), int(item.get("iter") or 0)))
    master_meta = {
        "train_version": V23_TRAIN_VERSION,
        "generated_at": _now(),
        "run_count": run_count,
        "log_root": LOG_BASE,
        "note": "Master workbook rebuilt from per-run heartbeat history",
        "skipped_run_count": len(skipped_runs),
    }
    master_events = [{"timestamp": _now(), "event_type": "workbook_refresh", "detail": f"runs={run_count}; skipped={len(skipped_runs)}"}]
    master_log_path = export_v23_training_workbook(get_v23_master_log_path(), master_rows, master_meta, master_events, master_review_rows, log_path)
    checkpoint_review_path = export_v23_checkpoint_review_workbook(get_v23_checkpoint_review_path(), master_review_rows, log_path)
    if skipped_runs:
        write_log(f"V23 master refresh skipped {len(skipped_runs)} historical runs without cached workbook: {_format_v23_run_list(skipped_runs)}", log_path)
    return {
        "run_log_path": run_log_path,
        "master_log_path": master_log_path,
        "checkpoint_review_path": checkpoint_review_path,
        "skipped_runs": skipped_runs,
    }


def format_report(data: dict, run_name: str, cycle_num: int) -> str:
    reward_vals = data.get("Train/mean_reward", [])
    ep_len_vals = data.get("Train/mean_episode_length", [])
    run_label = html.escape(str(run_name))
    match = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$", str(run_name or ""))
    if match:
        run_label = f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4)}"
    if not reward_vals:
        return f"⚠️ <b>HEARTBEAT</b> ({run_label})\n- metrics unavailable"
    current_iter = int(reward_vals[-1][0])
    run_dir = os.path.join(LOG_BASE, run_name)
    kpi = build_supervisor_kpi_snapshot(run_dir) if os.path.isdir(run_dir) else build_supervisor_kpi_snapshot(resolve_active_run_dir() or "")
    rewards = {}
    for tag, values in data.items():
        if tag.startswith("Episode_Reward/") and values:
            rewards[tag.replace("Episode_Reward/", "")] = float(values[-1][1])
    progress_pct = (current_iter / MAX_ITERATIONS * 100.0) if MAX_ITERATIONS > 0 else 0.0
    reasons = kpi.get("reasons") or []
    trend_defs = [
        ("trot_gait", "트로트"),
        ("diagonal_coupling", "대각커플링"),
        ("forward_velocity", "전진속도"),
        ("standing_height", "기립높이"),
    ]
    trend_lines = []
    for metric_name, label in trend_defs:
        tag = f"Episode_Reward/{metric_name}"
        values = data.get(tag, [])
        if not values:
            continue
        icon, pct = _trend_icon_and_pct(values)
        trend_lines.append(f"- {icon} {label}: {pct:+.1f}%")

    posture_raw_lines = []
    posture_candidates = [
        ("stance_width_mean_raw", "stance_width_mean"),
        ("shoulder_mean_abs_dev_from_target_raw", "shoulder_dev"),
        ("body_roll_abs_raw", "body_roll_abs"),
        ("body_pitch_abs_raw", "body_pitch_abs"),
    ]
    for metric_name, label in posture_candidates:
        value = rewards.get(metric_name)
        numeric = _safe_float(value, digits=4)
        if numeric is None:
            continue
        posture_raw_lines.append(f"- {label}: {numeric:+.4f}")

    stability_text = (
        f"{html.escape(str(kpi['stability']))} ({int(kpi['stability_score'] or 0)}/10)"
        if kpi.get("stability_valid")
        else html.escape(str(kpi["stability"]))
    )
    summary_lines = _build_heartbeat_summary(
        current_iter=current_iter,
        rewards=rewards,
        survival_pct=float(kpi.get("survival_pct") or 0.0),
        timeout_pct=float(kpi.get("timeout_pct") or 0.0),
        fall_pct=float(kpi.get("fall_pct") or 0.0),
        gait_grade=str(kpi.get("gait") or "N/A"),
        gait_score=int(kpi.get("gait_score") or 0),
        stab_grade=str(kpi.get("stability") or "N/A"),
        stab_score=int(kpi.get("stability_score") or 0),
        stab_valid=bool(kpi.get("stability_valid")),
        posture_grade=str(kpi.get("posture") or "N/A"),
        posture_score=int(kpi.get("posture_score") or 0),
    )

    lines = [
        f"💓 <b>HEARTBEAT</b> ({run_label})",
        "",
        f"- iter: {current_iter:,} / {MAX_ITERATIONS:,} ({progress_pct:.1f}%)",
        f"- reward: {float(kpi.get('reward') or 0.0):.3f} (avg10: {float(kpi.get('reward_avg10') or 0.0):.3f})",
        f"- ep_len: {float(kpi.get('ep_len') or 0.0):.1f} | survival: {float(kpi.get('survival_pct') or 0.0):.1f}%",
        f"- termination: timeout {float(kpi.get('timeout_pct') or 0.0):.0f}% / fall {float(kpi.get('fall_pct') or 0.0):.0f}%",
        "",
        f"- 운영 판정: {html.escape(str(kpi['verdict']))}",
    ]
    for reason in reasons[:2]:
        lines.append(f"  - {html.escape(str(reason))}")
    lines.extend(
        [
            "",
            "- 코어 품질",
            f"  - gait: {html.escape(str(kpi['gait']))} ({int(kpi['gait_score'] or 0)}/13)",
            f"  - stability: {stability_text}",
            f"  - posture/style: {html.escape(str(kpi.get('posture') or 'N/A'))} ({int(kpi.get('posture_score') or 0)}/10)",
        ]
    )
    foot_jitter_score = kpi.get("foot_jitter_score")
    if foot_jitter_score is not None:
        lines.append(f"  - foot_jitter: {float(foot_jitter_score):.1f}/100")
    lines.extend(
        [
            "",
            "- KPI 상태",
        ]
    )
    for metric_name, label in [
        ("standing_height", "기립"),
        ("forward_velocity", "전진"),
        ("diagonal_coupling", "대각커플링"),
    ]:
        icon, state = classify_primary_kpi(metric_name, rewards.get(metric_name, 0.0))
        lines.append(f"  - {icon} {label} {state}")
    posture_icon, posture_state = classify_posture_metric("flat_orientation_l2", rewards.get("flat_orientation_l2", 0.0))
    lines.append(f"  - {posture_icon} 자세수평 {posture_state}")
    if trend_lines:
        lines.extend(["", "- 핵심 추세"])
        lines.extend(f"  {line}" for line in trend_lines)
    if posture_raw_lines:
        lines.extend(["", "- posture/raw"])
        lines.extend(f"  {line}" for line in posture_raw_lines)
    if summary_lines:
        lines.extend(["", "- 해석"])
        lines.extend(f"  {html.escape(text)}" for text in summary_lines)
    lines.extend(
        [
            "",
            "- 참고",
            "  - contact stride/cycle은 참고 지표로만 취급",
            f"  - next report: iter {((current_iter // HEARTBEAT_ITER_STEP) + 1) * HEARTBEAT_ITER_STEP:,}",
        ]
    )
    return "\n".join(lines)


def parse_analysis_grade(text: str) -> dict:
    result = {"Grade": "N/A", "Score": 0, "Reward": 0, "Iter": 0, "Trend": "N/A", "GradeLetter": "?"}
    if not text:
        return result
    match = re.search(r"종합\s+등급:\s*(\w)\s+\(([^)]+)\)\s+\(점수:\s*(\d+)/13\)", text)
    if not match:
        match = re.search(r"(\w)\s+\(([^)]+)\)\s+\([^:]*:\s*(\d+)/13\)", text)
    if match:
        result["GradeLetter"] = match.group(1)
        result["Grade"] = f"{match.group(1)} ({match.group(2)})"
        result["Score"] = int(match.group(3))
    match = re.search(r"Mean Reward:\s*([-\d.]+)", text)
    if match:
        result["Reward"] = float(match.group(1))
    match = re.search(r"Current Iteration:\s*([\d,]+)", text)
    if match:
        result["Iter"] = int(match.group(1).replace(",", ""))
    match = re.search(r"Reward Trend:\s*(.+)", text)
    if match:
        trend = re.sub(r"[^\x20-\x7E가-힣()%+\-.\d]+", "", match.group(1).strip()).strip()
        result["Trend"] = trend
    return result


def reencode_video(src_path: str, target_fps: int, log_path: str) -> str:
    if target_fps >= 25:
        return src_path
    tmp_py = os.path.join(PROJECT_ROOT, "logs", "_reencode_tmp.py")
    out_path = re.sub(r"\.mp4$", f"_{target_fps}fps.mp4", src_path)
    py_code = f"""
import av
from fractions import Fraction

src = r{src_path!r}
dst = r{out_path!r}
target_fps = {target_fps}

inp = av.open(src)
in_stream = inp.streams.video[0]
out = av.open(dst, mode='w')
out_stream = out.add_stream('h264', rate=target_fps)
out_stream.width = in_stream.width
out_stream.height = in_stream.height
out_stream.pix_fmt = 'yuv420p'
out_stream.time_base = Fraction(1, target_fps)
out_stream.options = {{'crf': '18', 'preset': 'medium'}}

count = 0
for frame in inp.decode(video=0):
    new_frame = frame.reformat(format='yuv420p')
    new_frame.pts = count
    new_frame.time_base = Fraction(1, target_fps)
    for packet in out_stream.encode(new_frame):
        out.mux(packet)
    count += 1

for packet in out_stream.encode():
    out.mux(packet)

out.close()
inp.close()
"""
    try:
        with open(tmp_py, "w", encoding="utf-8") as file:
            file.write(py_code)
        write_log(f"Re-encoding video to {target_fps}fps: {os.path.basename(src_path)}", log_path)
        proc = _run_hidden_cmd(
            _wrap_conda_command(f'set PYTHONIOENCODING=utf-8 && python "{tmp_py}"'),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            write_log(
                f"Re-encode failed for {os.path.basename(src_path)}: rc={proc.returncode} {stderr or stdout}",
                log_path,
            )
            return src_path
        if not os.path.isfile(out_path):
            write_log(f"Re-encode output missing for {os.path.basename(src_path)}", log_path)
            return src_path
        try:
            os.remove(src_path)
        except OSError:
            pass
        shutil.move(out_path, src_path)
        return src_path
    except Exception as err:
        write_log(f"Re-encode error for {os.path.basename(src_path)}: {err}", log_path)
        return src_path
    finally:
        try:
            os.remove(tmp_py)
        except OSError:
            pass
        try:
            os.remove(out_path)
        except OSError:
            pass


def export_heartbeat_history_xlsx(run_dir: str, out_path: str, log_path: str) -> str | None:
    try:
        from openpyxl import Workbook
        from openpyxl.chart import LineChart, Reference
        from openpyxl.styles import Font
    except Exception as err:
        write_log(f"Heartbeat XLSX skipped (openpyxl unavailable): {err}", log_path)
        return None

    records = load_report_history(run_dir)
    scalar_data = read_tfevents(run_dir) or {}
    scalar_maps = {tag: {int(step): value for step, value in values} for tag, values in scalar_data.items()}

    def _flatten_value_rows(prefix: str, value) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        if isinstance(value, dict):
            for key, nested_value in value.items():
                child_prefix = f"{prefix}.{key}" if prefix else str(key)
                rows.extend(_flatten_value_rows(child_prefix, nested_value))
            return rows
        if isinstance(value, (list, tuple)):
            if all(not isinstance(item, (dict, list, tuple)) for item in value):
                rows.append((prefix, ", ".join(str(item) for item in value)))
                return rows
            for index, nested_value in enumerate(value):
                child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
                rows.extend(_flatten_value_rows(child_prefix, nested_value))
            return rows
        rows.append((prefix, "" if value is None else str(value)))
        return rows

    def _load_param_rows(file_path: str) -> list[tuple[str, str]]:
        if not os.path.isfile(file_path):
            return []
        try:
            import yaml

            with open(file_path, "r", encoding="utf-8") as file:
                try:
                    data = yaml.safe_load(file)
                except Exception:
                    file.seek(0)
                    data = yaml.unsafe_load(file)
            return _flatten_value_rows("", data)
        except Exception as err:
            write_log(f"Parameter sheet fallback for {os.path.basename(file_path)}: {err}", log_path)
        rows: list[tuple[str, str]] = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            for line_no, line in enumerate(file, start=1):
                rows.append((f"line_{line_no:04d}", line.rstrip("\n")))
        return rows

    def _write_kv_sheet(ws, title: str, rows: list[tuple[str, str]], header_font) -> None:
        ws.title = title
        ws.append(["key", "value"])
        for cell in ws[1]:
            cell.font = header_font
        for key, value in rows:
            ws.append([key, value])
        ws.freeze_panes = "A2"

    column_specs = [
        ("timestamp", "timestamp"),
        ("report_kind", "report_kind"),
        ("cycle_num", "cycle_num"),
        ("iteration", "iteration"),
        ("mean_reward", "mean_reward"),
        ("mean_episode_length", "mean_episode_length"),
        ("survival_pct", "survival_pct"),
        ("gait_score", "gait_score"),
        ("stability_score", "stability_score"),
        ("posture_style_score", "posture_style_score"),
        ("verdict", "verdict"),
        ("standing_height", ("primary_metrics", "standing_height")),
        ("forward_velocity", ("primary_metrics", "forward_velocity")),
        ("diagonal_coupling", ("primary_metrics", "diagonal_coupling")),
        ("trot_gait", ("primary_metrics", "trot_gait")),
        ("rear_joint_velocity", ("primary_metrics", "rear_joint_velocity")),
        ("foot_clearance", ("primary_metrics", "foot_clearance")),
        ("shoulder_neutral", ("primary_metrics", "shoulder_neutral")),
        ("shoulder_symmetry", ("primary_metrics", "shoulder_symmetry")),
        ("stance_width_penalty", ("primary_metrics", "stance_width_penalty")),
        ("joint_vel_l2", ("penalties", "joint_vel_l2")),
        ("action_rate_l2", ("penalties", "action_rate_l2")),
        ("dof_acc_l2", ("penalties", "dof_acc_l2")),
        ("ang_vel_xy_l2", ("penalties", "ang_vel_xy_l2")),
        ("flat_orientation_l2", ("penalties", "flat_orientation_l2")),
    ]

    def _resolve_record_value(record: dict, accessor):
        if isinstance(accessor, tuple):
            node = record.get(accessor[0], {}) or {}
            return node.get(accessor[1]) if isinstance(node, dict) else None
        return record.get(accessor)

    rows = []
    if records:
        for record in records:
            row = {}
            for column_name, accessor in column_specs:
                row[column_name] = _resolve_record_value(record, accessor)
            rows.append(row)
    else:
        reward_vals = scalar_data.get("Train/mean_reward", [])
        for step, reward_value in reward_vals:
            step = int(step)
            rows.append(
                {
                    "timestamp": "",
                    "report_kind": "tfevents",
                    "cycle_num": "",
                    "iteration": step,
                    "mean_reward": reward_value,
                    "mean_episode_length": scalar_maps.get("Train/mean_episode_length", {}).get(step),
                    "survival_pct": scalar_maps.get("Episode_Termination/time_out", {}).get(step),
                    "gait_score": None,
                    "stability_score": None,
                    "posture_style_score": None,
                    "verdict": "",
                    "standing_height": scalar_maps.get("Episode_Reward/standing_height", {}).get(step),
                    "forward_velocity": scalar_maps.get("Episode_Reward/forward_velocity", {}).get(step),
                    "diagonal_coupling": scalar_maps.get("Episode_Reward/diagonal_coupling", {}).get(step),
                    "trot_gait": scalar_maps.get("Episode_Reward/trot_gait", {}).get(step),
                    "rear_joint_velocity": scalar_maps.get("Episode_Reward/rear_joint_velocity", {}).get(step),
                    "foot_clearance": scalar_maps.get("Episode_Reward/foot_clearance", {}).get(step),
                    "shoulder_neutral": scalar_maps.get("Episode_Reward/shoulder_neutral", {}).get(step),
                    "shoulder_symmetry": scalar_maps.get("Episode_Reward/shoulder_symmetry", {}).get(step),
                    "stance_width_penalty": scalar_maps.get("Episode_Reward/stance_width_penalty", {}).get(step),
                    "joint_vel_l2": scalar_maps.get("Episode_Reward/joint_vel_l2", {}).get(step),
                    "action_rate_l2": scalar_maps.get("Episode_Reward/action_rate_l2", {}).get(step),
                    "dof_acc_l2": scalar_maps.get("Episode_Reward/dof_acc_l2", {}).get(step),
                    "ang_vel_xy_l2": scalar_maps.get("Episode_Reward/ang_vel_xy_l2", {}).get(step),
                    "flat_orientation_l2": scalar_maps.get("Episode_Reward/flat_orientation_l2", {}).get(step),
                }
            )

    if not rows:
        write_log("Heartbeat XLSX skipped: no history rows available", log_path)
        return None

    wb = Workbook()
    ws_overview = wb.active
    ws_overview.title = "Overview"
    ws_trends = wb.create_sheet("Trends")
    ws_raw = wb.create_sheet("RawData")
    ws_scalar_stats = wb.create_sheet("ScalarStats")
    ws_scalar_series = wb.create_sheet("ScalarSeries")
    ws_env = wb.create_sheet("EnvParams")
    ws_agent = wb.create_sheet("AgentParams")
    ws_report = wb.create_sheet("ReportMeta")
    header_font = Font(bold=True)
    headers = [column_name for column_name, _ in column_specs]

    ws_raw.append(headers)
    for cell in ws_raw[1]:
        cell.font = header_font
    for row in rows:
        ws_raw.append([row.get(header) for header in headers])
    ws_raw.freeze_panes = "A2"

    metrics = [
        "mean_reward",
        "mean_episode_length",
        "standing_height",
        "forward_velocity",
        "diagonal_coupling",
        "trot_gait",
        "rear_joint_velocity",
        "foot_clearance",
    ]
    ws_overview.append(["metric", "latest", "first", "delta"])
    for cell in ws_overview[1]:
        cell.font = header_font
    for metric in metrics:
        values = [row.get(metric) for row in rows if isinstance(row.get(metric), (int, float))]
        if not values:
            ws_overview.append([metric, None, None, None])
            continue
        ws_overview.append([metric, values[-1], values[0], values[-1] - values[0]])
    ws_overview.freeze_panes = "A2"

    trend_headers = ["iteration"] + metrics
    ws_trends.append(trend_headers)
    for cell in ws_trends[1]:
        cell.font = header_font
    for row in rows:
        ws_trends.append([row.get("iteration")] + [row.get(metric) for metric in metrics])
    ws_trends.freeze_panes = "A2"

    ws_scalar_stats.append(["tag", "last", "first", "min", "max", "delta", "points"])
    for cell in ws_scalar_stats[1]:
        cell.font = header_font
    for tag in sorted(scalar_data):
        values = scalar_data.get(tag) or []
        if not values:
            continue
        numeric_values = [float(value) for _, value in values]
        ws_scalar_stats.append(
            [
                tag,
                numeric_values[-1],
                numeric_values[0],
                min(numeric_values),
                max(numeric_values),
                numeric_values[-1] - numeric_values[0],
                len(numeric_values),
            ]
        )
    ws_scalar_stats.freeze_panes = "A2"

    scalar_chart_groups = [
        ("TrainReward", ["Train/mean_reward", "Train/mean_episode_length"]),
        ("PrimaryReward", [
            "Episode_Reward/standing_height",
            "Episode_Reward/forward_velocity",
            "Episode_Reward/diagonal_coupling",
            "Episode_Reward/trot_gait",
        ]),
        ("SupportReward", [
            "Episode_Reward/rear_joint_velocity",
            "Episode_Reward/foot_clearance",
            "Episode_Reward/shoulder_neutral",
            "Episode_Reward/shoulder_symmetry",
        ]),
        ("Penalty", [
            "Episode_Reward/joint_vel_l2",
            "Episode_Reward/action_rate_l2",
            "Episode_Reward/dof_acc_l2",
            "Episode_Reward/ang_vel_xy_l2",
            "Episode_Reward/flat_orientation_l2",
        ]),
        ("Termination", [
            "Episode_Termination/time_out",
            "Episode_Termination/bad_orientation",
        ]),
    ]
    selected_tags = []
    for _, tags in scalar_chart_groups:
        for tag in tags:
            if tag in scalar_data and tag not in selected_tags:
                selected_tags.append(tag)
    selected_steps = sorted({int(step) for tag in selected_tags for step, _ in scalar_data.get(tag, [])})
    ws_scalar_series.append(["iteration"] + selected_tags)
    for cell in ws_scalar_series[1]:
        cell.font = header_font
    selected_maps = {tag: {int(step): value for step, value in scalar_data.get(tag, [])} for tag in selected_tags}
    for step in selected_steps:
        ws_scalar_series.append([step] + [selected_maps[tag].get(step) for tag in selected_tags])
    ws_scalar_series.freeze_panes = "A2"

    report_rows = [
        ("run_dir", os.path.basename(run_dir)),
        ("checkpoint", os.path.basename(get_latest_checkpoint(run_dir) or "")),
        ("latest_iteration", str(rows[-1].get("iteration") if rows else "")),
        ("history_rows", str(len(rows))),
        ("scalar_tags", str(len(scalar_data))),
    ]
    _write_kv_sheet(ws_report, "ReportMeta", report_rows, header_font)
    _write_kv_sheet(ws_env, "EnvParams", _load_param_rows(os.path.join(run_dir, "params", "env.yaml")), header_font)
    _write_kv_sheet(ws_agent, "AgentParams", _load_param_rows(os.path.join(run_dir, "params", "agent.yaml")), header_font)

    chart_specs = [
        ("Reward", ["mean_reward", "mean_episode_length"]),
        ("Gait", ["forward_velocity", "diagonal_coupling", "trot_gait", "foot_clearance"]),
    ]
    for chart_index, (title, metric_names) in enumerate(chart_specs, start=1):
        chart = LineChart()
        chart.title = title
        chart.style = 2
        chart.y_axis.title = "value"
        chart.x_axis.title = "iteration"
        categories = Reference(ws_trends, min_col=1, min_row=2, max_row=ws_trends.max_row)
        for metric_name in metric_names:
            col_idx = trend_headers.index(metric_name) + 1
            data_ref = Reference(ws_trends, min_col=col_idx, min_row=1, max_row=ws_trends.max_row)
            chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(categories)
        ws_overview.add_chart(chart, f"F{1 + (chart_index - 1) * 15}")

    for chart_index, (title, metric_names) in enumerate(scalar_chart_groups, start=1):
        available_names = [name for name in metric_names if name in selected_tags]
        if not available_names or ws_scalar_series.max_row < 2:
            continue
        chart = LineChart()
        chart.title = title
        chart.style = 2
        chart.y_axis.title = "value"
        chart.x_axis.title = "iteration"
        categories = Reference(ws_scalar_series, min_col=1, min_row=2, max_row=ws_scalar_series.max_row)
        for metric_name in available_names:
            col_idx = selected_tags.index(metric_name) + 2
            data_ref = Reference(ws_scalar_series, min_col=col_idx, min_row=1, max_row=ws_scalar_series.max_row)
            chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(categories)
        ws_overview.add_chart(chart, f"P{1 + (chart_index - 1) * 15}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    wb.save(out_path)
    write_log(f"Heartbeat XLSX exported: {out_path}", log_path)
    return out_path


def _build_play_command(
    checkpoint_path: str,
    play_script: str,
    camera_view: str,
    camera_zoom: float,
    num_envs: int,
    headless: bool,
) -> str:
    command = (
        f'cd /d "{PROJECT_ROOT}" && '
        'set PYTHONIOENCODING=utf-8 && '
        f'"{ISAAC_LAB}" -p "{play_script}" '
        f'--task={TASK} --num_envs={num_envs} '
        f'--checkpoint="{checkpoint_path}" --video --video_length={VIDEO_LENGTH} '
        f'--camera_view={camera_view} --camera_zoom={camera_zoom}'
    )
    if headless:
        command += " --headless"
    return _wrap_conda_command(command)


def record_video_bundle(checkpoint_path: str, run_dir: str, clip_num: int, log_path: str, headless: bool) -> dict[str, str]:
    play_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "play.py")
    iter_num = get_checkpoint_iter(checkpoint_path)
    captured_videos: dict[str, str] = {}
    for spec in get_video_capture_specs(PLAY_ENVS):
        pre_videos = _snapshot_play_videos(run_dir)
        play_cmd = _build_play_command(
            checkpoint_path=checkpoint_path,
            play_script=play_script,
            camera_view=spec["camera_view"],
            camera_zoom=spec["camera_zoom"],
            num_envs=spec["num_envs"],
            headless=headless,
        )
        mode_label = "headless" if headless else "gui"
        write_log(f"Recording {spec['key']} ({mode_label}): {play_cmd}", log_path)
        capture_log_dir = os.path.join(PROJECT_ROOT, "logs", "video_capture")
        os.makedirs(capture_log_dir, exist_ok=True)
        capture_log_path = os.path.join(
            capture_log_dir,
            f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{spec['key']}_{mode_label}.log",
        )
        started_at = time.time()
        with open(capture_log_path, "wb") as capture_log_file:
            proc = _popen_hidden_cmd(play_cmd, stdout=capture_log_file, stderr=subprocess.STDOUT)
            timeout = time.time() + 480
            while proc.poll() is None and time.time() < timeout:
                time.sleep(5)

            timed_out = proc.poll() is None
            if timed_out:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
                except Exception:
                    pass

            elapsed = time.time() - started_at
            rc = proc.poll()
        if timed_out:
            write_log(f"Recording {spec['key']} timed out after {elapsed:.1f}s", log_path)
            tail = _read_text_tail(capture_log_path)
            if tail:
                write_log(f"Recording {spec['key']} log tail:\n{tail}", log_path)
            continue
        log_tail_text = ""
        if rc not in (0, None):
            write_log(f"Recording {spec['key']} exited with rc={rc} after {elapsed:.1f}s", log_path)
            log_tail_text = _read_text_tail(capture_log_path)
            if log_tail_text:
                write_log(f"Recording {spec['key']} log tail:\n{log_tail_text}", log_path)

        latest_video = _find_updated_play_video(run_dir, pre_videos)
        if not latest_video:
            write_log(f"Recording {spec['key']} failed: no new or updated MP4 was detected", log_path)
            if not log_tail_text:
                log_tail_text = _read_text_tail(capture_log_path)
                if log_tail_text:
                    write_log(f"Recording {spec['key']} log tail:\n{log_tail_text}", log_path)
            continue

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"clip_{clip_num}_iter{iter_num}_{spec['key']}_{ts}.mp4"
        dest_path = os.path.join(run_dir, "videos", new_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(latest_video, dest_path)
        dest_path = reencode_video(dest_path, VIDEO_FPS, log_path)
        try:
            digest = _sha256_file(dest_path)[:12]
            size = os.path.getsize(dest_path)
            write_log(f"Captured {spec['key']} -> {os.path.basename(dest_path)} ({size} bytes, sha256={digest}...)", log_path)
        except Exception:
            pass
        captured_videos[spec["key"]] = dest_path
    return captured_videos


def capture_videos_with_validation(checkpoint_path: str, run_dir: str, clip_num: int, log_path: str) -> dict[str, str]:
    attempt_modes = [VIDEO_CAPTURE_HEADLESS]
    if VIDEO_CAPTURE_FALLBACK_GUI and VIDEO_CAPTURE_HEADLESS:
        attempt_modes.append(False)

    last_error = ""
    for attempt_index, headless in enumerate(attempt_modes, start=1):
        mode_label = "headless" if headless else "gui"
        write_log(f"Video capture attempt {attempt_index}/{len(attempt_modes)} mode={mode_label}", log_path)
        captured_videos = record_video_bundle(
            checkpoint_path=checkpoint_path,
            run_dir=run_dir,
            clip_num=clip_num,
            log_path=log_path,
            headless=headless,
        )
        if not captured_videos:
            last_error = f"No videos were generated in {mode_label} mode."
            write_log(last_error, log_path)
            continue

        if VIDEO_REQUIRE_DISTINCT_VIEWS:
            duplicates = _find_duplicate_video_hashes(captured_videos)
            if duplicates:
                duplicate_groups = ", ".join("/".join(view_keys) for view_keys in duplicates.values())
                last_error = f"Duplicate video content detected across views: {duplicate_groups}"
                write_log(last_error, log_path)
                if headless and VIDEO_CAPTURE_FALLBACK_GUI:
                    write_log("Retrying video capture without headless mode due to duplicate hashes.", log_path)
                    continue
                raise RuntimeError(last_error)
        return captured_videos

    raise RuntimeError(last_error or "No videos were generated.")


def select_representative_video(captured_videos: dict[str, str]) -> str | None:
    for preferred_key in ("side", "overview", "rear", "top"):
        if preferred_key in captured_videos:
            return captured_videos[preferred_key]
    return next(iter(captured_videos.values()), None)


def run_detailed_analysis(run_dir: str, checkpoint_path: str, clip_num: int, video_path: str | None) -> str:
    del checkpoint_path, video_path
    if not os.path.isfile(ANALYZE_SCRIPT):
        return ""
    try:
        proc = subprocess.run(
            [sys.executable, ANALYZE_SCRIPT, "--run_dir", run_dir, "--clip_num", str(clip_num)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        text = proc.stdout or ""
        if proc.stderr.strip():
            write_log(f"Analysis stderr: {proc.stderr[:500]}", SUPERVISOR_LOG)
        return text
    except Exception as err:
        write_log(f"Analysis error: {err}", SUPERVISOR_LOG)
        return ""


def create_clip_artifact_zip(run_dir: str, checkpoint_path: str, clip_num: int, captured_videos: dict[str, str], kpi_snapshot: dict, analysis_text: str) -> dict | None:
    if not captured_videos:
        return None
    iter_num = get_checkpoint_iter(checkpoint_path)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_dir = os.path.join(run_dir, "artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    zip_path = os.path.join(artifact_dir, f"clip_{clip_num}_iter{iter_num}_{timestamp}.zip")
    heartbeat_xlsx_path = export_heartbeat_history_xlsx(
        run_dir,
        os.path.join(artifact_dir, f"clip_{clip_num}_iter{iter_num}_{timestamp}_heartbeat_history.xlsx"),
        SUPERVISOR_LOG,
    )
    v23_paths = refresh_v23_training_logs(run_dir, SUPERVISOR_LOG)
    v23_run_log_path = v23_paths.get("run_log_path") if v23_paths else None
    if REPORT_REQUIRE_XLSX and (not heartbeat_xlsx_path or not os.path.isfile(heartbeat_xlsx_path)):
        raise RuntimeError("Heartbeat XLSX export failed.")
    manifest = {
        "clip_num": clip_num,
        "iteration": iter_num,
        "checkpoint": os.path.basename(checkpoint_path),
        "run_dir": os.path.basename(run_dir),
        "videos": {key: os.path.basename(path) for key, path in captured_videos.items()},
        "heartbeat_history_xlsx": "heartbeat_history.xlsx" if heartbeat_xlsx_path and os.path.isfile(heartbeat_xlsx_path) else None,
        "v23_run_log_xlsx": os.path.basename(v23_run_log_path) if v23_run_log_path and os.path.isfile(v23_run_log_path) else None,
        "kpi_snapshot": kpi_snapshot,
        "analysis": parse_analysis_grade(analysis_text),
    }
    summary_text = (
        f"clip_num={clip_num}\n"
        f"iteration={iter_num}\n"
        f"checkpoint={os.path.basename(checkpoint_path)}\n"
        f"run_dir={os.path.basename(run_dir)}\n"
        f"verdict={kpi_snapshot['verdict']}\n"
        f"kpi_line={kpi_snapshot['kpi_line']}\n"
        f"reason={kpi_snapshot['reason']}\n"
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.txt", summary_text)
        archive.writestr("analysis_report.txt", analysis_text.strip() + "\n" if analysis_text.strip() else "Analysis output unavailable\n")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        if heartbeat_xlsx_path and os.path.isfile(heartbeat_xlsx_path):
            archive.write(heartbeat_xlsx_path, "metrics/heartbeat_history.xlsx")
        if v23_run_log_path and os.path.isfile(v23_run_log_path):
            archive.write(v23_run_log_path, f"metrics/{os.path.basename(v23_run_log_path)}")
        for key, path in captured_videos.items():
            if path and os.path.isfile(path):
                archive.write(path, f"videos/{key}_{os.path.basename(path)}")
    return {"zip_path": zip_path, "xlsx_path": heartbeat_xlsx_path}


def _cache_matches_current_schema(state: dict) -> bool:
    return int(state.get("cache_schema_version") or 0) == CACHE_SCHEMA_VERSION


def _report_zip_meets_requirements(zip_path: str) -> bool:
    if not zip_path or not os.path.isfile(zip_path):
        return False
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = set(archive.namelist())
        return (
            "metrics/heartbeat_history.xlsx" in names
            and any(name.startswith("metrics/spotmicro_v23_run_") and name.endswith("_training_log.xlsx") for name in names)
        )
    except Exception:
        return False


def _checkpoint_matches_cached(checkpoint_path: str, cached_checkpoint: str, file_map: dict | None) -> bool:
    if not checkpoint_path or checkpoint_path != cached_checkpoint or not file_map:
        return False
    return all(path and os.path.isfile(path) for path in file_map.values())


def ensure_current_videos(run_dir: str, checkpoint_path: str, log_path: str, force: bool = False) -> dict[str, str]:
    state = load_state()
    cached_videos = state.get("last_videos") or {}
    if (
        not force
        and _cache_matches_current_schema(state)
        and _checkpoint_matches_cached(checkpoint_path, state.get("last_video_checkpoint") or "", cached_videos)
    ):
        return cached_videos
    iter_num = get_checkpoint_iter(checkpoint_path)
    clip_num = max(1, iter_num)
    write_log(f"Generating current videos for iter {iter_num}", log_path)
    captured_videos = capture_videos_with_validation(checkpoint_path, run_dir, clip_num, log_path)
    if not captured_videos:
        raise RuntimeError("No videos were generated.")
    update_state(
        mode="stopped",
        active_run=os.path.basename(run_dir),
        active_checkpoint=checkpoint_path,
        last_videos=captured_videos,
        last_video_checkpoint=checkpoint_path,
    )
    return captured_videos


def stop_and_report(run_dir: str, checkpoint_path: str, log_path: str, force: bool = False) -> dict:
    state = load_state()
    cached_zip = state.get("last_report_zip") or ""
    cached_report_checkpoint = state.get("last_report_checkpoint") or ""
    cached_videos = state.get("last_videos") or {}
    if (
        not force
        and _cache_matches_current_schema(state)
        and checkpoint_path == cached_report_checkpoint
        and _report_zip_meets_requirements(cached_zip)
        and _checkpoint_matches_cached(checkpoint_path, state.get("last_video_checkpoint") or "", cached_videos)
    ):
        return {
            "zip_path": cached_zip,
            "xlsx_path": find_latest_report_xlsx(run_dir),
            "videos": cached_videos,
            "analysis_text": "",
            "kpi_snapshot": build_supervisor_kpi_snapshot(run_dir),
        }
    videos = ensure_current_videos(run_dir, checkpoint_path, log_path=log_path, force=force)
    representative_video = select_representative_video(videos)
    iter_num = get_checkpoint_iter(checkpoint_path)
    clip_num = max(1, iter_num)
    write_log(f"Generating report bundle for iter {iter_num}", log_path)
    analysis_text = run_detailed_analysis(run_dir, checkpoint_path, clip_num, representative_video)
    kpi_snapshot = build_supervisor_kpi_snapshot(run_dir)
    artifact_paths = create_clip_artifact_zip(run_dir, checkpoint_path, clip_num, videos, kpi_snapshot, analysis_text)
    zip_path = artifact_paths.get("zip_path") if artifact_paths else None
    heartbeat_xlsx_path = artifact_paths.get("xlsx_path") if artifact_paths else None
    if not zip_path or not os.path.isfile(zip_path):
        raise RuntimeError("Report ZIP was not created.")
    update_state(
        mode="stopped",
        active_run=os.path.basename(run_dir),
        active_checkpoint=checkpoint_path,
        last_report_zip=zip_path,
        last_report_checkpoint=checkpoint_path,
        last_videos=videos,
        last_video_checkpoint=checkpoint_path,
    )
    return {
        "zip_path": zip_path,
        "xlsx_path": heartbeat_xlsx_path,
        "videos": videos,
        "analysis_text": analysis_text,
        "kpi_snapshot": kpi_snapshot,
    }


def build_status_text() -> str:
    snapshot = _build_status_snapshot()
    state = snapshot["state"]
    run_dir = snapshot["run_dir"]
    checkpoint = snapshot["checkpoint"]
    iter_num = snapshot["iter_num"]
    training_alive = snapshot["training_alive"]
    heartbeat_alive = snapshot["heartbeat_alive"]
    mode = snapshot["mode"]

    def _status_light(value: str, mapping: dict[str, str], default: str) -> str:
        return f"{mapping.get(value, default)}{value}"

    lines = [
        "👮 SUPERVISOR STATUS",
        f"• mode: {_status_light(mode, {'idle': '⚪', 'training': '🟡', 'reporting': '🟡', 'rendering': '🟡', 'stopped': '🔴'}, '⚪')}",
        f"• training: {_status_light('alive' if training_alive else 'stopped', {'alive': '🟢', 'stopped': '🔴'}, '⚪')}",
        f"• heartbeat: {_status_light('alive' if heartbeat_alive else 'stopped', {'alive': '🟢', 'stopped': '🔴'}, '⚪')}",
        f"• supervisor_version: {snapshot['supervisor_version_text']}",
        f"• heartbeat_version: {snapshot['heartbeat_version_text']}",
        f"• run: {os.path.basename(run_dir) if run_dir else 'N/A'}",
        f"• checkpoint: {os.path.basename(checkpoint) if checkpoint else 'N/A'}",
        f"• iter: {iter_num:,}",
        f"• progress: {snapshot['progress_text']}",
        f"• reward: {snapshot['reward_text']}",
        f"• ep_len: {snapshot['ep_len_text']}",
        f"• verdict: {snapshot['verdict_text']}",
        f"• kpi: {snapshot['kpi_text']}",
        f"• last_heartbeat: {snapshot['last_heartbeat_text']}",
        f"• last_report_zip: {snapshot['last_report_zip_name']}",
    ]
    available_views = snapshot["available_views"]
    lines.append(f"• cached_views: {', '.join(available_views) if available_views else 'none'}")
    if TELEGRAM_VERBOSE_ERRORS and state.get("last_error"):
        lines.append(f"• last_error: {state['last_error']}")
    return "\n".join(lines)


def format_status_html() -> str:
    snapshot = _build_status_snapshot()
    state = snapshot["state"]
    run_dir = snapshot["run_dir"]
    checkpoint = snapshot["checkpoint"]
    iter_num = snapshot["iter_num"]
    training_alive = snapshot["training_alive"]
    heartbeat_alive = snapshot["heartbeat_alive"]
    mode = snapshot["mode"]

    def _status_light_html(value: str, mapping: dict[str, str], default: str) -> str:
        return f"{mapping.get(value, default)}{html.escape(value)}"

    lines = [
        "👮 <b>SUPERVISOR STATUS</b>",
        f"• mode: <code>{_status_light_html(mode, {'idle': '⚪', 'training': '🟡', 'reporting': '🟡', 'rendering': '🟡', 'stopped': '🔴'}, '⚪')}</code>",
        f"• training: <code>{_status_light_html('alive' if training_alive else 'stopped', {'alive': '🟢', 'stopped': '🔴'}, '⚪')}</code>",
        f"• heartbeat: <code>{_status_light_html('alive' if heartbeat_alive else 'stopped', {'alive': '🟢', 'stopped': '🔴'}, '⚪')}</code>",
        f"• supervisor_version: <code>{html.escape(snapshot['supervisor_version_text'])}</code>",
        f"• heartbeat_version: <code>{html.escape(snapshot['heartbeat_version_text'])}</code>",
        f"• run: <code>{html.escape(os.path.basename(run_dir) if run_dir else 'N/A')}</code>",
        f"• checkpoint: <code>{html.escape(os.path.basename(checkpoint) if checkpoint else 'N/A')}</code>",
        f"• iter: <code>{iter_num:,}</code>",
        f"• progress: <code>{html.escape(snapshot['progress_text'])}</code>",
        f"• reward: <code>{html.escape(snapshot['reward_text'])}</code>",
        f"• ep_len: <code>{html.escape(snapshot['ep_len_text'])}</code>",
        f"• verdict: <code>{html.escape(snapshot['verdict_text'])}</code>",
        f"• kpi: <code>{html.escape(snapshot['kpi_text'])}</code>",
        f"• last_heartbeat: <code>{html.escape(snapshot['last_heartbeat_text'])}</code>",
        f"• last_report_zip: <code>{html.escape(snapshot['last_report_zip_name'])}</code>",
    ]
    available_views = snapshot["available_views"]
    lines.append(f"• cached_views: <code>{html.escape(', '.join(available_views) if available_views else 'none')}</code>")
    if TELEGRAM_VERBOSE_ERRORS and state.get("last_error"):
        lines.append(f"• last_error: <code>{html.escape(str(state['last_error']))}</code>")
    return "\n".join(lines)


def format_supervisor_error_text(err: Exception) -> str:
    if TELEGRAM_VERBOSE_ERRORS:
        return f"⚠️ Supervisor Alert\n• detail: {err}"
    return "⚠️ Supervisor Alert\n• detail: 서버 로그를 확인하세요."


def _format_kpi_multiline(kpi_line: str) -> str:
    text = str(kpi_line or "")
    posture_marker = " | 🧍포즈"
    if posture_marker in text:
        head, tail = text.split(posture_marker, 1)
        return f"{head}\n  🧍포즈{tail}"
    return text


def format_report_summary(run_dir: str, checkpoint_path: str, analysis_text: str, kpi_snapshot: dict) -> str:
    grade = parse_analysis_grade(analysis_text)
    iter_num = get_checkpoint_iter(checkpoint_path)
    kpi_text = _format_kpi_multiline(kpi_snapshot["kpi_line"])
    return (
        "📦 Report Ready\n"
        f"• run: {os.path.basename(run_dir)}\n"
        f"• checkpoint: {os.path.basename(checkpoint_path)}\n"
        f"• iter: {iter_num:,}\n"
        f"• verdict: {kpi_snapshot['verdict']}\n"
        f"• kpi: \n{kpi_text}\n"
        f"• grade: {grade['Grade']}\n"
        f"• score: {grade['Score']}/13\n"
        f"• reward: {grade['Reward']}\n"
        f"• trend: {grade['Trend']}"
    )


def format_report_summary_html(run_dir: str, checkpoint_path: str, analysis_text: str, kpi_snapshot: dict) -> str:
    grade = parse_analysis_grade(analysis_text)
    iter_num = get_checkpoint_iter(checkpoint_path)
    kpi_text = html.escape(_format_kpi_multiline(kpi_snapshot["kpi_line"]))
    lines = [
        "📦 <b>REPORT READY</b>",
        f"• run: <code>{html.escape(os.path.basename(run_dir))}</code>",
        f"• checkpoint: <code>{html.escape(os.path.basename(checkpoint_path))}</code>",
        f"• iter: <code>{iter_num:,}</code>",
        f"• verdict: <b>{html.escape(str(kpi_snapshot['verdict']))}</b>",
        f"• kpi: \n<code>{kpi_text}</code>",
        f"• grade: <b>{html.escape(str(grade['Grade']))}</b>",
        f"• score: <code>{html.escape(str(grade['Score']))}/13</code>",
        f"• reward: <code>{html.escape(str(grade['Reward']))}</code>",
        f"• trend: <code>{html.escape(str(grade['Trend']))}</code>",
    ]
    return "\n".join(lines)


def resolve_context() -> tuple[str | None, str | None]:
    run_dir = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(run_dir)
    return run_dir, checkpoint


def command_variants() -> set[str]:
    return {"start", "stop", "status", "report", "front", "rear", "top", "side", "help", "shutdown"}


def help_text() -> str:
    return (
        "Command Menu\n"
        "/start : 훈련 시작 또는 latest checkpoint 재개\n"
        "/stop : 현재 훈련만 중단\n"
        "/status : 현재 상태 조회\n"
        "/report : training 중이면 최신 zip, stopped면 현재 checkpoint 기준 새 zip 생성\n"
        "/front, /rear, /top, /side : training 중이면 최신 영상, stopped면 현재 checkpoint 기준 새 영상 생성\n"
        "/shutdown : supervisor 종료\n"
        "/help : 명령 목록"
    )


def capture_exception() -> str:
    return traceback.format_exc(limit=6)
