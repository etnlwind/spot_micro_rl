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
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
import zipfile

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
CONDA_ENV_NAME = _env.get("CONDA_ENV_NAME") or os.environ.get("CONDA_DEFAULT_ENV", "env_isaaclab")

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

ZIP_FRAME_COUNT = int(_env.get("ZIP_FRAME_COUNT", "40"))
ZIP_IMAGE_MAX_WIDTH = int(_env.get("ZIP_IMAGE_MAX_WIDTH", "960"))
ZIP_IMAGE_QUALITY = int(_env.get("ZIP_IMAGE_QUALITY", "78"))
TELEGRAM_REMOTE_ACTIONS_ENABLED = str(_env.get("TELEGRAM_REMOTE_ACTIONS_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
TELEGRAM_REMOTE_ACTION_TIMEOUT_SEC = int(_env.get("TELEGRAM_REMOTE_ACTION_TIMEOUT_SEC", "120"))
REMOTE_SAFE_COMMIT_MAX_FILES = int(_env.get("REMOTE_SAFE_COMMIT_MAX_FILES", "12"))


def _resolve_conda_activate_bat() -> str | None:
    """Return the base conda activation script path when available."""
    candidates = [
        _env.get("CONDA_ACTIVATE_BAT"),
        os.path.join(os.path.dirname(os.environ.get("CONDA_EXE", "")), "activate.bat") if os.environ.get("CONDA_EXE") else None,
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


CONDA_ACTIVATE_BAT = _resolve_conda_activate_bat()


def _iter_processes_safe(attrs):
    """Yield psutil processes while skipping protected/system processes on Windows."""
    iterator = psutil.process_iter(attrs)
    while True:
        try:
            proc = next(iterator)
        except StopIteration:
            break
        except (psutil.Error, PermissionError, OSError):
            continue
        try:
            _ = proc.info
            yield proc
        except (psutil.Error, PermissionError, OSError):
            continue


def _wrap_conda_command(command: str) -> str:
    """Wrap a command so it runs inside the configured conda environment on Windows."""
    if sys.platform != "win32":
        return command
    if CONDA_ACTIVATE_BAT:
        return f'call "{CONDA_ACTIVATE_BAT}" && conda activate {CONDA_ENV_NAME} && {command}'
    return f'conda activate {CONDA_ENV_NAME} && {command}'


def _hidden_creationflags(extra_flags: int = 0) -> int:
    """Return Windows process flags that avoid opening visible shell windows."""
    if sys.platform == "win32":
        return extra_flags | subprocess.CREATE_NO_WINDOW
    return extra_flags


def _popen_hidden_cmd(command: str, **kwargs):
    """Run a shell command without opening a visible terminal window on Windows."""
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs["creationflags"] = _hidden_creationflags(kwargs.pop("creationflags", 0))
    return subprocess.Popen(["cmd", "/c", command], **kwargs)


def _run_hidden_cmd(command: str, **kwargs):
    """Run a shell command synchronously without opening a visible terminal window on Windows."""
    kwargs.setdefault("cwd", PROJECT_ROOT)
    kwargs["creationflags"] = _hidden_creationflags(kwargs.pop("creationflags", 0))
    return subprocess.run(["cmd", "/c", command], **kwargs)


def get_video_capture_specs(play_envs: int) -> list[dict]:
    """전송용 영상 캡처 조합을 반환합니다."""
    return [
        {
            "key": "overview",
            "label": "전체 로봇 오버뷰",
            "camera_view": "overview",
            "num_envs": play_envs,
            "camera_zoom": 1.0,
        },
        {
            "key": "side",
            "label": "로봇 1대 측면",
            "camera_view": "side",
            "num_envs": 1,
            "camera_zoom": 0.9,
        },
        {
            "key": "front",
            "label": "로봇 1대 정면",
            "camera_view": "front",
            "num_envs": 1,
            "camera_zoom": 0.9,
        },
        {
            "key": "rear",
            "label": "로봇 1대 후면",
            "camera_view": "rear",
            "num_envs": 1,
            "camera_zoom": 0.9,
        },
        {
            "key": "top",
            "label": "로봇 1대 상단",
            "camera_view": "top",
            "num_envs": 1,
            "camera_zoom": 0.85,
        },
    ]


def export_heartbeat_history_xlsx(run_dir: str, out_path: str) -> str | None:
    """Heartbeat JSONL 히스토리를 요약/트렌드/원본 탭이 있는 XLSX로 내보냅니다."""
    try:
        try:
            import training_heartbeat as heartbeat
        except ImportError:
            from scripts import training_heartbeat as heartbeat

        records = heartbeat.load_report_history(run_dir)
        from openpyxl import Workbook
        from openpyxl.chart import LineChart, Reference
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except Exception as err:
        write_log(f"Heartbeat history load failed: {err}")
        return None

    columns = [
        ("timestamp", "timestamp"),
        ("report_kind", "report_kind"),
        ("fallback_source", "fallback_source"),
        ("cycle_num", "cycle_num"),
        ("iteration", "iteration"),
        ("milestone", "milestone"),
        ("mean_reward", "mean_reward"),
        ("mean_episode_length", "mean_episode_length"),
        ("survival_pct", "survival_pct"),
        ("survival_pct_kind", "survival_pct_kind"),
        ("survival_pct_derived", "survival_pct_derived"),
        ("timeout", "timeout"),
        ("bad_orientation", "bad_orientation"),
        ("value_function_loss", "value_function_loss"),
        ("surrogate_loss", "surrogate_loss"),
        ("noise_std", "noise_std"),
        ("vel_err_xy", "vel_err_xy"),
        ("vel_err_yaw", "vel_err_yaw"),
        ("gait_grade", "gait_grade"),
        ("gait_score", "gait_score"),
        ("gait_score_kind", "gait_score_kind"),
        ("gait_score_estimated", "gait_score_estimated"),
        ("stability_grade", "stability_grade"),
        ("stability_score", "stability_score"),
        ("stability_score_kind", "stability_score_kind"),
        ("stability_score_estimated", "stability_score_estimated"),
        ("posture_style_grade", "posture_style_grade"),
        ("posture_style_score", "posture_style_score"),
        ("posture_style_score_kind", "posture_style_score_kind"),
        ("posture_style_score_estimated", "posture_style_score_estimated"),
        ("verdict", "verdict"),
        ("green_count", "green_count"),
        ("yellow_count", "yellow_count"),
        ("red_count", "red_count"),
        ("standing_height", ("primary_metrics", "standing_height")),
        ("forward_velocity", ("primary_metrics", "forward_velocity")),
        ("diagonal_coupling", ("primary_metrics", "diagonal_coupling")),
        ("trot_gait", ("primary_metrics", "trot_gait")),
        ("rear_joint_velocity", ("primary_metrics", "rear_joint_velocity")),
        ("foot_clearance", ("primary_metrics", "foot_clearance")),
        ("stride_length", ("primary_metrics", "stride_length")),
        ("gait_cycle_period", ("primary_metrics", "gait_cycle_period")),
        ("shoulder_neutral", ("primary_metrics", "shoulder_neutral")),
        ("shoulder_symmetry", ("primary_metrics", "shoulder_symmetry")),
        ("stance_width_penalty", ("primary_metrics", "stance_width_penalty")),
        ("joint_vel_l2", ("penalties", "joint_vel_l2")),
        ("action_rate_l2", ("penalties", "action_rate_l2")),
        ("dof_acc_l2", ("penalties", "dof_acc_l2")),
        ("ang_vel_xy_l2", ("penalties", "ang_vel_xy_l2")),
        ("flat_orientation_l2", ("penalties", "flat_orientation_l2")),
        ("same_side_penalty", ("penalties", "same_side_penalty")),
        ("reasons", "reasons"),
    ]
    key_metric_specs = [
        ("mean_reward", "평균 보상", "전반적인 학습 성과의 요약값입니다."),
        ("survival_pct", "생존율", "넘어지지 않고 버틴 비율로 안정성을 빠르게 보여줍니다."),
        ("mean_episode_length", "평균 에피소드 길이", "버티는 시간 증가 여부를 보여줍니다."),
        ("forward_velocity", "전진 속도 보상", "실제 전진 보행 의지가 살아나는지 보는 핵심 지표입니다."),
        ("diagonal_coupling", "대각 커플링", "트로트 리듬 형성 여부를 보는 핵심 보행 지표입니다."),
        ("foot_clearance", "발 들기", "다리가 바닥에 끌리지 않고 충분히 들리는지 보여줍니다."),
        ("trot_gait", "트로트 패턴", "트로트 패턴 보상이 실제로 성장하는지 확인합니다."),
        ("gait_score", "보행 점수", "heartbeat가 계산한 보행 품질 종합 점수입니다."),
        ("stability_score", "안정성 점수", "행동 거칠기와 자세 흔들림을 포함한 동작 안정성입니다."),
        ("posture_style_score", "포즈 점수", "V23 posture-first 기준에서 어깨, 스탠스폭, 기립자세를 종합한 점수입니다."),
        ("stance_width_penalty", "스탠스폭 페널티", "body-frame 기준으로 너무 넓은 spider stance를 얼마나 억제했는지 봅니다."),
        ("joint_vel_l2", "관절 속도 패널티", "절대값이 너무 커지면 진동성 행동 가능성이 큽니다."),
        ("action_rate_l2", "행동 변화 패널티", "정책 출력이 너무 출렁이는지 확인합니다."),
        ("flat_orientation_l2", "자세 기울기 패널티", "상체가 기울어져 균형이 무너지는지 보여줍니다."),
    ]

    def _resolve(record: dict, accessor):
        if isinstance(accessor, tuple):
            node = record.get(accessor[0], {}) or {}
            return node.get(accessor[1]) if isinstance(node, dict) else None
        value = record.get(accessor)
        if value is None and isinstance(accessor, str):
            fallback_map = {
                "survival_pct": "survival_pct_derived",
                "gait_score": "gait_score_estimated",
                "stability_score": "stability_score_estimated",
                "posture_style_score": "posture_style_score_estimated",
            }
            alt_key = fallback_map.get(accessor)
            if alt_key:
                value = record.get(alt_key)
        if isinstance(value, list):
            return " | ".join(str(item) for item in value)
        return value

    def _as_number(value):
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _series_values(name: str) -> list[float | None]:
        values = []
        accessor = next((accessor for column_name, accessor in columns if column_name == name), None)
        for record in records:
            values.append(_as_number(_resolve(record, accessor)))
        return values

    def _delta_text(values: list[float | None], higher_is_better: bool = True) -> str:
        filtered = [value for value in values if value is not None]
        if len(filtered) < 2:
            return "변화 데이터 부족"
        delta = filtered[-1] - filtered[0]
        if abs(delta) < 1e-9:
            return "변화 거의 없음"
        direction = "개선" if (delta > 0) == higher_is_better else "악화"
        return f"{direction} ({delta:+.3f})"

    def _record_from_tensorboard() -> list[dict]:
        data = heartbeat.read_tfevents(run_dir)
        if not data:
            return []

        reward_vals = data.get("Train/mean_reward", [])
        if not reward_vals:
            return []

        scalar_maps = {
            tag: {int(step): value for step, value in values}
            for tag, values in data.items()
        }

        def _get_scalar(tag: str, step: int):
            return scalar_maps.get(tag, {}).get(step)

        fallback_records = []
        for cycle_num, (step, reward_value) in enumerate(reward_vals, start=1):
            step = int(step)
            episode_length = _get_scalar("Train/mean_episode_length", step)
            timeout = _get_scalar("Episode_Termination/time_out", step)
            bad_orientation = _get_scalar("Episode_Termination/bad_orientation", step)

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
                primary_metrics[metric_name] = _get_scalar(f"Episode_Reward/{metric_name}", step)

            penalties = {}
            for metric_name in (
                "joint_vel_l2",
                "action_rate_l2",
                "dof_acc_l2",
                "ang_vel_xy_l2",
                "flat_orientation_l2",
                "same_side_penalty",
            ):
                penalties[metric_name] = _get_scalar(f"Episode_Reward/{metric_name}", step)

            max_ep = 10.0 * 50
            if timeout and timeout > 0.95 and episode_length and episode_length > 1:
                max_ep = episode_length
            survival_pct_derived = (episode_length / max_ep) * 100 if episode_length and max_ep > 0 else None

            reward_snapshot = {**primary_metrics, **penalties}
            gait_grade_estimated, gait_score_estimated, _ = heartbeat.gait_quality_score(reward_snapshot)
            stability_grade_estimated, stability_score_estimated, _stab_details, _stab_valid = heartbeat.motion_stability_score(
                reward_snapshot,
                gait_score_estimated,
            )
            posture_grade_estimated, posture_score_estimated, _ = heartbeat.posture_style_score(reward_snapshot)

            fallback_records.append(
                {
                    "timestamp": f"iter_{step}",
                    "report_kind": "tensorboard_fallback",
                    "fallback_source": "tensorboard_scalars",
                    "cycle_num": cycle_num,
                    "iteration": step,
                    "milestone": step,
                    "mean_reward": reward_value,
                    "mean_episode_length": episode_length,
                    "survival_pct": None,
                    "survival_pct_kind": "derived",
                    "survival_pct_derived": survival_pct_derived,
                    "timeout": timeout,
                    "bad_orientation": bad_orientation,
                    "value_function_loss": _get_scalar("Loss/value_function", step),
                    "surrogate_loss": _get_scalar("Loss/surrogate", step),
                    "noise_std": _get_scalar("Policy/mean_noise_std", step),
                    "vel_err_xy": _get_scalar("Metrics/base_velocity/error_vel_xy", step),
                    "vel_err_yaw": _get_scalar("Metrics/base_velocity/error_vel_yaw", step),
                    "gait_grade": None,
                    "gait_score": None,
                    "gait_score_kind": "estimated",
                    "gait_score_estimated": gait_score_estimated,
                    "stability_grade": None,
                    "stability_score": None,
                    "stability_score_kind": "estimated",
                    "stability_score_estimated": stability_score_estimated,
                    "posture_style_grade": None,
                    "posture_style_score": None,
                    "posture_style_score_kind": "estimated",
                    "posture_style_score_estimated": posture_score_estimated,
                    "verdict": "TensorBoard fallback",
                    "green_count": None,
                    "yellow_count": None,
                    "red_count": None,
                    "primary_metrics": primary_metrics,
                    "penalties": penalties,
                    "gait_grade_estimated": gait_grade_estimated,
                    "stability_grade_estimated": stability_grade_estimated,
                    "posture_style_grade_estimated": posture_grade_estimated,
                    "reasons": ["heartbeat JSONL 없음, TensorBoard 스칼라에서 재구성"],
                }
            )
        return fallback_records

    if not records:
        records = _record_from_tensorboard()
    if not records:
        return None

    title_fill = PatternFill("solid", fgColor="1F4E78")
    subtitle_fill = PatternFill("solid", fgColor="D9EAF7")
    header_fill = PatternFill("solid", fgColor="DDEBF7")
    emphasis_fill = PatternFill("solid", fgColor="FFF2CC")
    good_fill = PatternFill("solid", fgColor="E2F0D9")
    warn_fill = PatternFill("solid", fgColor="FCE4D6")

    workbook = Workbook()
    overview_sheet = workbook.active
    overview_sheet.title = "Overview"
    trends_sheet = workbook.create_sheet("Trends")
    raw_sheet = workbook.create_sheet("RawData")

    latest = records[-1]
    first = records[0]

    # Overview sheet
    overview_sheet.merge_cells("A1:F1")
    overview_sheet["A1"] = "SpotMicro Heartbeat Summary"
    overview_sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    overview_sheet["A1"].fill = title_fill
    overview_sheet["A1"].alignment = Alignment(horizontal="center")

    overview_sheet.merge_cells("A2:F4")
    overview_sheet["A2"] = (
        "이 탭은 보행 평가에서 중요한 지표만 먼저 보이도록 정리한 요약 탭입니다. "
        "전진, 대각 커플링, 발 들기, 보행/안정성 점수처럼 gait quality 판단에 직접 쓰는 값들을 우선 배치했습니다. "
        "아래 표의 '의미' 열을 보면 AI나 사람이 각 지표를 왜 보는지 바로 이해할 수 있습니다."
    )
    overview_sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")

    overview_sheet["A6"] = "런 개요"
    overview_sheet["A6"].font = Font(bold=True)
    overview_sheet["A6"].fill = subtitle_fill
    overview_sheet["A7"] = "Run"
    overview_sheet["B7"] = os.path.basename(run_dir)
    overview_sheet["A8"] = "첫 리포트 시각"
    overview_sheet["B8"] = first.get("timestamp")
    overview_sheet["A9"] = "마지막 리포트 시각"
    overview_sheet["B9"] = latest.get("timestamp")
    overview_sheet["A10"] = "리포트 수"
    overview_sheet["B10"] = len(records)
    overview_sheet["A11"] = "현재 Iter"
    overview_sheet["B11"] = latest.get("iteration")
    overview_sheet["A12"] = "현재 판정"
    overview_sheet["B12"] = latest.get("verdict")
    gait_label = latest.get("gait_grade") or latest.get("gait_grade_estimated") or "N/A"
    gait_score = _resolve(latest, "gait_score")
    stability_label = latest.get("stability_grade") or latest.get("stability_grade_estimated") or "N/A"
    stability_score = _resolve(latest, "stability_score")
    posture_label = latest.get("posture_style_grade") or latest.get("posture_style_grade_estimated") or "N/A"
    posture_score = _resolve(latest, "posture_style_score")
    overview_sheet["A13"] = "현재 보행/안정성"
    overview_sheet["B13"] = f"{gait_label} ({gait_score}) / {stability_label} ({stability_score})"
    overview_sheet["A14"] = "현재 posture/style"
    overview_sheet["B14"] = f"{posture_label} ({posture_score})"
    overview_sheet["A15"] = "데이터 출처"
    overview_sheet["B15"] = latest.get("fallback_source")

    overview_sheet["D6"] = "현재 핵심 해석"
    overview_sheet["D6"].font = Font(bold=True)
    overview_sheet["D6"].fill = subtitle_fill
    overview_sheet["D7"] = "좋은 신호"
    overview_sheet["E7"] = f"green {latest.get('green_count', 0)}"
    overview_sheet["D8"] = "주의 신호"
    overview_sheet["E8"] = f"yellow {latest.get('yellow_count', 0)}"
    overview_sheet["D9"] = "위험 신호"
    overview_sheet["E9"] = f"red {latest.get('red_count', 0)}"
    overview_sheet["D10"] = "판정 사유"
    overview_sheet["E10"] = " | ".join(latest.get("reasons") or [])
    overview_sheet["E10"].alignment = Alignment(wrap_text=True)

    metric_table_row = 18
    headers = ["지표", "현재값", "변화", "최고/최저 참고", "의미"]
    for col_index, header in enumerate(headers, start=1):
        cell = overview_sheet.cell(metric_table_row, col_index, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill

    for row_offset, (metric_name, label, description) in enumerate(key_metric_specs, start=1):
        row = metric_table_row + row_offset
        values = _series_values(metric_name)
        latest_value = next((value for value in reversed(values) if value is not None), None)
        filtered = [value for value in values if value is not None]
        best_ref = "-"
        if filtered:
            if metric_name in {"joint_vel_l2", "action_rate_l2", "flat_orientation_l2"}:
                best_ref = f"최소절대 {min(filtered, key=lambda item: abs(item)):.3f}"
            else:
                best_ref = f"최고 {max(filtered):.3f}"
        overview_sheet.cell(row, 1, label)
        overview_sheet.cell(row, 2, latest_value)
        overview_sheet.cell(row, 3, _delta_text(values, higher_is_better=metric_name not in {"joint_vel_l2", "action_rate_l2", "flat_orientation_l2"}))
        overview_sheet.cell(row, 4, best_ref)
        overview_sheet.cell(row, 5, description)
        overview_sheet.cell(row, 5).alignment = Alignment(wrap_text=True)
        overview_sheet.cell(row, 1).fill = emphasis_fill
        if metric_name in {"forward_velocity", "diagonal_coupling", "foot_clearance", "gait_score", "stability_score", "posture_style_score"}:
            overview_sheet.cell(row, 2).fill = good_fill
        if metric_name in {"joint_vel_l2", "action_rate_l2", "flat_orientation_l2", "stance_width_penalty"}:
            overview_sheet.cell(row, 2).fill = warn_fill

    # Trends sheet
    trends_sheet.merge_cells("A1:G1")
    trends_sheet["A1"] = "Trend Charts"
    trends_sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    trends_sheet["A1"].fill = title_fill
    trends_sheet["A1"].alignment = Alignment(horizontal="center")

    trends_sheet.merge_cells("A2:G4")
    trends_sheet["A2"] = (
        "이 탭은 중요한 보행 평가 지표의 시간 변화만 따로 모아 보여줍니다. "
        "보상 총합보다 forward_velocity, diagonal_coupling, foot_clearance, gait/stability score가 더 눈에 띄도록 배치했습니다. "
        "raw 로그는 아래 차트용 표와 RawData 탭에 모두 남겨져 있습니다."
    )
    trends_sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")

    trend_columns = [
        "iteration",
        "mean_reward",
        "survival_pct",
        "mean_episode_length",
        "forward_velocity",
        "diagonal_coupling",
        "foot_clearance",
        "trot_gait",
        "gait_score",
        "stability_score",
        "posture_style_score",
        "stance_width_penalty",
        "joint_vel_l2",
        "action_rate_l2",
        "flat_orientation_l2",
    ]
    trend_header_row = 6
    for col_index, name in enumerate(trend_columns, start=1):
        cell = trends_sheet.cell(trend_header_row, col_index, name)
        cell.font = Font(bold=True)
        cell.fill = header_fill
    for row_index, record in enumerate(records, start=trend_header_row + 1):
        for col_index, name in enumerate(trend_columns, start=1):
            accessor = next((accessor for column_name, accessor in columns if column_name == name), None)
            trends_sheet.cell(row_index, col_index, _resolve(record, accessor))

    def _add_chart(title: str, y_axis: str, data_cols: list[int], anchor: str):
        chart = LineChart()
        chart.title = title
        chart.y_axis.title = y_axis
        chart.x_axis.title = "Iteration"
        chart.height = 7
        chart.width = 15
        data = Reference(trends_sheet, min_col=min(data_cols), max_col=max(data_cols), min_row=trend_header_row, max_row=trend_header_row + len(records))
        cats = Reference(trends_sheet, min_col=1, min_row=trend_header_row + 1, max_row=trend_header_row + len(records))
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        trends_sheet.add_chart(chart, anchor)

    _add_chart("Reward / Survival", "value", [2, 3], "O6")
    _add_chart("Gait Quality Core", "score / reward", [5, 6, 7, 8], "O22")
    _add_chart("Gait / Stability / Posture Score", "score", [9, 10, 11], "O38")
    _add_chart("Penalty Watch", "penalty", [12, 13, 14, 15], "O54")

    # RawData sheet
    raw_sheet.merge_cells("A1:F1")
    raw_sheet["A1"] = "Raw Heartbeat Records"
    raw_sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    raw_sheet["A1"].fill = title_fill
    raw_sheet["A1"].alignment = Alignment(horizontal="center")

    raw_sheet.merge_cells("A2:F4")
    raw_sheet["A2"] = (
        "이 탭은 heartbeat가 저장한 원본 레코드를 거의 그대로 펼쳐놓은 탭입니다. "
        "데이터량이 많아서 요약 가독성은 낮지만, 세부 분석이나 후처리를 위해 모든 컬럼을 분리해 두었습니다. "
        "요약 판단은 Overview와 Trends를 먼저 보고, 상세 확인이 필요할 때만 이 탭을 보시면 됩니다."
    )
    raw_sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")

    raw_header_row = 6
    for col_index, (column_name, _) in enumerate(columns, start=1):
        cell = raw_sheet.cell(raw_header_row, col_index, column_name)
        cell.font = Font(bold=True)
        cell.fill = header_fill
    for row_index, record in enumerate(records, start=raw_header_row + 1):
        for col_index, (_, accessor) in enumerate(columns, start=1):
            raw_sheet.cell(row_index, col_index, _resolve(record, accessor))

    for sheet in (overview_sheet, trends_sheet, raw_sheet):
        sheet.freeze_panes = "A6"
        for column_cells in sheet.columns:
            column_length = 0
            column_letter = get_column_letter(column_cells[0].column)
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                column_length = max(column_length, min(len(value), 40))
            sheet.column_dimensions[column_letter].width = max(12, column_length + 2)

    overview_sheet.column_dimensions["E"].width = 52
    overview_sheet.column_dimensions["B"].width = 18
    trends_sheet.column_dimensions["A"].width = 14
    raw_sheet.column_dimensions["AL"].width = 50

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    workbook.save(out_path)
    return out_path


# Training / ops version tags
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


def _read_ops_version() -> str:
    for key in ("OPS_VERSION", "MONITOR_VERSION"):
        value = os.environ.get(key) or _env.get(key, "")
        if value:
            return value
    return _read_train_version() or ""


TRAIN_VERSION = _read_train_version()
OPS_VERSION = _read_ops_version()

# Curriculum Phase boundaries (must match rewards.py PHASE_WEIGHTS)
PHASE1_END_ITER = int(_env.get("PHASE1_END_ITER", "2000"))
PHASE2_END_ITER = int(_env.get("PHASE2_END_ITER", "6000"))

# Derived paths
LOG_BASE = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", LOG_SUBDIR)
MONITOR_LOG = os.path.join(PROJECT_ROOT, "logs", "monitor_log.txt")
ANALYZE_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "utils", "analyze_training.py")
MAINTENANCE_FLAG = os.path.join(PROJECT_ROOT, "logs", "maintenance.flag")
USER_STOP_FLAG = os.path.join(PROJECT_ROOT, "logs", "user_stop.flag")
TELEGRAM_PAUSE_FLAG = os.path.join(PROJECT_ROOT, "logs", "telegram_pause.flag")
TELEGRAM_CHAT_MODE_FLAG = os.path.join(PROJECT_ROOT, "logs", "telegram_chat_mode.flag")
TELEGRAM_UPDATES_LOG = os.path.join(PROJECT_ROOT, "logs", "telegram_updates.jsonl")
TELEGRAM_CHAT_INBOX = os.path.join(PROJECT_ROOT, "logs", "telegram_chat_inbox.jsonl")
TELEGRAM_CHAT_OUTBOX = os.path.join(PROJECT_ROOT, "logs", "telegram_chat_outbox.jsonl")
TELEGRAM_REMOTE_ACTION_LOG = os.path.join(PROJECT_ROOT, "logs", "telegram_remote_actions.jsonl")
HEARTBEAT_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "training_heartbeat.pid")
HEARTBEAT_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "training_heartbeat.py")
SUPERVISOR_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "training_supervisor.pid")
HEARTBEAT_HISTORY_JSONL = "heartbeat_reports.jsonl"
MIN_HEARTBEAT_RESTART_INTERVAL_SEC = int(_env.get("MIN_HEARTBEAT_RESTART_INTERVAL_SEC", "120"))
TELEGRAM_FILE_LOCK_TIMEOUT_SEC = float(_env.get("TELEGRAM_FILE_LOCK_TIMEOUT_SEC", "2.0"))
TELEGRAM_FILE_LOCK_RETRY_SEC = float(_env.get("TELEGRAM_FILE_LOCK_RETRY_SEC", "0.05"))

