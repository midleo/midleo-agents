import json, os
from modules import classes

def csv_json(file,array,check=False,cleanit=False):
    json_arr = []
    if os.path.isfile(file):
        if len(array) > 0:
            try:
               with open(file) as f:
                  json_arr = []
                  for line in f:
                     linearr=line.strip().split(',')
                     if(len(linearr)<2): 
                        pass
                     else:
                       in_arr={}
                       if(check and linearr[0]==check):
                         in_arr["type"]=array["type"]
                         in_arr["line"]=str("sumarized" if linearr[0]=='summary' else linearr[0])
                         for (key, value) in array.items():
                            try:
                               in_arr[key]=linearr[int(value)]
                            except:
                               pass
                         json_arr.append(in_arr)
                       else:
                         pass
                     if(not check and linearr[0]!=array["noteq"]):
                        in_arr["type"]=array["type"]
                        in_arr["line"]=str("sumarized" if linearr[0]=='summary' else linearr[0])
                        for (key, value) in array.items():
                            try:
                               in_arr[key]=linearr[int(value)]
                            except:
                               pass
                        json_arr.append(in_arr)
            except OSError as err:
               classes.Err("Error opening the file:"+str(err))
        if(cleanit):
            with open(file, 'w'): pass
    return json.dumps(json_arr)