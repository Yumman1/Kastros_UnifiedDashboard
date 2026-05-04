"""
Fetch Evolution API QR code and open it so you can scan with WhatsApp.
Run from project root: python -m agri_dashboard.show_qr
Or from agri_dashboard: python show_qr.py
"""
import base64
import os
import sys

# Ensure we load .env from agri_dashboard
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv()

import requests

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
EVOLUTION_API_PREFIX = (os.getenv("EVOLUTION_API_PREFIX") or "").strip().rstrip("/")
if EVOLUTION_API_PREFIX and not EVOLUTION_API_PREFIX.startswith("/"):
    EVOLUTION_API_PREFIX = "/" + EVOLUTION_API_PREFIX
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "agri-dashboard")

BASE = f"{EVOLUTION_API_URL}{EVOLUTION_API_PREFIX}"
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}


def main():
    if not EVOLUTION_API_KEY:
        print("Set EVOLUTION_API_KEY in agri_dashboard/.env")
        return 1
    url = f"{BASE}/instance/connect/{EVOLUTION_INSTANCE}"
    print(f"Fetching QR from {url} ...")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        data = r.json() if r.text else {}
    except Exception as e:
        print(f"Request failed: {e}")
        return 1
    if r.status_code != 200:
        print(f"API error {r.status_code}: {data}")
        return 1

    # Try common response shapes for base64 QR
    base64_str = None
    for key in ("base64", "base64Image", "qrcode", "qr"):
        val = data.get(key)
        if isinstance(val, str) and len(val) > 100:
            base64_str = val
            break
    if not base64_str and isinstance(data.get("instance"), dict):
        for key in ("base64", "base64Image", "qrcode"):
            val = data["instance"].get(key)
            if isinstance(val, str) and len(val) > 100:
                base64_str = val
                break

    if base64_str:
        if "base64," in base64_str:
            base64_str = base64_str.split("base64,", 1)[1]
        try:
            qr_bytes = base64.b64decode(base64_str)
        except Exception:
            print("Could not decode base64 QR.")
            return 1
        qr_path = os.path.join(SCRIPT_DIR, "evolution_qr.png")
        with open(qr_path, "wb") as f:
            f.write(qr_bytes)
        print(f"QR saved to: {qr_path}")
        # Open with default image viewer
        if sys.platform == "win32":
            os.startfile(qr_path)
        elif sys.platform == "darwin":
            os.system(f'open "{qr_path}"')
        else:
            os.system(f'xdg-open "{qr_path}"')
        print("Scan the QR with WhatsApp -> Settings -> Linked devices -> Link a device")
        return 0

    state = (data.get("instance") or {}).get("state") or data.get("state")
    if state == "open":
        print("Instance is already connected. To get a new QR:")
        print("  1. Open http://localhost:8080/manager")
        print("  2. Find agri-dashboard -> Logout / Disconnect")
        print("  3. Run this script again or click Get QR in Manager")
    else:
        print("No QR in API response. Response keys:", list(data.keys()))
        print("Try opening http://localhost:8080/manager and use Connect/QR there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
