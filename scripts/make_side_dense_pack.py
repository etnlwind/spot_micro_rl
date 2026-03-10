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
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUN_DIR = os.path.join(PROJECT_ROOT, "logs", "rsl_rl", "spot_micro_flat", "2026-03-10_07-43-51")
PLAY_DIR = os.path.join(RUN_DIR, "videos", "play")
ISAAC_LAB = r"C:\IsaacLab\isaaclab.bat"
TASK = "Isaac-Velocity-Flat-SpotMicro-v0"


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


def run_side_video(checkpoint, video_length=60, zoom=0.55):
    play_script = os.path.join(PROJECT_ROOT, "scripts", "rsl_rl", "play.py")
    cmd = (
        f'conda activate env_isaaclab && '
        f'cd /d {PROJECT_ROOT} && '
        f'set PYTHONIOENCODING=utf-8 && '
        f'{ISAAC_LAB} -p {play_script} '
        f'--task={TASK} --num_envs=1 --checkpoint={checkpoint} '
        f'--video --video_length={video_length} --camera_view=side --camera_zoom={zoom} '
        f'--save_contact_csv --contact_threshold=1.0 --headless'
    )
    proc = subprocess.run(["cmd", "/c", cmd], timeout=900)
    if proc.returncode != 0:
        return None
    out = os.path.join(PLAY_DIR, "rl-video-step-0.mp4")
    return out if os.path.isfile(out) else None

def load_contact_rows(csv_path):
    rows = []
    if not os.path.isfile(csv_path):
        return rows
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _contact_label(v):
    return "ON" if int(v) == 1 else "OFF"


def _contact_color(v):
    return (70, 220, 70) if int(v) == 1 else (190, 190, 190)


def extract_dense_frames(video_path, out_dir, frame_count=40, contact_rows=None):
    os.makedirs(out_dir, exist_ok=True)
    container = av.open(video_path)
    stream = container.streams.video[0]
    total = stream.frames if stream.frames and stream.frames > 0 else 0
    if total <= 0:
        total = sum(1 for _ in container.decode(video=0))
        container.close()
        container = av.open(video_path)

    # 1~2초 구간을 촘촘히: 중앙 근처에서 연속 40프레임 선택
    start = max(0, (total // 2) - (frame_count // 2))
    end = min(total, start + frame_count)

    saved = []
    idx = 0
    local_idx = 0
    for frame in container.decode(video=0):
        if idx < start:
            idx += 1
            continue
        if idx >= end:
            break
        img = frame.to_image().convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.rectangle((12, 12, 430, 58), fill=(0, 0, 0))
        draw.text((20, 20), f"side-close | frame {local_idx+1}/{end-start}", fill=(255, 255, 255))
        # Contact overlay (LF/RF/LR/RR)
        if contact_rows:
            contact_idx = min(max(idx, 0), len(contact_rows) - 1)
            c = contact_rows[contact_idx]
            overlay = [
                ("LF", int(c.get("LF", 0))),
                ("RF", int(c.get("RF", 0))),
                ("LR", int(c.get("LR", 0))),
                ("RR", int(c.get("RR", 0))),
            ]
            x = 20
            y = 38
            for name, state in overlay:
                txt = f"{name}:{_contact_label(state)}"
                draw.text((x, y), txt, fill=_contact_color(state))
                x += 92
        else:
            draw.text((20, 38), "contact overlay: csv not found", fill=(255, 220, 140))
        fp = os.path.join(out_dir, f"side_dense_{local_idx:03d}.jpg")
        img.save(fp, format="JPEG", quality=92)
        saved.append(fp)
        idx += 1
        local_idx += 1

    container.close()
    return saved


def make_gif(frame_paths, gif_path, duration_ms=55):
    if not frame_paths:
        return None
    images = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frame_paths]
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=duration_ms,
        optimize=False,
    )
    return gif_path


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for f in files:
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, src_dir))


def send_document(token, chat_id, file_path, caption):
    boundary = "----spotmicrodensezip"
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


def send_animation(token, chat_id, gif_path, caption):
    boundary = "----spotmicrogif"
    with open(gif_path, "rb") as f:
        b = f.read()

    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
    body += f"{chat_id}\r\n".encode()
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
    body += f"{caption}\r\n".encode("utf-8")
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="animation"; filename="' + os.path.basename(gif_path).encode() + b'"\r\n'
    body += b"Content-Type: image/gif\r\n\r\n"
    body += b
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{token}/sendAnimation"
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    urllib.request.urlopen(req, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video_length", type=int, default=60)
    parser.add_argument("--zoom", type=float, default=0.55)
    parser.add_argument("--frame_count", type=int, default=40)
    args = parser.parse_args()

    env = load_env(os.path.join(PROJECT_ROOT, ".env"))
    checkpoint = latest_checkpoint(RUN_DIR)
    if not checkpoint:
        print("ERROR: checkpoint not found")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    work = os.path.join(PROJECT_ROOT, "logs", "frame_packs", f"side_dense_{ts}")
    os.makedirs(work, exist_ok=True)

    src_video = run_side_video(checkpoint, video_length=args.video_length, zoom=args.zoom)
    if not src_video:
        print("ERROR: side video generation failed")
        return

    src_copy = os.path.join(work, "side_close.mp4")
    shutil.copy2(src_video, src_copy)

    contact_csv_src = os.path.join(PLAY_DIR, "contact_states_side.csv")
    contact_csv_copy = None
    contact_rows = []
    if os.path.isfile(contact_csv_src):
        contact_csv_copy = os.path.join(work, "contact_states_side.csv")
        shutil.copy2(contact_csv_src, contact_csv_copy)
        contact_rows = load_contact_rows(contact_csv_copy)

    frame_dir = os.path.join(work, "frames")
    frames = extract_dense_frames(src_copy, frame_dir, frame_count=args.frame_count, contact_rows=contact_rows)

    gif_path = os.path.join(work, "side_close_dense.gif")
    make_gif(frames, gif_path, duration_ms=55)

    readme = os.path.join(work, "README.txt")
    with open(readme, "w", encoding="utf-8") as f:
        f.write("Side-view dense gait pack (single robot centered)\n")
        f.write(f"Checkpoint: {checkpoint}\n")
        f.write(f"Video length: {args.video_length} frames\n")
        f.write(f"Camera zoom: {args.zoom}\n")
        f.write(f"Extracted frames: {len(frames)}\n")
        if contact_rows:
            f.write(f"Contact state overlay: enabled ({len(contact_rows)} steps from CSV).\n")
            f.write("Legend: LF/RF/LR/RR ON/OFF (threshold=1.0).\n")
        else:
            f.write("Contact state overlay: CSV not found (fallback mode).\n")

    zip_path = os.path.join(PROJECT_ROOT, "logs", "frame_packs", f"spotmicro_side_dense_{ts}.zip")
    zip_dir(work, zip_path)

    print(f"zip: {zip_path}")
    print(f"gif: {gif_path}")

    token = env.get("TELEGRAM_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        send_document(token, chat_id, zip_path, "Side close-up dense frames ZIP (1~2s)")
        send_animation(token, chat_id, gif_path, "Side close-up short GIF")
        print("telegram: sent")
    else:
        print("telegram: skipped")


if __name__ == "__main__":
    main()
