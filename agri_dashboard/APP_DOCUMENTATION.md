# Pakistan Commodities Trading Dashboard – Full Application Documentation

This document describes the entire application, its architecture, components, and how everything fits together.

---

## 1. Overview

The **Pakistan Commodities Trading Dashboard** is a decoupled web app that:

1. **Ingests** commodity price data from WhatsApp groups (via Evolution API)
2. **Extracts** structured data (commodity, price, city) using **Google Gemini free API** (cloud LLM)
3. **Stores** the data in SQLite
4. **Serves** data via FastAPI backend (`/webhook`, `/ingest`, `/rates`, `/forecast`, etc.)
5. **Displays** live rates, trends, forecasts, arbitrage, and news in a Streamlit dashboard

**Key commodities:** Cotton, Wheat, Corn, Rice, Sugar, Oil/Ghee (including Urdu/romanized variants: gandum, makai, kapas, meezan)  
**Geographic scope:** Pakistan cities (Karachi, Lahore, Faisalabad, Multan, Hyderabad, DG Khan, etc.)

---

## 2. Architecture (Decoupled)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           WHATSAPP GROUPS                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
         ┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
         │   Webhook    │   │ POST /ingest    │   │ File Upload   │
         │  POST /webhook│   │ (dashboard or   │   │ POST /ingest  │
         │  Real-time   │   │  scheduler)     │   │ /export       │
         └──────┬───────┘   └────────┬────────┘   └───────┬───────┘
                │                    │                    │
                └────────────────────┼────────────────────┘
                                     ▼
                          ┌──────────────────┐
                          │  Evolution API   │
                          │  (Docker) 8080   │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │  FastAPI Backend │
                          │  api.py :8000    │
                          │  /webhook        │
                          │  /ingest         │
                          │  /rates          │
                          │  /forecast       │
                          └────────┬─────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             ┌─────────────┐ ┌──────────────┐ ┌─────────────┐
             │  extractor  │ │  market_data │ │  forecast   │
             │  (Gemini)   │ │  (SQLite)    │ │  (Prophet)  │
             │  FREE API   │ └──────────────┘ └─────────────┘
             └─────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │  Streamlit App   │
                          │  app.py :8501    │
                          │  (or React later)│
                          └──────────────────┘
```

---

## 3. Components

### 3.1 FastAPI Backend (`api.py`)

**Purpose:** Decoupled API service for all backend logic.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/webhook` | Evolution API webhook – receive WhatsApp messages, extract via Gemini, store |
| POST | `/ingest` | Fetch messages from Evolution, extract, store |
| POST | `/ingest/export` | Ingest from WhatsApp chat export text |
| GET | `/rates` | Recent market rates (optional `?commodity=&city=&days=`) |
| GET | `/rates/last-ingest` | Last ingest metadata |
| GET | `/historic` | Historic data for trends |
| GET | `/forecast` | Prophet-based price forecast |
| GET | `/arbitrage` | Cross-city arbitrage opportunities |
| GET | `/news` | Market news and sentiment |
| POST | `/seed` | Seed sample data |

**Run backend:**
```powershell
uvicorn agri_dashboard.api:app --host 0.0.0.0 --port 8000
```

### 3.2 Streamlit Dashboard (`app.py`)

**Modes:**
- **Standalone:** No `API_BASE_URL` – uses local database and direct imports
- **Decoupled:** `API_BASE_URL=http://localhost:8000` – fetches all data from FastAPI backend

**Tabs:** Live Rates, Trends, AI Forecast, Arbitrage, Market Intelligence

**Run frontend:**
```powershell
# Standalone
streamlit run agri_dashboard/app.py --server.port 8501

# Decoupled (set API_BASE_URL first)
$env:API_BASE_URL = "http://localhost:8000"
streamlit run agri_dashboard/app.py --server.port 8501
```

### 3.3 Extraction (`extractor.py` + `dictionaries.py`)

**Purpose:** Extract commodity, price, city from unstructured WhatsApp text using **Gemini (free API)**.

- **`extractor.py`** – Uses `google-genai` to call Gemini 2.0 Flash. Sends each message line to Gemini, gets `{raw_commodity, price, city}`. Uses **thefuzz** to map raw words to `COMMODITY_GROUPS` (Meezan→OIL_GHEE, gandum→WHEAT, etc.).
- **`dictionaries.py`** – `COMMODITY_GROUPS`, `CITY_MAP` for Pakistani brands and cities.

