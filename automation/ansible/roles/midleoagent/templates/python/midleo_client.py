import base64,platform,json,re,uuid,time,subprocess,socket,sys,os
from multiprocessing import Process
from datetime import datetime
from modules import makerequest,decrypt,classes,certcheck

PORT_NUMBER = 5550
SIZE = 1024
AGENT_VER = "1.24.01"

if platform.system()=="Linux":
   from modules import lin_utils,lin_packages
elif platform.system()=="Windows":
   from modules import win_utils
else:
   exit()

def getcfgData():
    with open(os.getcwd()+"/config/agentConfig.json", 'r') as config_file:
        config_data=json.load(config_file)
        return config_data

def createConfigJson():
    try:
        config_data = getcfgData()
    except Exception as err:

        config_data = {
            "uid": str(uuid.uuid4().hex[:16]),
            "website": input("Please provide midleo DNS:"),
            "webssl": input("SSL enabled ? (y/n):"),
            "groupid": input("Please provide responsible GroupID:"),
            "updint": input("Update interval (in minutes):")
        }

        with open(os.getcwd()+"/config/agentConfig.json", 'w+') as config_file:
            json.dump(config_data, config_file)

def create():
    try:
        config_data = getcfgData()
        uid = config_data['uid']
        groupid = config_data['groupid']
        updint = config_data['updint']

        if platform.system()=="Windows":
            cpu = classes.CPU(win_utils.getCPUName(), win_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(win_utils.getName(), win_utils.getOS(), win_utils.getArchitecture(), win_utils.getMachineType(), cpu.__dict__, win_utils.getMemory(), win_utils.getDiskPartitions(), win_utils.getLBTS())
            net_config = classes.NetConfig(win_utils.getIP())
            config = classes.Config(uid,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, win_utils.getSoftware()) 
        elif platform.system()=="Linux":
            cpu = classes.CPU(lin_utils.getCPUName(), lin_utils.getCPUCoreCount())
            hw_config = classes.HWConfig(lin_utils.getName(), lin_utils.getOS(), lin_utils.getArchitecture(), lin_utils.getMachineType(), cpu.__dict__, lin_utils.getMemory(), lin_utils.getDiskPartitions(), lin_utils.getLBTS())
            net_config = classes.NetConfig(lin_utils.getIP())
            if os.path.isfile(os.getcwd()+"/config/certs.json"):
               cert_check = certcheck.Run(uid+uid+uid+uid)
            else:
               cert_check = []
            config = classes.Config(uid,groupid,AGENT_VER,updint, hw_config.__dict__, net_config.__dict__, lin_packages.getSoftware(), cert_check) 
        else:
            exit()

        return config
    except OSError as err:
        classes.Err("Error:"+str(err))
    except Exception as ex:
        classes.Err("Exception:"+str(ex))

def main():
    config = create()
    config_data = getcfgData()
    website = config_data['website']
    webssl = config_data['webssl']
    updint = config_data['updint']

    if 'error' in config.__dict__.keys():
        return

    try:
        output = json.dumps(config.__dict__)
        output = re.sub(r"<([a-zA-Z-_]+)?.([a-zA-Z-_]+)(\d?):(\s?)", "", output)
        output = re.sub(r">", "", output)
        makerequest.postData(webssl,website,json.loads(output))
        return updint
    except OSError as err:
        classes.Err("Error:"+str(err))
    except Exception as ex:
        classes.Err("Exception:"+str(ex))

createConfigJson()

def funcgetdata():
    while True:
        getupdint=main()
        time.sleep(int(getupdint)*60)

def listenfordata():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      config_data = getcfgData()
      uid = config_data['uid']
      uid = uid+uid+uid+uid
      s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR, 1)
      s.bind(('', PORT_NUMBER))
      s.listen(5)
      while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        conn, addr = s.accept()
        classes.Err("Info:"+"Connected by "+str(addr))
        data = conn.recv(1024)
        if not data:
           pass
           conn.close()
        try:
            data = data.rstrip()
            data = decrypt.decryptit(data,uid)
            data = json.loads(data)
            if not data["uid"]==uid:
               pass
               conn.close()
            if data["command"]:
               data["command"]=base64.b64decode(data["command"]).decode('utf-8')
               try:
                 output = subprocess.check_output(data["command"], shell=True,stderr=subprocess.STDOUT)
               except subprocess.CalledProcessError as e:
                 output=e.output
               classes.Err("Command:"+data["command"])
               conn.sendall(str.encode("Time:"+current_time+"<br>"+"Command:"+data["command"]+"<br>"+"Output:"+str(output.decode('utf-8'))))
               conn.close()
            else:
               classes.Err("Command:empty")
               conn.sendall(str.encode("Time:"+current_time+"<br>"+"Command:empty!"))
               conn.close()
        except Exception as ex:
            conn.sendall(str.encode("Error:"+str(ex)))
            conn.close()

if __name__ == '__main__':

    classes.ClearLog()
    proc1 = Process(target=funcgetdata)
    proc1.start()

    proc2 = Process(target=listenfordata)
    proc2.start()
