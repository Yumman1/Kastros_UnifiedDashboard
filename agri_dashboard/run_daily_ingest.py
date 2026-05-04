"""
One-shot WhatsApp data fetch for use with Windows Task Scheduler (or cron).
Run this script at your desired time each day to auto-import Live Rates from WhatsApp.

Setup in Windows Task Scheduler:
  1. Open Task Scheduler → Create Basic Task
  2. Trigger: Daily, set time (e.g. 8:00 AM)
  3. Action: Start a program
  4. Program: python (or full path to python.exe)
  5. Arguments: -m agri_dashboard.run_daily_ingest
  6. Start in: C:\Users\HP\Desktop\trading_AI_bot (your project folder)
"""

import os
import sys

# Ensure we can import from agri_dashboard
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from ingest_whatsapp import ingest_data

if __name__ == "__main__":
    ok, count, source = ingest_data(use_mock_if_no_api=False)
    # Log for Task Scheduler history
    print(f"[Daily Ingest] success={ok}, records={count}, source={source}")
