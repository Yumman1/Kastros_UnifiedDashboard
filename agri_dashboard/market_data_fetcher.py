"""
External market data: ICE Cotton #2 futures and USD/PKR exchange rate via yfinance.
Cached with Streamlit's @st.cache_data to avoid repeated API calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]


LBS_PER_KG = 2.20462


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ice_cotton_daily(days: int = 180) -> Optional[pd.DataFrame]:
    """ICE Cotton #2 futures daily close in US cents/lb."""
    if yf is None:
        return None
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        ticker = yf.Ticker("CT=F")
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    df = hist[["Close"]].copy()
    df = df.rename(columns={"Close": "close_cents_per_lb"})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df["date"] = df.index.date
    df = df.reset_index(drop=True)
    return df[["date", "close_cents_per_lb"]]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_usd_pkr_rate(days: int = 180) -> Optional[pd.DataFrame]:
    """Daily USD/PKR exchange rate."""
    if yf is None:
        return None
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        ticker = yf.Ticker("PKR=X")
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    df = hist[["Close"]].copy()
    df = df.rename(columns={"Close": "usd_pkr"})
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df["date"] = df.index.date
    df = df.reset_index(drop=True)
    return df[["date", "usd_pkr"]]


def convert_pkr_per_kg_to_cents_per_lb(
    price_per_kg: float,
    usd_pkr: float,
) -> float:
    """PKR/kg  ->  US cents/lb"""
    if usd_pkr <= 0:
        return 0.0
    price_per_lb = price_per_kg / LBS_PER_KG
    usd_per_lb = price_per_lb / usd_pkr
    return usd_per_lb * 100.0
