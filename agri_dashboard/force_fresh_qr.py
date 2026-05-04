"""
Create a NEW Evolution instance (different name) and fetch the QR code.
Old "agri-dashboard" session is kept in Docker volume, so reusing the same name
restores it as "open" and no QR is returned. Using a new name forces a fresh QR.
Run from project root: python -m agri_dashboard.force_fresh_qr
"""
import base64
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv()

from agri_dashboard.evolution_api import (
    delete_instance,
    create_instance,
    _base,
    _headers,
)
import requests


# New instance name each run so there's no old session in Docker volume → we get a QR
NEW_INSTANCE_NAME = f"agri-dashboard-{int(time.time())}"


def create_instance_with_name(name: str, integration: str = "WHATSAPP-BAILEYS"):
    """Create instance; returns (ok, message, full_response_dict). Use WHATSAPP-BAILEYS for QR."""
    import requests as req
    url = f"{_base()}/instance/create"
    r = req.post(
        url,
        headers=_headers(),
        json={"instanceName": name, "qrcode": True, "integration": integration},
        timeout=15,
    )
    data = r.json() if r.text else {}
    if r.status_code in (200, 201):
        return True, data.get("message", "Created"), data
    return False, data.get("message", data.get("error", r.text or f"Status {r.status_code}")), data


def get_connect_response(instance_name: str):
    url = f"{_base()}/instance/connect/{instance_name}"
    r = requests.get(url, headers=_headers(), timeout=15)
    if r.status_code != 200:
        return None, r.json() if r.text else {}
    return r.json() if r.text else {}, None


def extract_base64(data, from_value=None):
    """Get base64 QR from dict (or from a nested value)."""
    if from_value is not None and isinstance(from_value, str) and len(from_value) > 100:
        return from_value
    if not data:
        return None
    for key in ("base64", "base64Image", "qrcode", "qr", "pairingCode"):
        val = data.get(key)
        if isinstance(val, str) and len(val) > 100:
            return val
    if isinstance(data.get("instance"), dict):
        for key in ("base64", "base64Image", "qrcode", "qr"):
            val = data["instance"].get(key)
            if isinstance(val, str) and len(val) > 100:
                return val
    return None


def main():
    if not os.getenv("EVOLUTION_API_KEY"):
        print("Set EVOLUTION_API_KEY in agri_dashboard/.env")
        return 1

    instance = NEW_INSTANCE_NAME
    print(f"Creating NEW instance '{instance}' (fresh name = fresh QR)...")
    ok, msg, create_data = create_instance_with_name(instance)
    if not ok:
        print(f"  Create failed: {msg}")
        return 1
    print("  Created.")

    # Try QR from create response first (some APIs return it there)
    base64_str = extract_base64(create_data)
    if not base64_str and isinstance(create_data.get("instance"), dict):
        base64_str = extract_base64(create_data["instance"])

    if not base64_str:
        print("Fetching QR from connect endpoint (Baileys may need a few seconds)...")
        data, err = None, None
        for attempt in range(4):
            time.sleep(3 if attempt else 2)
            data, err = get_connect_response(instance)
            if err is not None:
                print(f"  Connect failed: {err}")
                return 1
            base64_str = extract_base64(data)
            if base64_str:
                break
            print(f"  Attempt {attempt + 1}/4: no QR yet, retrying...")
        if not base64_str:
            import json
            debug_path = os.path.join(SCRIPT_DIR, "evolution_connect_response.json")
            with open(debug_path, "w") as f:
                json.dump(data or {}, f, indent=2)
            print(f"  Full response saved to: {debug_path}")
    else:
        data = create_data

    if not base64_str:
        state = (data.get("instance") or {}).get("state") or data.get("state")
        print(f"  No QR in REST response (state={state}).")
        print("  This Evolution API only shows the QR in the Manager web UI.")
        print("")
        print("  Do this:")
        print("  1. Open: http://localhost:8080/manager")
        print("  2. Enter your API key (same as EVOLUTION_API_KEY in .env)")
        print(f"  3. Find instance '{instance}' and open it")
        print("  4. Click Connect / Get QR and scan with WhatsApp -> Linked devices")
        print(f"  5. In agri_dashboard/.env set: EVOLUTION_INSTANCE={instance}")
        return 1
    if "base64," in base64_str:
        base64_str = base64_str.split("base64,", 1)[1]
    try:
        qr_bytes = base64.b64decode(base64_str)
    except Exception:
        print("  Could not decode base64 QR.")
        return 1
    qr_path = os.path.join(SCRIPT_DIR, "evolution_qr.png")
    with open(qr_path, "wb") as f:
        f.write(qr_bytes)
    print(f"  QR saved to: {qr_path}")
    if sys.platform == "win32":
        os.startfile(qr_path)
    elif sys.platform == "darwin":
        os.system(f'open "{qr_path}"')
    else:
        os.system(f'xdg-open "{qr_path}"')
    print("\nScan the QR with WhatsApp -> Settings -> Linked devices -> Link a device")
    print(f"\nAfter linking, set in agri_dashboard/.env:")
    print(f"  EVOLUTION_INSTANCE={instance}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
