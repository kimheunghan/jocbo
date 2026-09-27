@echo off
rem 우리의 족보 - 이 파일 하나만 내려받아 두 번 누르면 됩니다.
rem 프로그램을 내려받고, 파이썬과 꾸러미를 설치하고, 화면까지 띄웁니다.
rem 이미 설치된 곳에서 다시 누르면 GitHub 최신과 똑같이 맞춘 뒤 띄웁니다.
setlocal enabledelayedexpansion
chcp 949 >nul
title 우리의 족보 - 설치

set "REPO=https://github.com/kimheunghan/jocbo"

rem cmd는 배치 파일을 한 줄씩 읽어 가며 실행합니다. 설치 폴더 안의 이 파일을
rem 그대로 돌리면 갱신이 실행 중인 자신을 새 판으로 바꿔 버리므로, 임시 폴더에
rem 사본을 두고 그 사본으로 넘어갑니다(call 없이 넘어가 돌아오지 않습니다).
if /i "%~1"=="--run" (
  set "TARGET=%~2"
  goto start
)
rem 받을 곳: 첫 인자 > 이 파일이 놓인 설치 폴더 > 문서\jocbo
set "TARGET=%USERPROFILE%\Documents\jocbo"
if exist "%~dp0start.bat" set "TARGET=%~dp0."
if not "%~1"=="" set "TARGET=%~1"
for %%T in ("%TARGET%") do set "TARGET=%%~fT"
copy /y "%~f0" "%TEMP%\jocbo-install.bat" >nul
"%TEMP%\jocbo-install.bat" --run "%TARGET%"

:start
echo.
echo   우리의 족보 - 설치
echo   ----------------------------------------
echo   받을 곳: %TARGET%
echo.

if exist "%TARGET%\start.bat" goto update

rem -- 새로 받기: git 이 있으면 clone, 없으면 ZIP ----
where git >nul 2>&1
if not errorlevel 1 (
  echo   내려받는 중... ^(git^)
  git clone "%REPO%.git" "%TARGET%"
  if errorlevel 1 goto failed
  goto run
)
echo   git 없음 - 압축파일로 내려받습니다.
call :fetchzip
if errorlevel 1 goto failed
move "%TEMP%\jocbo-main" "%TARGET%" >nul
if errorlevel 1 goto failed
goto run

rem -- 이미 받아 둔 폴더는 GitHub 최신과 똑같이 ----
:update
echo   이미 설치됨 - GitHub 최신으로 맞춥니다.
rem 서버가 도는 중이면 파일이 잠겨 갱신이 깨집니다.
if exist "%TARGET%\stop.bat" if exist "%TARGET%\stop.ps1" call "%TARGET%\stop.bat"
where git >nul 2>&1
if errorlevel 1 goto updatezip

pushd "%TARGET%"
rem 압축파일로 받았던 폴더도 여기서 git 으로 이어 받습니다.
if not exist ".git" git init -q
git remote remove origin >nul 2>&1
git remote add origin "%REPO%.git"
echo   최신 내려받는 중...
git fetch -q origin main
if errorlevel 1 (
  popd
  goto failed
)
rem 이 컴퓨터에서 바뀌었거나 git 이 모르는 파일이 있으면 통째로 백업한 뒤
rem 덮어씁니다. 족보 DB(jocbo.db)는 컴퓨터마다 따로라 git 이 다루지 않습니다.
set "DIRTY="
for /f "delims=" %%S in ('git status --porcelain 2^>nul') do set "DIRTY=1"
if defined DIRTY call :backup
rem 이 폴더에만 있는 커밋은 backup-날짜-시각 가지에 남겨 두고 넘어갑니다.
git rev-parse -q --verify HEAD >nul 2>&1
if not errorlevel 1 (
  git merge-base --is-ancestor HEAD origin/main
  if errorlevel 1 (
    call :stamp
    git branch -f backup-!STAMP! HEAD >nul
    echo   이 폴더에만 있던 커밋을 남겨 둡니다: backup-!STAMP!
  )
)
rem DB 를 git 으로 나르던 옛 판에서 넘어올 때 git 이 jocbo.db 를 지우므로,
rem 옆에 비켜 두었다가 되돌립니다.
if exist "jocbo.db" copy /y "jocbo.db" "%TEMP%\jocbo-keep.db" >nul
git reset -q --hard origin/main
if errorlevel 1 (
  popd
  goto failed
)
if not exist "jocbo.db" if exist "%TEMP%\jocbo-keep.db" copy /y "%TEMP%\jocbo-keep.db" "jocbo.db" >nul
if exist "%TEMP%\jocbo-keep.db" del "%TEMP%\jocbo-keep.db"
git branch -M main >nul 2>&1
git branch -q --set-upstream-to=origin/main main >nul 2>&1
for /f "delims=" %%L in ('git log --oneline -1') do echo   받은 판: %%L
popd
goto packages

