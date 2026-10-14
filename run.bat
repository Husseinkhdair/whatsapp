@echo off
chcp 65001 > nul
title WhatsApp Multi-Account Manager API
echo ========================================================
echo   WhatsApp Web Multi-Account Manager API (FastAPI)
echo ========================================================
echo Starting server on http://localhost:8000 ...
py -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
