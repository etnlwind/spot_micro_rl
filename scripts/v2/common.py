import contextlib
import datetime
import glob
import io
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
import uuid

import psutil

if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr and sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPTS_DIR, ".."))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from v1 import training_heartbeat as legacy_heartbeat
from v1 import training_supervisor as legacy_supervisor

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


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


_env = _load_env(ENV_FILE)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or _env.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or _env.get("TELEGRAM_CHAT_ID", "")
if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not found in .env or environment")
    sys.exit(1)

TG_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TASK = _env.get("TASK", "Isaac-Velocity-Flat-SpotMicro-v0")
LOG_SUBDIR = _env.get("LOG_SUBDIR", "spot_micro_flat")
ISAAC_LAB = _env.get("ISAAC_LAB_PATH", r"C:\IsaacLab\isaaclab.bat")
TRAIN_ENVS = int(_env.get("TRAIN_ENVS", "24576"))
PLAY_ENVS = int(_env.get("PLAY_ENVS", "50"))
MAX_ITERATIONS = int(_env.get("MAX_ITERATIONS", "15000"))
VIDEO_LENGTH = int(_env.get("VIDEO_LENGTH", "250"))
SUPERVISOR_POLL_SECONDS = int(_env.get("SUPERVISOR_POLL_SECONDS", "10"))
HEARTBEAT_POLL_SECONDS = int(_env.get("V2_HEARTBEAT_POLL_SECONDS", "30"))
HEARTBEAT_ITER_STEP = int(_env.get("V2_HEARTBEAT_ITER_STEP", "100"))

LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", LOG_SUBDIR)
STATE_FILE = os.path.join(PROJECT_ROOT, "logs", "v2_state.json")
SUPERVISOR_LOG = os.path.join(PROJECT_ROOT, "logs", "v2_supervisor.log")
HEARTBEAT_LOG = os.path.join(PROJECT_ROOT, "logs", "v2_heartbeat.log")
SUPERVISOR_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "v2_supervisor.pid")
HEARTBEAT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "v2_heartbeat.pid")
BUSY_LOCK_FILE = os.path.join(PROJECT_ROOT, "logs", "v2_busy.lock")
TRAINING_LOG = os.path.join(PROJECT_ROOT, "logs", "v2_training.log")

_tg_offset = 0


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


