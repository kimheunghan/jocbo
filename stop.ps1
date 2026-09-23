# 우리의 족보 - 이 폴더에서 돌고 있는 서버를 멈춥니다.
# stop.bat 이 불러 씁니다. 배치 안에 따옴표를 겹쳐 쓰지 않으려고 따로 두었습니다.
$ErrorActionPreference = 'SilentlyContinue'
$root = (Get-Location).Path
$found = @()

# 이 폴더의 파이썬으로 뜬 uvicorn
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn*' -and $_.CommandLine -like "*$root*" } |
    ForEach-Object { $found += $_.ProcessId }

# 8000 번을 잡고 있는 파이썬 (폴더를 옮겼거나 경로가 달라진 경우)
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess
    if ($p -and $p.ProcessName -eq 'python') { $found += $p.Id }
}

$found = $found | Sort-Object -Unique | Where-Object { $_ -gt 0 }

if (-not $found) {
    Write-Host '  실행 중인 서버 없음'
    exit 0
}

foreach ($id in $found) {
    # 앞의 것을 멈추면서 같이 사라졌을 수 있습니다.
    $p = Get-Process -Id $id
    if (-not $p) { continue }
    $name = $p.ProcessName
    Stop-Process -Id $id -Force
    Write-Host "  중지됨 - $name (PID $id)"
}

# 포트가 실제로 풀렸는지 확인합니다.
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Milliseconds 300
    if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen)) {
        Write-Host '  8000 번 풀림'
        exit 0
    }
}
Write-Host '  8000 번이 아직 잡혀 있습니다 - 창을 닫고 다시 시도하십시오.'
exit 1
