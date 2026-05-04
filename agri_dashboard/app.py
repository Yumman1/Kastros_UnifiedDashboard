"""
Pakistani Commodities Trading AI - Streamlit HITL app.
"""

from __future__ import annotations

from datetime import datetime
from io import StringIO
from typing import List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import (
    approve_all_pending,
    delete_market_trades,
    delete_pending_trade,
    fetch_market_trades,
    fetch_master_dictionary,
    fetch_pending_trades,
    init_db,
    insert_market_trade,
    insert_master_dictionary,
    insert_model_memory,
    insert_rejected_trade,
    reject_all_pending,
)
from dictionaries import PROVINCE_MAP
from extractor import extract_trade
from market_data_fetcher import (
    convert_pkr_per_kg_to_cents_per_lb,
    fetch_ice_cotton_daily,
    fetch_usd_pkr_rate,
)
from whatsapp_parser import parse_whatsapp_export


st.set_page_config(
    page_title="Pakistani Commodities Trading AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
init_db()

# Navigation keys → render_* (order preserved for radio)
_NAV: list[tuple[str, str]] = [
    ("ingestion", "📥 Data Ingestion"),
    ("dashboard", "📊 Live Dashboard"),
    ("analytics", "📈 Market Analytics"),
    ("hitl", "✅ Human Validation Queue"),
]
_NAV_BLURB: dict[str, str] = {
    "ingestion": "Ingest WhatsApp or CSV messages and run AI trade extraction into pending or approved rows.",
    "dashboard": "Browse every approved trade and curate the database with guarded bulk delete.",
    "analytics": "Slice by date and commodity, view provincial trends, and benchmark cotton against ICE futures.",
    "hitl": "Validate extractions, bulk approve/reject, teach the model, and extend the slang dictionary.",
}


def _inject_theme_css() -> None:
    st.markdown(
        """
<style>
  @import url("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap");

  html, body, input, button, textarea, [data-testid="stAppViewContainer"] * {
    font-family: "Plus Jakarta Sans", "Segoe UI", system-ui, sans-serif !important;
  }

  [data-testid="stAppViewContainer"] {
    background: linear-gradient(165deg, #f6faf7 0%, #eef4f0 45%, #e8f0eb 100%);
    color-scheme: light;
    color: #0f2922;
  }

  /* Main content: force dark text (Streamlit dark mode uses light text → invisible on our light BG) */
  [data-testid="stMain"] {
    color: #0f2922;
  }
  [data-testid="stMain"] .block-container,
  [data-testid="stMain"] .block-container p,
  [data-testid="stMain"] .block-container li,
  [data-testid="stMain"] .stMarkdown,
  [data-testid="stMain"] .stMarkdown p:not(.hero-sub),
  [data-testid="stMain"] .stMarkdown span:not(.hero-badge) {
    color: #143029 !important;
  }
  [data-testid="stMain"] .stMarkdown p.hero-sub {
    color: #415a4f !important;
  }
  [data-testid="stMain"] .stMarkdown span.hero-badge {
    color: #ffffff !important;
  }
  [data-testid="stMain"] [data-baseweb="typoParagraph"] {
    color: #143029 !important;
  }
  [data-testid="stMain"] [data-testid="stCaption"] {
    color: #143029 !important;
  }
  [data-testid="stMain"] h1,
  [data-testid="stMain"] h2,
  [data-testid="stMain"] h3,
  [data-testid="stMain"] h4 {
    color: #0f2922 !important;
  }
  [data-testid="stMain"] label,
  [data-testid="stMain"] [data-baseweb="typoLabel"] {
    color: #1b4332 !important;
  }
  [data-testid="stMain"] [data-testid="stMetricLabel"] {
    color: #415a4f !important;
  }
  [data-testid="stMain"] [data-testid="stMetricValue"] {
    color: #0f2922 !important;
  }
  [data-testid="stMain"] [data-testid="stMetricDelta"] svg,
  [data-testid="stMain"] [data-testid="stMetricDelta"] p {
    color: inherit;
  }
  [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
  [data-testid="stMain"] .stWidgetLabel p {
    color: #1b4332 !important;
  }
  [data-testid="stMain"] input:not([type="checkbox"]):not([type="radio"]),
  [data-testid="stMain"] textarea {
    color: #0f2922 !important;
    background-color: #ffffff !important;
    caret-color: #0f2922;
  }
  [data-testid="stMain"] [data-baseweb="select"] > div,
  [data-testid="stMain"] [data-baseweb="input"] > div {
    color: #0f2922 !important;
    background-color: #ffffff !important;
  }
  [data-testid="stMain"] pre,
  [data-testid="stMain"] code {
    color: #0f2922 !important;
    background-color: rgba(240, 248, 244, 0.95) !important;
  }
  [data-testid="stMain"] [data-testid="stExpander"] summary,
  [data-testid="stMain"] [data-testid="stExpander"] details summary p {
    color: #0f2922 !important;
  }
  [data-testid="stMain"] .stButton button[kind="secondary"],
  [data-testid="stMain"] .stButton button[kind="tertiary"] {
    color: #1b4332 !important;
    background-color: rgba(255, 255, 255, 0.9) !important;
  }

  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1b4332 0%, #2d6a4f 55%, #1b4332 100%);
    border-right: 1px solid rgba(255,255,255,0.08);
    color-scheme: dark;
  }
  [data-testid="stSidebar"] [data-baseweb="typoParagraph"],
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] .stMarkdown {
    color: rgba(255,255,255,0.92) !important;
  }
  [data-testid="stSidebar"] [data-baseweb="radio"] label {
    color: rgba(255,255,255,0.75) !important;
  }
  [data-testid="stSidebar"] .stRadio label {
    font-weight: 500;
  }

  [data-testid="stHeader"] {
    background: rgba(255,255,255,0.65);
    backdrop-filter: blur(8px);
  }

  .hero-title {
    font-size: 2.15rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #0f2922;
    margin: 0 0 0.35rem 0;
    line-height: 1.15;
  }
  .hero-sub {
    font-size: 1.05rem;
    color: #415a4f;
    margin: 0;
    max-width: 52rem;
    line-height: 1.5;
  }
  .hero-badge {
    display: inline-block;
    background: linear-gradient(135deg, #2d6a4f, #40916c);
    color: white;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    margin-bottom: 0.85rem;
  }

  .section-card {
    background: rgba(255,255,255,0.82);
    border: 1px solid rgba(45, 106, 79, 0.12);
    border-radius: 14px;
    padding: 1.25rem 1.35rem 1.35rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 8px 32px rgba(27, 67, 50, 0.06);
  }
  .section-card h2, .section-card h3 {
    margin-top: 0;
  }

  .sidebar-brand {
    color: rgba(255,255,255,0.95) !important;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: -0.02em;
    margin-bottom: 0.25rem;
  }
  .sidebar-brand-sub {
    color: rgba(255,255,255,0.65) !important;
    font-size: 0.8rem;
    margin-bottom: 1rem;
    line-height: 1.35;
  }

  .stat-pill {
    background: rgba(255,255,255,0.1);
    border-radius: 10px;
    padding: 0.65rem 0.75rem;
    margin-bottom: 0.5rem;
    border: 1px solid rgba(255,255,255,0.12);
  }
  .stat-pill .label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: rgba(255,255,255,0.55);
    margin-bottom: 0.2rem;
  }
  .stat-pill .value {
    font-size: 1.35rem;
    font-weight: 700;
    color: #d8f3dc;
  }

  div[data-testid="stMetricValue"] {
    font-weight: 700;
  }
  [data-testid="metric-container"] {
    background: rgba(255,255,255,0.75);
    border: 1px solid rgba(45, 106, 79, 0.1);
    border-radius: 12px;
    padding: 0.85rem 1rem;
  }

  .stButton button[kind="primary"] {
    background: linear-gradient(135deg, #2d6a4f, #40916c);
    border: none;
    font-weight: 600;
  }
  .stButton button[kind="secondary"] {
    border-color: rgba(45, 106, 79, 0.35);
  }

  footer { visibility: hidden; height: 0; }

  [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255,255,255,0.82) !important;
    border: 1px solid rgba(45, 106, 79, 0.12) !important;
    border-radius: 14px !important;
    padding: 0.85rem 1.15rem 1.15rem !important;
    margin-bottom: 1rem !important;
    box-shadow: 0 8px 32px rgba(27, 67, 50, 0.06);
  }
</style>
        """,
        unsafe_allow_html=True,
    )


def _sidebar_stats() -> None:
    try:
        n_pending = len(fetch_pending_trades())
        n_market = len(fetch_market_trades())
    except Exception:
        n_pending = n_market = 0
    st.sidebar.markdown(
        f"""
<div class="stat-pill"><div class="label">Pending review</div><div class="value">{n_pending}</div></div>
<div class="stat-pill"><div class="label">Approved trades</div><div class="value">{n_market}</div></div>
        """,
        unsafe_allow_html=True,
    )


def _apply_chart_theme(fig: go.Figure, height: int | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(255,255,255,0)",
        plot_bgcolor="rgba(248,250,247,0.9)",
        font=dict(family="Plus Jakarta Sans, Segoe UI, sans-serif", color="#0f2922", size=13),
        title_font=dict(size=16, color="#1b4332"),
        margin=dict(l=48, r=28, t=56, b=48),
    )
    if height is not None:
        fig.update_layout(height=height)
    fig.update_xaxes(
        gridcolor="rgba(45, 106, 79, 0.12)",
        zerolinecolor="rgba(45, 106, 79, 0.2)",
    )
    fig.update_yaxes(
        gridcolor="rgba(45, 106, 79, 0.12)",
        zerolinecolor="rgba(45, 106, 79, 0.2)",
    )
    return fig


def _decode_uploaded(uploaded_file) -> str:
    return uploaded_file.getvalue().decode("utf-8", errors="replace")


def _messages_from_upload(uploaded_file) -> List[dict]:
    name = (uploaded_file.name or "").lower()
    content = _decode_uploaded(uploaded_file)

    if name.endswith(".csv"):
        df = pd.read_csv(StringIO(content))
        preferred_cols = ["message", "raw_message", "text", "content", "body"]
        use_col = next((c for c in preferred_cols if c in df.columns), None)
        ts_col = next((c for c in ["timestamp", "date", "datetime", "received_at"] if c in df.columns), None)

        entries = []
        if use_col:
            for _, row in df.iterrows():
                msg = str(row.get(use_col, "")).strip()
                if not msg or msg == "nan":
                    continue
                ts = row.get(ts_col) if ts_col else None
                if ts is not None and str(ts).strip() and str(ts) != "nan":
                    try:
                        ts = pd.to_datetime(ts, errors="coerce")
                        ts = ts.strftime("%Y-%m-%d %H:%M:%S") if not pd.isna(ts) else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                entries.append({"message": msg, "timestamp": ts})
        else:
            for _, r in df.iterrows():
                joined = " | ".join([str(v).strip() for v in r.tolist() if str(v).strip() and str(v) != "nan"])
                if joined:
                    entries.append({"message": joined, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    else:
        parsed = parse_whatsapp_export(content, group_name="Uploaded WhatsApp Export")
        entries = []
        for p in parsed:
            msg = str(p.get("message", "")).strip()
            if not msg:
                continue
            ts = p.get("timestamp")
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entries.append({"message": msg, "timestamp": ts_str})

    return entries


def _to_dict_rows(rows):
    return [dict(r) for r in rows]


def render_data_ingestion() -> None:
    with st.container(border=True):
        st.header("Data Ingestion")
        st.caption("Upload a WhatsApp `.txt` export or a `.csv` with a message column to run extraction.")
        uploaded = st.file_uploader(
            "Upload CSV or TXT",
            type=["csv", "txt"],
            help="WhatsApp chat export (TXT) or spreadsheet with message text and optional timestamps.",
        )
        if not uploaded:
            st.info("Upload a file to begin extraction.")
            return

        if st.button("Process File", type="primary"):
            messages = _messages_from_upload(uploaded)
            if not messages:
                st.warning("No non-empty messages found.")
                return

            progress = st.progress(0)
            status = st.empty()
            approved = 0
            pending = 0
            errors = 0

            for idx, item in enumerate(messages, start=1):
                msg = item.get("message", "")
                ts = item.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                result = extract_trade(msg, received_timestamp=ts)
                approved += int(result.get("approved_count", 0))
                pending += int(result.get("pending_count", 0))
                if result.get("status") in {"error"}:
                    errors += 1

                progress.progress(idx / len(messages))
                status.text(f"Processed {idx}/{len(messages)} messages")

            c1, c2, c3 = st.columns(3)
            c1.metric("Approved trades", approved)
            c2.metric("Pending validation", pending)
            c3.metric("Errors/skipped", errors)
            st.success("File processing complete.")


def render_live_dashboard() -> None:
    with st.container(border=True):
        st.header("Live Dashboard")
        st.caption("Approved trades in the database. Export or curate rows—you can remove bad imports with care.")
        trades = _to_dict_rows(fetch_market_trades())
        if not trades:
            st.session_state.pop("live_dash_delete_confirm_ids", None)
            st.info("No approved trades yet.")
            return

        df = pd.DataFrame(trades)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
        df["original_price"] = pd.to_numeric(df["original_price"], errors="coerce")
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

        total = len(df)
        m1, m2 = st.columns(2)
        m1.metric("Total approved trades", total)
        m2.metric("Unique cities", int(df["city"].astype(str).nunique()))

        display_cols = ["id", "timestamp", "city", "commodity", "quantity", "original_price", "price_per_kg"]
        st.dataframe(
            df[[c for c in display_cols if c in df.columns]].sort_values("timestamp", ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Delete trades")
        st.caption("Removes selected rows from approved trades in the database (cannot be undone).")
        label_to_id: dict[str, int] = {}
        for r in trades:
            rid = int(r["id"])
            ts = str(r.get("timestamp") or "")
            city = str(r.get("city") or "")
            comm = str(r.get("commodity") or "")
            label = f"#{rid} | {ts} | {city} | {comm}"
            label_to_id[label] = rid

        pending_ids = st.session_state.get("live_dash_delete_confirm_ids")
        if pending_ids:
            st.warning(f"Permanently delete **{len(pending_ids)}** trade(s) from the database?")
            dc1, dc2 = st.columns(2)
            if dc1.button("Yes, delete", key="live_dash_delete_yes"):
                delete_market_trades(pending_ids)
                st.session_state.pop("live_dash_delete_confirm_ids", None)
                st.success("Selected trades removed.")
                st.rerun()
            if dc2.button("Cancel", key="live_dash_delete_no"):
                st.session_state.pop("live_dash_delete_confirm_ids", None)
                st.rerun()
        else:
            picked = st.multiselect(
                "Select trade(s) to delete",
                options=list(label_to_id.keys()),
                key="live_dash_delete_pick",
            )
            if picked and st.button("Delete selected", key="live_dash_delete_request"):
                st.session_state["live_dash_delete_confirm_ids"] = [label_to_id[lb] for lb in picked]
                st.rerun()


def _render_pending_item(p: dict) -> None:
    pending_id = p["id"]
    with st.expander(f"Pending Trade #{pending_id} | Confidence: {p.get('confidence_score', 0)}", expanded=False):
        st.markdown("**Raw Message**")
        st.code(p.get("raw_message", ""), language=None)
        st.markdown(f"**AI Reasoning:** {p.get('ai_reasoning', '')}")

        city = st.text_input("City", value=p.get("city", ""), key=f"city_{pending_id}")
        commodity = st.text_input("Commodity", value=p.get("commodity", ""), key=f"commodity_{pending_id}")
        quantity = st.number_input("Quantity", min_value=0, value=int(p.get("quantity") or 0), step=1, key=f"qty_{pending_id}")
        original_price = st.number_input(
            "Original Price", min_value=0.0, value=float(p.get("original_price") or 0.0), step=1.0, key=f"op_{pending_id}"
        )
        price_per_kg = st.number_input(
            "Price Per Kg", min_value=0.0, value=float(p.get("price_per_kg") or 0.0), step=0.1, key=f"ppk_{pending_id}"
        )

        col_a, col_b, col_c, col_d = st.columns(4)
        if col_a.button("Approve Trade", key=f"approve_{pending_id}", type="secondary"):
            insert_market_trade(
                timestamp=p["timestamp"],
                city=city,
                commodity=commodity,
                quantity=int(quantity),
                original_price=float(original_price),
                price_per_kg=float(price_per_kg),
            )
            delete_pending_trade(pending_id)
            st.success(f"Trade #{pending_id} approved.")
            st.rerun()

        if col_b.button("Fix & Teach AI", key=f"teach_open_{pending_id}", type="primary"):
            st.session_state[f"teach_mode_{pending_id}"] = True

        if col_c.button("Reject Trade", key=f"reject_open_{pending_id}"):
            st.session_state[f"reject_mode_{pending_id}"] = True

        if col_d.button("Reject (no reason)", key=f"reject_quick_{pending_id}"):
            insert_rejected_trade(p.get("raw_message", ""), "")
            delete_pending_trade(pending_id)
            st.success(f"Trade #{pending_id} rejected.")
            st.rerun()

        if st.session_state.get(f"reject_mode_{pending_id}", False):
            st.markdown("**Reject Trade**")
            rejection_reason = st.text_area(
                "Why are you rejecting this trade? (optional)",
                key=f"reject_reason_{pending_id}",
                placeholder="Leave blank to reject without a reason, or describe why…",
                height=80,
            )
            r1, r2 = st.columns(2)
            if r1.button("Confirm Reject", key=f"reject_confirm_{pending_id}"):
                insert_rejected_trade(p.get("raw_message", ""), rejection_reason.strip())
                delete_pending_trade(pending_id)
                st.success(f"Trade #{pending_id} rejected.")
                st.rerun()
            if r2.button("Cancel", key=f"reject_cancel_{pending_id}"):
                st.session_state[f"reject_mode_{pending_id}"] = False
                st.rerun()

        if st.session_state.get(f"teach_mode_{pending_id}", False):
            st.markdown("**Teach AI Memory**")
            keyword = st.text_input("Keyword", key=f"kw_{pending_id}", placeholder="e.g. phutti")
            mistake = st.text_input("Mistake", key=f"mistake_{pending_id}", placeholder="e.g. thought it was wheat")
            correction = st.text_input("Correction", key=f"corr_{pending_id}", placeholder="e.g. it is cotton")

            if st.button("Save Correction & Approve", key=f"teach_save_{pending_id}"):
                if not (keyword.strip() and mistake.strip() and correction.strip()):
                    st.warning("Please fill Keyword, Mistake, and Correction before saving.")
                    return
                insert_market_trade(
                    timestamp=p["timestamp"],
                    city=city,
                    commodity=commodity,
                    quantity=int(quantity),
                    original_price=float(original_price),
                    price_per_kg=float(price_per_kg),
                )
                memory_id = insert_model_memory(keyword.strip(), mistake.strip(), correction.strip())
                delete_pending_trade(pending_id)
                st.success(f"Trade #{pending_id} fixed, approved, and memory saved (ID: {memory_id}).")
                st.rerun()


def render_hitl_queue() -> None:
    with st.container(border=True):
        st.header("Human Validation Queue")
        st.caption("Review AI extractions, approve or reject, teach the model, and maintain slang → standard mappings.")
        pending_rows = _to_dict_rows(fetch_pending_trades())
        n = len(pending_rows)

        if not pending_rows:
            st.session_state.pop("hitl_bulk_accept_confirm", None)
            st.session_state.pop("hitl_bulk_reject_confirm", None)
            st.info("No pending trades. Great job.")
        else:
            if st.session_state.get("hitl_bulk_accept_confirm"):
                st.warning(f"Approve all **{n}** pending trades using each row’s **stored** fields (AI extraction), not unsaved edits in expanders?")
                ca1, ca2 = st.columns(2)
                if ca1.button("Yes, accept all", key="hitl_bulk_accept_yes"):
                    cnt = approve_all_pending()
                    st.session_state["hitl_bulk_accept_confirm"] = False
                    st.success(f"Approved {cnt} trade(s).")
                    st.rerun()
                if ca2.button("Cancel", key="hitl_bulk_accept_no"):
                    st.session_state["hitl_bulk_accept_confirm"] = False
                    st.rerun()
            elif st.session_state.get("hitl_bulk_reject_confirm"):
                st.warning(f"Reject all **{n}** pending trades? Each will be logged in rejected trades.")
                bulk_rr = st.text_input(
                    "Optional reason (applied to every reject)",
                    key="hitl_bulk_reject_reason",
                    placeholder="Leave empty for no reason",
                )
                cr1, cr2 = st.columns(2)
                if cr1.button("Yes, reject all", key="hitl_bulk_reject_yes"):
                    cnt = reject_all_pending(bulk_rr or "")
                    st.session_state["hitl_bulk_reject_confirm"] = False
                    st.success(f"Rejected {cnt} trade(s).")
                    st.rerun()
                if cr2.button("Cancel", key="hitl_bulk_reject_no"):
                    st.session_state["hitl_bulk_reject_confirm"] = False
                    st.rerun()
            else:
                st.caption(
                    "Bulk **Accept all** / **Reject all** use values already saved on each pending row (from the model), "
                    "not text you typed in an expander without approving."
                )
                bc1, bc2 = st.columns(2)
                if bc1.button("Accept all pending", key="hitl_bulk_accept"):
                    st.session_state["hitl_bulk_accept_confirm"] = True
                    st.session_state["hitl_bulk_reject_confirm"] = False
                    st.rerun()
                if bc2.button("Reject all pending", key="hitl_bulk_reject"):
                    st.session_state["hitl_bulk_reject_confirm"] = True
                    st.session_state["hitl_bulk_accept_confirm"] = False
                    st.rerun()

            for p in pending_rows:
                _render_pending_item(p)

        st.markdown("---")
        st.subheader("Master Dictionary")
        slang = st.text_input("Slang word", key="slang_word_input")
        standard = st.text_input("Standard word", key="standard_word_input")
        if st.button("Add Slang Mapping"):
            if slang.strip() and standard.strip():
                insert_master_dictionary(slang, standard)
                st.success("Dictionary mapping saved.")
                st.rerun()
            else:
                st.warning("Both slang and standard word are required.")

        dictionary_rows = _to_dict_rows(fetch_master_dictionary())
        if dictionary_rows:
            st.dataframe(pd.DataFrame(dictionary_rows), use_container_width=True, hide_index=True)


def _city_to_province(city: str) -> str:
    """Map a city name to its province using PROVINCE_MAP (case-insensitive + partial)."""
    if not city or city == "Unknown":
        return "Other"
    city_clean = city.strip()
    if city_clean in PROVINCE_MAP:
        return PROVINCE_MAP[city_clean]
    city_lower = city_clean.lower()
    for key, val in PROVINCE_MAP.items():
        if key.lower() == city_lower:
            return val
    # Partial match: if any known city name appears inside the value (handles
    # combined entries like "Shahdad Pur & Nawab Shah").
    for key, val in PROVINCE_MAP.items():
        if key.lower() in city_lower or city_lower in key.lower():
            return val
    return "Other"


def _linear_extrapolation(dates, values, forecast_days: int = 7):
    """Simple linear trend extrapolation continuing the trajectory of existing data."""
    import numpy as np
    dates_dt = pd.to_datetime(dates)
    x = (dates_dt - dates_dt.min()).dt.days.values.astype(float)
    y = np.array(values, dtype=float)
    mask = np.isfinite(y)
    if mask.sum() < 2:
        return [], []
    coeffs = np.polyfit(x[mask], y[mask], deg=1)
    last_day = x.max()
    future_x = np.arange(last_day + 1, last_day + 1 + forecast_days)
    future_y = np.polyval(coeffs, future_x)
    future_dates = pd.date_range(dates_dt.max() + pd.Timedelta(days=1), periods=forecast_days)
    return future_dates, future_y


def render_market_analytics() -> None:
    with st.container(border=True):
        st.header("Market Analytics")
        st.caption(
            "Filter by date and commodity, explore province-level prices, and compare local cotton to ICE #2 futures (market data via Yahoo Finance)."
        )

        trades = _to_dict_rows(fetch_market_trades())
        if not trades:
            st.info("No approved trades yet. Approve some trades in the HITL queue first.")
            return

        df = pd.DataFrame(trades)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["price_per_kg"] = pd.to_numeric(df["price_per_kg"], errors="coerce")
        df["original_price"] = pd.to_numeric(df["original_price"], errors="coerce")
        df = df.dropna(subset=["timestamp", "price_per_kg"])
        if df.empty:
            st.info("No valid trade data to analyse.")
            return

        df["province"] = df["city"].astype(str).apply(_city_to_province)
        df["trade_date"] = df["timestamp"].dt.date

        # ── filters ──
        min_date = df["trade_date"].min()
        max_date = df["trade_date"].max()
        f1, f2, f3 = st.columns(3)
        start_date = f1.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, key="analytics_start")
        end_date = f2.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, key="analytics_end")
        all_commodities = sorted(df["commodity"].astype(str).unique().tolist())
        commodity_filter = f3.multiselect("Commodities", options=all_commodities, default=all_commodities, key="analytics_commodities")

        if start_date > end_date:
            st.warning("Start date cannot be after end date.")
            return

        filtered = df[
            (df["trade_date"] >= start_date)
            & (df["trade_date"] <= end_date)
            & (df["commodity"].astype(str).isin(commodity_filter))
        ].copy()
        if filtered.empty:
            st.info("No trades for selected filters.")
            return

        # ─────────────────────────────────────────────────────────────────────
        # Section 1 – Province Price Trend with Prophet Forecast
        # ─────────────────────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Price Trend by Province (with Forecast)")

        province_daily = (
            filtered.groupby(["trade_date", "province"], as_index=False)["original_price"]
            .mean()
            .rename(columns={"original_price": "avg_price"})
            .sort_values("trade_date")
        )

        provinces = sorted(province_daily["province"].unique().tolist())
        fig_prov = go.Figure()

        all_prices = province_daily["avg_price"].dropna()
        y_min = float(all_prices.min()) if not all_prices.empty else 0
        y_max = float(all_prices.max()) if not all_prices.empty else 1
        y_padding = max((y_max - y_min) * 0.15, 50)

        for prov in provinces:
            prov_df = province_daily[province_daily["province"] == prov].copy()
            fig_prov.add_trace(go.Scatter(
                x=prov_df["trade_date"],
                y=prov_df["avg_price"],
                mode="lines+markers",
                name=prov,
            ))

            if len(prov_df) >= 2:
                future_dates, future_y = _linear_extrapolation(
                    prov_df["trade_date"], prov_df["avg_price"], forecast_days=7,
                )
                if len(future_dates) > 0:
                    fig_prov.add_trace(go.Scatter(
                        x=future_dates,
                        y=future_y,
                        mode="lines",
                        line=dict(dash="dot", width=2),
                        name=f"{prov} (trend)",
                        showlegend=True,
                    ))

        fig_prov.update_layout(
            title="Daily Avg Price by Province (PKR/Maund) + 7-day Trend",
            xaxis_title="Date",
            yaxis_title="PKR / Maund",
            legend_title="Province",
            hovermode="x unified",
            height=550,
            xaxis=dict(
                rangeslider=dict(visible=True),
                type="date",
            ),
            yaxis=dict(
                range=[y_min - y_padding, y_max + y_padding],
                autorange=False,
            ),
        )
        _apply_chart_theme(fig_prov)
        st.plotly_chart(fig_prov, use_container_width=True)

        # Province deviation chart – highlights the spread between provinces
        if len(provinces) > 1 and not province_daily.empty:
            st.markdown("#### Province Price Deviation from Daily Mean")
            st.caption("Shows how each province deviates from the all-province average on each day, making small differences visible.")
            daily_mean = province_daily.groupby("trade_date", as_index=False)["avg_price"].mean().rename(columns={"avg_price": "overall_mean"})
            dev_df = province_daily.merge(daily_mean, on="trade_date")
            dev_df["deviation"] = dev_df["avg_price"] - dev_df["overall_mean"]

            fig_dev = go.Figure()
            for prov in provinces:
                prov_dev = dev_df[dev_df["province"] == prov]
                fig_dev.add_trace(go.Scatter(
                    x=prov_dev["trade_date"],
                    y=prov_dev["deviation"],
                    mode="lines+markers",
                    name=prov,
                ))
            fig_dev.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Mean")
            fig_dev.update_layout(
                title="Province Price Deviation from Daily Average (PKR/Maund)",
                xaxis_title="Date",
                yaxis_title="Deviation (PKR / Maund)",
                legend_title="Province",
                hovermode="x unified",
                height=400,
            )
            _apply_chart_theme(fig_dev)
            st.plotly_chart(fig_dev, use_container_width=True)

        # ─────────────────────────────────────────────────────────────────────
        # Section 2 – ICE Cotton vs Local Cotton  &  Spread
        # ─────────────────────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Local Cotton vs ICE Cotton #2 Futures")

        ice_df = fetch_ice_cotton_daily(days=365)
        fx_df = fetch_usd_pkr_rate(days=365)

        if ice_df is None or fx_df is None or ice_df.empty or fx_df.empty:
            st.warning(
                "Could not fetch ICE Cotton or USD/PKR data from Yahoo Finance. "
                "Check your internet connection and that `yfinance` is installed."
            )
        else:
            cotton_trades = filtered[filtered["commodity"].astype(str).str.lower() == "cotton"].copy()

            if cotton_trades.empty:
                st.info("No local cotton trades in the selected date range.")
            else:
                fx_df = fx_df.copy()
                fx_df["date"] = pd.to_datetime(fx_df["date"])
                fx_df = fx_df.sort_values("date")
                ice_df = ice_df.copy()
                ice_df["date"] = pd.to_datetime(ice_df["date"])

                cotton_daily = (
                    cotton_trades.groupby("trade_date", as_index=False)
                    .agg(avg_price_per_kg=("price_per_kg", "mean"))
                )
                cotton_daily["date"] = pd.to_datetime(cotton_daily["trade_date"])

                merged = pd.merge_asof(
                    cotton_daily.sort_values("date"),
                    fx_df[["date", "usd_pkr"]],
                    on="date",
                    direction="nearest",
                )
                merged["local_cents_per_lb"] = merged.apply(
                    lambda r: convert_pkr_per_kg_to_cents_per_lb(r["avg_price_per_kg"], r["usd_pkr"]),
                    axis=1,
                )

                combined = pd.merge(
                    merged[["date", "local_cents_per_lb"]],
                    ice_df[["date", "close_cents_per_lb"]],
                    on="date",
                    how="outer",
                ).sort_values("date")

                # ── KPI cards ──
                latest_ice = ice_df["close_cents_per_lb"].iloc[-1] if not ice_df.empty else 0
                latest_fx = fx_df["usd_pkr"].iloc[-1] if not fx_df.empty else 0
                latest_local = merged["local_cents_per_lb"].iloc[-1] if not merged.empty else 0
                spread_val = latest_local - latest_ice if latest_local and latest_ice else 0
                provinces_reporting = int(filtered["province"].nunique())

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("ICE Cotton Close", f"{latest_ice:,.2f} c/lb")
                k2.metric("USD/PKR Rate", f"{latest_fx:,.2f}")
                k3.metric("Local Cotton", f"{latest_local:,.2f} c/lb")
                k4.metric("Spread (Local - ICE)", f"{spread_val:+,.2f} c/lb")
                k5.metric("Provinces Reporting", provinces_reporting)

                # ── Dual line chart ──
                fig_cotton = go.Figure()
                fig_cotton.add_trace(go.Scatter(
                    x=combined["date"],
                    y=combined["local_cents_per_lb"],
                    mode="lines+markers",
                    name="Local Cotton (converted)",
                    connectgaps=False,
                ))
                fig_cotton.add_trace(go.Scatter(
                    x=combined["date"],
                    y=combined["close_cents_per_lb"],
                    mode="lines",
                    name="ICE Cotton #2 Futures",
                ))
                fig_cotton.update_layout(
                    title="Local Cotton Price vs ICE Cotton #2 (US cents/lb)",
                    xaxis_title="Date",
                    yaxis_title="US cents / lb",
                    hovermode="x unified",
                    height=450,
                )
                _apply_chart_theme(fig_cotton)
                st.plotly_chart(fig_cotton, use_container_width=True)

                # ── Spread bar chart ──
                spread_df = combined.dropna(subset=["local_cents_per_lb", "close_cents_per_lb"]).copy()
                if not spread_df.empty:
                    spread_df["spread"] = spread_df["local_cents_per_lb"] - spread_df["close_cents_per_lb"]
                    colors = ["green" if s >= 0 else "red" for s in spread_df["spread"]]

                    fig_spread = go.Figure()
                    fig_spread.add_trace(go.Bar(
                        x=spread_df["date"],
                        y=spread_df["spread"],
                        marker_color=colors,
                        name="Spread",
                    ))
                    fig_spread.update_layout(
                        title="Daily Spread: Local Cotton - ICE Cotton (cents/lb)",
                        xaxis_title="Date",
                        yaxis_title="Spread (cents/lb)",
                        height=350,
                    )
                    _apply_chart_theme(fig_spread)
                    st.plotly_chart(fig_spread, use_container_width=True)
                    st.caption(
                        "Green = local premium (local price above ICE). "
                        "Red = local discount (local price below ICE)."
                    )
                else:
                    st.info("Not enough overlapping dates to compute the spread chart.")


def main() -> None:
    _inject_theme_css()

    st.sidebar.markdown(
        '<p class="sidebar-brand">Pakistani Commodities Desk</p>'
        '<p class="sidebar-brand-sub">Gemini extraction · Human-in-the-loop · Price intelligence</p>',
        unsafe_allow_html=True,
    )
    _sidebar_stats()
    st.sidebar.markdown(
        '<p style="color:rgba(255,255,255,0.45);font-size:0.72rem;margin:0.5rem 0 0.35rem;text-transform:uppercase;letter-spacing:0.08em;">Jump to</p>',
        unsafe_allow_html=True,
    )
    nav_labels = [label for _, label in _NAV]
    picked = st.sidebar.radio("Section", nav_labels, label_visibility="collapsed")
    active_key = _NAV[[lbl for _, lbl in _NAV].index(picked)][0]

    st.markdown(
        '<span class="hero-badge">HITL · Gemini · Market intelligence</span>',
        unsafe_allow_html=True,
    )
    st.markdown('<h1 class="hero-title">Pakistani Commodities Trading AI</h1>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="hero-sub">{_NAV_BLURB.get(active_key, "")}</p>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    if active_key == "ingestion":
        render_data_ingestion()
    elif active_key == "dashboard":
        render_live_dashboard()
    elif active_key == "analytics":
        render_market_analytics()
    else:
        render_hitl_queue()


if __name__ == "__main__":
    main()
