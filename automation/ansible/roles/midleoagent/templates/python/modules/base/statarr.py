import os

def ibmaceJVM():
    arr={}
    arr["noteq"]="ResourceName"
    arr["node"]=1
    arr["server"]=2
    arr["keys"]={}
    arr["keys"]["timestamp"]=5
    arr["keys"]["used"]=7
    arr["keys"]["max"]=9
    return arr

def ibmaceODBC():
    arr={}
    arr["noteq"]="ResourceName"
    arr["node"]=1
    arr["server"]=2
    arr["keys"]={}
    arr["keys"]["timestamp"]=5
    arr["keys"]["used"]=8
    return arr

def kafka():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def jboss():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def tomcat():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def activemq():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def ibmwas():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def weblogic():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def msiis():
    arr={}
    arr["noteq"]="metric"
    arr["node"]=1
    arr["server"]=2
    arr["keys"]={}
    arr["keys"]["timestamp"]=3
    arr["keys"]["count"]=4
    return arr

def avlCheck(thisapp,dcont="",cred=None):
    if(cred is None):
       cred = {}
    default_usr = ""
    default_pwd = ""
    default_mngmport = ""
    default_ssl = "no"
    arr={}
    arr["ibmmq"]="echo 'DISPLAY QMSTATUS' | "+os.environ['RUNMQSC']+" "+thisapp+" | grep RUNNING | wc -l"
    arr["ibmmqdocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c 'echo \"DISPLAY QMSTATUS\" | "+os.environ['RUNMQSC']+" "+thisapp+"' | grep RUNNING | wc -l"
    arr["ibmace"]="sudo -u "+os.environ['ACEUSR']+" -i 'mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmacedocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c '. "+os.environ['MQSIPROFILE']+" &&  mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmiib"]="sudo -u "+os.environ['ACEUSR']+" -i 'mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmiibdocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c '. "+os.environ['IIBMQSIPROFILE']+" &&  mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["axwaycft"]="ps -ef|grep CFTMAIN | wc -l"
    arr["axwayst"]="ps -ef|grep Axway | grep catalina | wc -l"
    arr["kafka"] = (
      "java -cp '/midleolibs/libs/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/kafka/resources/midleo_kafka.jar' midleo_kafka.kafka_main " +
      "'{\"function\":\"srvcheck\",\"server\":\"" + thisapp + "\"}' | grep " + thisapp + " | wc -l"
    )
    arr["jboss"] = (
      "java -cp '/midleolibs/libs/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/jboss/resources/midleo_jboss.jar' midleo_jboss.midleo_jboss " +
      "'{\"function\":\"srvcheck\",\"server\":\"" + thisapp + "\",\"usr\":\"" + cred.get("usr", default_usr) +
      "\",\"pwd\":\"" + cred.get("pwd", default_pwd) + "\",\"mngmport\":\"" + cred.get("mngmport", default_mngmport) +
      "\"}' | grep " + thisapp + " | wc -l"
    )
    arr["tomcat"] = (
      "java -cp '/midleolibs/libs/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/tomcat/resources/midleo_tomcat.jar' midleo_tomcat.midleo_tomcat " +
      "'{\"function\":\"srvcheck\",\"server\":\"" + thisapp + "\",\"usr\":\"" + cred.get("usr", default_usr) +
      "\",\"pwd\":\"" + cred.get("pwd", default_pwd) + "\",\"mngmport\":\"" + cred.get("mngmport", default_mngmport) +
      "\"}' | grep " + thisapp + " | wc -l"
    )
    arr["activemq"] = (
      "java -cp '/midleolibs/libs/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/activemq/resources/midleo_activemq.jar' midleo_activemq.activemq_main " +
      "'{\"function\":\"srvinfo\",\"server\":\"" + thisapp + "\",\"usr\":\"" + cred.get("usr", default_usr) +
      "\",\"pwd\":\"" + cred.get("pwd", default_pwd) + "\",\"mngmport\":\"" + cred.get("mngmport", default_mngmport) +
      "\"}' | grep " + thisapp + " | wc -l"
    )
    arr["ibmwas"] = (
      "java -cp '/midleolibs/libs/*:/midleolibs/vendor/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/ibmwas/resources/midleo_ibmwas.jar' midleo_ibmwas.ibmwas_main " +
      "'{\"function\":\"srvcheck\",\"server\":\"" + thisapp + "\",\"usr\":\"" + cred.get("usr", default_usr) +
      "\",\"ssl\":\"" + cred.get("ssl", default_ssl) +
      "\",\"pwd\":\"" + cred.get("pwd", default_pwd) + "\",\"soapport\":\"" + cred.get("mngmport", default_mngmport) +
      "\"}' | grep STARTED | wc -l"
    )
    arr["weblogic"] = (
      "java --add-opens java.base/java.io=ALL-UNNAMED "
      "-cp '/midleolibs/libs/*:/midleolibs/vendor/*:" + os.environ['MWAGTDIR'] +
      "/modules/statistics/weblogic/resources/midleo_weblogic.jar' "
      "midleo_weblogic.weblogic_main " +
      "'{\"function\":\"srvcheck\",\"server\":\"" + thisapp + "\",\"usr\":\"" + cred.get("usr", default_usr) +
      "\",\"ssl\":\"" + cred.get("ssl", default_ssl) +
      "\",\"pwd\":\"" + cred.get("pwd", default_pwd) + "\",\"mngmport\":\"" + cred.get("mngmport", default_mngmport) +
      "\"}' | grep RUNNING | wc -l"
    )
    return arr