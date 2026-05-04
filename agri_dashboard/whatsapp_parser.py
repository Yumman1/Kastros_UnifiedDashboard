"""
Parse WhatsApp chat export (.txt) files and extract messages for commodity price ingestion.
Supports standard WhatsApp export format (Android & iOS).
"""

import re
from datetime import datetime
from typing import List, Dict, Optional


# WhatsApp export formats:
# Android: [DD/MM/YYYY, HH:MM:SS] Sender Name: Message
# Android alt: DD/MM/YYYY, HH:MM:SS - Sender Name: Message
# iOS: [DD/MM/YYYY, HH:MM:SS AM/PM] Sender Name: Message
MESSAGE_PATTERN = re.compile(
    r'^\[?(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\s*\]?\s*[-–—]?\s*(.+?):\s*(.+)$',
    re.MULTILINE | re.IGNORECASE
)
# Fallback: date and time then sender
FALLBACK_PATTERN = re.compile(
    r'^(\d{1,2}/\d{1,2}/\d{2,4})[,\s]+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\s*[-–—]?\s*(.+?):\s*(.+)$',
    re.MULTILINE | re.IGNORECASE
)


def _parse_date(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse date and time strings from WhatsApp export into datetime."""
    date_str = date_str.strip()
    time_str = time_str.strip()
    try:
        # Date: DD/MM/YYYY or D/M/YY
        parts = date_str.replace('-', '/').split('/')
        if len(parts) != 3:
            return None
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        if year < 100:
            year += 2000
        # Time: 24h (e.g. 14:30:00) or 12h (e.g. 2:30 PM)
        time_clean = re.sub(r'\s+', ' ', time_str).strip().upper()
        is_pm = ' PM' in time_clean or 'PM' in time_clean
        time_clean = re.sub(r'\s*AM\s*|\s*PM\s*', '', time_clean, flags=re.I).strip()
        t_parts = time_clean.split(':')
        hour = int(t_parts[0]) if t_parts else 0
        minute = int(t_parts[1]) if len(t_parts) > 1 else 0
        second = int(t_parts[2]) if len(t_parts) > 2 else 0
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12 and ('AM' in time_str.upper() or 'PM' not in time_str.upper()):
            hour = 0
        hour = min(23, max(0, hour))
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, IndexError):
        return None


def parse_whatsapp_export(content: str, group_name: str = "WhatsApp Export") -> List[Dict]:
    """
    Parse WhatsApp chat export text content.
    
    Args:
        content: Raw text of the exported chat (e.g. from .txt file)
        group_name: Source name to use for all messages (e.g. group name)
    
    Returns:
        List of dicts with keys: timestamp, sender, message, source
    """
    messages = []
    lines = content.splitlines()
    current_message = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Try main pattern: [date, time] - Sender: text
        m = MESSAGE_PATTERN.match(line)
        if not m:
            m = FALLBACK_PATTERN.match(line)
        if m:
            date_str, time_str, sender, message = m.groups()
            dt = _parse_date(date_str, time_str)
            if dt:
                current_message = {
                    "timestamp": dt,
                    "sender": sender.strip(),
                    "message": message.strip(),
                    "source": group_name
                }
                messages.append(current_message)
            else:
                # Append to previous message if date parse failed (continuation line)
                if current_message and not re.match(r'^\[?\d', line):
                    current_message["message"] += "\n" + line
        else:
            # Continuation of previous message (no date prefix)
            if current_message and not re.match(r'^\[?\d{1,2}/\d{1,2}', line):
                current_message["message"] += "\n" + line
    
    return messages
