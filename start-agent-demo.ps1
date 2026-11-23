$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$html = Join-Path $root 'artifacts\steelchain-agent.html'
$apiUrl = 'http://127.0.0.1:8000'
$stdout = Join-Path $env:TEMP 'steelchain-agent-api.out.log'
$stderr = Join-Path $env:TEMP 'steelchain-agent-api.err.log'

try {
    $health = Invoke-RestMethod "$apiUrl/health" -TimeoutSec 2
    if ($health.status -ne 'ok') { throw '已有服务健康检查未通过' }
} catch {
    & python -c "import fastapi,uvicorn,langgraph,ortools" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host '缺少后端运行依赖。请先在此目录运行：' -ForegroundColor Yellow
        Write-Host 'python -m pip install -r requirements-agents.txt -r requirements-ml.txt -r requirements-optimization.txt'
        Read-Host '安装完成后按 Enter 重新启动'
        exit 1
    }
    $server = Start-Process -FilePath 'python' -ArgumentList @('-m','uvicorn','steelchain.agents.api:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 750
        try {
            $health = Invoke-RestMethod "$apiUrl/health" -TimeoutSec 2
            if ($health.status -eq 'ok') { $ready = $true; break }
        } catch {
            if ($server.HasExited) { break }
        }
    }
    if (-not $ready) {
        Write-Host "API 启动失败。错误日志：$stderr" -ForegroundColor Red
        if (Test-Path $stderr) { Get-Content $stderr -Tail 30 }
        Read-Host '按 Enter 关闭'
        exit 1
    }
}

Start-Process $html
Write-Host '钢链智脑已在浏览器中打开。关闭此窗口不会停止后端服务。' -ForegroundColor Green
Write-Host "API: $apiUrl  （日志：$stdout / $stderr）"
