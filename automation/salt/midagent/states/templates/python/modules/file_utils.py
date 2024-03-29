import json, os, csv
from modules import classes

def csv_json(file,array,check=False,cleanit=False):
    if os.path.isfile(file):
        if len(array) > 0:
            try:
               with open(file) as f:
                  reader_obj = csv.reader((line.replace('\0','') for line in f), delimiter = ',')
                  in_arr={}
                  for linearr in reader_obj:
                     if(len(linearr)<2): 
                        pass
                     else:
                       
                       if(check and linearr[0]==check):
                          if linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0]) not in in_arr:
                            in_arr[linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0])]=""
                          strline=""
                          for (key, value) in array["keys"].items():
                            try:
                              strline+=linearr[int(value)]+"#"
                            except:
                               pass
                          strline=strline[:-1]+";"
                          in_arr[linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0])]+=strline
                       else:
                          pass
                       if(not check and linearr[0]!=array["noteq"]):
                          if linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0]) not in in_arr:
                            in_arr[linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0])]=""
                          strline=""
                          for (key, value) in array["keys"].items():
                            try:
                              strline+=linearr[int(value)]+"#"
                            except:
                               pass
                          strline=strline[:-1]+";"
                          in_arr[linearr[int(array["node"])]+"#"+linearr[int(array["server"])]+"#"+str("sumarized" if linearr[0]=='summary' else linearr[0])]+=strline
            except OSError as err:
               classes.Err("Error opening the file:"+str(err))
        if(cleanit):
            with open(file, 'w'): pass
    return json.dumps(in_arr)