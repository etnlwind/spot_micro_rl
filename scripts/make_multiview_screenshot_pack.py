import argparse
import csv
import datetime
import glob
import os
import shutil
import subprocess
import zipfile
import urllib.request

import av

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUN_DIR = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", "spot_micro_flat", "2026-03-10_07-43-51")
PLAY_DIR = os.path.join(RUN_DIR, "videos", "play")
ISAAC_LAB = r"C:\IsaacLab\isaaclab.bat"
TASK = "Isaac-Velocity-Flat-SpotMicro-v0"

VIEWS = ["side", "front", "rear", "top_oblique"]
LIMB_ORDER = ["LF", "RF", "LR", "RR"]
LIMB_COLORS = {
    "LF": (255, 120, 120),
    "RF": (120, 180, 255),
    "LR": (120, 220, 150),
    "RR": (255, 200, 120),
}


def load_env(path):
    env = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def latest_checkpoint(run_dir):
    cands = sorted(glob.glob(os.path.join(run_dir, "model_*.pt")))
    return cands[-1] if cands else None


def run_play_for_view(checkpoint, view, video_length):
    play_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "play.py")
    cmd = (
        f'conda activate env_isaaclab && '
        f'cd /d {PROJECT_ROOT} && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'{ISAAC_LAB} -p {play_script} '
        f'--task={TASK} --num_envs=1 --checkpoint={checkpoint} '
        f'--video --video_length={video_length} --camera_view={view} '
        f'--save_contact_csv --contact_threshold=1.0 --headless'
    )
    proc = subprocess.run(["cmd", "/c", cmd], timeout=900)
    return proc.returncode == 0


def extract_frames(video_path, out_dir, prefix, count):
    return extract_frames_with_overlay(video_path, out_dir, prefix, count, [])


