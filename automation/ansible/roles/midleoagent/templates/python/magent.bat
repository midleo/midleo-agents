@echo off
setlocal enabledelayedexpansion

::script for midleo.CORE agent
::created by V.Vasilev
::https://vasilev.link

cd /d "%~dp0"
set "USR=%USERNAME%"
set "MWAGTDIR=%cd%"
set "HOMEDIR=%cd%\config"
set "DSPMQVER=D:\apps\IBM\MQ\bin\dspmqver"
set "DSPMQ=D:\apps\IBM\MQ\bin\dspmq"
set "RUNMQSC=D:\apps\IBM\MQ\bin\runmqsc"
set "AMQSEVT=D:\apps\IBM\MQ\bin\amqsevt"
set "ACEUSR=mqbrk"
set "MQSIPROFILE=D:\apps\IBM\ACE\server\bin\mqsiprofile"
set "IIBMQSIPROFILE=D:\apps\IBM\IIB\server\bin\mqsiprofile"
set "PYTHON=python"

if exist "%HOMEDIR%\mwagent.config.bat" (
  call "%HOMEDIR%\mwagent.config.bat"
)

if not defined PYTHON set "PYTHON=python"

"%PYTHON%" -c "import os,sys; sys.path.insert(0, os.getcwd()); from modules.base import configs; cfgdir=os.path.join(os.getcwd(),'config'); os.makedirs(cfgdir, exist_ok=True); cronf=os.path.join(cfgdir,'cronjobs.json'); 
import sys as _s; 
_s.exit('missing config\\cronjobs.json' if not os.path.isfile(cronf) else 0)"
if errorlevel 1 exit /b 1

if not exist "%HOMEDIR%\certs.json" echo {}>"%HOMEDIR%\certs.json"
if not exist "%HOMEDIR%\conftrack.json" echo {}>"%HOMEDIR%\conftrack.json"
if not exist "%HOMEDIR%\confavl.json" echo {}>"%HOMEDIR%\confavl.json"
if not exist "%HOMEDIR%\confapplstat.json" echo {}>"%HOMEDIR%\confapplstat.json"
if not exist "%HOMEDIR%\confactions.json" echo {}>"%HOMEDIR%\confactions.json"

"%PYTHON%" -c "import os,sys; sys.path.insert(0, os.getcwd()); from modules.base import configs; configs.syncCronjobsForConfig('conftrack.json', configs.gettrackData()); configs.syncCronjobsForConfig('confavl.json', configs.getAvlData()); configs.syncCronjobsForConfig('confapplstat.json', configs.getmonData())"
if errorlevel 1 exit /b 1

if /I "%1"=="addcert" goto addcert
if /I "%1"=="delcert" goto delcert
if /I "%1"=="enableavl" goto enableavl
if /I "%1"=="disableavl" goto disableavl
if /I "%1"=="stopavl" goto stopavl
if /I "%1"=="startavl" goto startavl
if /I "%1"=="addappstat" goto addappstat
if /I "%1"=="delappstat" goto delappstat
if /I "%1"=="addaction" goto addaction
if /I "%1"=="rmaction" goto rmaction
if /I "%1"=="enabletrackqm" goto enabletrackqm
if /I "%1"=="disabletrackqm" goto disabletrackqm
if /I "%1"=="maintenance" goto maintenance

goto usage

:addcert
set "json=%~2"
"%PYTHON%" "runable\addcert.py" !json!
exit /b %ERRORLEVEL%

:delcert
if "%~2"=="" (
  goto usage
)
"%PYTHON%" "runable\delcert.py" "%~2"
exit /b %ERRORLEVEL%

:enableavl
if "%~2"=="" (
  goto usage
)
"%PYTHON%" "runable\enableavl.py" %2 %3 %4
exit /b %ERRORLEVEL%

:disableavl
if "%~2"=="" (
  goto usage
)
"%PYTHON%" "runable\disableavl.py" %2 %3
exit /b %ERRORLEVEL%

:stopavl
if "%~3"=="" (
  goto usage
)
"%PYTHON%" "runable\stopavl.py" "%USR%" %2 %3 "%~4"
exit /b %ERRORLEVEL%

