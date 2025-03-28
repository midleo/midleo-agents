#!/bin/bash

#script for midleo.CORE agent
#created by V.Vasilev
#https://vasilev.link

cd $(dirname $0)
USR=`whoami`
HOMEDIR=$(pwd)"/config"

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

case "$1" in
   getdockerstat )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/getdockerstat.py" $2 "${3}"
      ;;
   * )
      echo ""
      echo "usage:"
      echo "   -  $0 getdockerstat SRV_TYPE APPSRV 'JSON'"
      echo ""
      
   esac