@echo off
REM MMC Fleet Robot launcher — restarts automatically if the process ever exits
REM (e.g. MT5 not ready yet at boot, wrong account, transient error). Retries
REM every 15s until it connects to demo 109082333 with Algo Trading on.
cd /d D:\MMC
:loop
echo ==== fleet start %date% %time% ==== >> D:\MMC\mmc\brain\weights\_fleet_stdout.log
C:\Python314\python.exe D:\MMC\examples\mt5_fleet_robot.py >> D:\MMC\mmc\brain\weights\_fleet_stdout.log 2>> D:\MMC\mmc\brain\weights\_fleet_stderr.log
echo ==== fleet exited %date% %time%, restarting in 15s ==== >> D:\MMC\mmc\brain\weights\_fleet_stdout.log
timeout /t 15 /nobreak >nul
goto loop
