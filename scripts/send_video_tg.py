"""Telegram 영상 전송 스크립트 (일회용)"""
import urllib.request
import json
import os
import sys

# .env 로드
env = {}
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

TOKEN = env["TELEGRAM_TOKEN"]
CHAT_ID = env["TELEGRAM_CHAT_ID"]
VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\project\spot_micro_rl\logs\rsl_rl\spot_micro_flat\2026-03-06_20-27-43\videos\play\rl-video-step-0.mp4"
CAPTION = sys.argv[2] if len(sys.argv) > 2 else "V18.1 model_600.pt"

url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
boundary = "----FormBoundary7MA4YWxkTrZu0gW"

with open(VIDEO_PATH, "rb") as vf:
    video_data = vf.read()

parts = []
# chat_id
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{CHAT_ID}\r\n")
# caption
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{CAPTION}\r\n")
# video header
parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"model_600.mp4\"\r\nContent-Type: video/mp4\r\n\r\n")

body = b""
for p in parts:
    body += p.encode("utf-8")
body += video_data
body += f"\r\n--{boundary}--\r\n".encode("utf-8")

req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
resp = urllib.request.urlopen(req, timeout=60)
result = json.loads(resp.read())
print(f"Video sent: {result['ok']}")
