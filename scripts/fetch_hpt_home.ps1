# Fetch every approved hospital website's /cms-hpt.txt, live, from this computer.
# Runs on Cooper's computer as a GitHub self-hosted runner job (Windows PowerShell 5.1).
# Writes each file exactly as received plus fetches.json describing every attempt.
# Nothing else on the computer is read or changed; output goes to the folder given.
param(
    [string]$WebsitesCsv = "data/reference/facility_websites.csv",
    [string]$OutDir = "hpt-home"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$sites = Import-Csv $WebsitesCsv |
    Where-Object { $_.status -eq "website" -and $_.reviewed_by -and $_.reviewed_at -and $_.website } |
    ForEach-Object { $_.website.Trim().TrimEnd("/").ToLower() } |
    Sort-Object -Unique

$results = @()
foreach ($site in $sites) {
    $url = "$site/cms-hpt.txt"
    $file = (($site -replace '^https?://', '') -replace '[^A-Za-z0-9.-]', '_') + ".txt"
    $path = Join-Path $OutDir $file
    $record = [ordered]@{
        site = $site; url = $url; file = $null; http_status = $null; final_url = $null
        fetched_at = (Get-Date).ToUniversalTime().ToString("o"); error = $null
    }
    foreach ($attempt in 1..3) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -OutFile $path -PassThru -TimeoutSec 60 -MaximumRedirection 5
            $record.http_status = [int]$resp.StatusCode
            if ($resp.BaseResponse.ResponseUri) {
                $record.final_url = $resp.BaseResponse.ResponseUri.AbsoluteUri       # Windows PowerShell 5.1
            } elseif ($resp.BaseResponse.RequestMessage) {
                $record.final_url = $resp.BaseResponse.RequestMessage.RequestUri.AbsoluteUri  # PowerShell 7
            }
            $record.file = $file
            $record.error = $null
            break
        } catch {
            $status = $null
            if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
            $record.http_status = $status
            $record.error = $_.Exception.Message
            if (Test-Path $path) { Remove-Item $path }
            if ($status -notin @(429, 502, 503, 504)) { break }
            Start-Sleep -Seconds (15 * $attempt)
        }
    }
    $results += [pscustomobject]$record
    Start-Sleep -Seconds 1
}

$results | ConvertTo-Json -Depth 3 | Set-Content -Encoding UTF8 (Join-Path $OutDir "fetches.json")
$ok = @($results | Where-Object { $_.file }).Count
Write-Output "Fetched $ok of $($results.Count) sites from this computer."
