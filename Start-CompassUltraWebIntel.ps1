$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Fill in Snowflake values before running the pipeline."
}

if (!(Test-Path ".venv\Scripts\python.exe")) {
  py -3.11 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DBT_PROFILES_DIR = $ProjectRoot
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py