:updatezip
echo   git 없음 - 압축파일로 최신을 덮어씁니다.
call :fetchzip
if errorlevel 1 goto failed
call :backup
robocopy "%TEMP%\jocbo-main" "%TARGET%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto failed
rmdir /s /q "%TEMP%\jocbo-main"

rem 새 판에서 꾸러미가 늘었으면 여기서 맞춥니다. start.bat 은 처음 한 번만 설치합니다.
:packages
if exist "%TARGET%\.venv\Scripts\python.exe" (
  echo   꾸러미 맞추는 중... ^(몇 분 걸릴 수 있습니다 - 창을 닫지 마세요^)
  "%TARGET%\.venv\Scripts\python.exe" -m pip install --quiet -r "%TARGET%\requirements.txt"
)

:run
if not exist "%TARGET%\start.bat" goto failed
echo.
echo   내려받기 완료 - 설치와 실행으로 넘어갑니다.
echo.
if defined JOCBO_NO_START exit /b 0

rem 바탕화면 폴더 이름은 언어마다 다릅니다(Desktop / 바탕 화면).
rem 윈도우에 직접 묻고 거기에 둡니다. 다음부터는 이것만 누르면 됩니다.
powershell -NoProfile -WindowStyle Hidden -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '우리의 족보.lnk'));" ^
  "$s.TargetPath='%TARGET%\start.bat'; $s.WorkingDirectory='%TARGET%'; $s.Save()" >nul 2>&1

cd /d "%TARGET%"
call "%TARGET%\start.bat"
exit /b 0

rem -- 설치 폴더를 옆에 통째로 복사해 둡니다(가상환경과 git 기록은 뺍니다) ----
:backup
call :stamp
set "BACKUP=%TARGET%-backup-%STAMP%"
robocopy "%TARGET%" "%BACKUP%" /E /XD .venv .git __pycache__ .pytest_cache /NFL /NDL /NJH /NJS /NP >nul
echo   바뀐 파일이 있어 백업해 둡니다: %BACKUP%
exit /b 0

rem -- 백업 이름에 붙일 날짜-시각 ----
:stamp
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%D"
exit /b 0

rem -- GitHub 최신을 압축파일로 받아 %TEMP%\jocbo-main 에 풉니다 ----
:fetchzip
set "ZIP=%TEMP%\jocbo-main.zip"
if exist "%TEMP%\jocbo-main" rmdir /s /q "%TEMP%\jocbo-main"
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Invoke-WebRequest -Uri '%REPO%/archive/refs/heads/main.zip' -OutFile '%ZIP%' -UseBasicParsing;" ^
  "Expand-Archive -Path '%ZIP%' -DestinationPath $env:TEMP -Force;" ^
  "Remove-Item '%ZIP%' -Force"
exit /b %errorlevel%

:failed
echo.
echo   내려받기 실패 - 인터넷 연결을 확인하거나 아래에서 직접 받으십시오.
echo   %REPO%
echo.
pause
exit /b 1
