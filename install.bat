@echo off
rem 우리의 족보 - 이 파일 하나만 내려받아 두 번 누르면 됩니다.
rem 프로그램을 내려받고, 파이썬과 꾸러미를 설치하고, 화면까지 띄웁니다.
setlocal enabledelayedexpansion
chcp 949 >nul
title 우리의 족보 - 설치

set "REPO=https://github.com/kimheunghan/jocbo"
rem 받을 곳. 첫 인자로 다른 폴더를 줄 수 있습니다 - install.bat D:\어디\jocbo
set "TARGET=%USERPROFILE%\Documents\jocbo"
if not "%~1"=="" set "TARGET=%~1"

echo.
echo   우리의 족보 - 설치
echo   ----------------------------------------
echo   받을 곳: %TARGET%
echo.

rem -- 이미 받아 둔 폴더가 있으면 최신으로만 ----
if exist "%TARGET%\start.bat" (
  echo   이미 설치됨 - 최신으로 맞춥니다.
  rem 서버가 도는 중이면 파일이 잠겨 git pull 이 깨집니다.
  if exist "%TARGET%\stop.bat" call "%TARGET%\stop.bat"
  where git >nul 2>&1
  if not errorlevel 1 (
    pushd "%TARGET%"
    git pull --ff-only
    popd
  ) else (
    echo   git 없음 - 내려받기는 건너뜁니다.
  )
  goto run
)

rem -- git 이 있으면 clone, 없으면 ZIP ----------
where git >nul 2>&1
if not errorlevel 1 (
  echo   내려받는 중... ^(git^)
  git clone --depth 1 "%REPO%.git" "%TARGET%"
  if errorlevel 1 goto failed
  goto run
)

echo   git 없음 - 압축파일로 내려받습니다.
set "ZIP=%TEMP%\jocbo-main.zip"
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Invoke-WebRequest -Uri '%REPO%/archive/refs/heads/main.zip' -OutFile '%ZIP%' -UseBasicParsing;" ^
  "Expand-Archive -Path '%ZIP%' -DestinationPath $env:TEMP -Force;" ^
  "if (Test-Path '%TARGET%') { Remove-Item '%TARGET%' -Recurse -Force };" ^
  "Move-Item (Join-Path $env:TEMP 'jocbo-main') '%TARGET%';" ^
  "Remove-Item '%ZIP%' -Force"
if errorlevel 1 goto failed

:run
if not exist "%TARGET%\start.bat" goto failed
echo.
echo   내려받기 완료 - 설치와 실행으로 넘어갑니다.
echo.

rem 바탕화면 폴더 이름은 언어마다 다릅니다(Desktop / 바탕 화면).
rem 윈도우에 직접 묻고 거기에 둡니다. 다음부터는 이것만 누르면 됩니다.
powershell -NoProfile -WindowStyle Hidden -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '우리의 족보.lnk'));" ^
  "$s.TargetPath='%TARGET%\start.bat'; $s.WorkingDirectory='%TARGET%'; $s.Save()" >nul 2>&1

cd /d "%TARGET%"
call "%TARGET%\start.bat"
exit /b 0

:failed
echo.
echo   내려받기 실패 - 인터넷 연결을 확인하거나 아래에서 직접 받으십시오.
echo   %REPO%
echo.
pause
exit /b 1
