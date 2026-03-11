import contextlib
import datetime
import glob
import hashlib
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
BUSY_LOCK_FILE = os.path.join(PROJECT_ROOT, "logs", "ops.lock")
TRAINING_LOG = os.path.join(PROJECT_ROOT, "logs", "training_launch.log")
ANALYZE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "utils", "analyze_training.py")
TG_OFFSET_FILE = os.path.join(PROJECT_ROOT, "logs", "telegram_offset.json")

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

_tg_offset: int | None = None


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
    candidates = [
        _env.get("CONDA_ACTIVATE_BAT"),
        os.path.join(os.path.dirname(os.environ.get("CONDA_EXE", "")), "activate.bat") if os.environ.get("CONDA_EXE") else None,
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


def send_text(text: str, log_path: str) -> None:
    payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
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


def _telegram_get_updates(offset: int, timeout_sec: int = 0) -> list[dict]:
    query = urllib.parse.urlencode({"offset": offset, "timeout": timeout_sec})
    url = f"{TG_BASE_URL}/getUpdates?{query}"
    response = json.loads(urllib.request.urlopen(url, timeout=max(15, timeout_sec + 5)).read().decode("utf-8"))
    if not response.get("ok"):
        return []
    return response.get("result") or []


def prime_update_offset(log_path: str) -> int:
    global _tg_offset
    stored_offset = load_telegram_offset()
    if stored_offset > 0:
        _tg_offset = stored_offset
        write_log(f"Telegram offset restored: {stored_offset}", log_path)
        return stored_offset
    updates = _telegram_get_updates(0, timeout_sec=0)
    next_offset = 0
    for update in updates:
        next_offset = max(next_offset, int(update.get("update_id", 0)) + 1)
    _tg_offset = next_offset
    save_telegram_offset(next_offset)
    write_log(f"Telegram offset primed: {next_offset}", log_path)
    return next_offset


def fetch_updates(timeout_sec: int = 0) -> list[dict]:
    global _tg_offset
    if _tg_offset is None:
        _tg_offset = load_telegram_offset()
    updates = _telegram_get_updates(_tg_offset, timeout_sec=timeout_sec)
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


def resolve_active_run_dir() -> str | None:
    state = load_state()
    active_run = state.get("active_run") or ""
    latest_run = get_latest_run_dir()
    if active_run:
        active_path = os.path.join(LOG_BASE, active_run)
        if os.path.isdir(active_path):
            if latest_run and os.path.basename(latest_run) > active_run:
                return latest_run
            return active_path
    return latest_run


def resolve_active_checkpoint(run_dir: str | None = None) -> str | None:
    run_dir = run_dir or resolve_active_run_dir()
    state = load_state()
    checkpoint = state.get("active_checkpoint") or ""
    if checkpoint and os.path.isfile(checkpoint):
        if run_dir and os.path.dirname(checkpoint) == run_dir:
            return checkpoint
    return get_latest_checkpoint(run_dir)


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
        activate_cmd = CONDA_ACTIVATE_BAT if " " not in CONDA_ACTIVATE_BAT else f'"{CONDA_ACTIVATE_BAT}"'
        return f"call {activate_cmd} && conda activate {CONDA_ENV_NAME} && {command}"
    return f"conda activate {CONDA_ENV_NAME} && {command}"


def _popen_hidden_cmd(command: str, **kwargs):
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs.setdefault("creationflags", kwargs.pop("creationflags", 0))
    kwargs.setdefault("startupinfo", kwargs.pop("startupinfo", None))
    kwargs["env"] = {**os.environ, "PYTHONIOENCODING": "utf-8", **kwargs.get("env", {})}
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    return subprocess.Popen(["cmd", "/c", command], **kwargs)


def _run_hidden_cmd(command: str, **kwargs):
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs.setdefault("creationflags", kwargs.pop("creationflags", 0))
    kwargs.setdefault("startupinfo", kwargs.pop("startupinfo", None))
    kwargs["env"] = {**os.environ, "PYTHONIOENCODING": "utf-8", **kwargs.get("env", {})}
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    return subprocess.run(["cmd", "/c", command], **kwargs)


def _launch_training_command(command: str, launcher_name: str) -> str:
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    launcher_path = os.path.join(logs_dir, launcher_name)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(launcher_path, "w", encoding="utf-8", newline="\n") as file:
        file.write("@echo off\n")
        file.write(f'echo ===== [{timestamp}] training launch =====>> "{TRAINING_LOG}"\n')
        file.write(f'echo cmd: {command}>> "{TRAINING_LOG}"\n')
        file.write(f'{command} >> "{TRAINING_LOG}" 2>&1\n')
    subprocess.Popen(
        ["cmd", "/c", f'start "" /b cmd /c "{launcher_path}"'],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return launcher_path


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


def build_supervisor_kpi_snapshot(run_dir: str) -> dict:
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
    current_ep_len = float(ep_len_vals[-1][1]) if ep_len_vals else 0.0
    timeout = float(_latest_scalar(data, "Episode_Termination/time_out") or 0.0)
    bad_orient = float(_latest_scalar(data, "Episode_Termination/bad_orientation") or 0.0)
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
            "survival_pct": survival_pct,
            "verdict": verdict,
            "reason": reasons[0] if reasons else "",
            "gait": gait_grade,
            "gait_score": gait_score,
            "stability": stab_grade,
            "stability_score": stab_score,
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


def format_report(data: dict, run_name: str, cycle_num: int) -> str:
    reward_vals = data.get("Train/mean_reward", [])
    ep_len_vals = data.get("Train/mean_episode_length", [])
    if not reward_vals:
        return "⚠️ Heartbeat metrics unavailable"
    current_iter = int(reward_vals[-1][0])
    current_reward = float(reward_vals[-1][1])
    current_ep_len = float(ep_len_vals[-1][1]) if ep_len_vals else 0.0
    run_dir = os.path.join(LOG_BASE, run_name)
    kpi = build_supervisor_kpi_snapshot(run_dir) if os.path.isdir(run_dir) else build_supervisor_kpi_snapshot(resolve_active_run_dir() or "")
    return (
        "💓 Heartbeat\n"
        f"- run: {run_name}\n"
        f"- cycle: {cycle_num}\n"
        f"- iter: {current_iter:,}\n"
        f"- reward: {current_reward:.3f}\n"
        f"- ep_len: {current_ep_len:.1f}\n"
        f"- verdict: {kpi['verdict']}\n"
        f"- kpi: {kpi['kpi_line']}\n"
        f"- gait: {kpi['gait']} {kpi['gait_score']}/13\n"
        f"- stability: {kpi['stability']} {kpi['stability_score']}/10"
    )


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


def create_clip_artifact_zip(run_dir: str, checkpoint_path: str, clip_num: int, captured_videos: dict[str, str], kpi_snapshot: dict, analysis_text: str) -> str | None:
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
    if REPORT_REQUIRE_XLSX and (not heartbeat_xlsx_path or not os.path.isfile(heartbeat_xlsx_path)):
        raise RuntimeError("Heartbeat XLSX export failed.")
    manifest = {
        "clip_num": clip_num,
        "iteration": iter_num,
        "checkpoint": os.path.basename(checkpoint_path),
        "run_dir": os.path.basename(run_dir),
        "videos": {key: os.path.basename(path) for key, path in captured_videos.items()},
        "heartbeat_history_xlsx": "heartbeat_history.xlsx" if heartbeat_xlsx_path and os.path.isfile(heartbeat_xlsx_path) else None,
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
        for key, path in captured_videos.items():
            if path and os.path.isfile(path):
                archive.write(path, f"videos/{key}_{os.path.basename(path)}")
    return zip_path


def _cache_matches_current_schema(state: dict) -> bool:
    return int(state.get("cache_schema_version") or 0) == CACHE_SCHEMA_VERSION


def _report_zip_meets_requirements(zip_path: str) -> bool:
    if not zip_path or not os.path.isfile(zip_path):
        return False
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = set(archive.namelist())
        return "metrics/heartbeat_history.xlsx" in names
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
        return {"zip_path": cached_zip, "videos": cached_videos, "analysis_text": "", "kpi_snapshot": build_supervisor_kpi_snapshot(run_dir)}
    videos = ensure_current_videos(run_dir, checkpoint_path, log_path=log_path, force=force)
    representative_video = select_representative_video(videos)
    iter_num = get_checkpoint_iter(checkpoint_path)
    clip_num = max(1, iter_num)
    write_log(f"Generating report bundle for iter {iter_num}", log_path)
    analysis_text = run_detailed_analysis(run_dir, checkpoint_path, clip_num, representative_video)
    kpi_snapshot = build_supervisor_kpi_snapshot(run_dir)
    zip_path = create_clip_artifact_zip(run_dir, checkpoint_path, clip_num, videos, kpi_snapshot, analysis_text)
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
    return {"zip_path": zip_path, "videos": videos, "analysis_text": analysis_text, "kpi_snapshot": kpi_snapshot}


def build_status_text() -> str:
    state = load_state()
    run_dir = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(run_dir)
    iter_num = get_checkpoint_iter(checkpoint)
    training_alive = is_training_running()
    lines = [
        "📡 Supervisor 상태",
        f"- mode: {state.get('mode', 'idle')}",
        f"- training: {'alive' if training_alive else 'stopped'}",
        f"- run: {os.path.basename(run_dir) if run_dir else 'N/A'}",
        f"- checkpoint: {os.path.basename(checkpoint) if checkpoint else 'N/A'}",
        f"- iter: {iter_num:,}",
        f"- last_report_zip: {os.path.basename(state.get('last_report_zip') or '') or 'N/A'}",
    ]
    last_videos = state.get("last_videos") or {}
    available_views = [key for key, path in sorted(last_videos.items()) if path and os.path.isfile(path)]
    lines.append(f"- cached_views: {', '.join(available_views) if available_views else 'none'}")
    if TELEGRAM_VERBOSE_ERRORS and state.get("last_error"):
        lines.append(f"- last_error: {state['last_error']}")
    return "\n".join(lines)


def format_supervisor_error_text(err: Exception) -> str:
    if TELEGRAM_VERBOSE_ERRORS:
        return f"⚠️ supervisor error: {err}"
    return "⚠️ supervisor error가 발생했습니다. 상세 내용은 서버 로그를 확인하세요."


def format_report_summary(run_dir: str, checkpoint_path: str, analysis_text: str, kpi_snapshot: dict) -> str:
    grade = parse_analysis_grade(analysis_text)
    iter_num = get_checkpoint_iter(checkpoint_path)
    return (
        "📦 Report 완료\n"
        f"- run: {os.path.basename(run_dir)}\n"
        f"- checkpoint: {os.path.basename(checkpoint_path)}\n"
        f"- iter: {iter_num:,}\n"
        f"- verdict: {kpi_snapshot['verdict']}\n"
        f"- kpi: {kpi_snapshot['kpi_line']}\n"
        f"- grade: {grade['Grade']}\n"
        f"- score: {grade['Score']}/13\n"
        f"- reward: {grade['Reward']}\n"
        f"- trend: {grade['Trend']}"
    )


def resolve_context() -> tuple[str | None, str | None]:
    run_dir = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(run_dir)
    return run_dir, checkpoint


def command_variants() -> set[str]:
    return {"start", "stop", "status", "report", "front", "rear", "top", "side", "help"}


def help_text() -> str:
    return (
        "🛠 명령\n"
        "/start : 훈련 시작 또는 latest checkpoint 재개\n"
        "/stop : 현재 훈련만 중단\n"
        "/status : 현재 상태 조회\n"
        "/report : training 중이면 최신 zip, stopped면 현재 checkpoint 기준 새 zip 생성\n"
        "/front, /rear, /top, /side : training 중이면 최신 영상, stopped면 현재 checkpoint 기준 새 영상 생성\n"
        "/help : 명령 목록"
    )


def capture_exception() -> str:
    return traceback.format_exc(limit=6)
