import json, os, csv
from modules.base import classes

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

def ReadAvl(logfile):
    if os.path.isfile(os.getcwd()+"/logs/"+logfile):
      try:
         with open(os.getcwd()+"/logs/"+logfile) as f:
            reader_obj = csv.reader((line.replace('\0','') for line in f), delimiter = ',')
            ret={}
            nl=0
            navl=0
            nplavl=0
            nnplavl=0
            pltext=""

            for linearr in reader_obj:
               if(len(linearr)<2): 
                  pass
               else:
                  nl+= 1
                  if (linearr[1]=="online"):
                     navl+= 1
                  elif (linearr[1]=="stopped"or linearr[1]=="started"):
                     nplavl+= 1
                     pltext+=linearr[0]+": "+linearr[1]+" - "+('nobody' if not(linearr[2]) else linearr[2])+" - "+('no comment' if len(linearr)<4 else linearr[3])+";"
                  else:
                     nnplavl+= 1
                     pltext+=linearr[0]+": not available;"

            navl=(navl/nl)*100
            nplavl=(nplavl/nl)*100
            nnplavl=(nnplavl/nl)*100

            ret["navl"]=navl
            ret["nplavl"]=nplavl
            ret["nnplavl"]=nnplavl
            ret["pltext"]=pltext

            with open(os.getcwd()+"/logs/"+logfile, 'w'): pass
      except OSError as err:
         classes.Err("Error opening the file:"+str(err))
         ret={}
    else:
      ret={}
    return ret