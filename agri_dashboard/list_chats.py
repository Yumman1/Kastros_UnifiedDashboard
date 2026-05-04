"""
List all WhatsApp chats (groups and contacts) for your Evolution instance.
Use this to find the group JID for EVOLUTION_CHAT_JID in .env.
Run from project root: python -m agri_dashboard.list_chats
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
os.chdir(SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

from agri_dashboard.evolution_api import EVOLUTION_INSTANCE, find_chats


def _safe_console(s: str) -> str:
    """Avoid UnicodeEncodeError on Windows console (cp1252)."""
    if not s:
        return s
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except (UnicodeEncodeError, AttributeError):
        return s.encode("ascii", errors="replace").decode("ascii")


def main():
    if not os.getenv("EVOLUTION_API_KEY"):
        print("Set EVOLUTION_API_KEY in agri_dashboard/.env")
        return 1
    print(f"Fetching chats for instance '{EVOLUTION_INSTANCE}'...\n")
    chats = find_chats(EVOLUTION_INSTANCE)
    if not chats:
        print("No chats found. Make sure WhatsApp is connected and you have chats.")
        return 0
    print("JID (use for EVOLUTION_CHAT_JID)     | Name / ID")
    print("-" * 60)
    for c in chats:
        # Prefer remoteJid (e.g. 923007654313-1414436245@g.us) for .env
        jid = c.get("remoteJid") or c.get("id") or c.get("jid") or "?"
        name = c.get("name") or c.get("subject") or ""
        print(f"{jid:<40} | {_safe_console(name)}")
    print("\nCopy the JID of your group (ends with @g.us) into .env:")
    print("  EVOLUTION_CHAT_JID=123456789012345@g.us")
    return 0

if __name__ == "__main__":
    sys.exit(main())
