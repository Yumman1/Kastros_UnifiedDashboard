"""
Debug Evolution API: print raw findChats and connection state.
Run from project root: python -m agri_dashboard.debug_evolution
"""
import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

import requests

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
EVOLUTION_API_PREFIX = (os.getenv("EVOLUTION_API_PREFIX") or "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "agri-dashboard")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

BASE = f"{EVOLUTION_API_URL}{EVOLUTION_API_PREFIX}"
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}


def main():
    print(f"EVOLUTION_INSTANCE from .env: {EVOLUTION_INSTANCE!r}")
    print(f"URL: {BASE}/chat/findChats/{EVOLUTION_INSTANCE}\n")
    if not EVOLUTION_API_KEY:
        print("EVOLUTION_API_KEY not set in .env")
        return 1
    # Connection state
    try:
        r = requests.get(f"{BASE}/instance/connectionState/{EVOLUTION_INSTANCE}", headers=HEADERS, timeout=5)
        print(f"Connection state: {r.status_code} -> {r.text[:200]}")
    except Exception as e:
        print(f"Connection state error: {e}")
    # Raw findChats
    try:
        r = requests.post(f"{BASE}/chat/findChats/{EVOLUTION_INSTANCE}", headers=HEADERS, json={}, timeout=15)
        print(f"\nfindChats status: {r.status_code}")
        data = r.json() if r.text else None
        if data is not None:
            print("findChats response (keys):", list(data.keys()) if isinstance(data, dict) else f"list len={len(data)}")
            print(json.dumps(data, indent=2)[:2000])
        else:
            print("findChats response: empty")
    except Exception as e:
        print(f"findChats error: {e}")

    # findMessages: get first chat's remoteJid and fetch messages
    if data is not None and EVOLUTION_API_KEY:
        chats_list = data if isinstance(data, list) else data.get("chats", data.get("data", []))
        if isinstance(chats_list, list) and len(chats_list) > 0:
            first = chats_list[0]
            remote_jid = first.get("remoteJid") or first.get("id")
            if remote_jid and "@" in str(remote_jid):
                print(f"\n--- findMessages for {remote_jid} ---")
                for body in [
                    {"where": {"key": {"remoteJid": remote_jid}}},
                    {"remoteJid": remote_jid, "size": 10, "page": 1},
                ]:
                    try:
                        url = f"{BASE}/chat/findMessages/{EVOLUTION_INSTANCE}"
                        r2 = requests.post(url, headers=HEADERS, json=body, timeout=15)
                        print(f"Body {list(body.keys())} -> status {r2.status_code}")
                        if r2.status_code == 200 and r2.text:
                            d2 = r2.json()
                            keys = list(d2.keys()) if isinstance(d2, dict) else f"list len={len(d2)}"
                            print(f"  Response: {keys}")
                            raw = d2.get("messages", d2.get("data", d2 if isinstance(d2, list) else []))
                            if isinstance(raw, list):
                                print(f"  Messages count: {len(raw)}")
                                if raw and isinstance(raw[0], dict):
                                    print(f"  First message keys: {list(raw[0].keys())[:15]}")
                            else:
                                print(f"  Raw (first 500 chars): {str(d2)[:500]}")
                        else:
                            print(f"  Response: {r2.text[:300]}")
                    except Exception as e2:
                        print(f"  Error: {e2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
