"""
start.py — One-command launcher for WorldBank Research Copilot
──────────────────────────────────────────────────────────────
Starts three services using `uv run` (always uses the project venv):
  1. FastAPI backend       → http://localhost:8002
  2. Streamlit dev panel   → http://localhost:8501
  3. Frontend static file  → http://localhost:3000

Usage:
  uv run python start.py
  python start.py          (also works — uv is invoked per-service)

Press Ctrl+C to stop all services.
"""

import subprocess
import sys
import time
import signal
import shutil
import threading
from pathlib import Path

# Force UTF-8 on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─────────────────────── colour helpers ───────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
VIOLET = "\033[95m"
WHITE  = "\033[97m"

def c(color, text): return f"{color}{text}{RESET}"

# ─────────────────────── check uv is available ────────────────
UV = shutil.which("uv")
if not UV:
    print(c(RED, "\n  ERROR: 'uv' not found on PATH."))
    print(c(YELLOW, "  Install it with:  pip install uv  or  winget install astral-sh.uv\n"))
    sys.exit(1)

ROOT     = Path(__file__).parent
FRONTEND = ROOT / "frontend"

# ─────────────────────── free port finder ─────────────────────
import socket

def find_free_port(preferred: int, max_tries: int = 10) -> int:
    """Return `preferred` if free, else the next available port."""
    for port in range(preferred, preferred + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return preferred  # fall back; the service will report the conflict itself

BACKEND_PORT   = find_free_port(8002)
STREAMLIT_PORT = find_free_port(8501)
FRONTEND_PORT  = find_free_port(3000)

# ─────────────────────── service definitions ──────────────────
# All commands use `uv run` so they always run inside the project venv,
# regardless of which Python is used to invoke this script.
SERVICES = [
    {
        "name":  "Backend  (FastAPI)",
        "color": CYAN,
        "url":   f"http://localhost:{BACKEND_PORT}",
        "docs":  f"http://localhost:{BACKEND_PORT}/docs",
        "cmd":   [UV, "run", "uvicorn", "app.main:app",
                  "--host", "0.0.0.0", "--port", str(BACKEND_PORT), "--reload"],
        "cwd":   ROOT,
    },
    {
        "name":  "Dev Panel (Streamlit)",
        "color": VIOLET,
        "url":   f"http://localhost:{STREAMLIT_PORT}",
        "docs":  None,
        "cmd":   [UV, "run", "streamlit", "run", "streamlit_app.py",
                  "--server.port", str(STREAMLIT_PORT),
                  "--server.headless", "true"],
        "cwd":   ROOT,
    },
    {
        "name":  "Frontend (static)",
        "color": GREEN,
        "url":   f"http://localhost:{FRONTEND_PORT}",
        "docs":  None,
        "cmd":   [UV, "run", "python", "-m", "http.server", str(FRONTEND_PORT),
                  "--directory", str(FRONTEND)],
        "cwd":   ROOT,
    },
]

processes = []

# ─────────────────────── banner ───────────────────────────────
def banner():
    print()
    print(c(BOLD + WHITE, "  +---------------------------------------------+"))
    print(c(BOLD + WHITE, "  |   WorldBank Research Copilot               |"))
    print(c(BOLD + WHITE, "  |   Starting all services via uv...          |"))
    print(c(BOLD + WHITE, "  +---------------------------------------------+"))
    print()

def url_table():
    print(c(BOLD, "  ------------------------- URLS -------------------------"))
    print()
    for svc in SERVICES:
        label = svc["name"].ljust(22)
        url   = c(BOLD + svc["color"], svc["url"])
        print(f"    {c(svc['color'], 'o')}  {label}  {url}")
        if svc.get("docs"):
            print(f"       {'API Docs'.ljust(22)}  {c(DIM, svc['docs'])}")
    print()
    print(c(BOLD + YELLOW, "  Open any URL above in your browser to test manually."))
    print(c(DIM,           "  Press Ctrl+C to stop all services."))
    print()

# ─────────────────────── log streaming ───────────────────────
def stream(proc, prefix, color):
    for line in proc.stdout:
        s = line.rstrip()
        if s:
            print(f"  {c(color + DIM, prefix + ' |')} {c(DIM, s)}", flush=True)

# ─────────────────────── start services ──────────────────────
def start_all():
    banner()
    print(c(DIM, "  Launching services with uv run...\n"))

    for svc in SERVICES:
        try:
            proc = subprocess.Popen(
                svc["cmd"],
                cwd=svc["cwd"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
            processes.append((svc, proc))

            tag = svc["name"].split("(")[0].strip()[:8].ljust(8)
            t = threading.Thread(
                target=stream,
                args=(proc, tag, svc["color"]),
                daemon=True,
            )
            t.start()

            print(f"  {c(GREEN, 'OK')} {c(svc['color'] + BOLD, svc['name'])} "
                  f"started  {c(DIM, '(pid ' + str(proc.pid) + ')')}")

        except FileNotFoundError as e:
            print(f"  {c(RED, 'ERR')} Could not start {svc['name']}: {e}")

    # give services a moment to bind ports
    time.sleep(3)
    print()
    url_table()

# ─────────────────────── cleanup ─────────────────────────────
def stop_all(signum=None, frame=None):
    print(f"\n  {c(YELLOW, 'Stopping all services...')}")
    for _, p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    for _, p in processes:
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
    print(c(GREEN, "  All stopped. Goodbye!\n"))
    sys.exit(0)

# ─────────────────────── main ────────────────────────────────
if __name__ == "__main__":
    signal.signal(signal.SIGINT,  stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    start_all()

    # keep alive; report if a service dies
    try:
        while True:
            for svc, proc in processes:
                if proc.poll() is not None:
                    print(f"\n  {c(RED, 'DIED')} {svc['name']} "
                          f"exited with code {proc.returncode}")
            time.sleep(5)
    except KeyboardInterrupt:
        stop_all()
