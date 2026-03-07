import psutil
for p in psutil.process_iter(['pid','name','cmdline','status']):
    try:
        cmdline = p.info['cmdline']
        if not cmdline:
            continue
        cmd = ' '.join(cmdline)
        cmd_lower = cmd.lower()
        if ('train.py' in cmd_lower or 'heartbeat' in cmd_lower or 'supervisor' in cmd_lower) and 'spot' in cmd_lower:
            print(f"PID: {p.info['pid']}  Status: {p.info['status']}")
            print(f"  CMD: {cmd[:250]}")
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
