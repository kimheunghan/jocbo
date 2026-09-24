@echo off
rem 우리의 족보 - 내려받은 폴더에서 이 파일을 두 번 누르면 설치와 실행이 함께 됩니다.
rem 처음 한 번만 오래 걸리고, 두 번째부터는 바로 열립니다.
setlocal enabledelayedexpansion
chcp 949 >nul
cd /d "%~dp0"
title 우리의 족보

echo.
echo   우리의 족보
echo   ----------------------------------------
echo.

rem -- 새 판 확인 -------------------------------
rem 바탕화면 바로가기는 이 파일을 엽니다. GitHub 에 새 판이 있으면 install.bat 에
rem 넘겨 백업과 갱신을 맡기고(call 없이 넘어가 돌아오지 않습니다), 끝나면 그쪽이
rem 새 start.bat 을 다시 엽니다. 인터넷이나 git 이 없으면 지금 판으로 엽니다.
rem 이 폴더에만 있는 커밋이 있으면(고치는 컴퓨터) 건드리지 않습니다.
if not exist ".git" goto checked
where git >nul 2>&1 || goto checked
echo   새 판 확인 중...
git fetch -q origin main >nul 2>&1 || goto checked
set "HERE="
set "LATEST="
for /f %%H in ('git rev-parse HEAD 2^>nul') do set "HERE=%%H"
for /f %%H in ('git rev-parse origin/main 2^>nul') do set "LATEST=%%H"
if "%HERE%"=="%LATEST%" goto checked
git merge-base --is-ancestor HEAD origin/main >nul 2>&1 || goto checked
echo   새 판이 있습니다 - 갱신합니다.
"%~dp0install.bat" "%~dp0."
:checked

rem -- 파이썬 찾기 ------------------------------
set "PY="
for %%V in (3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo   파이썬 없음 - 먼저 설치 필요
  echo.
  where winget >nul 2>&1
  if errorlevel 1 (
    echo   https://www.python.org/downloads/ 에서 설치
    echo   설치 화면의 "Add python.exe to PATH" 반드시 선택
  ) else (
    echo   지금 설치할까요? ^(winget 사용^)
    choice /c YN /n /m "   [Y] 설치  [N] 직접 설치 "
    if !errorlevel! equ 1 (
      winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
      echo.
      echo   설치 완료 - 이 창을 닫고 start.bat 다시 실행
    ) else (
      echo   https://www.python.org/downloads/ 에서 설치
    )
  )
  echo.
  pause
  exit /b 1
)

for /f "tokens=2" %%V in ('%PY% -V 2^>^&1') do set "PYVER=%%V"
echo   파이썬 %PYVER%

rem -- 가상환경 ---------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo   가상환경 생성 중...
  %PY% -m venv .venv
  if errorlevel 1 goto failed
)
set "VENV=.venv\Scripts\python.exe"

rem -- 꾸러미 -----------------------------------
"%VENV%" -c "import fastapi, uvicorn, sqlalchemy, multipart" >nul 2>&1
if errorlevel 1 (
  echo   꾸러미 설치 중... ^(처음 한 번만^)
  "%VENV%" -m pip install --quiet --upgrade pip
  "%VENV%" -m pip install --quiet -r requirements.txt
  if errorlevel 1 goto failed
)
echo   꾸러미 준비됨

rem -- 판독기 (선택) ----------------------------
"%VENV%" -c "import rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   족보 이미지 판독기 - 미설치
  echo   사진에서 인물을 읽어 옮겨 적는 기능입니다. 약 200MB를 내려받습니다.
  echo   설치하지 않아도 나머지 기능은 모두 동작합니다.
  choice /c YN /n /t 20 /d N /m "   [Y] 설치  [N] 나중에  (20초 후 자동으로 나중에) "
  if !errorlevel! equ 1 (
    echo   판독기 설치 중... ^(몇 분 걸립니다^)
    "%VENV%" -m pip install --quiet -r requirements-ocr.txt
    if errorlevel 1 (
      echo   판독기 설치 실패 - 나머지 기능은 그대로 사용 가능
    ) else (
      echo   판독기 준비됨
    )
  )
) else (
  echo   판독기 준비됨
)

rem -- 처음 설치라면 족보를 넣어 둡니다 -----------
rem 기록이 있는 설치는 건드리지 않습니다.
if not exist "jocbo.db" (
  echo   족보 불러오는 중...
  "%VENV%" -m db.seed_reference_page
  if errorlevel 1 echo   족보 불러오기 실패 - 빈 화면으로 시작합니다.
)

rem -- 브라우저 ---------------------------------
rem 크롬이 있으면 크롬으로, 없으면 기본 브라우저로 엽니다.
rem %ProgramFiles(x86)% 의 괄호가 for ( ) 블록을 깨뜨리므로 한 줄씩 확인합니다.
set "CHROME="
set "PF86=%ProgramFiles(x86)%"
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%PF86%\Google\Chrome\Application\chrome.exe" set "CHROME=%PF86%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not defined CHROME for /f "tokens=2,*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" /ve 2^>nul ^| find "REG_SZ"') do set "CHROME=%%B"

rem -- 실행 -------------------------------------
echo.
echo   ----------------------------------------
echo   http://127.0.0.1:8000
if defined CHROME (echo   크롬으로 엽니다.) else (echo   크롬 없음 - 기본 브라우저로 엽니다.)
echo   창을 닫거나 Ctrl+C 를 누르면 종료됩니다.
echo   ----------------------------------------
echo.

rem 서버가 자리를 잡을 때까지 잠시 기다렸다가 엽니다.
if defined CHROME (
  start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process -FilePath '%CHROME%' -ArgumentList 'http://127.0.0.1:8000'"
) else (
  start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"
)

"%VENV%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
goto done

:failed
echo.
echo   설치 실패 - 위의 메시지를 확인하십시오.
echo.
pause
exit /b 1

:done
echo.
echo   종료됨
pause
