import psutil
targets = ['train.py', 'training_supervisor', 'training_heartbeat']
for p in psutil.process_iter():
    try:
        cmd = ' '.join(p.cmdline())
        if any(t in cmd for t in targets):
            print(f"Killing PID={p.pid}: {cmd[:150]}")
            p.kill()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    except Exception as e:
        print(f"Error: {e}")
print("--- all killed ---")
