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

$FeedPath = "C:\Users\enter\Compass-Ultra\app\public\crawler-feed.json"
$DiscoverArgs = @("scripts\discover_websites.py", "--source-url", "https://www.compassultra.com/")
if (Test-Path $FeedPath) {
  $DiscoverArgs += @("--feed-file", $FeedPath)
}

.\.venv\Scripts\python.exe @DiscoverArgs
.\.venv\Scripts\python.exe scripts\crawl_websites_to_snowflake.py --urls-file targets\discovered_websites.txt --max-pages 5
$env:DBT_PROFILES_DIR = $ProjectRoot
.\.venv\Scripts\dbt.exe build --select stg_web_pages fct_website_signals mart_prospect_accounts mart_website_query_index

