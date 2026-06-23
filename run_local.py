"""Jalankan SublyAI di localhost dan buka browser otomatis."""

from server_boot import run_server

if __name__ == "__main__":
    run_server(open_browser=True)