param(
    [int]$api_port = 8000
)

Write-Host "Activating virtual environment and installing requirements..."

# Create venv if missing
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Activate venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install all requirements
pip install -r cloud/api/requirements.txt
pip install -r edge/requirements.txt
pip install -r edge/wake/requirements.txt

Write-Host "Starting API server..."

# Start FastAPI server
Start-Process -NoNewWindow -FilePath python -ArgumentList "-m", "uvicorn", "cloud.api.main:app", "--host", "0.0.0.0", "--port", "$api_port", "--reload"

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "=================================================================="
Write-Host " Cypher API is starting on http://127.0.0.1:$api_port"
Write-Host ""
Write-Host " To register your edge-device, run:"
Write-Host ""
Write-Host "   curl -X POST http://localhost:$api_port/v1/device/register "
Write-Host "        -H 'Content-Type: application/json' "
Write-Host "        -d '{\"device_id\":\"edge-device-001\"}'"
Write-Host ""
Write-Host " After registering, set CY_DEVICE_TOKEN in your environment or"
Write-Host " in edge/client_app/.env"
Write-Host "=================================================================="
