@echo off
setlocal enabledelayedexpansion

::script for midleo.CORE agent
::created by V.Vasilev
::https://vasilev.link

cd /d "%~dp0"
set USR=%USERNAME%
set HOMEDIR=%cd%\config
set DSPMQVER=D:\apps\IBM\MQ\bin\dspmqver
set DSPMQ=D:\apps\IBM\MQ\bin\dspmq
set RUNMQSC=D:\apps\IBM\MQ\bin\runmqsc
set AMQSEVT=D:\apps\IBM\MQ\bin\amqsevt
set ACEUSR=mqbrk
set MQSIPROFILE=D:\apps\IBM\ACE\server\bin\mqsiprofile

IF "%1"=="addcert" (
  goto addcert
)
IF "%1"=="delcert" (
  goto delcert
)
IF "%1"=="enableavl" (
  goto enableavl
)
IF "%1"=="disableavl" (
  goto disableavl
)
IF "%1"=="stopavl" (
  goto stopavl
)
IF "%1"=="startavl" (
  goto startavl
)
IF "%1"=="addappstat" (
  goto addappstat
)
IF "%1"=="delappstat" (
  goto delappstat
)
IF "%1"=="enabletrackqm" (
  goto enabletrackqm
)
IF "%1"=="disabletrackqm" (
  goto disabletrackqm
)

goto usage


:addcert
set /P TOOL=Tool (keytool or runmqakm):
set /P KEYSTORE=keystore (ex /var/tmp/key.jks):
set /P LABEL=Label (ex democert):
set /P PWD=Password:
python "runable\addcert.py" %TOOL%#%KEYSTORE%#%LABEL%#%PWD%
EXIT /B 0

:delcert
if NOT "%2"=="" (
  python "runable\delcert.py" %2
)
EXIT /B 0

:enableavl
if NOT "%3"=="" (
  python "runable\enableavl.py" %USR% %2 %3 %4
)
EXIT /B 0

:disableavl
if NOT "%2"=="" (
  python "runable\disableavl.py" %USR% %2
)
EXIT /B 0

:stopavl
if NOT "%3"=="" (
  python "runable\stopavl.py" %USR% %2 %3
)
EXIT /B 0

:startavl
if NOT "%2"=="" (
  python "runable\startavl.py" %USR% %2
)
EXIT /B 0

:addappstat
if NOT "%3"=="" (
  set "json=%~4"
  python "runable\addappstat.py" %2 %3 !json!
)
EXIT /B 0

:delappstat
if NOT "%3"=="" (
  python "runable\delappstat.py" %2 %3
)
EXIT /B 0

:enabletrackqm
if NOT "%2"=="" (
  python "runable\enabletrackqm.py" %2
)
EXIT /B 0

:disabletrackqm
if NOT "%2"=="" (
  python "runable\disabletrackqm.py" %2
)
EXIT /B 0

:usage
echo usage:
echo    -  %~nx0 addcert
echo    -  %~nx0 delcert LABEL
echo    -  %~nx0 enableavl APP_SERVER SERVER_TYPE DOCKER_CONTAINER(In case it is working on Docker)
echo    -  %~nx0 disableavl APP_SERVER
echo    -  %~nx0 stopavl APP_SERVER comment
echo    -  %~nx0 startavl APP_SERVER
echo    -  %~nx0 addappstat SRV_TYPE APPSRV '{"queues":"TEST.*,VVV.*","channels":"SDR.*,CHL.*"}'
echo    -  %~nx0 delappstat SRV_TYPE APPSRV
echo    -  %~nx0 enabletrackqm QMGR # Transfer the mqat.ini file to /var/mqm/qmgr/QMGR/ folder
echo    -  %~nx0 disabletrackqm QMGR
EXIT /B 0
