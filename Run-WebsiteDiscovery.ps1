param(
  [string]$SourceUrl = $env:WEB_DISCOVERY_SOURCE_URL,
  [string]$FeedPath = $env:WEB_DISCOVERY_FEED_PATH,
  [int]$MaxPages = 5,
  [bool]$OpenApp = $true
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

Get-Content -LiteralPath ".env" | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
  }
}

if ([string]::IsNullOrWhiteSpace($SourceUrl)) {
  $SourceUrl = "https://www.compassultra.com/"
}

if ([string]::IsNullOrWhiteSpace($FeedPath)) {
  $FeedPath = "C:\Users\enter\Compass-Ultra\app\public\crawler-feed.json"
}

$DiscoverArgs = @("scripts\discover_websites.py", "--source-url", $SourceUrl)
if (Test-Path $FeedPath) {
  $DiscoverArgs += @("--feed-file", $FeedPath)
}

.\.venv\Scripts\python.exe @DiscoverArgs
.\.venv\Scripts\python.exe scripts\crawl_websites_to_snowflake.py --urls-file targets\discovered_websites.txt --max-pages $MaxPages
$env:DBT_PROFILES_DIR = $ProjectRoot
.\.venv\Scripts\dbt.exe build --select stg_web_pages fct_website_signals mart_prospect_accounts mart_website_query_index

if ($OpenApp) {
  $AppUrl = "http://localhost:8501"
  $AppIsRunning = $false
  try {
    $TcpClient = [System.Net.Sockets.TcpClient]::new()
    $Connect = $TcpClient.BeginConnect("127.0.0.1", 8501, $null, $null)
    $AppIsRunning = $Connect.AsyncWaitHandle.WaitOne(500, $false)
    if ($AppIsRunning) {
      $TcpClient.EndConnect($Connect)
    }
    $TcpClient.Close()
  } catch {
    $AppIsRunning = $false
  }

  if ($AppIsRunning) {
    Start-Process $AppUrl
  } else {
    .\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
  }
}
