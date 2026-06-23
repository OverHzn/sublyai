"""Jalankan server saja — untuk Electron desktop shell (tanpa buka browser)."""

from server_boot import run_server

if __name__ == "__main__":
    run_server(open_browser=False)