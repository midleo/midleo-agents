
import json


def register_appsrv(name,token,appcode,proj,srvdata):
    ret = {"name": name, "changes": {}, "result": False, "comment": ""}

    try:
        out = __salt__['mwagent_extapi.register_mw_appsrv'](token,appcode,proj,srvdata)
        payload = json.loads(out) if isinstance(out, str) else out
        if isinstance(payload, dict) and payload.get("error"):
            ret["comment"] = str(payload["error"])
            return ret

        ret["result"] = True
        ret["changes"] = {"appsrv": srvdata}
        ret["comment"] = "application server registration submitted"
    except Exception as e:
        ret["comment"] = str(e)

    return ret
