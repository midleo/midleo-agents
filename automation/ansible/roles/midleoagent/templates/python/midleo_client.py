import base64,json,subprocess,socket,os,zlib
from datetime import datetime
from modules.base import decrypt,classes,configs

PORT_NUMBER = 5550
SIZE = 1024
AGENT_VER = "1.24.10"

configs.createConfigJson()

def listenfordata():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
      config_data = configs.getcfgData()
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
        data = conn.recv(10240)
        if not data:
           pass
           conn.close()
        try:
            datamess = data.rstrip()
            datamess = json.loads(datamess)
            data = decrypt.decryptit(datamess["data"],uid)
            data = json.loads(data)
            ftype=(data['ftype'] if 'ftype' in data else "")
            if not data["uid"]==uid:
               pass
               conn.close()
            if 'filename' in data and ftype=='create':
               strf=base64.b64decode(datamess["file"])
               strd=zlib.decompress(strf).decode('utf-8').replace('\r', '')
               try:
                 tf = open(data["filename"], "w")
                 tf.write(strd)
                 tf.close()
                 output=""
               except IOError:
                 output="File write failed:"+data["filename"]
               classes.Err("filename:"+data["filename"])
               conn.sendall(str.encode("Time:"+current_time+"<br>"+"filename:"+data["filename"]+"<br>"+str(output)))
               conn.close()
            if 'filename' in data and ftype=='delete':
               try:
                  os.remove(data["filename"])
                  output="File deleted:"+data["filename"]
               except OSError as e:
                  output="Error"+e.filename+" - "+e.strerror
               classes.Err("filename:"+data["filename"])
               conn.sendall(str.encode("Time:"+current_time+"<br>"+"filename:"+data["filename"]+"<br>"+str(output)))
               conn.close()
            elif 'command' in data:
               data["command"]=base64.b64decode(data["command"]).decode('utf-8')
               try:
                 process = subprocess.Popen(data["command"], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 stdout, stderr = process.communicate()
                 output = stdout.decode('utf-8').strip()
                 conn.sendall(str.encode("Time:"+current_time+"<br>"+"Command:"+data["command"]+"<br>"+"Output:"+str(output)))
               except subprocess.CalledProcessError as e:
                 output=e.output
               classes.Err("Command:"+data["command"])
               conn.close()
            else:
               classes.Err("Command:empty")
               conn.sendall(str.encode("Time:"+current_time+"<br>"+"Command:empty!"))
               conn.close()
        except Exception as ex:
            conn.sendall(str.encode("Error in receive:"+str(ex)))
            conn.close()

if __name__ == '__main__':

    classes.ClearLog()
    listenfordata()
