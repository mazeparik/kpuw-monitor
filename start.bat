@echo off
chcp 65001 > nul
title KPUW Slot Monitor (Odciski palcow)
echo ========================================================
echo    Запуск моніторингу черги KPUW Bydgoszcz
echo ========================================================
echo.
python monitor.py
pause