REMOTE_BLOCKED_TEXT_MARKERS = (
    "http://",
    "https://",
    "curl ",
    "wget ",
    "invoke-webrequest",
    "start-bitstransfer",
    "scp ",
    "sftp ",
    "ftp ",
    "webhook",
    "token",
    "password",
    "credential",
    "secret",
    ".env",
    "id_rsa",
    "known_hosts",
    "remove-item",
    "del ",
    "erase ",
    "format ",
    "diskpart",
    "reg delete",
    "shutdown",
    "restart-computer",
    "stop-computer",
    "taskkill",
    "stop-process",
    "kill-process",
    "git reset --hard",
    "git clean -fd",
)

REMOTE_BLOCKED_PATH_PREFIXES = (
    "logs/",
    "outputs/",
    ".git/",
    "source/spot_micro_rl/spot_micro_rl.egg-info/",
)

REMOTE_BLOCKED_PATH_SUFFIXES = (
    ".env",
    ".pt",
    ".pth",
    ".mp4",
    ".zip",
    ".jsonl",
    ".pid",
    ".flag",
    ".db",
    ".sqlite",
    ".csv",
)

REMOTE_ALLOWED_COMMIT_SUFFIXES = (
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
)

# ── State ────────────────────────────────────────────────────────
_tg_offset = 0
_last_analysis_text = ""
_prev_score = -1
_heartbeat_alert_sent = False
_last_heartbeat_restart_ts = 0.0
_chat_storage_health = {
    "append_ok": 0,
    "append_fail": 0,
    "read_ok": 0,
    "read_fail": 0,
    "rewrite_ok": 0,
    "rewrite_fail": 0,
    "probe_ok": 0,
    "probe_fail": 0,
    "last_error": "",
    "last_error_ts": "",
    "last_probe_ts": "",
}


