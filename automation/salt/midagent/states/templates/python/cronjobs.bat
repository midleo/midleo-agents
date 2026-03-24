@echo off
setlocal EnableExtensions EnableDelayedExpansion

::script for midleo.CORE agent
::created by V.Vasilev
::https://vasilev.link

cd /d "%~dp0"
set "MWAGTDIR=%cd%"
set "HOMEDIR=%cd%\config"
set "LOCKDIR=%TEMP%\mwagent_cron.lock"
set "PYTHON=python"

set "DSPMQVER=D:\apps\IBM\MQ\bin\dspmqver"
set "DSPMQ=D:\apps\IBM\MQ\bin\dspmq"
set "RUNMQSC=D:\apps\IBM\MQ\bin\runmqsc"
set "AMQSEVT=D:\apps\IBM\MQ\bin\amqsevt"
set "ACEUSR=mqbrk"
set "MQSIPROFILE=D:\apps\IBM\ACE\server\bin\mqsiprofile"
set "IIBMQSIPROFILE=D:\apps\IBM\IIB\server\bin\mqsiprofile"

if exist "%HOMEDIR%\mwagent.config.bat" (
  call "%HOMEDIR%\mwagent.config.bat"
)

if not defined PYTHON set "PYTHON=python"

if not exist "%HOMEDIR%" mkdir "%HOMEDIR%"

if exist "%LOCKDIR%" (
  exit /b 0
)

mkdir "%LOCKDIR%" 2>nul
if errorlevel 1 exit /b 0

if /I "%1"=="help" goto help

if not exist "%HOMEDIR%\mwagent.config.bat" exit /b 1
if not exist "%HOMEDIR%\cronjobs.json" exit /b 1

if not exist "%HOMEDIR%\certs.json" echo {}>"%HOMEDIR%\certs.json"
if not exist "%HOMEDIR%\conftrack.json" echo {}>"%HOMEDIR%\conftrack.json"
if not exist "%HOMEDIR%\confavl.json" echo {}>"%HOMEDIR%\confavl.json"
if not exist "%HOMEDIR%\confapplstat.json" echo {}>"%HOMEDIR%\confapplstat.json"

"%PYTHON%" -c "import os,sys; sys.path.insert(0, os.getcwd()); from modules.base import configs; configs.syncCronjobsForConfig('conftrack.json', configs.gettrackData()); configs.syncCronjobsForConfig('confavl.json', configs.getAvlData()); configs.syncCronjobsForConfig('confapplstat.json', configs.getmonData())"
if errorlevel 1 goto end

set "MWAGTDIR=%cd%"
set "HOMEDIR=%cd%\config"
set "DSPMQVER=%DSPMQVER%"
set "DSPMQ=%DSPMQ%"
set "RUNMQSC=%RUNMQSC%"
set "AMQSEVT=%AMQSEVT%"
set "ACEUSR=%ACEUSR%"
set "MQSIPROFILE=%MQSIPROFILE%"
set "IIBMQSIPROFILE=%IIBMQSIPROFILE%"
set "PYTHON=%PYTHON%"

"%PYTHON%" "runable\run_cronjobs.py"

:end
rmdir "%LOCKDIR%" 2>nul
exit /b %ERRORLEVEL%

:help
echo Cronjobs for MWAdmin
echo Used for background processes
rmdir "%LOCKDIR%" 2>nul
exit /b 0