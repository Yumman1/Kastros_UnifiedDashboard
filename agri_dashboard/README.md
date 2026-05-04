# Pakistan Commodities Trading Dashboard

A Local-First Python dashboard for tracking Cotton, Wheat, and Corn prices in the Pakistan market. Ingests data from WhatsApp groups via Evolution API and extracts structured prices using a local LLM (Ollama).

## Features

- 📈 **Live Rates**: View market prices with group names (from WhatsApp)
- 📊 **Trends**: Interactive charts showing price trends over time
- 🤖 **AI Forecast**: Prophet-based ML forecasts for next 7 days
- 💰 **Arbitrage**: Cross-city profit opportunities
- 📰 **Market Intelligence**: News sentiment
- 📥 **WhatsApp Import**: Fetch from Evolution API or upload chat export
- 🤖 **LLM Extraction**: Ollama (llama3.2:1b) parses unstructured messages into commodity/price/city

**For full architecture and documentation, see [APP_DOCUMENTATION.md](APP_DOCUMENTATION.md).**

## Setup Instructions

### 1. Install Dependencies

Open your terminal (PowerShell on Windows) and run:

```powershell
pip install -r agri_dashboard/requirements.txt
```

### 2. Initialize Database and Add Sample Data

Run the data ingestion script to initialize the database:

```powershell
python agri_dashboard/ingest_whatsapp.py
```

Or manually seed the database from the dashboard (use the "Seed Sample Data" button in the sidebar).

### 3. Run the Dashboard

Start the Streamlit application:

```powershell
streamlit run agri_dashboard/streamlit_app.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

## Configuration

Edit `agri_dashboard/.env`:

- **Evolution API**: `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_CHAT_JID`
- **Ollama**: `OLLAMA_URL`, `OLLAMA_MODEL` (default: llama3.2:1b)

See [AUTOMATION_SETUP.md](AUTOMATION_SETUP.md) and [APP_DOCUMENTATION.md](APP_DOCUMENTATION.md) for details.

## Usage

1. **Live Rates Tab**: View today's prices with filtering options
2. **Trends Tab**: Analyze price trends over time with interactive charts
3. **AI Forecast Tab**: Get ML-powered price predictions for the next 7 days

Use the sidebar filters to narrow down by commodity (Cotton, Wheat, Corn) or city.

## Cotton-Only Offline LLM Test

Run a quota-safe Gemini test on a local WhatsApp export file (no Evolution API fetch):

```powershell
python agri_dashboard/cotton_llm_test.py --file "C:\Users\HP\Desktop\trading_AI_bot\WhatsApp Chat with Business Club Commodities.txt" --max-messages 8
```

Notes:
- `--max-messages` is limited to `5-10` to protect Gemini credits.
- Extraction is cotton-only and converts detected prices to `price_per_kg_pkr`.
- Outputs are written to `agri_dashboard/outputs/` as JSON and CSV.
- Add `--write-db` if you also want accepted rows inserted into `market_data.db`.
