#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

cd $(dirname $0)
USR=`whoami`

HOMEDIR=$(pwd)"/config"
DSPMQVER=/opt/mqm/bin/dspmqver
DSPMQ=/opt/mqm/bin/dspmq
RUNMQSC=/opt/mqm/bin/runmqsc
AMQSEVT=/opt/mqm/bin/amqsevt
ACEUSR=mqbrk
MQSIPROFILE=/opt/ibm/ace-12/server/bin/mqsiprofile

if [[ ! -z "${PYTHON_PATH}" ]]; then
  PYTHON=${PYTHON_PATH}
else
  PYTHON="{{python_install_dir}}"
fi


export DSPMQ
export DSPMQVER
export AMQSEVT
export RUNMQSC
export ACEUSR
export MQSIPROFILE

YM=$(date '+%Y-%m')
WD=$(date '+%d')
HOUR=$(date '+%H%M')
CM=$(date +%M)

if [[ ! -e $HOMEDIR ]]; then
    mkdir $HOMEDIR
fi

LRFILE=$HOMEDIR"/nextrun.txt"
TST=$(date '+%s')
if [ -e "$LRFILE" ]; then
  T=$(head -n 1 $LRFILE)
  if [ -z "$T" ]; then
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
         $PYTHON "runable/runmqtracker.py" $AMQSEVT
      fi
      if [ -e "$HOMEDIR/confavl.json" ]; then
         if [ $HOUR == "2359" ]; then
            $PYTHON "runable/resetappavl.py" $YM $WD
         else
            $PYTHON "runable/runappavllin.py"
         fi
      fi
      if [ $TST -le $(date '+%s') ]; then
         $PYTHON "runable/getsrvdata.py"
      fi
      ;;
   esac