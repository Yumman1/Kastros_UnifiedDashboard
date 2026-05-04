"""
Debug Evolution API findMessages - see raw response structure.
Run: python -m agri_dashboard.debug_fetch
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
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "Instance1")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_CHAT_JID = (os.getenv("EVOLUTION_CHAT_JID") or "").strip()

BASE = f"{EVOLUTION_API_URL}{EVOLUTION_API_PREFIX}"
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}

def main():
    jids = [j.strip() for j in EVOLUTION_CHAT_JID.split(",") if j.strip()] if EVOLUTION_CHAT_JID else []
    if not jids:
        print("EVOLUTION_CHAT_JID not set. Fetching chats first...")
        r = requests.post(f"{BASE}/chat/findChats/{EVOLUTION_INSTANCE}", headers=HEADERS, json={}, timeout=15)
        r.raise_for_status()
        data = r.json()
        chats = data if isinstance(data, list) else data.get("chats", data.get("data", []))
        jids = [c.get("remoteJid") or c.get("id") for c in (chats or [])[:3] if (c.get("remoteJid") or c.get("id"))]
    if not jids:
        print("No chats found")
        return 1
    jid = jids[0]
    print(f"Fetching messages for {jid}...")
    body = {"where": {"key": {"remoteJid": jid}}, "limit": 10}
    r = requests.post(f"{BASE}/chat/findMessages/{EVOLUTION_INSTANCE}", headers=HEADERS, json=body, timeout=30)
    print(f"Status: {r.status_code}")
    data = r.json()
    print("Response keys:", list(data.keys()) if isinstance(data, dict) else f"list len={len(data)}")
    raw = data.get("messages", data.get("data"))
    if raw is None and isinstance(data, list):
        raw = data
    if isinstance(raw, list):
        print(f"Messages count: {len(raw)}")
        if raw:
            print("\nFirst message (full):")
            print(json.dumps(raw[0], indent=2, default=str)[:2000])
    else:
        print("Raw response:", json.dumps(data, indent=2, default=str)[:1500])
    return 0

if __name__ == "__main__":
    sys.exit(main())
