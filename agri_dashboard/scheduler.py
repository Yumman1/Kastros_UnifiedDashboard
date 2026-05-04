"""
Background scheduler: runs WhatsApp data fetch at a fixed time every day.
Keeps running until you stop it (Ctrl+C). Use this if you don't want to use Task Scheduler.

Usage:
  python -m agri_dashboard.scheduler

Configure in .env:
  INGEST_DAILY_AT=08:00   # 24h format, e.g. 08:00 = 8 AM, 14:30 = 2:30 PM
"""

import os
import sys
import time
from datetime import datetime

# Ensure we can import from agri_dashboard
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)

from dotenv import load_dotenv
load_dotenv()

try:
    import schedule
except ImportError:
    print("Install schedule: pip install schedule")
    sys.exit(1)

from ingest_whatsapp import ingest_data


def job():
    print(f"[{datetime.now().isoformat()}] Running scheduled WhatsApp fetch...")
    ok, count, source = ingest_data(use_mock_if_no_api=False)
    print(f"[{datetime.now().isoformat()}] Done. success={ok}, records={count}, source={source}")


def main():
    raw = os.getenv("INGEST_DAILY_AT", "08:00").strip()
    try:
        h, m = raw.split(":")
        hour, minute = int(h), int(m)
    except Exception:
        hour, minute = 8, 0
    schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(job)
    print(f"Daily WhatsApp ingest scheduled at {hour:02d}:{minute:02d}. Press Ctrl+C to stop.")
    # Run once on start if we're past the scheduled time today (optional)
    now = datetime.now()
    if (now.hour, now.minute) >= (hour, minute):
        job()
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
