@echo off
setlocal EnableExtensions EnableDelayedExpansion

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
set IIBMQSIPROFILE=D:\apps\IBM\IIB\server\bin\mqsiprofile

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /format:list') do set datetime=%%I

set YEAR=%datetime:~0,4%
set MONTH=%datetime:~4,2%
set DAY=%datetime:~6,2%
set HOUR=%datetime:~8,2%
set MINUTE=%datetime:~10,2%

set YM=%YEAR%-%MONTH%
set WD=%DAY%
set CM=%MINUTE%
set HOUR=%HOUR%%MINUTE%
call :GetUnixTime UNIX_TIME

IF not exist %HOMEDIR% (mkdir %HOMEDIR%)

IF "%1"=="help" (
  goto help
)

set LRFILE=%HOMEDIR%\nextrun.txt
set TST=%UNIX_TIME%
if exist %LRFILE% (
   for /f "delims=" %%T in ('type %LRFILE%') do (
    if NOT %%T=="" (
       set TST=%%T
    )
   )
) 

if exist %HOMEDIR%\confapplstat.json (
  set CMTRUE=
  if %CM%==14 (goto resstat)
  if %CM%==00 (goto resstat)
  goto readstat

  :resstat
  python "runable\resetapplstat.py"
  EXIT /B 0

  :readstat
  python "runable\getapplstat.py"
  EXIT /B 0
)
if exist %HOMEDIR%\conftrack.json (
  python "runable\runmqtracker.py" %AMQSEVT%
)
if exist %HOMEDIR%\confavl.json (
  if %HOUR%=="2359" (
    python "runable\resetappavl.py" %YM% %WD%
  ) else (
    python "runable\runappavlwin.py"
  )
)

EXIT /B 0

:help
echo Cronjobs for MWAdmin
echo Used for background processes
EXIT /B 0

:GetUnixTime
for /f %%x in ('wmic path win32_utctime get /format:list ^| findstr "="') do (
    set %%x)
set /a z=(14-100%Month%%%100)/12, y=10000%Year%%%10000-z
set /a ut=y*365+y/4-y/100+y/400+(153*(100%Month%%%100+12*z-3)+2)/5+Day-719469
set /a ut=ut*86400+100%Hour%%%100*3600+100%Minute%%%100*60+100%Second%%%100
endlocal & set "%1=%ut%"