:startavl
if "%~2"=="" (
  goto usage
)
"%PYTHON%" "runable\startavl.py" "%USR%" "%~2" "%~3"
exit /b %ERRORLEVEL%

:addappstat
if "%~3"=="" (
  goto usage
)
set "json=%~4"
"%PYTHON%" "runable\addappstat.py" "%~2" "%~3" !json!
exit /b %ERRORLEVEL%

:delappstat
if "%~3"=="" (
  goto usage
)
"%PYTHON%" "runable\delappstat.py" "%~2" "%~3"
exit /b %ERRORLEVEL%

:addaction
if "%~2"=="" (
  goto usage
)
if not "%~3"=="" (
  set "json=%~3"
  "%PYTHON%" "runable\addaction.py" "%~2" !json!
) else (
  set "json=%~2"
  "%PYTHON%" "runable\addaction.py" !json!
)
exit /b %ERRORLEVEL%

:rmaction
if "%~2"=="" (
  goto usage
)
"%PYTHON%" "runable\rmaction.py" "%~2"
exit /b %ERRORLEVEL%

:enabletrackqm
if "%~2"=="" (
  echo Empty Qmanager
  exit /b 1
)
"%PYTHON%" "runable\enabletrackqm.py" "%~2"
exit /b %ERRORLEVEL%

:disabletrackqm
if "%~2"=="" (
  echo Empty Qmanager
  exit /b 1
)
"%PYTHON%" "runable\disabletrackqm.py" "%~2"
exit /b %ERRORLEVEL%

:maintenance
if "%~2"=="" (
  echo usage: %~nx0 maintenance on^|off [comment]
  exit /b 1
)

if /I "%~2"=="on" (
  > "%HOMEDIR%\maintenance.flag" echo %date% %time% %~3
) else if /I "%~2"=="off" (
  if exist "%HOMEDIR%\maintenance.flag" del /f /q "%HOMEDIR%\maintenance.flag"
) else (
  echo usage: %~nx0 maintenance on^|off [comment]
  exit /b 1
)

"%PYTHON%" "runable\setmaintenance.py" "%~2" "%~3"
exit /b %ERRORLEVEL%

:usage
echo usage:
echo    -  %~nx0 addcert "{\"tool\":\"keytool\",\"keystore\":\"C:\\temp\\key.jks\",\"excluded\":\"alias1,alias2\",\"password\":\"testpass\"}"
echo    -  %~nx0 delcert LABEL_OR_KEYSTORE
echo    -  %~nx0 enableavl APP_SERVER SERVER_TYPE "{\"docker\":\"DOCKER_CONTAINER_NAME\",\"user\":\"USERNAME_FOR_APPLICATION_SERVER_ACCESS\",\"pass\":\"PASSWORD_FOR_APPLICATION_SERVER_ACCESS\"}"
echo    -  %~nx0 disableavl APP_SERVER SERVER_TYPE
echo    -  %~nx0 stopavl APP_SERVER SERVER_TYPE comment
echo    -  %~nx0 startavl APP_SERVER SERVER_TYPE
echo    -  %~nx0 addappstat SRV_TYPE APPSRV "{\"queues\":\"TEST.*,VVV.*\",\"channels\":\"SDR.*,CHL.*\"}"
echo    -  %~nx0 delappstat SRV_TYPE APPSRV
echo    -  %~nx0 addaction APP_SERVER_TYPE.ERROR_CODE "{\"script\":\"C:\\actions\\restart.cmd\",\"args\":[\"{appserver_type}\",\"{error_code}\"],\"monid\":\"monaction\",\"appsrvid\":\"none\",\"appsrv\":\"tomcat01\",\"message\":\"Action already started recently\"}"
echo    -  %~nx0 addaction "{\"action_key\":\"APP_SERVER_TYPE.ERROR_CODE\",\"script\":\"C:\\actions\\restart.cmd\"}"
echo    -  %~nx0 rmaction APP_SERVER_TYPE.ERROR_CODE
echo    -  %~nx0 enabletrackqm QMGR
echo    -  %~nx0 disabletrackqm QMGR
echo    -  %~nx0 maintenance on^|off [comment]
exit /b 0
