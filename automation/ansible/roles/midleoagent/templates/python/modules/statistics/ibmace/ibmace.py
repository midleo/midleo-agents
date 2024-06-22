import json,glob
from modules.base import makerequest,classes,configs,file_utils,statarr

def resetStat(q):
    try:
       stat_data = configs.getstatData()
       config_data = configs.getcfgData()
       website = config_data['website']
       webssl = config_data['webssl']
       if len(stat_data)>0:
          for k,item in stat_data.items():
             func = getattr(statarr, item["function"], None)
             files = glob.glob(item["file"])
             for file in files:
                ret=file_utils.csv_json(file,func(),item["line"],item["clean"])
                retarr=json.loads(ret)
                if len(retarr)>0:
                   ret={}
                   ret["type"]=item["type"]
                   ret["subtype"]=item["function"].replace(item["type"],"")
                   ret["data"]=retarr
                   makerequest.postStatData(webssl,website,json.dumps(ret))   
    except OSError as err:
       classes.Err("Error opening the file statlist:"+str(err))