def default_state() -> dict:
    return {
        "updated_at": _now(),
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
            old_pid = int(open(pid_file, "r", encoding="utf-8").read().strip())
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
        raise RuntimeError("Another v2 operation is already running.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(f"{label}\n")
            file.write(f"{os.getpid()}\n")
            file.write(f"{_now()}\n")
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


def fetch_updates(timeout_sec: int = 0) -> list[dict]:
    global _tg_offset
    query = urllib.parse.urlencode({"offset": _tg_offset, "timeout": timeout_sec})
    url = f"{TG_BASE_URL}/getUpdates?{query}"
    response = json.loads(urllib.request.urlopen(url, timeout=max(15, timeout_sec + 5)).read().decode("utf-8"))
    if not response.get("ok"):
        return []
    updates = response.get("result") or []
    for update in updates:
        _tg_offset = max(_tg_offset, int(update.get("update_id", 0)) + 1)
    return updates


def extract_message(update: dict) -> tuple[str | None, str | None]:
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text") or message.get("caption")
    chat_id = message.get("chat", {}).get("id")
    return text, str(chat_id) if chat_id is not None else None


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
    return legacy_supervisor.get_latest_checkpoint(run_dir) if run_dir else None


def _looks_like_training_command(name: str, cmdline: str) -> bool:
    cmdline_l = cmdline.lower()
    if "training_supervisor" in cmdline_l or "training_heartbeat" in cmdline_l:
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


def build_train_command(resume_run_dir: str | None = None, checkpoint_path: str | None = None) -> str:
    train_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "train.py")
    parts = [
        f'"{ISAAC_LAB}"',
        "-p",
        f'"{train_script}"',
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
    return " ".join(parts)


def launch_training(log_path: str) -> dict:
    if is_training_running():
        return {"mode": "already-running", "run_dir": resolve_active_run_dir(), "checkpoint": resolve_active_checkpoint()}

    baseline_run = get_latest_run_dir()
    resume_run = resolve_active_run_dir()
    checkpoint = resolve_active_checkpoint(resume_run)
    command = build_train_command(resume_run, checkpoint) if checkpoint else build_train_command()
    write_log(f"Launching training: {command}", log_path)

    _ensure_logs_dir()
    with open(TRAINING_LOG, "ab") as training_log:
        subprocess.Popen(
            ["cmd", "/c", command],
            cwd=PROJECT_ROOT,
            stdout=training_log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

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


def find_latest_video(view_key: str, run_dir: str | None = None) -> str | None:
    search_roots = [run_dir] if run_dir else []
    if LOG_BASE not in search_roots:
        search_roots.append(LOG_BASE)
    patterns = [f"*{view_key}*.mp4"]
    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        matches = []
        for pattern in patterns:
            matches.extend(glob.glob(os.path.join(root, "**", pattern), recursive=True))
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


def _checkpoint_matches_cached(checkpoint_path: str, cached_checkpoint: str, file_map: dict | None) -> bool:
    if not checkpoint_path or not cached_checkpoint or checkpoint_path != cached_checkpoint:
        return False
    if not file_map:
        return False
    return all(path and os.path.isfile(path) for path in file_map.values())


def ensure_current_videos(run_dir: str, checkpoint_path: str, log_path: str, force: bool = False) -> dict[str, str]:
    state = load_state()
    cached_videos = state.get("last_videos") or {}
    if not force and _checkpoint_matches_cached(checkpoint_path, state.get("last_video_checkpoint") or "", cached_videos):
        return cached_videos

    iter_num = legacy_supervisor.get_checkpoint_iter(checkpoint_path)
    clip_num = max(1, iter_num)
    write_log(f"Generating current videos for iter {iter_num}", log_path)
    captured_videos = legacy_supervisor.record_video_bundle(checkpoint_path, run_dir, clip_num)
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
        and checkpoint_path == cached_report_checkpoint
        and cached_zip
        and os.path.isfile(cached_zip)
        and _checkpoint_matches_cached(checkpoint_path, state.get("last_video_checkpoint") or "", cached_videos)
    ):
        return {"zip_path": cached_zip, "videos": cached_videos, "analysis_text": "", "kpi_snapshot": legacy_supervisor.build_supervisor_kpi_snapshot(run_dir)}

    videos = ensure_current_videos(run_dir, checkpoint_path, log_path=log_path, force=force)
    representative_video = legacy_supervisor.select_representative_video(videos)
    iter_num = legacy_supervisor.get_checkpoint_iter(checkpoint_path)
    clip_num = max(1, iter_num)
    write_log(f"Generating report bundle for iter {iter_num}", log_path)
    legacy_supervisor._last_analysis_text = ""
    legacy_supervisor.run_detailed_analysis(run_dir, checkpoint_path, clip_num, representative_video)
    analysis_text = legacy_supervisor._last_analysis_text
    kpi_snapshot = legacy_supervisor.build_supervisor_kpi_snapshot(run_dir)
    zip_path = legacy_supervisor.create_clip_artifact_zip(
        run_dir,
        checkpoint_path,
        clip_num,
        videos,
        kpi_snapshot,
        analysis_text,
    )
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
    iter_num = legacy_supervisor.get_checkpoint_iter(checkpoint) if checkpoint else 0
    training_alive = is_training_running()
    lines = [
        "📡 V2 상태",
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
    if state.get("last_error"):
        lines.append(f"- last_error: {state['last_error']}")
    return "\n".join(lines)


def format_report_summary(run_dir: str, checkpoint_path: str, analysis_text: str, kpi_snapshot: dict) -> str:
    grade = legacy_supervisor.parse_analysis_grade(analysis_text)
    iter_num = legacy_supervisor.get_checkpoint_iter(checkpoint_path)
    return (
        "📦 V2 report 완료\n"
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
        "🛠 V2 명령\n"
        "- start : 훈련 시작 또는 latest checkpoint 재개\n"
        "- stop : 현재 훈련만 중단\n"
        "- status : 현재 상태 조회\n"
        "- report : training 중이면 최신 zip, stopped면 현재 checkpoint 기준 새 zip 생성\n"
        "- front / rear / top / side : training 중이면 최신 영상, stopped면 현재 checkpoint 기준 새 영상 생성\n"
        "- help : 명령 목록"
    )


def capture_exception() -> str:
    return traceback.format_exc(limit=6)
