#!/bin/bash
#wrapper for Midleo PCF script

HOMEDIR=$(pwd)
QM=`dspmq | sed -n "s/.*QMNAME(\([^ ]*\)).*(Running)$/\1/p"`
if [ -z "$QM" ]; then
  echo "QMGR(s) not available"; exit 1
fi
TYPEMON=$1
THRESHOLD=$2
if [ -z "${THRESHOLD}" ]; then
  echo "      Usage: $0 TYPE_OF_MON THRESHOLD"
  echo "TYPE_OF_MON: QAGE - monitor queue age, QFULL - monitor percentage of maxdepth/curdepth"
  echo "  THRESHOLD: value in seconds for the monitoring threshold"
  exit 1
fi

OS=`uname -s`
if [ "$OS" = "SunOS" ]; then
  MAILER=/usr/bin/mail
elif [ "$OS" = "Linux" ]; then
  MAILER=/usr/sbin/sendmail
fi

SERVER=`hostname`

load_config ()
{
   if [ -e "$HOMEDIR/midleo.conf" ]; then
      . $HOMEDIR/midleo.conf
   else
      create_config
   fi
}
create_config (){
    echo "Midleo DNS server name:"
    read midleodns
    if [ -z "${midleodns}" ]; then
       rm $HOMEDIR/"midleo.conf"
    else
       echo "midleodns=$midleodns" > $HOMEDIR/"midleo.conf"
    fi
    echo "Midleo Monitoring ID (if only email notification needed - write the word EMAIL):"
    read midleomonid
    if [ -z "${midleomonid}" ]; then
       rm $HOMEDIR/"midleo.conf"
    else
       if [ "${midleomonid}" == "EMAIL" ]; then
          echo "Email for the notifications:"
          read monitoremail
          if [ -z "${monitoremail}" ]; then
             rm $HOMEDIR/"midleo.conf"
          else
             echo monitoremail=$monitoremail >> $HOMEDIR/"midleo.conf"
          fi
       else
          echo "midleomonid=$midleomonid" >> $HOMEDIR/"midleo.conf"
       fi
    fi
    echo "Monitoring queues: QLOCAL.*;SYSTEM.FTE.*;QLOCAL2.*;"
    read monitoringq
    if [ -z "${monitoringq}" ]; then
       rm $HOMEDIR/"midleo.conf"
    else
       echo monitoringq=\""$monitoringq\"" >> $HOMEDIR/"midleo.conf"
    fi
    echo "IBM MQ library path(example - /opt/mqm/java/lib64):"
    read ibmmqlibpath
    if [ -z "${ibmmqlibpath}" ]; then
       rm $HOMEDIR/"midleo.conf"
    else
       echo ibmmqlibpath=$ibmmqlibpath >> $HOMEDIR/"midleo.conf"
    fi
}

load_config
JAVA_OPTS="-Djava.library.path=$ibmmqlibpath"

email_attachment() { 
  boundary="_====_midleo_====_$(date +%Y%m%d%H%M%S)_====_"
  mailfrom="noreply@midleo.com"
  mailto=$monitoremail
  arrinp=("$@")
  {
  echo "From: $mailfrom"
  echo "To: $mailto"
  echo "Subject: Monitoring alert from `hostname`"
  echo "Content-Type: multipart/mixed; boundary=\"$boundary\""
  echo "MIME-Version: 1.0"
  echo "--$boundary
Content-Type: text/html; charset=UTF8

IBM MQ monitoring alert from MIDLEO!<br>
Details:<br>
<br>
server: `hostname`<br><br>
<table style='border:none;background-color:#fff;table-layout:fixed;-webkit-text-size-adjust:100%;' border='0px' width='100%' cellspacing='0' cellpadding='0' align='center' bgcolor='#fff'>
<thead><tr><td style='padding:5px;border: none; border-collapse: collapse!important; border-spacing: 0!important; -webkit-text-size-adjust: 100%;  color: #666;'>Type</td><td>Name</td><td>Max</td><td>Current</td><td>Alert On</td></tr></thead>
<tbody>
"
for obj in "${arrinp[@]}";
  do
    if [ "$obj" != "[" ] && [ "$obj" != "]" ]; then
       echo ${obj//\"}
    fi
  done
echo "</tbody></table><br><br><b>Please act acordingly!</b>
<br><br><br> 
<font color='#14599b'>Regards<br>
MidlEO Team</font>
"
  }  | $MAILER $mailto
}

for J in ${QM}
   do
   javaout=`java ${JAVA_OPTS} -jar $HOMEDIR/midleomon.jar '{"function":"'$TYPEMON'","qmanager":"'$J'","alertnum":'$THRESHOLD'}' "$monitoringq"`
   if [[ ! -z "$javaout" ]]; then
     # echo $javaout
     if [[ ! -z "${monitoremail}" ]]; then
        readarray -t inparr < <(echo "${javaout}" | jq '.APPOBJ[] | ["<tr><td style=\"padding:5px;border: none; border-collapse: collapse!important; border-spacing: 0!important; -webkit-text-size-adjust: 100%;  color: #666;\">" + .TYPE + "</td><td>" + .NAME + "</td><td>" + (.MAX|tostring) + "</td><td>" + (.CURRENT|tostring) + "</td><td>" + (.ALERTON|tostring)+"</td></tr>"]')
        email_attachment "${inparr[@]}"
     fi
     if [[ ! -z "${midleomonid}" ]]; then
       curl \
-H "Accept: application/json" \
-H "Content-Type:application/json" \
-X POST --data "${javaout}" "https://${midleodns}/monapi/alert/?monid=${midleomonid}&srv=${SERVER}"
     fi
   fi
done