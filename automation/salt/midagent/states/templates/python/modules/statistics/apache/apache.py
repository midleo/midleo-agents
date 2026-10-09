import os

from modules.base import classes
from modules.statistics import common


CONNECTION_FIELDS = {key: '' for key in ('usr', 'pwd', 'mngmport', 'jmxport', 'port', 'webport', 'host', 'ssl', 'sslverify', 'ssl_verify', 'conntype')}
STATUS_METRICS = {'BusyWorkers': 'BusyWorkers', 'IdleWorkers': 'IdleWorkers', 'TotalAccesses': 'Total Accesses',
                  'TotalKBytes': 'Total kBytes', 'Uptime': 'Uptime', 'ReqPerSec': 'ReqPerSec', 'BytesPerSec': 'BytesPerSec', 'CPULoad': 'CPULoad'}


def restAvailabilityCheck(thisnode, values):
    port = '443' if common.truthy(values.get('ssl')) else '80'
    return int(common.http_available(common.http_status(thisnode, values, port)))


def getStat(thisnode, inpdata):
    try:
        values, metrics = common.pop_fields(common.parse_json_object(inpdata), CONNECTION_FIELDS)
        _, metrics = common.split_optadvisor_config(metrics)
        port = '443' if common.truthy(values.get('ssl')) else '80'
        result = common.http_status(thisnode, values, port)
        counts = {'HTTPStatus': result['http_status'], 'ResponseTime': result['response_time_ms'], 'Availability': int(common.http_available(result))}
        if STATUS_METRICS.keys() & metrics.keys():
            base, _ = common.rest_base_url(thisnode, values, port)
            status = common.http_status(thisnode, values, port, url=base + '/server-status?auto', include_body=True)
            if status['http_status'] == 200:
                fields = dict(line.split(':', 1) for line in status.get('body', '').splitlines() if ':' in line)
                counts.update({key: number for key, field in STATUS_METRICS.items() if (number := common.numeric_value(fields.get(field))) is not None})
            else:
                classes.Err('Apache server-status metrics require mod_status and access for this agent (HTTP ' + str(status['http_status']) + ')')
        for subtype, logdir in metrics.items():
            if subtype in counts:
                common.write_simple_stat(logdir, subtype, thisnode, subtype, counts[subtype])
    except Exception as error:
        classes.Err('Apache statistics failed:' + str(error))


def resetStat(thisnode, website, webssl, legacy_token, stat_data):
    _, metrics = common.split_optadvisor_config(stat_data if isinstance(stat_data, dict) else {})
    common.post_csv_stats('apache', 'apache', website, webssl, legacy_token, metrics, lambda logdir, subtype: os.path.join(logdir, 'Statistics_' + subtype + '.csv'))




def operations(request):
    from modules.statistics.apache.operations import ApacheOperations, discover_instance
    return ApacheOperations(discover_instance(request))


def getInfo(thisnode, values, request):
    return operations(request).execute(request)


def execute(request):
    return operations(request).execute(request)
