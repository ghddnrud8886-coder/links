@cd /d "C:\Users\dzimo\Desktop\shorts-auto"
@echo off
rem Make 4 videos in one go (no upload while data\upload_hold.json is active; videos stay in output\).
rem Products come from the AliExpress Affiliate API (price 15,000-60,000 KRW, different concepts back to back).
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

for %%i in (1 2 3 4) do (
  echo ==================================================
  echo Video %%i of 4
  echo ==================================================
  python main.py --csv --api --upload
  if errorlevel 1 echo FAILED on video %%i - see messages above
)

echo.
echo Finished. Videos: output\   Work logs: 작업기록\
pause
