# Evolution API - Create instance and get QR (PowerShell)
# Run from project folder: .\agri_dashboard\evolution_connect.ps1
# Evolution API v2 uses /api prefix (atendai/evolution-api). If you get 404, try removing $apiPrefix.

# Load .env from agri_dashboard if present
$envPath = Join-Path $PSScriptRoot ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), ($matches[2].Trim() -replace '^["'']|["'']$'), 'Process') }
    }
}
$base = if ($env:EVOLUTION_API_URL) { $env:EVOLUTION_API_URL.TrimEnd('/') } else { "http://localhost:8080" }
$apikey = if ($env:EVOLUTION_API_KEY) { $env:EVOLUTION_API_KEY } else { "your-secret-key" }
$instance = if ($env:EVOLUTION_INSTANCE) { $env:EVOLUTION_INSTANCE } else { "agri-dashboard" }
# Some deployments use /api prefix; atendai/evolution-api (v2.2) uses no prefix. Set EVOLUTION_API_PREFIX=/api in .env if needed.
$apiPrefix = if ($env:EVOLUTION_API_PREFIX -ne $null) { $env:EVOLUTION_API_PREFIX.TrimEnd('/') } else { "" }
if ($apiPrefix -and -not $apiPrefix.StartsWith("/")) { $apiPrefix = "/" + $apiPrefix }

# 0) Check if Evolution API is reachable
Write-Host "Checking Evolution API at $base..." -ForegroundColor Cyan
$reachable = $false
try {
    $null = Invoke-WebRequest -Uri $base -Method Get -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $reachable = $true
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 404) { $reachable = $true }  # server answered with 404 = it's there
}
if (-not $reachable) {
    Write-Host "Evolution API is NOT reachable at $base" -ForegroundColor Red
    Write-Host "  - Is Docker running? Check with: docker ps" -ForegroundColor Yellow
    Write-Host "  - Start Evolution API with:" -ForegroundColor Yellow
    Write-Host "    docker run -d --name evolution_api -p 8080:8080 -e AUTHENTICATION_API_KEY=$apikey atendai/evolution-api:latest" -ForegroundColor White
    Write-Host "  - Then run this script again." -ForegroundColor Yellow
    exit 1
}
Write-Host "Evolution API is reachable." -ForegroundColor Green

# 1) Create instance
Write-Host "Creating instance '$instance'..." -ForegroundColor Cyan
$body = "{`"instanceName`": `"$instance`", `"qrcode`": true, `"integration`": `"EVOLUTION`"}"
try {
    $r = Invoke-RestMethod -Uri "$base$apiPrefix/instance/create" -Method Post -Headers @{
        "Content-Type" = "application/json"
        "apikey"       = $apikey
    } -Body $body
    Write-Host "Instance create response: $r" -ForegroundColor Green
} catch {
    Write-Host "Create response (may be OK if already exists): $($_.Exception.Message)" -ForegroundColor Yellow
}

# 2) Get connection QR
Write-Host "`nGetting QR code to connect WhatsApp..." -ForegroundColor Cyan
try {
    $qr = Invoke-RestMethod -Uri "$base$apiPrefix/instance/connect/$instance" -Method Get -Headers @{ "apikey" = $apikey }
    $base64 = $qr.base64
    if (-not $base64) { $base64 = $qr.base64Image }
    if (-not $base64) { $base64 = $qr.qrcode }
    if ($base64) {
        # Remove data URL prefix if present
        if ($base64 -match "^data:image/[^;]+;base64,(.+)$") { $base64 = $matches[1] }
        $qrPath = Join-Path $PSScriptRoot "evolution_qr.png"
        [System.IO.File]::WriteAllBytes($qrPath, [System.Convert]::FromBase64String($base64))
        Write-Host "QR code saved to: $qrPath" -ForegroundColor Green
        Write-Host "Opening QR image - scan it with WhatsApp (Linked devices)..." -ForegroundColor Cyan
        Start-Process $qrPath
    } else {
        $state = $qr.instance.state
        if ($state -eq "open") {
            Write-Host "Instance is already connected (state: open). No QR needed - WhatsApp is linked." -ForegroundColor Green
            Write-Host "To link a different phone: open $base/manager , find this instance, and use Logout / Disconnect then Connect again." -ForegroundColor Yellow
        } else {
            Write-Host "No QR in response. Open Manager and connect from there:" -ForegroundColor Yellow
            Write-Host "  $base/manager" -ForegroundColor White
            Write-Host "Find instance '$instance' and click Connect / Show QR." -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "Connect response: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "Try opening the Manager to get the QR: $base/manager" -ForegroundColor Yellow
}

Write-Host "`nOn your phone: WhatsApp -> Settings -> Linked devices -> Link a device -> Scan QR." -ForegroundColor Cyan
