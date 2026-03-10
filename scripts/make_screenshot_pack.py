import argparse
import glob
import os
import zipfile
import datetime
import urllib.parse
import urllib.request

import av


def load_env(env_path):
    env = {}
    if not os.path.isfile(env_path):
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def latest_video(project_root):
    pattern = os.path.join(project_root, "logs", "rsl_rl", "spot_micro_flat", "*", "videos", "*.mp4")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    return files[-1] if files else None


def extract_consecutive_frames(video_path, out_dir, count=10):
    os.makedirs(out_dir, exist_ok=True)

    container = av.open(video_path)
    stream = container.streams.video[0]

    total_frames = stream.frames if stream.frames and stream.frames > 0 else 0
    if total_frames <= 0:
        # fallback decode count
        total_frames = sum(1 for _ in container.decode(video=0))
        container.close()
        container = av.open(video_path)
        stream = container.streams.video[0]

    start = max(0, (total_frames // 2) - (count // 2))
    end = start + count

    saved = []
    idx = 0
    for frame in container.decode(video=0):
        if idx < start:
            idx += 1
            continue
        if idx >= end:
            break
        img = frame.to_image()
        fn = f"side_seq_{idx:04d}.jpg"
        fp = os.path.join(out_dir, fn)
        img.save(fp, format="JPEG", quality=92)
        saved.append(fp)
        idx += 1

    container.close()
    return saved


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_dir):
            for name in files:
                fp = os.path.join(root, name)
                arc = os.path.relpath(fp, src_dir)
                zf.write(fp, arc)


def send_document(token, chat_id, file_path, caption):
    boundary = "----spotmicroboundary"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

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
    body += file_bytes
    body += f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    urllib.request.urlopen(req, timeout=60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, default="")
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    env = load_env(os.path.join(project_root, ".env"))

    video_path = args.video or latest_video(project_root)
    if not video_path or not os.path.isfile(video_path):
        print("ERROR: no video found")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    pack_root = os.path.join(project_root, "logs", "frame_packs", f"pack_{ts}")
    frame_dir = os.path.join(pack_root, "side")
    os.makedirs(frame_dir, exist_ok=True)

    saved = extract_consecutive_frames(video_path, frame_dir, count=args.count)

    # metadata note
    note = os.path.join(pack_root, "README.txt")
    with open(note, "w", encoding="utf-8") as f:
        f.write("SpotMicro gait screenshot pack\n")
        f.write(f"Source video: {video_path}\n")
        f.write(f"Frames: {len(saved)} consecutive frames (side-focused)\n")
        f.write("Note: front/rear packs require multi-view capture run after latest code update.\n")

    zip_path = os.path.join(project_root, "logs", "frame_packs", f"spotmicro_screenshots_side_{ts}.zip")
    zip_dir(pack_root, zip_path)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"video: {video_path}")
    print(f"frames_saved: {len(saved)}")
    print(f"zip: {zip_path}")
    print(f"zip_size_mb: {size_mb:.2f}")

    token = env.get("TELEGRAM_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if token and chat_id:
        caption = "SpotMicro 스크린샷 ZIP (측면 연속프레임 10장)"
        send_document(token, chat_id, zip_path, caption)
        print("telegram: sent")
    else:
        print("telegram: skipped (missing token/chat_id)")


if __name__ == "__main__":
    main()
