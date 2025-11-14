#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

cd $(dirname $0)
USR=`whoami`
MWAGTDIR=$(pwd)
HOMEDIR=$(pwd)"/config"
if [[ ! -e $HOMEDIR ]]; then
    mkdir $HOMEDIR
fi
if [ ! -f $HOMEDIR"/mwagent.config" ]
then
  echo "no mwagent.config file found"
else
. $HOMEDIR"/mwagent.config"
fi

export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE
export IIBMQSIPROFILE
export MWAGTDIR

YM=$(date '+%Y-%m')
WD=$(date '+%d')
HOUR=$(date '+%H%M')
CM=$(date +%M)

LRFILE=$HOMEDIR"/nextrun.txt"
TST=$(date '+%s')
if [ -e "$LRFILE" ]; then
  T=$(head -n 1 $LRFILE)
  if [ "$T" ]; then
     TST=$T
  fi  
fi

case "$1" in
    help )
      echo "Cronjobs for MWAdmin"
      echo "Used for background processes"
      ;;
    * )
      if [ -f $HOMEDIR"/confapplstat.json" ]; then
         if [[ $CM == "30" || $CM == "00" ]]; then
            $PYTHON "runable/resetapplstat.py"
         else
            $PYTHON "runable/getapplstat.py"
         fi
      fi
      if [ -f $HOMEDIR"/conftrack.json" ]; then
         $PYTHON "runable/runmqtracker.py"
      fi
      if [ -e "$HOMEDIR/confavl.json" ]; then
         if [ $HOUR == "2359" ]; then
            $PYTHON "runable/resetappavl.py" $YM $WD
         else
            $PYTHON "runable/runappavllin.py"
         fi
         $PYTHON "runable/runmqevents.py"
      fi
      if [ $TST -le $(date '+%s') ]; then
         $PYTHON "runable/getsrvdata.py"
      fi
      $PYTHON "runable/getextmonchecks.py"
      ;;
   esac