@echo off
setlocal EnableExtensions EnableDelayedExpansion

::script for midleo.CORE agent
::created by V.Vasilev
::https://vasilev.link

cd /d "%~dp0"
set "MWAGTDIR=%cd%"
set "HOMEDIR=%cd%\config"
set "LOCKDIR=%TEMP%\mwagent_cron.lock"

if exist "%HOMEDIR%\mwagent.config.bat" call "%HOMEDIR%\mwagent.config.bat"
if exist "%HOMEDIR%\mwagent.config" call :loadcfg "%HOMEDIR%\mwagent.config"

if not defined PYTHON set "PYTHON=python"

if not exist "%HOMEDIR%" mkdir "%HOMEDIR%"

if exist "%LOCKDIR%" (
  exit /b 0
)

mkdir "%LOCKDIR%" 2>nul
if errorlevel 1 exit /b 0

if /I "%1"=="help" goto help

if not exist "%HOMEDIR%\mwagent.config" if not exist "%HOMEDIR%\mwagent.config.bat" exit /b 1
if not exist "%HOMEDIR%\cronjobs.json" exit /b 1

if not exist "%HOMEDIR%\certs.json" echo {}>"%HOMEDIR%\certs.json"
if not exist "%HOMEDIR%\conftrack.json" echo {}>"%HOMEDIR%\conftrack.json"
if not exist "%HOMEDIR%\confavl.json" echo {}>"%HOMEDIR%\confavl.json"
if not exist "%HOMEDIR%\confapplstat.json" echo {}>"%HOMEDIR%\confapplstat.json"
if not exist "%HOMEDIR%\confoptadvisor.json" echo {}>"%HOMEDIR%\confoptadvisor.json"
if not exist "%HOMEDIR%\confmessagebackup.json" echo {}>"%HOMEDIR%\confmessagebackup.json"

"%PYTHON%" -c "import os,sys; sys.path.insert(0, os.getcwd()); from modules.base import configs; configs.syncCronjobsForConfig('conftrack.json', configs.gettrackData()); configs.syncCronjobsForConfig('confavl.json', configs.getAvlData()); configs.syncCronjobsForConfig('confapplstat.json', configs.getmonData()); configs.syncCronjobsForConfig('confoptadvisor.json', configs.getOptAdvisorData()); configs.syncCronjobsForConfig('confmessagebackup.json', configs.getMessageBackupData())"
if errorlevel 1 goto end

"%PYTHON%" "runable\run_cronjobs.py"

:end
rmdir "%LOCKDIR%" 2>nul
exit /b %ERRORLEVEL%

:help
echo Cronjobs for MWAdmin
echo Used for background processes
rmdir "%LOCKDIR%" 2>nul
exit /b 0

:loadcfg
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~1") do (
  if not "%%A"=="" set "%%A=%%~B"
)
exit /b 0
