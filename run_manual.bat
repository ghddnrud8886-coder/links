@cd /d "C:\Users\dzimo\Desktop\shorts-auto"
@echo off
rem Manual product Short from data\ product list (see manual_queue.py).
rem Usage: run_manual.bat [naver ^| coupang ^| etc]   (no argument = first pending row of any sheet)
rem Step 1 renders the video only. Step 2 asks before uploading, so you can check output\ first.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo ==================================================
echo [1/2] Render one Short from the first pending row %1
echo ==================================================
python main.py --manual %1
if errorlevel 1 (
  echo FAILED - see messages above
  pause
  exit /b 1
)

echo.
echo Check the new video in the output folder (and the work log folder).
set /p GO="Upload to YouTube now? (Y/N): "
if /i not "%GO%"=="Y" (
  echo Not uploaded. The row is marked as rendered in the sheet.
  pause
  exit /b 0
)

echo ==================================================
echo [2/2] Upload and post the link comment
echo ==================================================
python main.py --upload-last
pause
