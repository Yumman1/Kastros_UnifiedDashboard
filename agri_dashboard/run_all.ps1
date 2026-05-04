# Run the full trading dashboard stack (FastAPI backend + Streamlit frontend)
# Usage: .\agri_dashboard\run_all.ps1
# Prerequisites: Evolution API (Docker), GEMINI_API_KEY in .env

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $projectRoot) { $projectRoot = (Get-Location).Path }
Set-Location $projectRoot

# Load .env from agri_dashboard
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $val = ($matches[2].Trim() -replace '^["'']|["'']$')
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

$base = if ($env:EVOLUTION_API_URL) { $env:EVOLUTION_API_URL.TrimEnd('/') } else { "http://localhost:8080" }
$apikey = if ($env:EVOLUTION_API_KEY) { $env:EVOLUTION_API_KEY } else { "your-secret-key" }
$instance = if ($env:EVOLUTION_INSTANCE) { $env:EVOLUTION_INSTANCE } else { "agri-dashboard" }

Write-Host "=== Trading Dashboard (FastAPI + Gemini) ===" -ForegroundColor Cyan
Write-Host "Project: $projectRoot"
Write-Host "Evolution: $base | Instance: $instance"
Write-Host ""

# Pick Python explicitly to avoid accidental Anaconda shell/process behavior.
# Priority: local .venv -> py launcher -> python on PATH.
$pythonExe = $null
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
} else {
    throw "No Python executable found. Install Python or create .venv."
}
Write-Host "Using Python: $pythonExe" -ForegroundColor Green

# 1) Start FastAPI backend (webhook + ingest + rates) on port 8000
Write-Host "Starting FastAPI backend on port 8000..." -ForegroundColor Yellow
if ($pythonExe -eq "py") {
    $backendArgs = @("-3", "-m", "uvicorn", "agri_dashboard.api:app", "--host", "0.0.0.0", "--port", "8000")
} else {
    $backendArgs = @("-m", "uvicorn", "agri_dashboard.api:app", "--host", "0.0.0.0", "--port", "8000")
}
$backendProc = Start-Process -FilePath $pythonExe -ArgumentList $backendArgs -WorkingDirectory $projectRoot -PassThru -NoNewWindow
Write-Host "Waiting for backend to be ready..." -ForegroundColor Yellow
$maxAttempts = 10
$attempt = 0
$ready = $false
while ($attempt -lt $maxAttempts) {
    Start-Sleep -Seconds 2
    $attempt++
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if ($ready) {
    Write-Host "Backend ready." -ForegroundColor Green
} else {
    Write-Host "Backend may still be starting. If you see 'API unreachable', wait a few seconds and refresh." -ForegroundColor Yellow
}

# 2) Configure Evolution webhook (Evolution in Docker needs host.docker.internal to reach host)
$webhookUrl = "http://host.docker.internal:8000/webhook"
Write-Host "Configuring Evolution webhook: $webhookUrl" -ForegroundColor Yellow
try {
    $webhookObj = @{
        enabled = $true
        url = $webhookUrl
        webhook_by_events = $false
        events = @("MESSAGES_UPSERT")
    }
    $body = @{ webhook = $webhookObj } | ConvertTo-Json -Depth 3
    $null = Invoke-RestMethod -Uri "$base/webhook/set/$instance" -Method Post `
        -Headers @{ "Content-Type" = "application/json"; "apikey" = $apikey } -Body $body
    Write-Host "Webhook configured." -ForegroundColor Green
} catch {
    Write-Host "Webhook config failed (Evolution may not be running): $($_.Exception.Message)" -ForegroundColor Yellow
}

# 3) Set API_BASE_URL for decoupled Streamlit
$env:API_BASE_URL = "http://localhost:8000"

Write-Host ""
Write-Host "Starting Streamlit dashboard (decoupled mode)..." -ForegroundColor Yellow
Write-Host "Open http://localhost:8501 in your browser" -ForegroundColor Cyan
Write-Host ""

# 4) Run Streamlit (foreground)
try {
    if ($pythonExe -eq "py") {
        & py -3 -m streamlit run agri_dashboard/app.py --server.port 8501
    } else {
        & $pythonExe -m streamlit run agri_dashboard/app.py --server.port 8501
    }
} finally {
    if ($backendProc -and -not $backendProc.HasExited) {
        Write-Host "Stopping FastAPI backend (PID $($backendProc.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
    }
}