def load_contact_rows(csv_path):
    rows = []
    if not os.path.isfile(csv_path):
        return rows
    with open(csv_path, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(row)
    return rows


def extract_frames_with_overlay(video_path, out_dir, prefix, count, contact_rows):
    os.makedirs(out_dir, exist_ok=True)
    c = av.open(video_path)
    stream = c.streams.video[0]
    total = stream.frames if stream.frames and stream.frames > 0 else 0
    if total <= 0:
        total = sum(1 for _ in c.decode(video=0))
        c.close()
        c = av.open(video_path)

    start = max(0, (total // 2) - (count // 2))
    end = start + count

    saved = []
    idx = 0
    for frame in c.decode(video=0):
        if idx < start:
            idx += 1
            continue
        if idx >= end:
            break
        img = frame.to_image().convert("RGB")
        if contact_rows:
            from PIL import ImageDraw

            draw = ImageDraw.Draw(img)
            draw.rectangle((12, 12, 600, 64), fill=(0, 0, 0))
            draw.text((20, 18), f"toe-contact overlay | frame {idx - start + 1}/{end - start}", fill=(255, 255, 255))
            x = 20
            for limb in LIMB_ORDER:
                state = int(contact_rows[min(idx, len(contact_rows) - 1)].get(limb, 0))
                force = float(contact_rows[min(idx, len(contact_rows) - 1)].get(f"{limb}_force", 0.0))
                color = LIMB_COLORS[limb] if state == 1 else (170, 170, 170)
                draw.text((x, 40), f"{limb} toe {'ON' if state else 'OFF'} {force:4.1f}N", fill=color)
                x += 140
        fp = os.path.join(out_dir, f"{prefix}_{idx:04d}.jpg")
        img.save(fp, format="JPEG", quality=92)
        saved.append(fp)
        idx += 1

    c.close()
    return saved


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for f in files:
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, src_dir))


def send_document(token, chat_id, file_path, caption):
    boundary = "----spotmicrozipboundary"
    with open(file_path, "rb") as f:
        b = f.read()

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
    body += f"{chat_id}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
    body += f"{caption}\r\n".encode("utf-8")
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="document"; filename="' + os.path.basename(file_path).encode() + b'"\r\n'
    body += b"Content-Type: application/zip\r\n\r\n"
    body += b
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    urllib.request.urlopen(req, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, default="")
    parser.add_argument("--tag", type=str, default="")
    parser.add_argument("--side_count", type=int, default=40)
    parser.add_argument("--other_count", type=int, default=40)
    parser.add_argument("--video_length", type=int, default=120)
    args = parser.parse_args()

    env = load_env(os.path.join(PROJECT_ROOT, ".env"))
    checkpoint = args.checkpoint or latest_checkpoint(RUN_DIR)
    if not checkpoint:
        print("ERROR: checkpoint not found")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = args.tag or os.path.splitext(os.path.basename(checkpoint))[0]
    work = os.path.join(PROJECT_ROOT, "logs", "frame_packs", f"multiview_{tag}_{ts}")
    src_dir = os.path.join(work, "source_videos")
    os.makedirs(src_dir, exist_ok=True)

    copied = {}
    contact_dir = os.path.join(work, "contact_metrics")
    os.makedirs(contact_dir, exist_ok=True)
    for view in VIEWS:
        ok = run_play_for_view(checkpoint, view, args.video_length)
        if not ok:
            print(f"WARN: play failed for {view}")
            continue
        latest = os.path.join(PLAY_DIR, "rl-video-step-0.mp4")
        if not os.path.isfile(latest):
            print(f"WARN: no play output for {view}")
            continue
        dst = os.path.join(src_dir, f"{view}.mp4")
        shutil.copy2(latest, dst)
        copied[view] = dst
        print(f"captured: {view} -> {dst}")

        # contact raw-force/boolean export files produced by play.py
        csv_src = os.path.join(PLAY_DIR, f"contact_states_{view}.csv")
        contact_rows = []
        if os.path.isfile(csv_src):
            shutil.copy2(csv_src, os.path.join(contact_dir, f"contact_states_{view}.csv"))
            contact_rows = load_contact_rows(csv_src)
        else:
            print(f"WARN: missing contact csv for {view}")

        meta_src = os.path.join(PLAY_DIR, f"contact_meta_{view}.json")
        if os.path.isfile(meta_src):
            shutil.copy2(meta_src, os.path.join(contact_dir, f"contact_meta_{view}.json"))
        else:
            print(f"WARN: missing contact meta for {view}")

    # frame extraction
    frame_root = os.path.join(work, "frames")
    total = 0
    for view, vp in copied.items():
        out = os.path.join(frame_root, view)
        count = args.side_count if view == "side" else args.other_count
        saved = extract_frames_with_overlay(
            vp,
            out,
            f"{view}_seq",
            count,
            load_contact_rows(os.path.join(contact_dir, f"contact_states_{view}.csv")),
        )
        total += len(saved)
        print(f"frames_{view}: {len(saved)}")

    readme = os.path.join(work, "README.txt")
    with open(readme, "w", encoding="utf-8") as f:
        f.write("SpotMicro gait screenshot pack (multi-view)\n")
        f.write(f"Checkpoint: {checkpoint}\n")
        f.write(f"Views: {', '.join(copied.keys())}\n")
        f.write(f"Frames total: {total}\n")
        f.write("Included: side/front/rear/top_oblique.\n")
        f.write("Each view includes 40 consecutive frames by default.\n")
        f.write("Contact metrics included per view: toe-primary raw force, boolean, rigid body mapping.\n")
        f.write("All extracted frames include toe-contact overlay (LF/RF/LR/RR).\n")

    zip_path = os.path.join(PROJECT_ROOT, "logs", "frame_packs", f"spotmicro_screenshots_multiview_{tag}_{ts}.zip")
    zip_dir(work, zip_path)
    print(f"zip: {zip_path}")

    token = env.get("TELEGRAM_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        send_document(token, chat_id, zip_path, "SpotMicro 멀티뷰 스크린샷 ZIP (side/front/rear/top)")
        print("telegram: sent")
    else:
        print("telegram: skipped")


if __name__ == "__main__":
    main()
