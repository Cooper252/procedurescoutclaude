# Download, live from this computer, the price files listed in the cms-hpt.txt
# of the sites in data/reference/home_runner_price_sites.csv (sites whose
# servers refuse GitHub). Runs on Cooper's computer as a GitHub self-hosted
# runner job (Windows PowerShell 5.1), right after fetch_hpt_home.ps1.
# Reads the cms-hpt.txt files that script just fetched; writes each price file
# exactly as received plus prices.json describing every attempt. Nothing else
# on the computer is read or changed; output goes to the folder given.
param(
    [string]$SitesCsv = "data/reference/home_runner_price_sites.csv",
    [string]$HptDir = "hpt-home",
    [string]$OutDir = "prices-home",
    [long]$MaxBytes = 524288000   # 500 MB per file
)

$ErrorActionPreference = "Stop"
# TLS 1.2, plus TLS 1.3 where this Windows supports it (some sites accept only 1.3)
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]12288
} catch {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$fetches = @()
$index = Join-Path $HptDir "fetches.json"
if (Test-Path $index) {
    $raw = Get-Content -Raw -Encoding UTF8 $index | ConvertFrom-Json
    foreach ($item in $raw) { $fetches += $item }   # also unwraps PowerShell 5.1's single array object
}

$sites = Import-Csv $SitesCsv | ForEach-Object { $_.site.Trim().TrimEnd("/").ToLower() } | Sort-Object -Unique
$urls = @()
foreach ($site in $sites) {
    $f = $fetches | Where-Object { $_.site -eq $site -and $_.file } | Select-Object -First 1
    if (-not $f) { Write-Output "No cms-hpt.txt from this computer for $site"; continue }
    foreach ($line in Get-Content (Join-Path $HptDir $f.file)) {
        if ($line -match '^\s*mrf-url\s*:\s*(\S+)\s*$') { $urls += $Matches[1] }
    }
}
$urls = $urls | Where-Object { $_ -match '^https?://' } | Sort-Object -Unique

$results = @()
$n = 0
foreach ($url in $urls) {
    $n += 1
    $file = "price-$n.bin"
    $path = Join-Path $OutDir $file
    $record = [ordered]@{
        url = $url; file = $null; http_status = $null; final_url = $null; bytes = $null
        fetched_at = (Get-Date).ToUniversalTime().ToString("o"); error = $null
    }
    foreach ($attempt in 1..2) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -OutFile $path -PassThru -TimeoutSec 600 -MaximumRedirection 5
            $record.http_status = [int]$resp.StatusCode
            if ($resp.BaseResponse.ResponseUri) {
                $record.final_url = $resp.BaseResponse.ResponseUri.AbsoluteUri       # Windows PowerShell 5.1
            } elseif ($resp.BaseResponse.RequestMessage) {
                $record.final_url = $resp.BaseResponse.RequestMessage.RequestUri.AbsoluteUri  # PowerShell 7
            }
            $size = (Get-Item $path).Length
            if ($size -gt $MaxBytes) {
                Remove-Item $path
                $record.error = "larger than $MaxBytes bytes; not kept"
            } else {
                $record.file = $file
                $record.bytes = $size
                $record.error = $null
            }
            break
        } catch {
            $status = $null
            if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
            $record.http_status = $status
            $record.error = $_.Exception.Message
            if (Test-Path $path) { Remove-Item $path }
            if ($status -notin @(429, 502, 503, 504)) { break }
            Start-Sleep -Seconds 15
        }
    }
    $results += [pscustomobject]$record
}

ConvertTo-Json -InputObject @($results) -Depth 3 | Set-Content -Encoding UTF8 (Join-Path $OutDir "prices.json")
$ok = @($results | Where-Object { $_.file }).Count
Write-Output "Downloaded $ok of $($results.Count) price files from this computer."
