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

def kafkaBrokerTopicMetricsBytesInPerSec():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def kafkaBrokerTopicMetricsBytesOutPerSec():
    arr={}
    arr["noteq"]="key"
    arr["node"]=1
    arr["server"]=1
    arr["keys"]={}
    arr["keys"]["timestamp"]=2
    arr["keys"]["count"]=3
    return arr

def avlCheck(thisapp,dcont=""):
    arr={}
    arr["ibmmq"]="echo 'DISPLAY QMSTATUS' | "+os.environ['RUNMQSC']+" "+thisapp+" | grep RUNNING | wc -l"
    arr["ibmmqdocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c 'echo \"DISPLAY QMSTATUS\" | "+os.environ['RUNMQSC']+" "+thisapp+"' | grep RUNNING | wc -l"
    arr["ibmace"]="sudo -u "+os.environ['ACEUSR']+" -i 'mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmacedocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c '. "+os.environ['MQSIPROFILE']+" &&  mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmiib"]="sudo -u "+os.environ['ACEUSR']+" -i 'mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmiibdocker"]="/usr/bin/docker exec -t "+dcont+" /bin/bash -c '. "+os.environ['IIBMQSIPROFILE']+" &&  mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["axwaycft"]="ps -ef|grep CFTMAIN | wc -l"
    arr["axwayst"]="ps -ef|grep Axway | grep catalina | wc -l"
    return arr