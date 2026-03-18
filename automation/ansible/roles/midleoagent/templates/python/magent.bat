@echo off
setlocal enabledelayedexpansion

::script for midleo.CORE agent
::created by V.Vasilev
::https://vasilev.link

cd /d "%~dp0"
set USR=%USERNAME%
set MWAGTDIR=%cd%
set HOMEDIR=%cd%\config
set DSPMQVER=D:\apps\IBM\MQ\bin\dspmqver
set DSPMQ=D:\apps\IBM\MQ\bin\dspmq
set RUNMQSC=D:\apps\IBM\MQ\bin\runmqsc
set AMQSEVT=D:\apps\IBM\MQ\bin\amqsevt
set ACEUSR=mqbrk
set MQSIPROFILE=D:\apps\IBM\ACE\server\bin\mqsiprofile
set IIBMQSIPROFILE=D:\apps\IBM\IIB\server\bin\mqsiprofile

if exist "%HOMEDIR%\mwagent.config.bat" (
  call "%HOMEDIR%\mwagent.config.bat"
)

IF /I "%1"=="addcert" (
  goto addcert
)
IF /I "%1"=="delcert" (
  goto delcert
)
IF /I "%1"=="enableavl" (
  goto enableavl
)
IF /I "%1"=="disableavl" (
  goto disableavl
)
IF /I "%1"=="stopavl" (
  goto stopavl
)
IF /I "%1"=="startavl" (
  goto startavl
)
IF /I "%1"=="addappstat" (
  goto addappstat
)
IF /I "%1"=="delappstat" (
  goto delappstat
)
IF /I "%1"=="enabletrackqm" (
  goto enabletrackqm
)
IF /I "%1"=="disabletrackqm" (
  goto disabletrackqm
)
IF /I "%1"=="maintenance" (
  goto maintenance
)
IF /I "%1"=="createconfig" (
  goto createconfig
)

goto usage

:addcert
set "json=%~2"
python "runable\addcert.py" !json!
EXIT /B 0

:delcert
if NOT "%~2"=="" (
  python "runable\delcert.py" "%~2"
)
EXIT /B 0

:enableavl
if NOT "%~3"=="" (
  python "runable\enableavl.py" "%~2" "%~3" "%~4" "%~5" "%~6"
)
EXIT /B 0

:disableavl
if NOT "%~2"=="" (
  python "runable\disableavl.py" "%~2" "%~3"
)
EXIT /B 0

:stopavl
if NOT "%~3"=="" (
  python "runable\stopavl.py" "%USR%" "%~2" "%~3" "%~4"
)
EXIT /B 0

:startavl
if NOT "%~2"=="" (
  python "runable\startavl.py" "%USR%" "%~2" "%~3"
)
EXIT /B 0

:addappstat
if NOT "%~3"=="" (
  set "json=%~4"
  python "runable\addappstat.py" "%~2" "%~3" !json!
)
EXIT /B 0

:delappstat
if NOT "%~3"=="" (
  python "runable\delappstat.py" "%~2" "%~3"
)
EXIT /B 0

:enabletrackqm
if NOT "%~2"=="" (
  python "runable\enabletrackqm.py" "%~2"
)
EXIT /B 0

:disabletrackqm
if NOT "%~2"=="" (
  python "runable\disabletrackqm.py" "%~2"
)
EXIT /B 0

:maintenance
if "%~2"=="" (
  echo usage: %~nx0 maintenance on^|off [comment]
  EXIT /B 1
)

if /I "%~2"=="on" (
  > "%HOMEDIR%\maintenance.flag" echo %date% %time% %~3
) else if /I "%~2"=="off" (
  if exist "%HOMEDIR%\maintenance.flag" del /f /q "%HOMEDIR%\maintenance.flag"
) else (
  echo usage: %~nx0 maintenance on^|off [comment]
  EXIT /B 1
)

python "runable\setmaintenance.py" "%~2" "%~3"
EXIT /B %ERRORLEVEL%

:createconfig
python "runable\createconfig.py"
EXIT /B 0

:usage
echo usage:
echo    -  %~nx0 addcert '{"tool":"keytool","keystore":"/var/tmp/key.jks","label":"demolabel","password":"testpass"}'
echo    -  %~nx0 delcert LABEL
echo    -  %~nx0 enableavl APP_SERVER SERVER_TYPE DOCKER_CONTAINER(In case it is working on Docker) USER(password) PASS(password)
echo    -  %~nx0 disableavl APP_SERVER SERVER_TYPE
echo    -  %~nx0 stopavl APP_SERVER SERVER_TYPE comment
echo    -  %~nx0 startavl APP_SERVER SERVER_TYPE
echo    -  %~nx0 addappstat SRV_TYPE APPSRV '{"queues":"TEST.*,VVV.*","channels":"SDR.*,CHL.*"}'
echo    -  %~nx0 delappstat SRV_TYPE APPSRV
echo    -  %~nx0 enabletrackqm QMGR # Transfer the mqat.ini file to /var/mqm/qmgr/QMGR/ folder
echo    -  %~nx0 disabletrackqm QMGR
echo    -  %~nx0 maintenance on^|off [comment]
echo    -  %~nx0 createconfig
EXIT /B 0