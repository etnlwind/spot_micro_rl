"""Auto-stop: iter 500 milestone 리포트 후 전체 프로세스 정지.

milestone_monitor가 500 리포트를 보낸 뒤 (60초 대기) 모든 학습/모니터 프로세스를 종료합니다.
모델은 RSL-RL이 자동 저장하므로 데이터 손실 없음.
"""
import os
import sys
import time
import datetime
import io

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
RUN_DIR = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", "spot_micro_flat", "2026-03-09_00-05-49")
TARGET_ITER = 500
POLL_SEC = 30


def _load_env():
    env = {}
    p = os.path.join(PROJECT_ROOT, ".env")
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def send_telegram(text):
    import urllib.request, urllib.parse
    env = _load_env()
    token = env.get("TELEGRAM_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"[TG] {e}")


def get_current_iter():
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    try:
        ea = EventAccumulator(RUN_DIR)
        ea.Reload()
        rw = ea.Scalars("Train/mean_reward")
        if rw:
            return int(rw[-1].step), rw[-1].value
    except Exception as e:
        print(f"[READ] {e}")
    return 0, 0


def kill_all():
    import psutil
    my_pid = os.getpid()
    targets = ["train.py", "heartbeat.py", "supervisor.py", "training_heartbeat", "training_supervisor",
               "tensorboard", "milestone_monitor"]
    killed = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        if p.pid == my_pid:
            continue
        try:
            cmd = " ".join(p.info["cmdline"] or []).lower()
            if any(t in cmd for t in targets) and "psutil" not in cmd:
                name = next((t for t in targets if t in cmd), "?")
                p.terminate()
                killed.append(f"PID {p.pid} ({name})")
        except Exception:
            pass
    return killed


def main():
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] Auto-stop: waiting for iter >= {TARGET_ITER}, then shutdown")

    while True:
        it, rw = get_current_iter()
        now = datetime.datetime.now().strftime("%H:%M:%S")

        if it >= TARGET_ITER:
            print(f"[{now}] iter {it} reached (reward={rw:.1f})!")
            # milestone_monitor가 리포트 보낼 시간 확보
            print(f"[{now}] Waiting 90s for milestone report to be sent...")
            time.sleep(90)

            # 최종 iter 확인
            it2, rw2 = get_current_iter()
            print(f"[{now}] Final iter: {it2}, reward: {rw2:.1f}")

            # 정지
            killed = kill_all()
            for k in killed:
                print(f"  Killed: {k}")

            msg = (
                f"[V20] 🛑 <b>Auto-Stop 완료</b>\n"
                f"iter {it2} (reward {rw2:.1f})에서 학습 중단\n"
                f"종료 프로세스: {len(killed)}개\n"
                f"{''.join(chr(10) + '  ' + k for k in killed)}\n\n"
                f"Resume 명령:\n"
                f"<code>C:\\IsaacLab\\isaaclab.bat -p scripts/rsl_rl/train.py "
                f"--task=Isaac-Velocity-Flat-SpotMicro-v0 --num_envs=24576 "
                f"--headless --max_iterations=15000 "
                f"--resume --load_run=2026-03-09_00-05-49</code>"
            )
            send_telegram(msg)
            print(f"\n=== All stopped. Safe to shutdown. ===")
            break

        print(f"[{now}] iter {it}/{TARGET_ITER} (reward={rw:.1f}) — waiting...")
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
