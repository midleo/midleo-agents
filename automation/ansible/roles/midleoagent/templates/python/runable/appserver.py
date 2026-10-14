import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.statistics import common
from modules.base import secrets


def execute_encoded(encoded):
    if not isinstance(encoded, str) or len(encoded) > 100000:
        raise ValueError('One encoded application server operation is required')
    request = json.loads(base64.b64decode(encoded, validate=True).decode('utf-8'))
    if not isinstance(request, dict):
        raise ValueError('An application server operation object is required')
    technology = request.get('technology')
    if request.get('action') in ('bundle_resolve', 'bundle_compare', 'bundle_diff', 'bundle_prepare', 'bundle_deploy'):
        request['technology'] = {'wildfly': 'jboss'}.get(technology, technology)
        from modules.statistics import configuration_bundle
        result = configuration_bundle.execute(request)
        if len(json.dumps(result).encode('utf-8')) > 1400000:
            raise ValueError('Agent result exceeds output limit')
        return result
    module = common.statistics_module(technology)
    request['technology'] = {'httpd': 'apache', 'wildfly': 'jboss'}.get(technology, technology)
    action = request.get('action')
    server = str(request.get('server') or '')
    connection = request.get('connection') or {}
    if not server or not isinstance(connection, dict):
        raise ValueError('Application server host and connection settings are required')
    if action == 'check':
        count = common.availability_count(technology, server, connection, windows=os.name == 'nt')
        if count is None:
            raise ValueError('Availability is unsupported for this server type')
        result = {'status': 'running' if count else 'unavailable'}
    elif action == 'httpcheck':
        result = common.http_status(server, connection, str(connection.get('port') or '80'))
        result['status'] = 'running' if common.http_available(result) else 'unavailable'
    elif request['technology'] in ('tomcat', 'jboss') and action in ('inspect', 'read', 'backup_read', 'prepare', 'validate', 'deploy', 'rollback'):
        from modules.statistics import configuration
        result = configuration.execute(request)
    elif action == 'inspect' and callable(getattr(module, 'getInfo', None)):
        result = module.getInfo(server, connection, request)
    elif action in ('inspect', 'read', 'backup_read', 'prepare', 'validate', 'start', 'stop', 'restart', 'reload', 'deploy', 'rollback') and callable(getattr(module, 'execute', None)):
        result = module.execute(request)
    elif action == 'inspect':
        count = common.availability_count(technology, server, connection, windows=os.name == 'nt')
        if count is None:
            raise ValueError('Server inspection is unsupported for this server type')
        result = {'status': 'running' if count else 'unavailable'}
    else:
        raise ValueError('Unsupported application server operation')
    result.setdefault('success', True)
    if len(json.dumps(result).encode('utf-8')) > 450000:
        raise ValueError('Agent result exceeds output limit')
    return result


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError('One encoded application server operation is required')
        result = execute_encoded(sys.argv[1])
    except Exception as error:
        print(json.dumps({'success': False, 'status': 'failed', 'errorlog': secrets.redact_text(str(error))[:4096]}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
