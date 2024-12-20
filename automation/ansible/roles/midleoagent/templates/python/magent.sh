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
	addcert )
      $PYTHON "runable/addcert.py" $2
      ;;
   delcert )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/delcert.py" $2
      ;;
   enableavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/enableavl.py" $USR $2 $3 $4
      ;;
   disableavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/disableavl.py" $USR $2
      ;;
   stopavl )
      if [ -z "$3" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/stopavl.py" $USR $2 "${3}"
      ;;
   startavl )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/startavl.py" $USR $2
      ;;
   addappstat )
      if [ -z "$3" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/addappstat.py" $2 $3 $4
      ;;
   delappstat )
      if [ -z "$2" ]
      then
        $0
        exit 1
      fi
      $PYTHON "runable/delappstat.py" $2 $3
      ;;
   enabletrackqm )
      if [ -z "$2" ]
      then
        echo "Empty Qmanager"
        exit 1
      fi
      sudo su - mqm -c "echo 'ALTER QMGR ACTVTRC(ON)' | $RUNMQSC $2"
      $PYTHON "runable/enabletrackqm.py" $2
      ;;
   disabletrackqm )
      if [ -z "$2" ]
      then
        echo "Empty Qmanager"
        exit 1
      fi
      sudo su - mqm -c "echo 'ALTER QMGR ACTVTRC(OFF)' | $RUNMQSC $2"
      $PYTHON "runable/disabletrackqm.py" $2
      ;;
   createconfig )
      if [ -f $HOMEDIR"/agentConfig.json" ]
      then
         echo "file config/agentConfig.json already exist"
      else
        $PYTHON "runable/createconfig.py"
      fi
      ;;
   * )
      echo ""
      echo "usage:"
      echo "   -  $0 addcert '{\"tool\":\"keytool\",\"keystore\":\"/var/tmp/key.jks\",\"label\":\"demolabel\",\"password\":\"testpass\"}'"
      echo "   -  $0 delcert LABEL"
      echo "   -  $0 enableavl APP_SERVER SERVER_TYPE DOCKER_CONTAINER(In case it is working on Docker)"
      echo "   -  $0 disableavl APP_SERVER"
      echo "   -  $0 stopavl APP_SERVER comment"
      echo "   -  $0 startavl APP_SERVER"
      echo "   -  $0 addappstat SRV_TYPE APPSRV '{\"queues\":\"TEST.*,VVV.*\",\"channels\":\"SDR.*,CHL.*\"}'"
      echo "   -  $0 delappstat SRV_TYPE APPSRV"
      echo "   -  $0 enabletrackqm QMGR # Transfer the mqat.ini file to /var/mqm/qmgr/QMGR/ folder"
      echo "   -  $0 disabletrackqm QMGR"
      echo "   -  $0 createconfig"
      echo ""
  
   esac