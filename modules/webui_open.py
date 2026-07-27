"""Open the WebUI in the default browser or an Electron shell after the server is listening."""

from __future__ import annotations

import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser

_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_electron_gallery_dir() -> str | None:
    override = os.environ.get("WEBUI_ELECTRON_GALLERY_DIR", "").strip()
    if override and os.path.isfile(os.path.join(override, "package.json")):
        return os.path.abspath(override)
    parent = os.path.dirname(_backend_root)
    for name in ("image-scoring-gallery", "electron-image-scoring"):
        p = os.path.join(parent, name)
        if os.path.isfile(os.path.join(p, "package.json")):
            return p
    return None


def _open_default_browser(url: str) -> None:
    if os.environ.get("WSL_DISTRO_NAME"):
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Opened WebUI in default browser (Windows): {url}")
            return
        except Exception as e:
            print(f"Could not open browser via cmd.exe ({e}); trying webbrowser module.")
    try:
        if webbrowser.open(url):
            print(f"Opened WebUI in browser: {url}")
        else:
            print(f"webbrowser.open returned False for {url}")
    except Exception as e:
        print(f"Could not open browser: {e}")


def _open_electron_shell(webui_url: str) -> None:
    gallery = resolve_electron_gallery_dir()
    if not gallery:
        print(
            "WEBUI_OPEN_UI=electron: no gallery repo found next to the backend "
            "(expected sibling image-scoring-gallery). Set WEBUI_ELECTRON_GALLERY_DIR or use browser."
        )
        return
    is_wsl = bool(os.environ.get("WSL_DISTRO_NAME"))
    if is_wsl:
        try:
            gal_win = subprocess.check_output(["wslpath", "-w", gallery]).decode().strip()
        except Exception as e:
            print(f"WEBUI_OPEN_UI=electron: wslpath failed: {e}")
            return
    else:
        gal_win = os.path.abspath(gallery)
    inner = f'cd /d "{gal_win}" && set ELECTRON_IS_DEV=1 && npx electron . --webui-shell={webui_url}'
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", inner],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"Started Electron WebUI shell: {webui_url}")
    except Exception as e:
        print(f"WEBUI_OPEN_UI=electron: failed to start Electron: {e}")


def schedule_webui_open(host_for_client: str, port: int, mode: str) -> None:
    mode = (mode or "").strip().lower()
    if mode not in ("browser", "electron"):
        return

    base = f"http://{host_for_client}:{port}".rstrip("/")
    url = f"{base}/ui/"

    def worker() -> None:
        health = f"{base}/ui/"
        for _ in range(120):
            try:
                urllib.request.urlopen(health, timeout=2)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        else:
            print("WEBUI_OPEN_UI: timed out waiting for server; open the UI manually.")
            return

        if mode == "browser":
            _open_default_browser(url)
        else:
            _open_electron_shell(url)

    threading.Thread(target=worker, daemon=True).start()