def _set_chat_storage_error(action: str, path: str, err: Exception):
    _chat_storage_health["last_error"] = f"{action} {os.path.basename(path)}: {err}"
    _chat_storage_health["last_error_ts"] = datetime.datetime.now().isoformat(timespec="seconds")


def _chat_lock_path(path: str) -> str:
    return f"{path}.lock"


def _with_path_lock(path: str, action: str, func):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock_path = _chat_lock_path(path)
    deadline = time.time() + max(0.1, TELEGRAM_FILE_LOCK_TIMEOUT_SEC)
    lock_fd = None

    while time.time() < deadline:
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = f"pid={os.getpid()}\nts={datetime.datetime.now().isoformat(timespec='seconds')}\naction={action}\n"
            os.write(lock_fd, payload.encode("utf-8", errors="replace"))
            break
        except FileExistsError:
            time.sleep(TELEGRAM_FILE_LOCK_RETRY_SEC)
        except Exception as err:
            _set_chat_storage_error(action, path, err)
            raise

    if lock_fd is None:
        err = TimeoutError(f"lock timeout after {TELEGRAM_FILE_LOCK_TIMEOUT_SEC:.2f}s")
        _set_chat_storage_error(action, path, err)
        raise err

    try:
        return func()
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        try:
            os.remove(lock_path)
        except OSError:
            pass


