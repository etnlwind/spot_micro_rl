import psutil
for pid in [49540, 79296]:
    try:
        p = psutil.Process(pid)
        print(f"PID={pid} name={p.name()} cmd={' '.join(p.cmdline())[:200]}")
    except Exception as e:
        print(f"PID={pid}: {e}")
# Also check for any isaaclab or train processes
for p in psutil.process_iter():
    try:
        cmd = ' '.join(p.cmdline())
        if 'train.py' in cmd or 'isaaclab' in cmd.lower():
            print(f"FOUND: PID={p.pid} cmd={cmd[:200]}")
    except:
        pass
print("--- done ---")
