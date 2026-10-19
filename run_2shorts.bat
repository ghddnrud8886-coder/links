@cd /d "C:\Users\dzimo\Desktop\shorts-auto"
@echo off
rem One-click: render + upload 2 Shorts in a row (uploads unlisted, then auto-publishes to public after the comment succeeds - see uploader.py).
rem Each run reserves its product in data\trend_history.json before rendering, so the 2nd run never picks the same one.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo ==================================================
echo [1/2] first Shorts: pick product - render - upload - comment
echo ==================================================
python main.py --csv --upload
if errorlevel 1 (echo [1/2] FAILED - see messages above) else (echo [1/2] done)

echo.
echo Waiting 10 seconds before the 2nd video...
timeout /t 10

echo ==================================================
echo [2/2] second Shorts: next product from the queue
echo ==================================================
python main.py --csv --upload
if errorlevel 1 (echo [2/2] FAILED - see messages above) else (echo [2/2] done)

echo.
echo Finished. Uploaded files are in uploaded_videos\ and the log is in data\trend_history.json
pause
