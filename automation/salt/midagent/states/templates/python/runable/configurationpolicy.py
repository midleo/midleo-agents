import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.base import secrets
from modules.statistics.configuration_policy import configuration_defaults, delete_policy, set_configuration, update_policy, validate_policy


def execute(arguments):
    home = Path(os.getcwd()).resolve()
    if 3 <= len(arguments) <= 5 and arguments[0] == 'set':
        return set_configuration(home, arguments[1], arguments[2], arguments[3] if len(arguments) > 3 else '', arguments[4] if len(arguments) > 4 else '')
    if len(arguments) == 2 and arguments[0] == 'disable':
        return set_configuration(home, arguments[1])
    if len(arguments) == 4 and arguments[0] == 'add':
        return update_policy(home, arguments[2], arguments[1], json.loads(arguments[3]))
    if len(arguments) == 3 and arguments[0] == 'delete':
        return delete_policy(home, arguments[2], arguments[1])
    if len(arguments) == 3 and arguments[0] == 'validate':
        return validate_policy(home, arguments[1], arguments[2])
    if len(arguments) == 2 and arguments[0] == 'encoded':
        if len(arguments[1]) > 32768:
            raise ValueError('Configuration settings exceed the size limit')
        payload = json.loads(base64.b64decode(arguments[1], validate=True).decode('utf-8'))
        if not isinstance(payload, dict) or set(payload) != {'instance', 'technology', 'settings'}:
            raise ValueError('Invalid configuration policy request')
        if not isinstance(payload['settings'], dict) or set(payload['settings']) - {'config_root', 'folders', 'configuration_directory', 'enabled'}:
            raise ValueError('Unsupported remote configuration setting')
        defaults = configuration_defaults(payload['technology'], allow_disabled=True)
        if defaults is not None:
            if not defaults['enabled']:
                return {'success': True, 'status': 'disabled'}
            return {'success': True, 'status': 'agent_defaults', 'configuration_root': defaults['config_root'], 'folders': defaults['folders']}
        return update_policy(home, payload['instance'], payload['technology'], payload['settings'])
    raise ValueError('Use add SRV_TYPE APPSRVID JSON, delete SRV_TYPE APPSRVID or encoded ENCODED_SETTINGS')


if __name__ == '__main__':
    try:
        print(json.dumps(execute(sys.argv[1:])))
    except Exception as error:
        print(json.dumps({'success': False, 'errorlog': secrets.redact_text(str(error))[:1024]}))
        sys.exit(1)
