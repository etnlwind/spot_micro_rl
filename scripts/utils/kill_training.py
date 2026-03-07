import psutil
for p in psutil.process_iter():
    try:
        cmd = ' '.join(p.cmdline())
        if 'train.py' in cmd:
            print(f"TRAIN PID={p.pid} name={p.name()} status={p.status()}")
            # Kill this process tree
            parent = psutil.Process(p.pid)
            for child in parent.children(recursive=True):
                print(f"  Killing child PID={child.pid}")
                child.kill()
            print(f"  Killing PID={p.pid}")
            parent.kill()
            print("  DONE")
    except (psutil.AccessDenied, psutil.NoSuchProcess, Exception) as e:
        pass
print("--- scan complete ---")
