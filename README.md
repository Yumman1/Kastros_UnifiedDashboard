# Pakistan Commodities Trading Dashboard

A comprehensive AI-powered trading intelligence platform for Pakistan's agricultural commodities market (Cotton, Wheat, Corn).

## 🌾 Features

- 📈 **Live Rates**: Real-time market price monitoring
- 📊 **Trends**: Historical price analysis with interactive charts
- 🤖 **AI Forecast**: 7-day price predictions using Prophet ML
- 💰 **Arbitrage Scanner**: Automated profit opportunity detection
- 📰 **Market Intelligence**: News sentiment analysis

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/agri-commodity-trading-application.git
cd agri-commodity-trading-application
```

2. Install dependencies:
```bash
pip install -r agri_dashboard/requirements.txt
```

3. Initialize database and add sample data:
```bash
python agri_dashboard/ingest_whatsapp.py
```

4. Run the dashboard:
```bash
python -m streamlit run agri_dashboard/app.py
```

The dashboard will open at `http://localhost:8501`

## 📁 Project Structure

```
agri_dashboard/
├── app.py                 # Main Streamlit dashboard
├── database.py           # Database operations
├── ingest_whatsapp.py    # Data collection script
├── forecast.py           # Prophet ML forecasting
├── analysis.py           # Arbitrage detection
├── news_engine.py        # Sentiment analysis
├── requirements.txt      # Python dependencies
└── README.md             # Setup instructions
```

## 📚 Documentation

- [Business Documentation](agri_dashboard/BUSINESS_DOCUMENTATION.md) - Comprehensive business overview
- [Executive Summary](agri_dashboard/EXECUTIVE_SUMMARY.md) - Quick reference guide
- [Setup Guide](agri_dashboard/README.md) - Detailed setup instructions

## 🛠️ Technology Stack

- **Frontend**: Streamlit
- **Database**: SQLite
- **ML Framework**: Prophet (Facebook)
- **Visualization**: Plotly
- **Language**: Python 3.8+

## 📝 License

This project is open source and available for use.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Contact

For questions or support, please open an issue on GitHub.

---

**Built with ❤️ for Pakistan's Commodities Trading Community**
