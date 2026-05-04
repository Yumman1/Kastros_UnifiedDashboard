"""
Evolution API client for fetching WhatsApp chats and messages.
"""

import os
from datetime import datetime
from typing import List, Optional

import requests
from dotenv import load_dotenv

_agri_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_agri_dir, ".env"))

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
EVOLUTION_API_PREFIX = (os.getenv("EVOLUTION_API_PREFIX") or "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "agri-dashboard")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")

BASE = f"{EVOLUTION_API_URL}{EVOLUTION_API_PREFIX}"
HEADERS = {"Content-Type": "application/json", "apikey": EVOLUTION_API_KEY}


def find_chats(instance: str) -> List[dict]:
    """Fetch list of chats (groups, contacts) for the instance."""
    url = f"{BASE}/chat/findChats/{instance}"
    try:
        r = requests.post(url, headers=HEADERS, json={}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"findChats: {e}") from e

    chats = data if isinstance(data, list) else data.get("chats", data.get("data", []))
    return chats if isinstance(chats, list) else []


def _extract_text_from_message(msg: dict) -> Optional[str]:
    """Extract plain text from Evolution message object."""
    if not isinstance(msg, dict):
        return None
    # Try various shapes: message.conversation, message.extendedTextMessage.text, content.text
    inner = msg.get("message") or msg.get("content") or msg
    if isinstance(inner, str):
        return inner.strip() if inner.strip() else None
    if isinstance(inner, dict):
        t = inner.get("conversation")
        if isinstance(t, str) and t.strip():
            return t.strip()
        ext = inner.get("extendedTextMessage") or {}
        if isinstance(ext, dict):
            t = ext.get("text")
            if isinstance(t, str) and t.strip():
                return t.strip()
    return None


def _extract_timestamp(msg: dict) -> datetime:
    """Extract timestamp from message."""
    ts = msg.get("messageTimestamp") or msg.get("timestamp")
    if ts is not None:
        try:
            return datetime.fromtimestamp(int(ts))
        except (ValueError, TypeError):
            pass
    return datetime.now()


def fetch_messages_for_chat(
    instance: str,
    remote_jid: str,
    limit: int = 500,
    debug_out: Optional[List[str]] = None,
) -> List[dict]:
    """Fetch messages from a single chat. Returns list of {body, from, timestamp}."""
    def _log(m: str):
        if debug_out is not None:
            debug_out.append(f"[evolution_api] {m}")

    url = f"{BASE}/chat/findMessages/{instance}"
    body = {"where": {"key": {"remoteJid": remote_jid}}, "limit": limit}
    try:
        r = requests.post(url, headers=HEADERS, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _log(f"findMessages failed: {e}")
        return []

    # Evolution v2 returns: { messages: { records: [...], total, pages } } or { messages: [...] }
    msgs_obj = data.get("messages", data.get("data"))
    if isinstance(msgs_obj, dict) and "records" in msgs_obj:
        raw = msgs_obj["records"]
    elif isinstance(msgs_obj, list):
        raw = msgs_obj
    elif isinstance(data, list):
        raw = data
    else:
        raw = []

    out = []
    source = str(remote_jid)
    for m in raw:
        text = _extract_text_from_message(m)
        if not text:
            continue
        ts = _extract_timestamp(m)
        out.append({"body": text, "from": source, "timestamp": ts.isoformat(), "source": source})

    if not out and raw and debug_out:
        # Debug: log first raw message keys to fix parser
        first = raw[0] if isinstance(raw[0], dict) else {}
        _log(f"Raw msg keys (0 extracted): {list(first.keys())[:20]}")
    return out


def fetch_all_messages_for_ingest(
    instance: str,
    chat_jids: Optional[List[str]] = None,
    chat_jid: Optional[str] = None,
    debug_out: Optional[List[str]] = None,
) -> Optional[List[dict]]:
    """
    Fetch messages from Evolution API for ingest.
    If chat_jids or chat_jid provided, fetch from those chats only.
    Otherwise fetch from all chats.
    Returns list of {body, from/source, timestamp} or None on error.
    """
    def _log(m: str):
        if debug_out is not None:
            debug_out.append(f"[evolution_api] {m}")

    jids = []
    if chat_jids:
        jids = [j.strip() for j in chat_jids if j and str(j).strip()]
    elif chat_jid and str(chat_jid).strip():
        jids = [str(chat_jid).strip()]

    if not jids:
        # Fetch all chats, then messages from each
        try:
            chats = find_chats(instance)
        except Exception as e:
            _log(f"find_chats failed: {e}")
            return []
        for c in chats:
            jid = c.get("remoteJid") or c.get("id") or c.get("jid")
            if jid and "@" in str(jid):
                jids.append(str(jid))

    if not jids:
        _log("No chats to fetch from")
        return []

    # Build JID -> group/chat name mapping (subject=group name, name=contact)
    jid_to_name = {}
    try:
        chats = find_chats(instance)
        for c in chats:
            jid = c.get("remoteJid") or c.get("id") or c.get("jid")
            # Groups use subject, contacts use name or pushName
            name = c.get("subject") or c.get("name") or c.get("pushName") or c.get("formattedName")
            if jid and name:
                jid_to_name[str(jid)] = str(name).strip()
    except Exception as e:
        _log(f"Could not fetch chat names: {e}")

    # Testing limits: few messages to stay under Gemini free tier (15 RPM)
    MAX_PER_CHAT = int(os.getenv("INGEST_MAX_PER_CHAT", "1"))
    MAX_TOTAL = int(os.getenv("INGEST_MAX_TOTAL", "3"))
    all_msgs = []
    for jid in jids:
        if len(all_msgs) >= MAX_TOTAL:
            break
        msgs = fetch_messages_for_chat(instance, jid, limit=MAX_PER_CHAT, debug_out=debug_out)
        remaining = MAX_TOTAL - len(all_msgs)
        chunk = msgs[:remaining]
        # Use group name instead of JID when available
        chat_name = jid_to_name.get(str(jid), str(jid))
        for m in chunk:
            m["source"] = chat_name
            m["from"] = chat_name
        all_msgs.extend(chunk)
        _log(f"Chat {chat_name[:30] if chat_name != jid else jid[:30]}...: {len(msgs)} fetched, {len(chunk)} added")

    _log(f"Total messages to process: {len(all_msgs)}")
    return all_msgs[:MAX_TOTAL]
