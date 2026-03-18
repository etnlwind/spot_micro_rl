import psutil
found = False
for p in psutil.process_iter(['pid','name','cmdline','status']):
    try:
        cmdline = p.info.get('cmdline') or []
        if not cmdline:
            continue
        cmd = ' '.join(cmdline)
        cmd_lower = cmd.lower()
        if 'train.py' in cmd_lower or 'heartbeat' in cmd_lower or 'supervisor' in cmd_lower:
            print(f"PID: {p.info['pid']}  Status: {p.info['status']}  Name: {p.info['name']}")
            print(f"  CMD: {cmd[:250]}")
            found = True
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
if not found:
    print("No training/monitor processes found.")
