import csv
import json
import os

from modules.base import classes

LOG_DIR = os.path.join(os.getcwd(), "logs")


def _safe_index(row, index):
    try:
        idx = int(index)
        if idx < 0 or idx >= len(row):
            return None
        return row[idx]
    except Exception:
        return None


def _summary_name(value):
    return "sumarized" if value == "summary" else value


def _group_key(row, mapping):
    node = _safe_index(row, mapping.get("node"))
    server = _safe_index(row, mapping.get("server"))
    if node is None or server is None or len(row) < 1:
        return None
    return node + "#" + server + "#" + str(_summary_name(row[0]))


def _truncate_file(path):
    try:
        with open(path, "w", encoding="utf-8"):
            pass
    except OSError as err:
        classes.Err("Error cleaning the file:" + str(err))


def csv_json(file,array,check=False,cleanit=True):
    in_arr={}
    if os.path.isfile(file):
        if len(array) > 0:
            try:
               with open(file, encoding="utf-8", errors="ignore", newline="") as f:
                  reader_obj = csv.reader((line.replace('\0','') for line in f), delimiter=',')
                  for linearr in reader_obj:
                     if len(linearr) < 2:
                        continue
                     include = (
                        (check and linearr[0] == check)
                        or (not check and linearr[0] != array.get("noteq"))
                     )
                     if not include:
                        continue
                     group_key = _group_key(linearr, array)
                     if not group_key:
                        continue
                     if group_key not in in_arr:
                        in_arr[group_key] = ""
                     values = []
                     for value in array.get("keys", {}).values():
                        cell = _safe_index(linearr, value)
                        if cell is not None:
                           values.append(cell)
                     in_arr[group_key] += "#".join(values) + ";"
            except OSError as err:
               classes.Err("Error opening the file:"+str(err))
        if(cleanit):
            _truncate_file(file)
    return json.dumps(in_arr)

def ReadAvl(logfile):
    path = os.path.join(LOG_DIR, os.path.basename(logfile))
    if os.path.isfile(path):
      try:
         with open(path, encoding="utf-8", errors="ignore", newline="") as f:
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
                     user = "nobody" if len(linearr) < 3 or not linearr[2] else linearr[2]
                     comment = "no comment" if len(linearr) < 4 else linearr[3]
                     pltext+=linearr[0]+": "+linearr[1]+" - "+user+" - "+comment+";"
                  else:
                     nnplavl+= 1
                     pltext+=linearr[0]+": not available;"

            if nl > 0:
               navl=(navl/nl)*100
               nplavl=(nplavl/nl)*100
               nnplavl=(nnplavl/nl)*100

            ret["navl"]=navl
            ret["nplavl"]=nplavl
            ret["nnplavl"]=nnplavl
            ret["pltext"]=pltext

            _truncate_file(path)
      except OSError as err:
         classes.Err("Error opening the file:"+str(err))
         ret={}
    else:
      ret={}
    return ret

def WriteCSV(filename,dict,header,type="w"):
    if dict:
       os.makedirs(LOG_DIR, exist_ok=True)
       path = os.path.join(LOG_DIR, os.path.basename(filename) + ".csv")
       with open(path, type, encoding="utf-8", newline='') as file:
          writer = csv.DictWriter(file, fieldnames = header)
          if type=="w":
            writer.writeheader()
          writer.writerows(dict)
       try:
          os.chmod(path, 0o600)
       except Exception:
          pass