**Config:** `GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env`. Get free key at [Google AI Studio](https://aistudio.google.com/).

### 3.4 Evolution API Integration

**Modules:** `evolution_api.py`, `list_chats.py`, `evolution_connect.ps1`, etc.

**Webhook:** Point Evolution to `http://localhost:8000/webhook` (FastAPI) or `http://host.docker.internal:8000/webhook` when Evolution runs in Docker.

### 3.5 Database (`database.py`)

**Storage:** SQLite `market_data.db`  
**Schema:** `market_data` – id, timestamp, commodity, source, price, city, sentiment_score, raw_message

---

## 4. Configuration (`.env`)

| Variable              | Description                          | Example |
|-----------------------|--------------------------------------|---------|
| GEMINI_API_KEY        | **Required** for extraction. Free at Google AI Studio | `AIza...` |
| GOOGLE_API_KEY        | Alternative to GEMINI_API_KEY        | `AIza...` |
| GEMINI_MODEL          | Gemini model name                    | `gemini-2.0-flash` |
| GEMINI_RETRY_ON_429   | Retry after quota (429)              | `true` |
| API_BASE_URL          | Backend URL for decoupled mode       | `http://localhost:8000` |
| EVOLUTION_API_URL     | Evolution API base URL               | `http://localhost:8080` |
| EVOLUTION_API_KEY     | API key for Evolution                | `your-secret-key` |
| EVOLUTION_INSTANCE    | Instance name                        | `agri-dashboard` |
| EVOLUTION_CHAT_JID    | Group JIDs (comma-separated)         | `120363044934335729@g.us,...` |
| INGEST_DAILY_AT       | Scheduled fetch time (24h)           | `08:00` |
| INGEST_MAX_PER_CHAT   | Max messages per chat (testing: 1)   | `1` |
| INGEST_MAX_TOTAL      | Max messages total (testing: 3)      | `3` |
| GEMINI_RPM_LIMIT      | Max Gemini API calls/min (free: 15)  | `15` |

---

## 5. How to Run

### Prerequisites
- Python 3.10+
- `pip install -r agri_dashboard/requirements.txt`
- **GEMINI_API_KEY** (free at https://aistudio.google.com/)
- Evolution API (Docker) if using WhatsApp fetch

### Decoupled (recommended for production)

**Terminal 1 – Backend:**
```powershell
cd c:\Users\HP\Desktop\trading_AI_bot
uvicorn agri_dashboard.api:app --host 0.0.0.0 --port 8000
```

**Terminal 2 – Frontend:**
```powershell
$env:API_BASE_URL = "http://localhost:8000"
$env:GEMINI_API_KEY = "your-gemini-api-key"
streamlit run agri_dashboard/app.py --server.port 8501
```

**Evolution webhook:** Point to `http://localhost:8000/webhook` (or `http://host.docker.internal:8000/webhook` from Docker).

### Standalone (all-in-one)
```powershell
streamlit run agri_dashboard/app.py --server.port 8501
```
Database and extraction run in the same process. No API_BASE_URL needed.

---

## 6. Key Design Decisions

| Decision | Reason |
|----------|--------|
| **Gemini (free) instead of Ollama** | No local GPU; free cloud API; faster extraction |
| **Decoupled FastAPI + Streamlit** | Backend can scale independently; easy to replace Streamlit with React later |
| **Hybrid Gemini + thefuzz** | Gemini extracts raw entities; thefuzz maps brands/typos to master categories |
| **dictionaries.py** | Single source of truth for Pakistani brands; avoids LLM hallucination |
| **Pre-filter before extraction** | Skip messages with no commodity/price hints to save API calls |

---

## 7. File Structure

```
agri_dashboard/
├── api.py                 # FastAPI backend (webhook, ingest, rates, forecast, etc.)
├── api_client.py          # Client for frontend when using API mode
├── app.py                 # Streamlit dashboard
├── database.py            # SQLite operations
├── dictionaries.py        # Knowledge base (commodities, cities)
├── evolution_api.py       # Evolution API client
├── extractor.py           # Gemini + thefuzz extraction
├── ingest_whatsapp.py     # Message fetch + extraction orchestration
├── receiver.py            # Legacy Flask webhook (use api.py /webhook instead)
├── forecast.py            # Prophet forecasts
├── analysis.py            # Arbitrage
├── news_engine.py         # News + sentiment
├── whatsapp_parser.py     # Chat export parser
├── scheduler.py           # Daily ingest
├── run_daily_ingest.py    # One-off ingest
├── .env
├── requirements.txt
└── APP_DOCUMENTATION.md   # This file
```

---

## 8. Troubleshooting

| Issue | Check |
|-------|--------|
| 0 records extracted | GEMINI_API_KEY set in .env; valid key from Google AI Studio |
| Backend unreachable | Backend running on 8000; CORS allowed |
| No messages from Evolution | Evolution running, WhatsApp connected, EVOLUTION_CHAT_JID correct |
| Import/API errors | `pip install -r agri_dashboard/requirements.txt`; ensure google-genai installed |
