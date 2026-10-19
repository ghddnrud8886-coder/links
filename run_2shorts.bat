@cd /d "C:\Users\dzimo\Desktop\shorts-auto"
@echo off
rem One-click: pick a product, render and upload ONE Short (uploads unlisted, then auto-publishes to public after the comment succeeds - see uploader.py).
rem The product is reserved in data\trend_history.json before rendering, so the next run never picks the same one.
rem File name kept as run_2shorts.bat so existing desktop shortcuts keep working.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo ==================================================
echo Shorts: pick product - render - upload - comment
echo ==================================================
python main.py --csv --upload
if errorlevel 1 (echo FAILED - see messages above) else (echo done)

echo.
echo Finished. Video: output\   Uploaded files: uploaded_videos\   History: data\trend_history.json
pause
