import subprocess, os, sys

# 已在运行就不重启，避免 kill/restart 闪 cmd
PID_FILE = os.path.join(os.path.expanduser('~'), '.claude', 'cc_monitor.pid')
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        r = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True, timeout=3)
        if str(pid) in r.stdout:
            sys.exit(0)
    except Exception:
        pass

script = os.path.join(os.path.dirname(__file__), 'cc_monitor.py')
subprocess.Popen(['pythonw', script],
                 creationflags=0x00000008, close_fds=True)
