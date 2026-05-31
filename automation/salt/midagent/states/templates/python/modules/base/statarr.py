import json
import os
import shlex

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
    app = str(thisapp)
    cont = str(dcont)
    mwagtdir = os.environ["MWAGTDIR"]
    runmqsc = os.environ["RUNMQSC"]
    aceusr = os.environ["ACEUSR"]
    mqsiprofile = os.environ["MQSIPROFILE"]
    iibmqsiprofile = os.environ["IIBMQSIPROFILE"]

    def q(value):
        return shlex.quote(str(value))

    def java_payload(data):
        return q(json.dumps(data, separators=(",", ":")))

    kafka_cp = q("/midleolibs/libs/*:" + mwagtdir + "/modules/statistics/kafka/resources/midleo_kafka.jar")
    jboss_cp = q("/midleolibs/libs/*:" + mwagtdir + "/modules/statistics/jboss/resources/midleo_jboss.jar")
    tomcat_cp = q("/midleolibs/libs/*:" + mwagtdir + "/modules/statistics/tomcat/resources/midleo_tomcat.jar")
    activemq_cp = q("/midleolibs/libs/*:" + mwagtdir + "/modules/statistics/activemq/resources/midleo_activemq.jar")
    ibmwas_cp = q("/midleolibs/libs/*:/midleolibs/vendor/*:" + mwagtdir + "/modules/statistics/ibmwas/resources/midleo_ibmwas.jar")
    weblogic_cp = q("/midleolibs/libs/*:/midleolibs/vendor/*:" + mwagtdir + "/modules/statistics/weblogic/resources/midleo_weblogic.jar")

    arr={}
    arr["ibmmq"]="echo 'DISPLAY QMSTATUS' | "+q(runmqsc)+" "+q(app)+" | grep RUNNING | wc -l"
    arr["ibmmqdocker"]="/usr/bin/docker exec -t "+q(cont)+" /bin/bash -c "+q("echo \"DISPLAY QMSTATUS\" | "+q(runmqsc)+" "+q(app))+" | grep RUNNING | wc -l"
    arr["ibmace"]="sudo -u "+q(aceusr)+" -i mqsilist | grep "+q(app)+" | grep running | wc -l"
    arr["ibmacedocker"]="/usr/bin/docker exec -t "+q(cont)+" /bin/bash -c "+q(". "+q(mqsiprofile)+" && mqsilist")+" | grep "+q(app)+" | grep running | wc -l"
    arr["ibmiib"]="sudo -u "+q(aceusr)+" -i mqsilist | grep "+q(app)+" | grep running | wc -l"
    arr["ibmiibdocker"]="/usr/bin/docker exec -t "+q(cont)+" /bin/bash -c "+q("mqsilist")+" | grep "+q(app)+" | grep running | wc -l"
    arr["axwaycft"]="ps -ef|grep CFTMAIN | wc -l"
    arr["axwayst"]="ps -ef|grep Axway | grep catalina | wc -l"
    arr["kafka"] = (
      "java -cp " + kafka_cp + " midleo_kafka.kafka_main " +
      java_payload({"function": "srvcheck", "server": app}) + " | grep " + q(app) + " | wc -l"
    )
    arr["jboss"] = (
      "java -cp " + jboss_cp + " midleo_jboss.midleo_jboss " +
      java_payload({"function": "srvcheck", "server": app, "usr": cred.get("usr", default_usr),
      "pwd": cred.get("pwd", default_pwd), "mngmport": cred.get("mngmport", default_mngmport)}) +
      " | grep " + q(app) + " | wc -l"
    )
    arr["tomcat"] = (
      "java -cp " + tomcat_cp + " midleo_tomcat.midleo_tomcat " +
      java_payload({"function": "srvcheck", "server": app, "usr": cred.get("usr", default_usr),
      "pwd": cred.get("pwd", default_pwd), "mngmport": cred.get("mngmport", default_mngmport)}) +
      " | grep " + q(app) + " | wc -l"
    )
    arr["activemq"] = (
      "java -cp " + activemq_cp + " midleo_activemq.activemq_main " +
      java_payload({"function": "srvinfo", "server": app, "usr": cred.get("usr", default_usr),
      "pwd": cred.get("pwd", default_pwd), "mngmport": cred.get("mngmport", default_mngmport)}) +
      " | grep " + q(app) + " | wc -l"
    )
    arr["ibmwas"] = (
      "java -cp " + ibmwas_cp + " midleo_ibmwas.ibmwas_main " +
      java_payload({"function": "srvcheck", "server": app, "usr": cred.get("usr", default_usr),
      "ssl": cred.get("ssl", default_ssl), "pwd": cred.get("pwd", default_pwd),
      "soapport": cred.get("mngmport", default_mngmport)}) + " | grep STARTED | wc -l"
    )
    arr["weblogic"] = (
      "java --add-opens java.base/java.io=ALL-UNNAMED "
      "-cp " + weblogic_cp + " "
      "midleo_weblogic.weblogic_main " +
      java_payload({"function": "srvcheck", "server": app, "usr": cred.get("usr", default_usr),
      "ssl": cred.get("ssl", default_ssl), "pwd": cred.get("pwd", default_pwd),
      "mngmport": cred.get("mngmport", default_mngmport)}) + " | grep RUNNING | wc -l"
    )
    return arr
