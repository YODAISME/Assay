import os
import sys
import time
import socket
import subprocess
import webbrowser
import uvicorn

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def resolve_port(port: int = 8000) -> int:
    if not is_port_in_use(port):
        return port

    print(f"  [Auto-Recovery] Port {port} is occupied by an earlier background session.")
    print(f"  Releasing port {port}...")

    # On Windows, find PID listening on this port and terminate it
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
            current_pid = os.getpid()
            for line in output.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and "LISTENING" in parts[3].upper():
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != current_pid:
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                        time.sleep(0.6)
        except Exception:
            pass

    # Verify if port is freed
    if not is_port_in_use(port):
        print(f"  Successfully cleared port {port}!")
        return port

    # If still occupied (e.g. by system process), pick next free port
    for alt_port in range(port + 1, port + 20):
        if not is_port_in_use(alt_port):
            print(f"  Falling back to open port: {alt_port}")
            return alt_port

    return port

if __name__ == "__main__":
    active_port = resolve_port(8000)
    url = f"http://localhost:{active_port}"

    print("=" * 60)
    print("  ASSAY TALENT INTELLIGENCE PLATFORM — LIQUID LIGHT")
    print("=" * 60)
    print(f"  Server URL: {url}")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run("backend.app:app", host="127.0.0.1", port=active_port, reload=False)
