# Automated WhatsApp → Live Rates Pipeline

WhatsApp messages flow through **Ollama (LLM)** for extraction, then into the database for the **Live Rates** page. Two ingestion paths: **real-time webhook** and **manual/scheduled fetch**.

---

## 0. Install Ollama and LLM Model (Required)

All message processing uses **Ollama** for commodity/price/city extraction.

1. Install [Ollama](https://ollama.com) and ensure it runs on port 11434.
2. Pull the model:
   ```powershell
   ollama pull llama3.2:1b
   ```
3. Optional in `agri_dashboard/.env`:
   ```env
   OLLAMA_URL=http://localhost:11434/api/chat
   OLLAMA_MODEL=llama3.2:1b
   ```

If Ollama is offline, no market data will be extracted (messages are skipped).

---

## 1. Run Evolution API and connect WhatsApp

The app uses **[Evolution API](https://github.com/EvolutionAPI/evolution-api)** (free, no subscription).

### Step 1: Run Evolution API (Docker)

Evolution API **v2** (current image) needs **PostgreSQL and Redis**. The easiest way is to use the included Compose file.

1. Install [Docker](https://docs.docker.com/engine/install/) and Docker Compose if you don’t have them.
2. **Option A – Recommended: run with Docker Compose** (starts API + PostgreSQL + Redis). From the **project root** (`trading_AI_bot`):
   ```powershell
   docker compose -f agri_dashboard/docker-compose.evolution.yaml up -d
   ```
   Or from `agri_dashboard`: `docker compose -f docker-compose.evolution.yaml up -d`
   Ensure `agri_dashboard/.env` has `EVOLUTION_API_KEY=your-secret-key` (same value is passed to the container). The compose file uses **v2** and the `/api` prefix (default in the app).
3. **Option B – Single container (not recommended):**  
   Running only `docker run ... atendai/evolution-api:latest` **fails** with "Database provider invalid" because v2 requires a database. Use Option A instead.
4. Check that it’s running: run `docker ps` and confirm `evolution_api`, `evolution_postgres`, and `evolution_redis` are **Up**. Open [http://localhost:8080](http://localhost:8080) in your browser.

### Step 2: Create an instance and connect WhatsApp

**atendai/evolution-api** (v2.2) uses **no `/api` prefix** (paths like `/instance/create`). The script and app use the prefix from `EVOLUTION_API_PREFIX` in `.env` (leave empty for this image).

**Easiest:** run the PowerShell script (reads from `agri_dashboard/.env`):

```powershell
.\agri_dashboard\evolution_connect.ps1
```

Then open the URL it prints (e.g. `http://localhost:8080/manager`) to scan the QR if the script didn’t show one.

**Or call the API manually** (atendai/evolution-api uses no `/api` prefix):

1. **Create instance** (one-time; body must include `integration: "EVOLUTION"`):

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8080/instance/create" -Method Post -Headers @{ "Content-Type" = "application/json"; "apikey" = "your-secret-key" } -Body '{"instanceName": "agri-dashboard", "qrcode": true, "integration": "EVOLUTION"}'
   ```

2. **Get QR code**:

   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8080/instance/connect/agri-dashboard" -Method Get -Headers @{ "apikey" = "your-secret-key" }
   ```

   Or open in browser: `http://localhost:8080/manager` (if available) and connect from the Evolution manager UI.

If your Evolution API uses the **`/api`** path prefix, set in `.env`: **`EVOLUTION_API_PREFIX=/api`**. For atendai/evolution-api (Docker Compose), leave it empty.

3. **Link WhatsApp on your phone**
   - Open WhatsApp → **Settings** → **Linked devices** → **Link a device**
   - Scan the QR code shown by the API. After that, this number is connected to Evolution API.

### Step 3: Configure the app

Edit `agri_dashboard/.env`:

```env
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=your-secret-key
EVOLUTION_INSTANCE=agri-dashboard
```

- **Optional:** If your Evolution API uses `/api` in paths, set `EVOLUTION_API_PREFIX=/api`. For the included Docker Compose (atendai/evolution-api), leave it empty.
- **Optional:** To fetch only from one group, set the group JID (get it from Evolution API “find chats” or manager):
  ```env
  EVOLUTION_CHAT_JID=120363123456789012@g.us
  ```
  Leave `EVOLUTION_CHAT_JID` empty to fetch from all chats.

---

## 2. Real-time ingestion: Webhook receiver

For **instant** processing of incoming WhatsApp messages:

1. Start the receiver:
   ```powershell
   cd C:\Users\HP\Desktop\trading_AI_bot
   python -m agri_dashboard.receiver
   ```
   Listens on `http://0.0.0.0:5050` (port 5050 to avoid conflicts).

2. Expose it (if Evolution runs on another machine): use ngrok or similar:
   ```powershell
   ngrok http 5050
   ```

3. Configure Evolution API webhook (Evolution v2 uses nested `webhook` object). For Evolution in Docker, use `host.docker.internal` to reach your PC:
   ```powershell
   $body = @{ webhook = @{
     enabled = $true
     url = "http://host.docker.internal:5050/webhook"
     webhook_by_events = $false
     events = @("MESSAGES_UPSERT")
   }} | ConvertTo-Json -Depth 3
   Invoke-RestMethod -Uri "http://localhost:8080/webhook/set/Instance1" -Method Post -Headers @{ "Content-Type" = "application/json"; "apikey" = "your-secret-key" } -Body $body
   ```

4. Incoming WhatsApp messages → Evolution → POST to `/webhook` → Ollama extraction → database → **Live Rates**.

---

## 3. Run the daily fetch (Option A: Scheduler)

1. In `agri_dashboard/.env` set the time (24h format):
   ```env
   INGEST_DAILY_AT=08:00
   ```

2. Install dependency:
   ```powershell
   pip install schedule
   ```

3. Start the scheduler:
   ```powershell
   cd C:\Users\HP\Desktop\trading_AI_bot
   python -m agri_dashboard.scheduler
   ```
   It will run the WhatsApp fetch at that time every day. Leave the terminal open; stop with `Ctrl+C`.

---

## 4. Run the daily fetch (Option B: Task Scheduler)

1. Open **Task Scheduler** → Create Basic Task → **Daily** at your desired time.
2. **Action:** Start a program  
   - **Program:** `python`  
   - **Arguments:** `-m agri_dashboard.run_daily_ingest`  
   - **Start in:** `C:\Users\HP\Desktop\trading_AI_bot`

---

## 5. Data flow: WhatsApp → LLM → Live Rates

All messages (webhook or fetch) are sent to **Ollama (llama3.2:1b)** to extract commodity, price, city. The LLM understands Urdu/romanized variants. Extracted records go to `market_data` and appear on **Live Rates**.

---

## 6. Dashboard “Fetch from API”

In the dashboard → **Live Rates** → **Import from WhatsApp** → **Fetch from API**:
- Uses Evolution API config (`.env`). Ensure Evolution API and **Ollama** are running.

---

## 7. Optional: UltraMsg

If you prefer a hosted API, you can still set UltraMsg in `.env`. The app will use **Evolution first** if `EVOLUTION_API_KEY` is set; otherwise it uses UltraMsg when its credentials are set.

---

## 8. Troubleshooting

| Issue | What to do |
|-------|------------|
| “Last import” never updates | Check Evolution API is running (`http://localhost:8080`) and `.env` has correct `EVOLUTION_API_KEY` and `EVOLUTION_INSTANCE`. |
| Evolution returns 401 | Use the same value for `AUTHENTICATION_API_KEY` in Docker and `EVOLUTION_API_KEY` in `.env`. |
| No messages from a group | Set `EVOLUTION_CHAT_JID` to the group JID (e.g. from Evolution API “find chats” or manager). |
| Scheduler does nothing at 8 AM | Ensure `INGEST_DAILY_AT=08:00` is in `.env` and the scheduler script is running. |
| No records extracted / 0 imported | Ensure **Ollama** is running (`ollama serve`) and `llama3.2:1b` is pulled. |
| Webhook not receiving | Point Evolution webhook URL to `http://host.docker.internal:5050/webhook` (Evolution in Docker). Keep the receiver running. |

---

**Summary:** Install Ollama + llama3.2:1b → Run Evolution API → connect WhatsApp → (optional) run webhook receiver for real-time → or use **Fetch from API** / scheduler. All paths use the LLM to normalize data for Live Rates.
