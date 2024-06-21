import pymqi
from modules.base import classes

def qmConn(thisqm):
    try:
        qmgr = pymqi.connect(thisqm)
    except pymqi.MQMIError as ex:
        classes.Err("Exception:"+str(ex))
        qmgr = None
    return qmgr
def qmDisc(thisqm):
    thisqm.disconnect()

def qStat(thisqm,q,queues):
    try:
        args = []
        args.append(pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME,
                                String=q.encode('utf-8')))
        args.append(pymqi.CFIN(Parameter=pymqi.CMQC.MQIA_Q_TYPE,
                                Value=pymqi.CMQC.MQQT_LOCAL))
        
        filters = []

        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_Q(args, filters)
        for queue_info in response:
            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode('utf-8').strip()
            queues[qname]={}
            queues[qname]["curdepth"] = queue_info[pymqi.CMQC.MQIA_CURRENT_Q_DEPTH]
            queues[qname]["maxdepth"] = queue_info[pymqi.CMQC.MQIA_MAX_Q_DEPTH]
            queues[qname]["percfull"] = depthperc(queue_info)
            queues[qname]["backthres"] = queue_info[pymqi.CMQC.MQIA_BACKOUT_THRESHOLD]
            queues[qname]["trdepth"] = queue_info[pymqi.CMQC.MQIA_TRIGGER_DEPTH]
            queues[qname]["maxmsgl"] = queue_info[pymqi.CMQC.MQIA_MAX_MSG_LENGTH]
            queues[qname]["depthhlim"] = queue_info[pymqi.CMQC.MQIA_Q_DEPTH_HIGH_LIMIT]
            queues[qname]["depthllim"] = queue_info[pymqi.CMQC.MQIA_Q_DEPTH_LOW_LIMIT]
        return queues
    except pymqi.MQMIError as ex:
        classes.Err("Exception:"+str(ex))

def qStatInfo(thisqm,q,queues):
    try:
        args = []
        args.append(pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME,
                                String=q.encode('utf-8')))
        args.append(pymqi.CFIN(Parameter=pymqi.CMQC.MQIA_Q_TYPE,
                                Value=pymqi.CMQC.MQQT_LOCAL))
        args.append(pymqi.CFIN(Parameter=pymqi.CMQCFC.MQIACF_Q_STATUS_ATTRS,
                                Value=pymqi.CMQCFC.MQIACF_ALL))
        filters = []
        filters.append(
            pymqi.CFIF(Parameter=pymqi.CMQC.MQIA_CURRENT_Q_DEPTH,
                       Operator=pymqi.CMQCFC.MQCFOP_GREATER,
                       FilterValue=0))

        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_INQUIRE_Q_STATUS(args, filters)
        for queue_info in response:
            
            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode('utf-8').strip()
            if qname not in queues:
               queues[qname]={}
            queues[qname]["curdepth"] = queue_info[pymqi.CMQC.MQIA_CURRENT_Q_DEPTH]
            queues[qname]["opincount"] = queue_info[pymqi.CMQC.MQIA_OPEN_INPUT_COUNT]
            queues[qname]["opoutcount"] = queue_info[pymqi.CMQC.MQIA_OPEN_OUTPUT_COUNT]
            queues[qname]["uncmess"] = queue_info[pymqi.CMQCFC.MQIACF_UNCOMMITTED_MSGS]
            queues[qname]["oldmessage"] = queue_info[pymqi.CMQCFC.MQIACF_OLDEST_MSG_AGE]
            queues[qname]["lastget"] = queue_info[pymqi.CMQCFC.MQCACF_LAST_GET_DATE].decode('utf-8').strip()+" "+queue_info[pymqi.CMQCFC.MQCACF_LAST_GET_TIME].decode('utf-8').strip()
            queues[qname]["lastput"] = queue_info[pymqi.CMQCFC.MQCACF_LAST_PUT_DATE].decode('utf-8').strip()+" "+queue_info[pymqi.CMQCFC.MQCACF_LAST_PUT_TIME].decode('utf-8').strip()
        
        return queues

    except pymqi.MQMIError as ex:
        classes.Err("Exception:"+str(ex))

def qResStat(thisqm,q,queues):
    try:
        args = []
        args.append(pymqi.CFST(Parameter=pymqi.CMQC.MQCA_Q_NAME,
                                String=q.encode('utf-8')))
        filters = []

        pcf = pymqi.PCFExecute(thisqm, response_wait_interval=5000)
        response = pcf.MQCMD_RESET_Q_STATS(args, filters)
        for queue_info in response:
            qname = queue_info[pymqi.CMQC.MQCA_Q_NAME].decode('utf-8').strip()
            if qname not in queues:
               queues[qname]={}
            queues[qname]["highqdepth"] = queue_info[pymqi.CMQC.MQIA_HIGH_Q_DEPTH]
            queues[qname]["deqcount"] = queue_info[pymqi.CMQC.MQIA_MSG_DEQ_COUNT]
            queues[qname]["enqcount"] = queue_info[pymqi.CMQC.MQIA_MSG_ENQ_COUNT]
            queues[qname]["timereset"] = queue_info[pymqi.CMQC.MQIA_TIME_SINCE_RESET]

        return queues
    except pymqi.MQMIError as ex:
        classes.Err("Exception:"+str(ex))

def getStat(thisqm,q):
    try:
        qmgr = qmConn(thisqm)
        if(qmgr!=None):
            queues={}
            queues=qStat(qmgr,q,queues)
            queues=qStatInfo(qmgr,q,queues)
            queues=qResStat(qmgr,q,queues)
            qmDisc(qmgr)
    except pymqi.MQMIError as ex:
        classes.Err("Exception:"+str(ex))


def depthperc(queue_info):
    if pymqi.CMQC.MQIA_CURRENT_Q_DEPTH not in queue_info or pymqi.CMQC.MQIA_MAX_Q_DEPTH not in queue_info:
        return None
    depthcur = queue_info[pymqi.CMQC.MQIA_CURRENT_Q_DEPTH]
    depthmax = queue_info[pymqi.CMQC.MQIA_MAX_Q_DEPTH]
    depthperc = (depthcur / depthmax) * 100
    return depthperc