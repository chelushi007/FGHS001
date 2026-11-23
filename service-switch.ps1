$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8000
$apiUrl = "http://127.0.0.1:$port"
$html = Join-Path $root 'artifacts\steelchain-agent.html'
$stateDir = Join-Path $env:LOCALAPPDATA 'SteelChainAgent'
$stateFile = Join-Path $stateDir 'api.pid'
$stdout = Join-Path $stateDir 'api.out.log'
$stderr = Join-Path $stateDir 'api.err.log'

function Test-AgentApi {
    try {
        $response = Invoke-RestMethod "$apiUrl/health" -TimeoutSec 2
        return $response.status -eq 'ok'
    } catch {
        return $false
    }
}

function Get-SwitchOwnedProcess {
    if (-not (Test-Path $stateFile)) { return $null }
    try { $state = Get-Content -Raw $stateFile | ConvertFrom-Json } catch { return $null }
    $processId = 0
    if (-not [int]::TryParse([string]$state.pid, [ref]$processId)) { return $null }
    try {
        $proc = Get-Process -Id $processId -ErrorAction Stop
        if ($proc.ProcessName -match '^python' -and $proc.StartTime.ToUniversalTime().Ticks -eq [long]$state.start_ticks) { return $proc }
    } catch { return $null }
    return $null
}

if (-not (Test-Path $html)) {
    Write-Host 'HTML file is missing. Extract the complete project ZIP and double-click this switch from its root folder.' -ForegroundColor Red
    exit 1
}

$owned = Get-SwitchOwnedProcess
if ($owned -and (Test-AgentApi)) {
    Stop-Process -Id $owned.ProcessId -Force
    Remove-Item -LiteralPath $stateFile -Force
    Write-Host 'SteelChain Agent API stopped.' -ForegroundColor Yellow
    exit 0
}

if (Test-AgentApi) {
    Write-Host 'The API is already running outside this switch. Opening the HTML without stopping that service.' -ForegroundColor Green
    Start-Process $html
    exit 0
}

$requirements = @('requirements-agents.txt', 'requirements-ml.txt', 'requirements-optimization.txt') | ForEach-Object { Join-Path $root $_ }
if (($requirements | Where-Object { -not (Test-Path $_) }).Count -gt 0) {
    Write-Host 'Dependency files are missing. Download and extract the complete project ZIP, not only the HTML file.' -ForegroundColor Red
    exit 1
}

& python -c 'import fastapi,uvicorn,langgraph,ortools' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Python dependencies are missing. Installing them from this project folder...' -ForegroundColor Yellow
    Push-Location $root
    try { & python -m pip install -r $requirements[0] -r $requirements[1] -r $requirements[2] }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Dependency installation failed. Check the pip error above.' -ForegroundColor Red
        exit 1
    }
}

New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$server = Start-Process -FilePath 'python' -ArgumentList @('-m','uvicorn','steelchain.agents.api:app','--host','127.0.0.1','--port',"$port") -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    if (Test-AgentApi) { $ready = $true; break }
    if ($server.HasExited) { break }
}

if (-not $ready) {
    Write-Host "API did not start. Error log: $stderr" -ForegroundColor Red
    if (Test-Path $stderr) { Get-Content $stderr -Tail 30 }
    exit 1
}

$serverProcess = Get-Process -Id $server.Id -ErrorAction Stop
@{ pid = $server.Id; start_ticks = $serverProcess.StartTime.ToUniversalTime().Ticks } | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding ascii
Start-Process $html
Write-Host 'SteelChain Agent is running and the HTML workbench is open.' -ForegroundColor Green
Write-Host 'Double-click this switch again to stop the API started by this switch.'
