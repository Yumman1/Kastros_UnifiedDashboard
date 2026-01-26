# Pakistan Commodities Trading Dashboard

A Local-First Python dashboard for tracking Cotton, Wheat, and Corn prices in the Pakistan market.

## Features

- 📈 **Live Rates**: View today's market prices in real-time
- 📊 **Trends**: Interactive charts showing price trends over time
- 🤖 **AI Forecast**: Prophet-based ML forecasts for next 7 days
- 🔍 **Filters**: Filter by commodity and city
- 💾 **Local Storage**: SQLite database for offline-first operation

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
streamlit run agri_dashboard/app.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

## Configuration

Edit `agri_dashboard/.env` to add your UltraMsg API credentials when ready:

```
ULTRAMSG_API_URL=https://api.ultramsg.com
ULTRAMSG_API_KEY=your_api_key_here
ULTRAMSG_INSTANCE_ID=your_instance_id_here
```

## Project Structure

```
agri_dashboard/
├── app.py              # Main Streamlit dashboard
├── database.py         # Database operations
├── ingest_whatsapp.py  # Data collection script
├── forecast.py         # Prophet forecasting module
├── requirements.txt    # Python dependencies
├── .env               # Environment variables
└── market_data.db     # SQLite database (created automatically)
```

## Usage

1. **Live Rates Tab**: View today's prices with filtering options
2. **Trends Tab**: Analyze price trends over time with interactive charts
3. **AI Forecast Tab**: Get ML-powered price predictions for the next 7 days

Use the sidebar filters to narrow down by commodity (Cotton, Wheat, Corn) or city.
