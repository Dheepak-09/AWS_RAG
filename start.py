
import subprocess
import sys
import os
import threading
import webbrowser
import time

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = BASE_DIR
BACKEND_DIR  = BASE_DIR

FRONTEND_PORT = 3000
BACKEND_PORT  = 8000

# ---------------------------------------------------------------------------
# Start FastAPI backend
# ---------------------------------------------------------------------------
def start_backend():
    print("[Backend]  Starting FastAPI on http://127.0.0.1:8000 ...")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", str(BACKEND_PORT)],
        cwd=BACKEND_DIR,
    )

# ---------------------------------------------------------------------------
# Start frontend static server
# ---------------------------------------------------------------------------
def start_frontend():
    print(f"[Frontend] Starting static server on http://127.0.0.1:{FRONTEND_PORT} ...")
    subprocess.run(
        [sys.executable, "-m", "http.server", str(FRONTEND_PORT)],
        cwd=FRONTEND_DIR,
    )

# ---------------------------------------------------------------------------
# Open browser after a short delay
# ---------------------------------------------------------------------------
def open_browser():
    time.sleep(2)  # wait for servers to be ready
    url = f"http://127.0.0.1:{FRONTEND_PORT}/frontend.html"
    print(f"[Browser]  Opening {url}")
    webbrowser.open(url)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  Ailaysa RAG — Starting up")
    print("=" * 50)

    # Run backend and frontend in separate threads
    backend_thread  = threading.Thread(target=start_backend,  daemon=True)
    frontend_thread = threading.Thread(target=start_frontend, daemon=True)

    backend_thread.start()
    frontend_thread.start()

    # Open browser automatically
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    print("\n  Backend  → http://127.0.0.1:8000")
    print("  Frontend → http://127.0.0.1:3000/frontend.html")
    print("  API Docs → http://127.0.0.1:8000/docs")
    print("\n  Press Ctrl+C to stop everything\n")

    try:
        # Keep main thread alive
        backend_thread.join()
        frontend_thread.join()
    except KeyboardInterrupt:
        print("\n[Stopped]  Shutting down...")
        sys.exit(0)