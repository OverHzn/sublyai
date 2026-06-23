"""Core server bootstrap — dipakai run_local.py, run_server.py, dan Electron shell."""

from __future__ import annotations

import os
import shutil
import socket
import sys

HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_RANGE = range(8000, 8010)
PORT_MARKER = "SUBLYAI_PORT="


def check_deps() -> None:
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg tidak ditemukan di PATH.", flush=True)
        print("Install ffmpeg dulu, lalu jalankan ulang.", flush=True)
        sys.exit(1)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
            return True
        except OSError:
            return False


def pick_port() -> int:
    for port in PORT_RANGE:
        if port_free(port):
            return port
    print(
        f"ERROR: Port {DEFAULT_PORT}-{PORT_RANGE.stop - 1} semua dipakai.",
        flush=True,
    )
    print("Tutup instance SublyAI lain, lalu jalankan ulang.", flush=True)
    sys.exit(1)


def run_server(*, open_browser: bool = False) -> None:
    check_deps()
    port = pick_port()
    url = f"http://{HOST}:{port}"

    # Electron shell membaca baris ini dari stdout
    print(f"{PORT_MARKER}{port}", flush=True)

    if port != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} sedang dipakai — pakai port {port}.", flush=True)

    print(f"SublyAI starting at {url}", flush=True)

    if open_browser and os.environ.get("SUBLYAI_NO_BROWSER") != "1":
        import threading
        import time
        import webbrowser

        def _open() -> None:
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
        print("Tekan Ctrl+C untuk stop.\n", flush=True)

    import uvicorn

    uvicorn.run("app:app", host=HOST, port=port, reload=False, log_level="info")