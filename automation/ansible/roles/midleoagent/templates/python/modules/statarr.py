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

def avlCheck(thisapp):
    arr={}
    arr["ibmmq"]=os.environ['DSPMQ']+" -m "+thisapp+" -s | grep Running | wc -l"
    arr["ibmace"]="su "+os.environ['ACEUSR']+" -c '. "+os.environ['MQSIPROFILE']+" && mqsilist' | grep "+thisapp+" | grep running | wc -l"
    arr["ibmacedocker"]="/usr/bin/docker exec -t ibmace /bin/bash -c '. "+os.environ['MQSIPROFILE']+" &&  mqsilist' | grep "+thisapp+" | grep running | wc -l"
    return arr