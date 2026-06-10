$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvPath = Join-Path $ProjectRoot ".env"

if (!(Test-Path $EnvPath)) {
  Copy-Item (Join-Path $ProjectRoot ".env.example") $EnvPath
}

Write-Host ""
Write-Host "Compass Ultra Web Intel - Snowflake Password Setup"
Write-Host "This writes the password only to your local .env file. It does not print it."
Write-Host ""

$SecurePassword = Read-Host "Enter Snowflake password for DACAMERAGIRL" -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
try {
  $PlainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
}

$updates = [ordered]@{
  "SNOWFLAKE_ACCOUNT" = "CLTFCIZ-ED38268"
  "SNOWFLAKE_USER" = "DACAMERAGIRL"
  "SNOWFLAKE_AUTHENTICATOR" = ""
  "SNOWFLAKE_PASSWORD" = $PlainPassword
  "SNOWFLAKE_ROLE" = "ACCOUNTADMIN"
  "SNOWFLAKE_WAREHOUSE" = "COMPUTE_WH"
  "SNOWFLAKE_DATABASE" = "DATA_OPS"
  "SNOWFLAKE_WEB_SCHEMA" = "RAW_WEBSITE_INTEL"
  "SNOWFLAKE_STAGING_SCHEMA" = "STAGING"
  "SNOWFLAKE_ANALYTICS_SCHEMA" = "ANALYTICS"
  "DBT_TARGET" = "prod_password"
}

$lines = Get-Content -LiteralPath $EnvPath
$seen = @{}
$newLines = foreach ($line in $lines) {
  if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
    $key = $matches[1]
    if ($updates.Contains($key)) {
      $seen[$key] = $true
      "$key=$($updates[$key])"
    } else {
      $line
    }
  } else {
    $line
  }
}

foreach ($key in $updates.Keys) {
  if (!$seen.ContainsKey($key)) {
    $newLines += "$key=$($updates[$key])"
  }
}

Set-Content -LiteralPath $EnvPath -Value $newLines
Write-Host ""
Write-Host "Snowflake password saved locally. Tell Codex: done"