def _append_jsonl(path: str, record: dict) -> bool:
    def _write():
        with open(path, "a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    try:
        _with_path_lock(path, "append", _write)
        _chat_storage_health["append_ok"] += 1
        return True
    except Exception as err:
        _chat_storage_health["append_fail"] += 1
        write_log(f"JSONL append failed ({os.path.basename(path)}): {err}")
        return False


def _read_jsonl_records(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []

    def _read():
        records = []
        with open(path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    try:
        records = _with_path_lock(path, "read", _read)
        _chat_storage_health["read_ok"] += 1
        return records
    except Exception as err:
        _chat_storage_health["read_fail"] += 1
        write_log(f"JSONL read failed ({os.path.basename(path)}): {err}")
        return []


def _rewrite_jsonl_records(path: str, records: list[dict]) -> bool:
    def _rewrite():
        fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                for record in records:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
            os.replace(temp_path, path)
        except Exception:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise

    try:
        _with_path_lock(path, "rewrite", _rewrite)
        _chat_storage_health["rewrite_ok"] += 1
        return True
    except Exception as err:
        _chat_storage_health["rewrite_fail"] += 1
        write_log(f"JSONL rewrite failed ({os.path.basename(path)}): {err}")
        return False


def _probe_chat_storage() -> tuple[bool, str]:
    probe_path = os.path.join(PROJECT_ROOT, "logs", "telegram_chat_storage_probe.tmp")
    payload = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "pid": os.getpid(),
    }

    try:
        ok = _append_jsonl(probe_path, payload)
        if not ok:
            raise RuntimeError("probe append failed")
        records = _read_jsonl_records(probe_path)
        if not records:
            raise RuntimeError("probe readback empty")
        try:
            os.remove(probe_path)
        except OSError:
            pass
        try:
            os.remove(_chat_lock_path(probe_path))
        except OSError:
            pass
        _chat_storage_health["probe_ok"] += 1
        _chat_storage_health["last_probe_ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        return True, "ok"
    except Exception as err:
        _chat_storage_health["probe_fail"] += 1
        _set_chat_storage_error("probe", probe_path, err)
        _chat_storage_health["last_probe_ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        return False, str(err)


def _get_chat_storage_status() -> dict:
    probe_ok, probe_detail = _probe_chat_storage()
    inbox_records = _read_jsonl_records(TELEGRAM_CHAT_INBOX)
    outbox_records = _read_jsonl_records(TELEGRAM_CHAT_OUTBOX)
    outbox_pending = sum(1 for record in outbox_records if not record.get("sent"))
    health_ok = probe_ok
    return {
        "mode": "on" if is_telegram_chat_mode_enabled() else "off",
        "probe_ok": probe_ok,
        "probe_detail": probe_detail,
        "inbox_count": len(inbox_records),
        "outbox_pending": outbox_pending,
        "last_error": _chat_storage_health["last_error"] or "none",
        "last_error_ts": _chat_storage_health["last_error_ts"] or "n/a",
        "last_probe_ts": _chat_storage_health["last_probe_ts"] or "n/a",
        "io_ok": health_ok,
    }


def get_heartbeat_history_path(run_dir: str) -> str:
    return os.path.join(run_dir, HEARTBEAT_HISTORY_JSONL)


def load_latest_heartbeat_record(run_dir: str) -> dict | None:
    history_path = get_heartbeat_history_path(run_dir)
    records = _read_jsonl_records(history_path)
    return records[-1] if records else None


def set_telegram_pause_flag():
    os.makedirs(os.path.dirname(TELEGRAM_PAUSE_FLAG), exist_ok=True)
    with open(TELEGRAM_PAUSE_FLAG, "w", encoding="utf-8") as file:
        file.write(datetime.datetime.now().isoformat(timespec="seconds"))
    write_log("Telegram pause flag SET")


def remove_telegram_pause_flag():
    try:
        os.remove(TELEGRAM_PAUSE_FLAG)
    except OSError:
        pass
    write_log("Telegram pause flag REMOVED")


def is_telegram_paused() -> bool:
    return os.path.isfile(TELEGRAM_PAUSE_FLAG)


def set_telegram_chat_mode_flag():
    os.makedirs(os.path.dirname(TELEGRAM_CHAT_MODE_FLAG), exist_ok=True)
    with open(TELEGRAM_CHAT_MODE_FLAG, "w", encoding="utf-8") as file:
        file.write(datetime.datetime.now().isoformat(timespec="seconds"))
    write_log("Telegram chat mode flag SET")


def remove_telegram_chat_mode_flag():
    try:
        os.remove(TELEGRAM_CHAT_MODE_FLAG)
    except OSError:
        pass
    write_log("Telegram chat mode flag REMOVED")


def is_telegram_chat_mode_enabled() -> bool:
    return os.path.isfile(TELEGRAM_CHAT_MODE_FLAG)


def sleep_with_command_poll(total_sec: int, run_dir: str | None = None, checkpoint: str | None = None, step_sec: int = 5):
    """긴 대기 중에도 Telegram 명령을 짧게 polling합니다."""
    remaining = max(0, int(total_sec))
    while remaining > 0:
        chunk = min(step_sec, remaining)
        time.sleep(chunk)
        remaining -= chunk
        process_pending_telegram_commands(run_dir=run_dir, checkpoint=checkpoint)


def is_training_complete(iter_num: int) -> bool:
    """훈련이 완료 임계값에 도달했는지 반환."""
    return iter_num >= MAX_ITERATIONS - 100


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

def _pid_matches_script(pid: int, script_name: str) -> bool:
    try:
        proc = psutil.Process(pid)
        cmdline = " ".join(proc.cmdline()).lower()
        return script_name.lower() in cmdline
    except (psutil.Error, PermissionError, OSError):
        return False

def write_pid_file():
    """Supervisor PID를 파일에 기록."""
    os.makedirs(os.path.dirname(SUPERVISOR_PID_FILE), exist_ok=True)
    with open(SUPERVISOR_PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def acquire_lock():
    """PID 잠금 파일로 supervisor 중복 실행을 방지."""
    if os.path.isfile(SUPERVISOR_PID_FILE):
        try:
            with open(SUPERVISOR_PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid() and _pid_matches_script(old_pid, "training_supervisor.py"):
                print(f"ERROR: Another training_supervisor is already running (PID {old_pid})")
                sys.exit(1)
        except (ValueError, OSError):
            pass
    write_pid_file()


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
    """텔레그램 메시지 전송 (UTF-8 명시). OPS_VERSION 자동 prefix."""
    if OPS_VERSION:
        msg = f"[{OPS_VERSION}] {msg}"
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


def send_telegram_document(file_path: str, caption: str = ""):
    """텔레그램 문서 파일 전송 (zip diagnostics 등)."""
    if not file_path or not os.path.isfile(file_path):
        write_log(f"[TG] Document not found: {file_path} (skip)")
        return
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > 50:
            write_log(f"[TG] Document too large: {file_size_mb:.2f}MB > 50MB limit (skip)")
            send_telegram(f"⚠️ 진단 ZIP 크기 초과: {file_size_mb:.2f}MB (50MB 제한)")
            return

        import uuid
        boundary = uuid.uuid4().hex
        filename = os.path.basename(file_path)

        with open(file_path, "rb") as file:
            payload = file.read()

        body = b""
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += f"{TELEGRAM_CHAT_ID}\r\n".encode()
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
        body += f"{caption}\r\n".encode("utf-8")
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="document"; filename="' + filename.encode() + b'"\r\n'
        body += b"Content-Type: application/zip\r\n\r\n"
        body += payload
        body += f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            f"{TG_BASE_URL}/sendDocument",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        urllib.request.urlopen(req, timeout=180)
        write_log(f"[TG] Document sent OK: {filename} ({file_size_mb:.2f}MB)")
    except Exception as e:
        write_log(f"[TG] Document send FAILED: {e} (skip)")
        send_telegram(f"⚠️ 진단 ZIP 전송 실패: {e}")


def _fetch_telegram_updates(timeout_sec: int = 0) -> list[dict]:
    """Telegram getUpdates 결과를 반환하고 offset을 전진시킵니다."""
    global _tg_offset
    query = urllib.parse.urlencode({"offset": _tg_offset, "timeout": timeout_sec})
    url = f"{TG_BASE_URL}/getUpdates?{query}"
    resp = json.loads(urllib.request.urlopen(url, timeout=max(15, timeout_sec + 5)).read().decode("utf-8"))
    if not resp.get("ok"):
        return []
    updates = resp.get("result") or []
    for update in updates:
        _tg_offset = max(_tg_offset, int(update.get("update_id", 0)) + 1)
    return updates


def _extract_telegram_message(update: dict) -> tuple[str | None, str | None, dict]:
    msg = update.get("message") or update.get("edited_message") or {}
    text = msg.get("text") or msg.get("caption")
    chat_id = msg.get("chat", {}).get("id")
    return text, str(chat_id) if chat_id is not None else None, msg


def _log_telegram_update(update: dict, text: str, chat_id: str | None, handled: bool = False, outcome: str = ""):
    msg = update.get("message") or update.get("edited_message") or {}
    from_user = msg.get("from", {}) or {}
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "update_id": update.get("update_id"),
        "chat_id": chat_id,
        "from_id": from_user.get("id"),
        "from_username": from_user.get("username"),
        "text": text,
        "handled": bool(handled),
        "outcome": outcome,
    }
    _append_jsonl(TELEGRAM_UPDATES_LOG, record)


def _log_telegram_chat_message(update: dict, text: str, chat_id: str | None):
    msg = update.get("message") or update.get("edited_message") or {}
    from_user = msg.get("from", {}) or {}
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "update_id": update.get("update_id"),
        "chat_id": chat_id,
        "from_id": from_user.get("id"),
        "from_username": from_user.get("username"),
        "text": text,
        "mode": "chat_inbox",
    }
    _append_jsonl(TELEGRAM_CHAT_INBOX, record)


def queue_telegram_chat_reply(text: str, source: str = "copilot"):
    payload = (text or "").strip()
    if not payload:
        return
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "text": payload,
        "sent": False,
    }
    _append_jsonl(TELEGRAM_CHAT_OUTBOX, record)


def flush_telegram_chat_outbox() -> int:
    records = _read_jsonl_records(TELEGRAM_CHAT_OUTBOX)
    if not records:
        return 0

    sent_count = 0
    updated_records = []
    for record in records:
        if record.get("sent"):
            updated_records.append(record)
            continue
        try:
            send_telegram(f"💬 Copilot\n{record.get('text', '')}")
            record["sent"] = True
            record["sent_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            sent_count += 1
        except Exception as err:
            record["send_error"] = str(err)
        updated_records.append(record)

    _rewrite_jsonl_records(TELEGRAM_CHAT_OUTBOX, updated_records)

    return sent_count


def _log_remote_action(payload: str, action: str, status: str, detail: str = "", update: dict | None = None):
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "status": status,
        "payload": payload,
        "detail": detail,
    }
    if update:
        record["update_id"] = update.get("update_id")
    _append_jsonl(TELEGRAM_REMOTE_ACTION_LOG, record)


def _run_repo_process(args: list[str], timeout_sec: int = TELEGRAM_REMOTE_ACTION_TIMEOUT_SEC) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            creationflags=_hidden_creationflags(),
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired as err:
        stdout = (err.stdout or "").strip() if isinstance(err.stdout, str) else ""
        stderr = (err.stderr or "").strip() if isinstance(err.stderr, str) else ""
        return 124, stdout, stderr or f"timeout after {timeout_sec}s"


def _shorten_text(text: str, max_lines: int = 20, max_chars: int = 1500) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    shortened = "\n".join(lines)
    if len(shortened) > max_chars:
        shortened = shortened[: max_chars - 3] + "..."
    return shortened


def _normalize_repo_path(path: str) -> str:
    normalized = (path or "").strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_remote_safe_repo_path(path: str) -> tuple[bool, str]:
    normalized = _normalize_repo_path(path).lower()
    if not normalized:
        return False, "empty path"
    for prefix in REMOTE_BLOCKED_PATH_PREFIXES:
        if normalized.startswith(prefix):
            return False, f"blocked path prefix: {prefix}"
    for suffix in REMOTE_BLOCKED_PATH_SUFFIXES:
        if normalized.endswith(suffix):
            return False, f"blocked file suffix: {suffix}"
    if normalized in {".env", ".env.local", ".env.production"}:
        return False, "sensitive env file"
    if normalized.endswith(REMOTE_ALLOWED_COMMIT_SUFFIXES):
        return True, ""
    if os.path.basename(normalized) in {"readme", "readme.md", ".gitignore"}:
        return True, ""
    return False, "unapproved file type"


def _parse_git_status_entries(text: str) -> list[dict]:
    entries = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith("##"):
            continue
        status = raw_line[:2]
        path_text = raw_line[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        entries.append({
            "status": status,
            "path": _normalize_repo_path(path_text),
        })
    return entries


def _get_git_status_entries() -> tuple[list[dict], str]:
    code, stdout, stderr = _run_repo_process(["git", "status", "--short", "--branch", "--untracked-files=all"])
    if code != 0:
        raise RuntimeError(stderr or stdout or "git status failed")
    return _parse_git_status_entries(stdout), stdout


def _extract_commit_message(payload: str) -> str | None:
    match = re.search(r"(?:commit\s*message|메시지|커밋메시지)\s*[:=]\s*(.+)$", payload, re.IGNORECASE)
    if not match:
        return None
    message = match.group(1).strip().strip("\"'")
    return message[:120] if message else None


def _build_remote_commit_message(payload: str, safe_files: list[str]) -> str:
    explicit = _extract_commit_message(payload)
    if explicit:
        return explicit
    lowered = [path.lower() for path in safe_files]
    if all(path.startswith("scripts/") for path in lowered):
        return "chore: update training automation scripts"
    if all(path.endswith(".md") for path in lowered):
        return "docs: update project notes"
    if any(path.endswith("training_supervisor.py") for path in lowered):
        return "chore: harden telegram supervisor automation"
    return "chore: apply telegram-approved workspace updates"


def _classify_remote_action(payload: str) -> tuple[str | None, dict]:
    text = (payload or "").strip()
    lowered = text.lower()
    if not text:
        return None, {}
    if "커밋" in text and "푸시" in text:
        return "git-commit-push", {}
    if "커밋" in text:
        return "git-commit", {}
    if re.search(r"\bgit\s+status\b|깃\s*상태|git 상태", lowered):
        return "git-status", {}
    if "push" in lowered or "푸시" in text:
        return "git-push-blocked", {}
    if "heartbeat" in lowered and ("restart" in lowered or "재시작" in text):
        return "restart-heartbeat", {}
    if "resume" in lowered or "재개" in text:
        return "resume", {}
    if "pause" in lowered or "일시정지" in text or "멈춰" in text:
        return "pause", {}
    if "front" in lowered or "프론트" in text:
        return "front-video", {}
    if re.search(r"\btop\b", lowered) or "탑" in text or "위에서" in text:
        return "top-video", {}
    if "latest_report" in lowered or "리포트" in text or "보고" in text:
        return "latest-report", {}
    if "status" in lowered or "상태" in text:
        return "train-status", {}
    return None, {}


def _scan_remote_payload_risk(payload: str) -> list[str]:
    lowered = (payload or "").lower()
    reasons = []
    for marker in REMOTE_BLOCKED_TEXT_MARKERS:
        if marker in lowered:
            reasons.append(marker)
    return sorted(set(reasons))


def _format_git_entries(entries: list[dict], max_items: int = 8) -> str:
    if not entries:
        return "(no changes)"
    lines = []
    for entry in entries[:max_items]:
        lines.append(f"{entry['status'].strip() or '??'} {entry['path']}")
    if len(entries) > max_items:
        lines.append(f"... (+{len(entries) - max_items} more)")
    return "\n".join(lines)


def _execute_remote_commit(push_after: bool, payload: str) -> tuple[bool, str, str]:
    entries, raw_status = _get_git_status_entries()
    if not entries:
        return True, "remote-noop", "커밋할 변경이 없습니다."

    safe_files = []
    blocked = []
    for entry in entries:
        ok, reason = _is_remote_safe_repo_path(entry["path"])
        if ok:
            safe_files.append(entry["path"])
        else:
            blocked.append(f"{entry['path']} ({reason})")

    if blocked:
        detail = "\n".join(blocked[:8])
        return True, "remote-rejected", f"원격 커밋 차단: 민감/런타임 파일 포함\n{detail}"

    safe_files = sorted(dict.fromkeys(safe_files))
    if len(safe_files) > REMOTE_SAFE_COMMIT_MAX_FILES:
        return True, "remote-rejected", f"원격 커밋 차단: 안전 파일 수가 너무 많습니다 ({len(safe_files)}개)."

    commit_message = _build_remote_commit_message(payload, safe_files)
    code, _stdout, stderr = _run_repo_process(["git", "add", "--", *safe_files])
    if code != 0:
        raise RuntimeError(stderr or "git add failed")

    diff_code, diff_stdout, diff_stderr = _run_repo_process(["git", "diff", "--cached", "--stat"])
    if diff_code != 0:
        raise RuntimeError(diff_stderr or "git diff --cached --stat failed")
    if not diff_stdout.strip():
        return True, "remote-noop", "staging 이후 커밋할 차이가 없습니다."

    commit_code, commit_stdout, commit_stderr = _run_repo_process(["git", "commit", "-m", commit_message])
    if commit_code != 0:
        detail = commit_stderr or commit_stdout or "git commit failed"
        return True, "remote-rejected", f"원격 커밋 실패\n{_shorten_text(detail)}"

    summary = [
        f"커밋 완료: {commit_message}",
        _shorten_text(diff_stdout, max_lines=12, max_chars=900),
        _shorten_text(commit_stdout or commit_stderr, max_lines=12, max_chars=900),
    ]

    if push_after:
        push_code, push_stdout, push_stderr = _run_repo_process(["git", "push"])
        if push_code != 0:
            detail = push_stderr or push_stdout or "git push failed"
            return True, "remote-rejected", "\n".join(summary + [f"push 실패\n{_shorten_text(detail)}"])
        summary.append(_shorten_text(push_stdout or push_stderr or "git push 완료", max_lines=10, max_chars=700))
        return True, "remote-commit-push", "\n".join(summary)

    return True, "remote-commit", "\n".join(summary)


def _execute_remote_action(action: str, payload: str, run_dir: str | None = None, checkpoint: str | None = None) -> tuple[bool, str, str]:
    if action == "train-status":
        return True, "remote-status", format_status_message(run_dir=run_dir, checkpoint=checkpoint)
    if action == "latest-report":
        return True, "remote-report", format_latest_report_message(run_dir=run_dir)
    if action == "pause":
        handled, outcome = handle_telegram_command("/pause", run_dir=run_dir, checkpoint=checkpoint)
        return handled, f"remote-{outcome}", "pause 실행"
    if action == "resume":
        handled, outcome = handle_telegram_command("/resume", run_dir=run_dir, checkpoint=checkpoint)
        return handled, f"remote-{outcome}", "resume 실행"
    if action == "restart-heartbeat":
        handled, outcome = handle_telegram_command("/restart_heartbeat", run_dir=run_dir, checkpoint=checkpoint)
        return handled, f"remote-{outcome}", "heartbeat 재시작 실행"
    if action == "front-video":
        handled, outcome = handle_telegram_command("/front", run_dir=run_dir, checkpoint=checkpoint)
        return handled, f"remote-{outcome}", "front 영상 요청 실행"
    if action == "top-video":
        handled, outcome = handle_telegram_command("/top", run_dir=run_dir, checkpoint=checkpoint)
        return handled, f"remote-{outcome}", "top 영상 요청 실행"
    if action == "git-status":
        entries, raw_status = _get_git_status_entries()
        body = _shorten_text(raw_status or _format_git_entries(entries), max_lines=20, max_chars=1500)
        return True, "remote-git-status", f"git status\n{body}"
    if action == "git-commit":
        return _execute_remote_commit(push_after=False, payload=payload)
    if action == "git-commit-push":
        return _execute_remote_commit(push_after=True, payload=payload)
    if action == "git-push-blocked":
        return True, "remote-rejected", "원격 단독 push는 차단했습니다. 커밋+푸시 요청만 허용합니다."
    return False, "", ""


def try_handle_telegram_chat_action(update: dict, text: str, chat_id: str | None, run_dir: str | None = None, checkpoint: str | None = None) -> tuple[bool, str]:
    if not is_telegram_chat_mode_enabled() or not TELEGRAM_REMOTE_ACTIONS_ENABLED:
        return False, ""

    payload = _extract_chat_payload(text)
    if not payload:
        return False, ""

    action, _meta = _classify_remote_action(payload)
    risk_reasons = _scan_remote_payload_risk(payload)

    if action is None:
        if risk_reasons:
            detail = ", ".join(risk_reasons[:6])
            send_telegram(f"⛔ 원격 실행 차단\n- 사유: {detail}\n- 요청: {payload[:200]}")
            _log_remote_action(payload, "unknown", "rejected", detail, update=update)
            return True, "chat-remote-rejected"
        return False, ""

    if risk_reasons and action not in {"train-status", "latest-report", "pause", "resume", "restart-heartbeat", "front-video", "top-video", "git-status", "git-commit", "git-commit-push", "git-push-blocked"}:
        detail = ", ".join(risk_reasons[:6])
        send_telegram(f"⛔ 원격 실행 차단\n- 사유: {detail}\n- 요청: {payload[:200]}")
        _log_remote_action(payload, action, "rejected", detail, update=update)
        return True, "chat-remote-rejected"

    try:
        handled, outcome, detail = _execute_remote_action(action, payload, run_dir=run_dir, checkpoint=checkpoint)
    except Exception as err:
        detail = f"{action} failed: {err}"
        write_log(f"Remote action error: {detail}")
        send_telegram(f"⚠️ 원격 실행 실패\n- action: {action}\n- error: {err}")
        _log_remote_action(payload, action, "error", detail, update=update)
        return True, "chat-remote-error"

    if handled:
        send_telegram(f"🤖 원격 실행 결과\n- action: {action}\n{_shorten_text(detail, max_lines=20, max_chars=1600)}")
        _log_remote_action(payload, action, outcome or "executed", detail, update=update)
        return True, outcome or "chat-remote-action"

    return False, ""


def _extract_chat_payload(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    parts = stripped.split(maxsplit=1)
    if len(parts) >= 2 and _normalize_command(parts[0]) == "/chat":
        return parts[1].strip()
    return stripped


def handle_telegram_chat_message(update: dict, text: str, chat_id: str | None) -> bool:
    if not is_telegram_chat_mode_enabled():
        return False
    payload = _extract_chat_payload(text)
    if not payload:
        return False
    _log_telegram_chat_message(update, payload, chat_id)
    send_telegram(
        "💬 chat inbox에 저장했습니다.\n"
        "자동 실행 가능한 안전 작업이 아니어서 inbox로만 적재했습니다.\n"
        "필요하면 이후 VS Code 세션에서 읽어 확인할 수 있습니다."
    )
    return True


def _normalize_command(text: str) -> str:
    token = (text or "").strip().split()[0].lower() if text else ""
    if "@" in token:
        token = token.split("@", 1)[0]
    return token


def get_training_process_pids() -> list[int]:
    pids = []
    for pid, cmdline in _get_python_pids_with_cmdline():
        cmdline_l = cmdline.lower()
        if "scripts\\rsl_rl\\train.py" in cmdline_l or "scripts/rsl_rl/train.py" in cmdline_l:
            pids.append(pid)
    return sorted(set(pids))


def test_training_alive() -> bool:
    return bool(get_training_process_pids())


def format_status_message(run_dir: str | None = None, checkpoint: str | None = None) -> str:
    run_dir = run_dir or get_latest_run_dir()
    checkpoint = checkpoint or (get_latest_checkpoint(run_dir) if run_dir else None)
    iter_num = get_checkpoint_iter(checkpoint) if checkpoint else 0
    gpu_mem = get_gpu_memory_mb()
    training_pids = get_training_process_pids()
    heartbeat_alive = test_heartbeat_alive()
    pause_state = "paused" if is_telegram_paused() else "running"
    chat_status = _get_chat_storage_status()
    lines = [
        "📡 Supervisor 상태",
        f"- mode: {pause_state}",
        f"- training: {'alive' if training_pids else 'stopped'} {training_pids if training_pids else ''}",
        f"- heartbeat: {'alive' if heartbeat_alive else 'missing'}",
        f"- supervisor_pid: {os.getpid()}",
        f"- gpu_mem_mb: {gpu_mem}",
        f"- chat_storage: {'ok' if chat_status['io_ok'] else 'degraded'} | mode={chat_status['mode']} | inbox={chat_status['inbox_count']} | outbox_pending={chat_status['outbox_pending']}",
    ]
    if run_dir:
        lines.append(f"- run: {os.path.basename(run_dir)}")
    if checkpoint:
        lines.append(f"- checkpoint: {os.path.basename(checkpoint)}")
        lines.append(f"- iter: {iter_num:,}")

    if run_dir:
        kpi = build_supervisor_kpi_snapshot(run_dir)
        lines.append(f"- verdict: {kpi['verdict']}")
        lines.append(f"- kpi: {kpi['kpi_line']}")
    return "\n".join(lines)


def format_latest_report_message(run_dir: str | None = None) -> str:
    run_dir = run_dir or get_latest_run_dir()
    if not run_dir:
        return "⚠️ latest run을 찾지 못했습니다."
    record = load_latest_heartbeat_record(run_dir)
    if not record:
        return f"⚠️ heartbeat history가 없습니다: {os.path.basename(run_dir)}"

    primary = record.get("primary_metrics") or {}
    reasons = record.get("reasons") or []
    reason_text = reasons[0] if reasons else "N/A"
    return (
        "📝 최신 heartbeat 요약\n"
        f"- run: {record.get('run_name') or os.path.basename(run_dir)}\n"
        f"- ts: {record.get('timestamp', 'N/A')}\n"
        f"- kind: {record.get('report_kind', 'N/A')}\n"
        f"- iter: {int(record.get('iteration', 0)):,}\n"
        f"- reward: {record.get('mean_reward', 'N/A')}\n"
        f"- survival: {record.get('survival_pct', 'N/A')}%\n"
        f"- verdict: {record.get('verdict', 'N/A')}\n"
        f"- gait: {record.get('gait_grade', 'N/A')} ({record.get('gait_score', 'N/A')}/13)\n"
        f"- stability: {record.get('stability_grade', 'N/A')} ({record.get('stability_score', 'N/A')}/10)\n"
        f"- posture: {record.get('posture_style_grade', 'N/A')} ({record.get('posture_style_score', 'N/A')}/10)\n"
        f"- stand/fwd/diag: {primary.get('standing_height', 'N/A')} / {primary.get('forward_velocity', 'N/A')} / {primary.get('diagonal_coupling', 'N/A')}\n"
        f"- reason: {reason_text}"
    )


def find_latest_view_video(run_dir: str | None, view_key: str) -> str | None:
    if not run_dir or not os.path.isdir(run_dir):
        return None
    patterns = {
        "front": ["*front*.mp4"],
        "top": ["*top*.mp4"],
    }
    candidates = []
    for pattern in patterns.get(view_key, [f"*{view_key}*.mp4"]):
        candidates.extend(glob.glob(os.path.join(run_dir, "**", pattern), recursive=True))
    candidates = [path for path in candidates if os.path.isfile(path)]
    if not candidates:
        return None
    candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return candidates[0]


def build_command_help() -> str:
    return (
        "🛠 Telegram 명령\n"
        "- /status : 현재 run, iter, 프로세스, KPI 상태\n"
        "- /latest_report : 최신 heartbeat 요약 재전송\n"
        "- /chat : chat inbox 모드 ON/OFF 토글\n"
        "- /chat_off : chat inbox 모드 OFF\n"
        "- /chat_status : chat inbox/outbox 상태 확인\n"
        "- /pause : 현재 학습 프로세스 정지 후 pause 모드 진입\n"
        "- /resume : latest checkpoint에서 학습 재개\n"
        "- /restart_heartbeat : heartbeat만 재시작\n"
        "- /front : 최근 front-view mp4 재전송\n"
        "- /top : 최근 top-view mp4 재전송\n"
        "- chat 자유문 : 안전검사 통과 시 상태/영상/git status/commit/push 일부 자동 실행\n"
        "- /help : 명령 목록"
    )


def handle_telegram_command(text: str, run_dir: str | None = None, checkpoint: str | None = None) -> tuple[bool, str]:
    command = _normalize_command(text)
    if command in {"", "1", "2"}:
        return False, ""

    if command in {"/chat", "chat"}:
        if is_telegram_chat_mode_enabled():
            remove_telegram_chat_mode_flag()
            chat_status = _get_chat_storage_status()
            send_telegram(
                "💬 chat inbox 모드를 껐습니다.\n"
                f"- inbox messages: {chat_status['inbox_count']}\n"
                f"- outbox pending: {chat_status['outbox_pending']}\n"
                "자유문은 더 이상 chat inbox로 적재되지 않습니다."
            )
            return True, "chat-off"

        set_telegram_chat_mode_flag()
        payload = _extract_chat_payload(text)
        if payload and payload not in {"/chat", "chat"}:
            _log_telegram_chat_message({"message": {"from": {}, "chat": {"id": TELEGRAM_CHAT_ID}}}, payload, str(TELEGRAM_CHAT_ID))
            send_telegram(
                "💬 chat inbox 모드를 켰습니다.\n"
                f"- inbox file: logs/telegram_chat_inbox.jsonl\n"
                f"- outbox file: logs/telegram_chat_outbox.jsonl\n"
                f"첫 메시지도 inbox에 저장했습니다: {payload[:120]}"
            )
        else:
            send_telegram(
                "💬 chat inbox 모드를 켰습니다.\n"
                "- inbox file: logs/telegram_chat_inbox.jsonl\n"
                "- outbox file: logs/telegram_chat_outbox.jsonl\n"
                "이제 자유문을 보내면 inbox에 저장되고, 내가 남긴 답변은 outbox를 통해 Telegram으로 전달됩니다."
            )
        return True, "chat-on"

    if command in {"/chat_off", "chat_off", "/chat_stop", "chat_stop"}:
        remove_telegram_chat_mode_flag()
        send_telegram("💬 chat inbox 모드를 껐습니다.")
        return True, "chat-off"

    if command in {"/chat_status", "chat_status"}:
        chat_status = _get_chat_storage_status()
        send_telegram(
            "💬 chat bridge 상태\n"
            f"- mode: {chat_status['mode']}\n"
            f"- io: {'ok' if chat_status['io_ok'] else 'degraded'}\n"
            f"- probe: {'ok' if chat_status['probe_ok'] else 'failed'} ({chat_status['probe_detail']})\n"
            f"- inbox messages: {chat_status['inbox_count']}\n"
            f"- outbox pending: {chat_status['outbox_pending']}\n"
            f"- last error: {chat_status['last_error']}\n"
            f"- last error ts: {chat_status['last_error_ts']}\n"
            f"- last probe ts: {chat_status['last_probe_ts']}\n"
            f"- inbox file: logs/telegram_chat_inbox.jsonl\n"
            f"- outbox file: logs/telegram_chat_outbox.jsonl"
        )
        return True, "chat-status"

    if command in {"/help", "help"}:
        send_telegram(build_command_help())
        return True, "help"

    if command in {"/status", "status"}:
        send_telegram(format_status_message(run_dir=run_dir, checkpoint=checkpoint))
        return True, "status"

    if command in {"/latest_report", "latest_report", "/report", "report"}:
        send_telegram(format_latest_report_message(run_dir=run_dir))
        return True, "latest_report"

    if command in {"/pause", "pause"}:
        already_paused = is_telegram_paused()
        set_telegram_pause_flag()
        if test_training_alive():
            send_telegram("⏸️ Telegram pause 요청 수신. 학습 프로세스를 정지합니다.")
            set_maintenance_flag()
            try:
                ensure_gpu_clean(reason="telegram-pause")
            finally:
                remove_maintenance_flag()
            send_telegram("⏸️ pause 완료. /resume 으로 재개할 수 있습니다.")
        elif already_paused:
            send_telegram("⏸️ 이미 pause 상태입니다. /resume 으로 재개할 수 있습니다.")
        else:
            send_telegram("⏸️ 학습 프로세스는 이미 멈춰 있습니다. pause 상태로 전환했습니다.")
        return True, "pause"

    if command in {"/resume", "resume"}:
        if test_training_alive():
            remove_telegram_pause_flag()
            send_telegram("▶️ 이미 학습 프로세스가 실행 중입니다. pause 플래그만 해제했습니다.")
            return True, "resume-already-running"

        run_dir = run_dir or get_latest_run_dir()
        checkpoint = checkpoint or (get_latest_checkpoint(run_dir) if run_dir else None)
        if not run_dir or not checkpoint:
            send_telegram("⚠️ 재개할 latest run/checkpoint를 찾지 못했습니다.")
            return True, "resume-missing-checkpoint"

        iter_num = get_checkpoint_iter(checkpoint)
        next_regular_iter = get_next_regular_trigger(iter_num)
        remove_telegram_pause_flag()
        remove_user_stop_flag()
        send_telegram(
            f"▶️ Telegram resume 요청 수신\n"
            f"- run: {os.path.basename(run_dir)}\n"
            f"- checkpoint: {os.path.basename(checkpoint)}\n"
            f"- iter: {iter_num:,}"
        )
        resume_training(run_dir, checkpoint, next_regular_iter=next_regular_iter)
        return True, "resume"

    if command in {"/restart_heartbeat", "restart_heartbeat", "/hb", "hb"}:
        restart_heartbeat()
        return True, "restart_heartbeat"

    if command in {"/front", "front", "/top", "top"}:
        view_key = "front" if "front" in command else "top"
        run_dir = run_dir or get_latest_run_dir()
        video_path = find_latest_view_video(run_dir, view_key)
        if not video_path:
            send_telegram(f"⚠️ 최근 {view_key}-view 영상 파일을 찾지 못했습니다.")
            return True, f"{view_key}-missing"
        iter_num = get_checkpoint_iter(checkpoint) if checkpoint else 0
        send_telegram_video(video_path, f"📹 latest {view_key}-view | iter {iter_num:,} | {os.path.basename(run_dir) if run_dir else 'N/A'}")
        return True, view_key

    return False, ""


def process_pending_telegram_commands(run_dir: str | None = None, checkpoint: str | None = None):
    """대기 중인 Telegram 업데이트를 짧게 polling하고 허용 명령을 처리합니다."""
    flush_telegram_chat_outbox()
    try:
        updates = _fetch_telegram_updates(timeout_sec=0)
    except Exception as err:
        write_log(f"[TG] Poll failed: {err}")
        return

    for update in updates:
        text, chat_id, _msg = _extract_telegram_message(update)
        if not text or str(chat_id) != str(TELEGRAM_CHAT_ID):
            continue
        handled, outcome = handle_telegram_command(text.strip(), run_dir=run_dir, checkpoint=checkpoint)
        if not handled:
            handled, outcome = try_handle_telegram_chat_action(update, text.strip(), chat_id, run_dir=run_dir, checkpoint=checkpoint)
        if not handled and handle_telegram_chat_message(update, text.strip(), chat_id):
            handled = True
            outcome = "chat-inbox"
        if not handled and re.match(r"^\s*[12]\s*$", text):
            send_telegram("ℹ️ 지금은 선택 대기 중이 아닙니다. /help 로 사용 가능한 명령을 확인하세요.")
            outcome = "ignored-choice-outside-decision"
        _log_telegram_update(update, text.strip(), chat_id, handled=handled or bool(outcome), outcome=outcome)


def flush_telegram_updates():
    """이전 Telegram 메시지를 모두 소진하여 offset 갱신."""
    global _tg_offset
    try:
        updates = _fetch_telegram_updates(timeout_sec=0)
        if updates:
            write_log(f"[TG] Flushed {len(updates)} pending updates")
    except Exception:
        pass


def get_telegram_reply(timeout_sec: int = 600) -> str | None:
    """텔레그램 사용자 응답 대기. timeout_sec 이내 응답 없으면 None."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            updates = _fetch_telegram_updates(timeout_sec=10)
            for update in updates:
                text, chat_id, _msg = _extract_telegram_message(update)
                if not text or str(chat_id) != str(TELEGRAM_CHAT_ID):
                    continue
                stripped = text.strip()
                handled, outcome = handle_telegram_command(stripped)
                _log_telegram_update(update, stripped, chat_id, handled=handled, outcome=outcome or ("decision-reply" if not handled else outcome))
                if handled:
                    continue
                write_log(f"[TG] Reply received: {stripped}")
                return stripped
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
        posture_grade, posture_score, _posture_details = heartbeat.posture_style_score(rewards)
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
            "kpi_line": " | ".join(primary_items + [f"🧍포즈 {posture_grade} {posture_score}/10"]),
            "caption_suffix": f"{verdict} | Gait {gait_grade} {gait_score}/13 | Stability {stability_label} | Posture {posture_grade} {posture_score}/10",
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
    for proc in _iter_processes_safe(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "python" in proc.info["name"].lower():
                cmdline = " ".join(proc.info["cmdline"] or [])
                result.append((proc.info["pid"], cmdline))
        except (psutil.Error, PermissionError, OSError):
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
    for proc in _iter_processes_safe(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "kit.exe":
                proc.kill()
        except (psutil.Error, PermissionError, OSError):
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
    global _last_heartbeat_restart_ts
    now = time.time()
    cooldown_left = MIN_HEARTBEAT_RESTART_INTERVAL_SEC - (now - _last_heartbeat_restart_ts)
    if cooldown_left > 0:
        write_log(f"Heartbeat restart skipped due to cooldown ({cooldown_left:.0f}s left)")
        return True
    _last_heartbeat_restart_ts = now

    write_log("Restarting training_heartbeat...")
    # 기존 PID 파일 제거
    try:
        os.remove(HEARTBEAT_PID_FILE)
    except OSError:
        pass

    # 최신 run dir 찾기
    latest_run = get_latest_run_dir()
    hb_cmd = [sys.executable, HEARTBEAT_SCRIPT, "--iter_step", "100", "--poll", "30"]
    if latest_run:
        hb_cmd.extend(["--run_dir", latest_run])

    subprocess.Popen(
        hb_cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP |
            (subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        ),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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

def record_video_bundle(checkpoint_path: str, run_dir: str, clip_num: int) -> dict[str, str]:
    """오버뷰 + 단일 로봇 상세 시점 영상을 순차 캡처합니다."""
    cp_name = os.path.basename(checkpoint_path)
    iter_num = get_checkpoint_iter(checkpoint_path)
    write_log(f"Recording clip #{clip_num} from: {cp_name}")

    play_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "play.py")
    captured_videos: dict[str, str] = {}

    for spec in get_video_capture_specs(PLAY_ENVS):
        view_name = spec["camera_view"]
        view_key = spec["key"]
        view_label = spec["label"]
        num_envs = spec["num_envs"]
        camera_zoom = spec["camera_zoom"]

        write_log(f"Recording view: {view_label} ({view_name}, envs={num_envs})")
        pre_videos = set(glob.glob(os.path.join(run_dir, "videos", "play", "*.mp4")))

        play_cmd = _wrap_conda_command(
            f'cd /d "{PROJECT_ROOT}" && '
            f'set PYTHONIOENCODING=utf-8 && '
            f'"{ISAAC_LAB}" -p "{play_script}" '
            f'--task={TASK} --num_envs={num_envs} '
            f'--checkpoint="{checkpoint_path}" --video --video_length={VIDEO_LENGTH} '
            f'--camera_view={view_name} --camera_zoom={camera_zoom}'
        )
        write_log(f"play_cmd({view_key}): {play_cmd}")
        proc = _popen_hidden_cmd(play_cmd)

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
        new_name = f"clip_{clip_num}_iter{iter_num}_{view_key}_{ts}.mp4"
        dest_path = os.path.join(run_dir, "videos", new_name)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(latest_video, dest_path)
        size_mb = os.path.getsize(dest_path) / (1024 * 1024)
        write_log(f"Video saved: {new_name} ({size_mb:.1f}MB)")

        # 느린 재생 속도로 재인코딩
        reencoded = reencode_video(dest_path, VIDEO_FPS)
        if reencoded:
            dest_path = reencoded

        captured_videos[view_key] = dest_path

    if not captured_videos:
        write_log("WARNING: No video file found across all views!")

    return captured_videos


def record_video(checkpoint_path: str, run_dir: str, clip_num: int) -> str | None:
    """대표 영상 경로 반환용 호환 래퍼."""
    captured_videos = record_video_bundle(checkpoint_path, run_dir, clip_num)
    return select_representative_video(captured_videos)


def select_representative_video(captured_videos: dict[str, str]) -> str | None:
    """분석/로그 대표 영상 경로를 선택합니다."""
    for preferred_key in ("side", "overview", "rear", "top"):
        if preferred_key in captured_videos:
            return captured_videos[preferred_key]
    return next(iter(captured_videos.values()), None)


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

        reencode_cmd = _wrap_conda_command(
            f'set PYTHONIOENCODING=utf-8 && python "{tmp_py}"'
        )
        proc = _run_hidden_cmd(
            reencode_cmd,
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


def send_clip_video_set(captured_videos: dict[str, str], clip_num: int, iter_num: int, progress_pct: float, kpi_snapshot: dict, is_final: bool = False):
    """요청된 영상 세트를 순서대로 전송합니다."""
    specs = get_video_capture_specs(PLAY_ENVS)
    total = len(specs)
    prefix = "🏆 최종" if is_final else f"🎬 Clip #{clip_num}"
    for idx, spec in enumerate(specs, start=1):
        video_path = captured_videos.get(spec["key"])
        if not video_path:
            continue
        caption = (
            f"{prefix} {idx}/{total} | {spec['label']} | "
            f"Iter {iter_num} / {MAX_ITERATIONS} ({progress_pct}%) | {kpi_snapshot['caption_suffix']}"
        )
        send_telegram_video(video_path, caption)


def extract_video_frames(video_path: str, out_dir: str, prefix: str, frame_count: int) -> list[str]:
    """영상에서 균등 샘플링한 정지 프레임을 JPEG로 저장합니다."""
    try:
        import av
    except ImportError:
        write_log("Frame extraction skipped: PyAV not installed")
        return []

    os.makedirs(out_dir, exist_ok=True)
    container = av.open(video_path)
    stream = container.streams.video[0]
    total_frames = int(stream.frames or 0)

    if total_frames <= 0:
        total_frames = sum(1 for _ in container.decode(video=0))
        container.close()
        container = av.open(video_path)

    if total_frames <= 0:
        container.close()
        return []

    sample_count = max(1, min(frame_count, total_frames))
    if sample_count == 1:
        selected_indices = [0]
    else:
        selected_indices = sorted({
            round(index * (total_frames - 1) / (sample_count - 1)) for index in range(sample_count)
        })

    selected_set = set(selected_indices)
    saved = []
    for frame_index, frame in enumerate(container.decode(video=0)):
        if frame_index not in selected_set:
            continue
        image = frame.to_image().convert("RGB")
        if ZIP_IMAGE_MAX_WIDTH > 0 and image.width > ZIP_IMAGE_MAX_WIDTH:
            scale = ZIP_IMAGE_MAX_WIDTH / image.width
            image = image.resize((ZIP_IMAGE_MAX_WIDTH, max(1, int(image.height * scale))))
        frame_path = os.path.join(out_dir, f"{prefix}_{frame_index:04d}.jpg")
        image.save(frame_path, format="JPEG", quality=ZIP_IMAGE_QUALITY, optimize=True)
        saved.append(frame_path)
        if len(saved) >= len(selected_indices):
            break

    container.close()
    return saved


def create_clip_artifact_zip(
    run_dir: str,
    checkpoint_path: str,
    clip_num: int,
    captured_videos: dict[str, str],
    kpi_snapshot: dict,
    analysis_text: str,
) -> str | None:
    """보행 분석 텍스트와 정지 프레임 묶음을 ZIP으로 생성합니다."""
    if not captured_videos:
        write_log("Artifact ZIP skipped: no captured videos")
        return None

    iter_num = get_checkpoint_iter(checkpoint_path)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_root = os.path.join(run_dir, "artifacts", f"clip_{clip_num}_iter{iter_num}_{timestamp}")
    metrics_root = os.path.join(artifact_root, "metrics")
    frames_root = os.path.join(artifact_root, "frames")
    os.makedirs(metrics_root, exist_ok=True)
    os.makedirs(frames_root, exist_ok=True)

    grade = parse_analysis_grade(analysis_text)
    summary_lines = [
        f"clip_num={clip_num}",
        f"iteration={iter_num}",
        f"checkpoint={os.path.basename(checkpoint_path)}",
        f"run_dir={os.path.basename(run_dir)}",
        f"verdict={kpi_snapshot['verdict']}",
        f"reason={kpi_snapshot['reason']}",
        f"kpi_line={kpi_snapshot['kpi_line']}",
        f"gait={kpi_snapshot['gait']} ({kpi_snapshot['gait_score']}/13)",
        f"stability={kpi_snapshot['stability']} ({kpi_snapshot['stability_score']}/10)",
        f"analysis_grade={grade['Grade']}",
        f"analysis_score={grade['Score']}/13",
        f"analysis_reward={grade['Reward']}",
        f"analysis_trend={grade['Trend']}",
        "",
        "captured_videos:",
    ]
    for spec in get_video_capture_specs(PLAY_ENVS):
        video_path = captured_videos.get(spec["key"])
        if video_path:
            summary_lines.append(f"- {spec['label']}: {os.path.basename(video_path)}")

    summary_path = os.path.join(metrics_root, "summary.txt")
    with open(summary_path, "w", encoding="utf-8") as file:
        file.write("\n".join(summary_lines) + "\n")

    analysis_path = os.path.join(metrics_root, "analysis_report.txt")
    with open(analysis_path, "w", encoding="utf-8") as file:
        file.write(analysis_text.strip() + "\n" if analysis_text.strip() else "Analysis output unavailable\n")

    manifest = {
        "clip_num": clip_num,
        "iteration": iter_num,
        "checkpoint": os.path.basename(checkpoint_path),
        "run_dir": os.path.basename(run_dir),
        "zip_frame_count": ZIP_FRAME_COUNT,
        "videos": {},
        "frames": {},
        "heartbeat_history_xlsx": None,
        "kpi_snapshot": kpi_snapshot,
        "analysis": grade,
    }

    heartbeat_xlsx_path = export_heartbeat_history_xlsx(
        run_dir,
        os.path.join(metrics_root, "heartbeat_history.xlsx"),
    )
    if heartbeat_xlsx_path:
        manifest["heartbeat_history_xlsx"] = os.path.basename(heartbeat_xlsx_path)

    for spec in get_video_capture_specs(PLAY_ENVS):
        video_path = captured_videos.get(spec["key"])
        if not video_path:
            continue
        manifest["videos"][spec["key"]] = os.path.basename(video_path)
        saved_frames = extract_video_frames(
            video_path,
            os.path.join(frames_root, spec["key"]),
            spec["key"],
            ZIP_FRAME_COUNT,
        )
        manifest["frames"][spec["key"]] = len(saved_frames)

    manifest_path = os.path.join(metrics_root, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as file:
        json.dump(manifest, file, indent=2, ensure_ascii=False)

    zip_path = os.path.join(run_dir, "artifacts", f"clip_{clip_num}_iter{iter_num}_{timestamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(artifact_root):
            for name in files:
                file_path = os.path.join(root, name)
                archive.write(file_path, os.path.relpath(file_path, artifact_root))

    write_log(f"Artifact ZIP created: {zip_path}")
    return zip_path


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

    analysis_cmd = _wrap_conda_command(
        f'cd /d "{PROJECT_ROOT}" && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'"{ISAAC_LAB}" -p "{ANALYZE_SCRIPT}" '
        f'--run_dir "{run_dir}" --clip_num {clip_num}'
    )
    write_log(f"analysis_cmd: {analysis_cmd}")

    try:
        proc = _popen_hidden_cmd(
            analysis_cmd,
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
    train_cmd = _wrap_conda_command(
        f'cd /d "{PROJECT_ROOT}" && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'"{ISAAC_LAB}" -p "{train_script}" '
        f'--task={TASK} --num_envs={TRAIN_ENVS} --headless '
        f'--max_iterations={MAX_ITERATIONS} '
        f'--resume --load_run={run_name} --checkpoint={cp_name}'
    )
    write_log(f"train_cmd: {train_cmd}")
    _popen_hidden_cmd(
        train_cmd,
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

    # PID 기록 + 중복 실행 방지
    acquire_lock()

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
        f"10분 무응답 → 자동 계속\n\n"
        f"🛠 원격 명령: /help"
    )

    clip_num = 0
    last_clip_iter = 0
    last_verdict = "🟢 계속 진행"
    next_regular_iter = VIDEO_INTERVAL_EARLY_ITER
    last_observed_checkpoint = ""
    completed_run_signature = ""
    exit_notice = "👋 Training Supervisor 종료"

    try:
        while True:
            try:
                process_pending_telegram_commands(run_dir=get_latest_run_dir())
                sleep_with_command_poll(SUPERVISOR_POLL_SECONDS, run_dir=get_latest_run_dir())

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
                process_pending_telegram_commands(run_dir=run_dir, checkpoint=checkpoint)

                iter_num = get_checkpoint_iter(checkpoint)
                kpi_snapshot = build_supervisor_kpi_snapshot(run_dir)
                run_signature = f"{run_dir}|{checkpoint}|{iter_num}"
                if not last_observed_checkpoint:
                    last_observed_checkpoint = checkpoint
                    last_verdict = kpi_snapshot["verdict"]
                    next_regular_iter = get_next_regular_trigger(iter_num)
                    last_clip_iter = max(0, iter_num - get_regular_video_interval(iter_num))
                    if is_training_complete(iter_num):
                        completed_run_signature = run_signature
                    write_log(
                        f"Supervisor armed at iter {iter_num} | "
                        f"{format_trigger_status(next_regular_iter, last_clip_iter, kpi_snapshot['verdict'], last_verdict)}"
                    )

                if completed_run_signature and run_signature == completed_run_signature:
                    write_log(
                        f"Completed run already handled: {os.path.basename(run_dir)} / "
                        f"{os.path.basename(checkpoint)} (iter {iter_num})"
                    )
                    exit_notice = None
                    break

                if is_telegram_paused():
                    continue

                if is_training_complete(iter_num):
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
                captured_videos: dict[str, str] = {}
                artifact_zip_path = None
                progress_pct = round((iter_num / MAX_ITERATIONS) * 100, 1)
                send_telegram(
                    f"🎬 Clip #{clip_num} 시작\n"
                    f"├ 📍 Iter: {iter_num} / {MAX_ITERATIONS} ({progress_pct}%)\n"
                    f"├ Trigger: {trigger_reason}\n"
                    f"└ 📂 {os.path.basename(run_dir)} / {os.path.basename(checkpoint)}"
                )

                # 훈련 완료 체크
                if is_training_complete(iter_num):
                    completed_run_signature = run_signature
                    write_log(f"===== TRAINING COMPLETE (iter {iter_num}) =====")
                    send_telegram(f"🏁 훈련 완료 감지 (iter {iter_num}/{MAX_ITERATIONS})\n최종 영상과 분석을 정리합니다...")
                    try:
                        ensure_gpu_clean(reason="complete")
                    except Exception:
                        pass
                    try:
                        captured_videos = record_video_bundle(checkpoint, run_dir, clip_num)
                        video_path = select_representative_video(captured_videos)
                        send_clip_video_set(captured_videos, clip_num, iter_num, progress_pct, kpi_snapshot, is_final=True)
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
                        artifact_zip_path = create_clip_artifact_zip(
                            run_dir,
                            checkpoint,
                            clip_num,
                            captured_videos,
                            kpi_snapshot,
                            _last_analysis_text,
                        )
                        if artifact_zip_path:
                            send_telegram_document(
                                artifact_zip_path,
                                f"🏁 최종 진단 ZIP | Iter {iter_num} | 분석지표 + 시점별 정지프레임 {ZIP_FRAME_COUNT}장"
                            )

                        grade = parse_analysis_grade(_last_analysis_text)
                        send_telegram(
                            f"🏆 훈련 종료 요약\n\n"
                            f"📊 등급: {grade['Grade']}\n"
                            f"🎯 점수: {grade['Score']}/13\n"
                            f"💰 Reward: {grade['Reward']}\n"
                            f"📈 Trend: {grade['Trend']}\n"
                            f"🚦 운영 판정: {kpi_snapshot['verdict']}\n"
                            f"🧭 KPI: {kpi_snapshot['kpi_line']}\n"
                            f"🦿 Gait: {kpi_snapshot['gait']} ({kpi_snapshot['gait_score']}/13)\n"
                            f"🛡 Stability: {kpi_snapshot['stability']} ({kpi_snapshot['stability_score']}/10)"
                        )
                        exit_notice = "🏁 Training Supervisor 종료\n완료된 훈련의 최종 정리를 마쳤습니다"
                    except Exception:
                        send_telegram("🏁 훈련 완료. 최종 정리를 마쳤습니다.")
                        exit_notice = "🏁 Training Supervisor 종료"
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
                send_telegram(f"🎥 P2/5: 4종 영상 녹화 중... ({VIDEO_LENGTH} steps)")
                try:
                    captured_videos = record_video_bundle(checkpoint, run_dir, clip_num)
                    video_path = select_representative_video(captured_videos)
                    send_clip_video_set(captured_videos, clip_num, iter_num, progress_pct, kpi_snapshot)
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

                try:
                    artifact_zip_path = create_clip_artifact_zip(
                        run_dir,
                        checkpoint,
                        clip_num,
                        captured_videos,
                        kpi_snapshot,
                        _last_analysis_text,
                    )
                    if artifact_zip_path:
                        send_telegram_document(
                            artifact_zip_path,
                            f"📦 Clip #{clip_num} 진단 ZIP | Iter {iter_num} | 분석지표 + 시점별 정지프레임 {ZIP_FRAME_COUNT}장"
                        )
                except Exception as e:
                    write_log(f"Artifact ZIP err: {e} (skip)")

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
                            exit_notice = "🛑 Training Supervisor 종료\n사용자 요청으로 감시를 중단했습니다"
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
                            exit_notice = "🛑 Training Supervisor 종료\n사용자 요청으로 감시를 중단했습니다"
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

                if is_telegram_paused():
                    write_log("Resume skipped due to Telegram pause flag")
                    send_telegram("⏸️ pause 플래그가 있어 자동 재개를 건너뜁니다. /resume 으로 다시 시작하세요.")
                    remove_maintenance_flag()
                    last_verdict = kpi_snapshot["verdict"]
                    continue

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

    if exit_notice:
        send_telegram(exit_notice)
    write_log("Monitor exiting.")


if __name__ == "__main__":
    main()
