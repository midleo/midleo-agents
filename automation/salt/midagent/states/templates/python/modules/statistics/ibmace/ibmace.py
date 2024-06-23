import json,glob
from modules.base import makerequest,classes,configs,file_utils,statarr

def resetStat(thisnode,website,webssl,stat_data):
    try:
       if len(stat_data)>0:
          for k,item in stat_data.items():
             func = getattr(statarr, "ibmace"+k, None)
             files = glob.glob(item+"ResourceStats_"+thisnode+"_*_"+k+".txt")
             for file in files:
                ret=file_utils.csv_json(file,func(),"",True)
                retarr=json.loads(ret)
                if len(retarr)>0:
                   ret={}
                   ret["type"]="ibmace"
                   ret["subtype"]=k
                   ret["data"]=retarr
                   makerequest.postStatData(webssl,website,json.dumps(ret))  

    except OSError as err:
       classes.Err("Error opening the file statlist:"+str(err))

def getStat(thisqm,inpdata):
   return