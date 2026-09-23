@echo off
rem 우리의 족보 - 돌고 있는 서버를 멈춥니다.
rem 새로 내려받아 갱신하기 전에 먼저 이것을 누릅니다.
setlocal
chcp 949 >nul
cd /d "%~dp0"
title 우리의 족보 - 중지

echo.
echo   우리의 족보 - 중지
echo   ----------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
echo   ----------------------------------------
echo.
ping -n 4 127.0.0.1 >nul
