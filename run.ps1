$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $projectRoot 'backend'
$frontendPath = Join-Path $projectRoot 'frontend'
$backendPython = Join-Path $backendPath '.venv\Scripts\python.exe'
$backendCommand = if (Test-Path $backendPython) {
    '& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload'
} else {
    'python -m uvicorn app.main:app --reload'
}

Start-Process powershell.exe -WorkingDirectory $backendPath -ArgumentList @(
    '-NoExit',
    '-Command',
    $backendCommand
)

Start-Process powershell.exe -WorkingDirectory $frontendPath -ArgumentList @(
    '-NoExit',
    '-Command',
    'npm run dev'
)

Write-Host 'Backend and frontend started in separate PowerShell windows.'
Write-Host 'Backend:  http://127.0.0.1:8000'
Write-Host 'Frontend: http://localhost:5173'
