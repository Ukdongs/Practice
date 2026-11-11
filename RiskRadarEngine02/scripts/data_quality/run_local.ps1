param(
    [Parameter(Mandatory=$true)][string]$Python,
    [string]$SourceDirectory = 'C:\Users\Public\Documents\RiskRadarOpenDataResearch',
    [string]$PytestSitePackages = ''
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Push-Location $repo
try {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
    if ($PytestSitePackages) { $env:PYTHONPATH = $PytestSitePackages }
    New-Item -ItemType Directory -Force artifacts/data_quality | Out-Null
    $log = 'artifacts/data_quality/run.log'
    "UTC: $([DateTime]::UtcNow.ToString('o'))`nInterpreter: $Python`nSource: $SourceDirectory`nNetwork: none" | Set-Content $log -Encoding utf8
    & $Python --version 2>&1 | ForEach-Object { $_; $_ | Out-File -FilePath $log -Append -Encoding utf8 }
    foreach ($site in @('i80', 'us101', 'lankershim', 'peachtree')) {
        $inputCsv = Join-Path $SourceDirectory "ngsim_contiguous_${site}_20s.csv"
        "Command: analyze_ngsim.py $inputCsv --output artifacts/data_quality/${site}_20s.json" | Add-Content $log -Encoding utf8
        & $Python scripts/data_quality/analyze_ngsim.py $inputCsv --output "artifacts/data_quality/${site}_20s.json" 2>&1 | ForEach-Object { $_; $_ | Out-File -FilePath $log -Append -Encoding utf8 }
        if ($LASTEXITCODE -ne 0) { throw "Analyzer failed: $site" }
    }
    & $Python -m pytest prism-risk-engine/tests/test_data_quality.py -q -p no:cacheprovider --basetemp=artifacts/data_quality/pytest_tmp 2>&1 | ForEach-Object { $_; $_ | Out-File -FilePath $log -Append -Encoding utf8 }
    if ($LASTEXITCODE -ne 0) { throw 'QA tests failed' }
} finally { Pop-Location }
