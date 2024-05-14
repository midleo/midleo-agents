
def register_appsrv(name,token,appcode,proj,srvdata):
    
    try:
        out = __salt__['mwagent_extapi.register_mw_appsrv'](token,appcode,proj,srvdata)
    except Exception as e:
        out={"error":str(e)}

    return out