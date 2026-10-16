import copy
import hashlib
import json
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from modules.base import configs
from modules.statistics.apache.operations import instance_lock, read_bytes, relative, trusted, write_json

TECHNOLOGIES = frozenset(('tomcat', 'jboss', 'weblogic', 'ibmwas', 'liberty'))
MAX_FILES = 2000
MAX_POLICY_BYTES = 524288


def configuration_defaults(technology, configuration=None, allow_disabled=False):
    technology = {'wildfly': 'jboss'}.get(technology, technology)
    if technology not in TECHNOLOGIES:
        raise ValueError('Use a supported server type')
    configuration = configs.getcfgData() if configuration is None else configuration
    prefix = technology.upper()
    enabled = str(configuration.get(prefix + '_CONFIG_ENABLED', '')).lower()
    if not enabled:
        return None
    if enabled not in ('y', 'yes', 'true', '1', 'n', 'no', 'false', '0'):
        raise ValueError(prefix + '_CONFIG_ENABLED must be y or n')
    if enabled in ('n', 'no', 'false', '0'):
        if allow_disabled:
            return {'enabled': False}
        raise ValueError('Configuration deployment is disabled by ' + prefix + '_CONFIG_ENABLED')
    user = configuration.get(prefix + '_USER', '').strip()
    root = configuration_directory(configuration.get(prefix + '_CONFIG_DIR', ''))
    folders = folder_names([item.strip() for item in configuration.get(prefix + '_CONFIG_FOLDERS', '').split(',') if item.strip()])
    for folder in folders:
        configuration_directory(str(root / folder))
    if user and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}\$?', user):
        raise ValueError('Invalid ' + prefix + '_USER')
    return {'config_root': str(root), 'folders': folders,
            'configuration_directory': technology == 'tomcat', 'enabled': True}


def configured_policy(home, request):
    options = configuration_defaults(request.get('technology'))
    if options is None:
        return None
    instance = identity(request.get('policy_instance') or request.get('instance'))
    home = directory(str(Path(home).resolve()))
    root = Path(options['config_root'])
    if root == home or root in home.parents or home in root.parents:
        raise ValueError('Configuration and agent installation directories must be separate')
    runtime = home / 'runtime' / 'configuration'
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    trusted(runtime, private=True)
    policy = {}
    try:
        from modules.statistics.configuration import load_policy
        policy = load_policy(home / 'config' / 'configuration-policy.json', dict(request, instance=instance))
    except (FileNotFoundError, KeyError):
        pass
    if policy.get('technology', request['technology']) != request['technology']:
        raise ValueError('Configuration policy belongs to another server type')
    automatic_files = not policy or policy.get('managed_files') is True
    policy = copy.deepcopy(policy)
    policy.update(options, technology=request['technology'])
    if automatic_files:
        policy.update(allowed_files=[], allow_new_files=True, allow_existing_files=True, managed_files=True)
    policy['configuration_defaults_hash'] = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
    for key, name in (('staging_root', 'staging'), ('backup_root', 'backups')):
        target = runtime / name
        target.mkdir(mode=0o700, exist_ok=True)
        trusted(target, private=True)
        policy[key] = str(target)
    command = policy.get('validation_command', [])
    if not command or (len(command) > 2 and command[1] == str(home / 'runable' / 'configurationpolicy.py') and command[2] == 'validate'):
        policy['validation_command'] = ['@MIDLEO_CONFIGURATION_VALIDATE@']
    return policy


def set_configuration(home, technology, root=None, user='', folders=''):
    technology = {'wildfly': 'jboss'}.get(technology, technology)
    if technology not in TECHNOLOGIES:
        raise ValueError('Use a supported server type')
    prefix = technology.upper()
    values = {prefix + '_CONFIG_ENABLED': 'n'}
    if root is not None:
        if not re.fullmatch(r'[A-Za-z0-9_./:\\-]+', root):
            raise ValueError('Use an absolute configuration directory without shell characters')
        values.update({prefix + '_CONFIG_ENABLED': 'y', prefix + '_CONFIG_DIR': root.rstrip('/\\'),
                       prefix + '_CONFIG_FOLDERS': folders, prefix + '_USER': user})
        configuration_defaults(technology, values)
    config = directory(str(Path(home).resolve())) / 'config'
    trusted(config)
    path = config / 'mwagent.config'
    trusted(path)
    with instance_lock(config / 'configuration-policy.lock'):
        text = path.read_text(encoding='utf-8')
        newline = '\r\n' if '\r\n' in text else '\n'
        lines = []
        remaining = dict(values)
        for line in text.splitlines():
            key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
            if key in values:
                if key in remaining:
                    lines.append(key + '=' + remaining.pop(key))
            else:
                lines.append(line)
        lines.extend(key + '=' + value for key, value in remaining.items())
        import tempfile
        descriptor, temporary = tempfile.mkstemp(prefix='.mwagent-', dir=str(config))
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
                stream.write(newline.join(lines) + newline)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode) & 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'success': True, 'technology': technology, 'enabled': root is not None,
            'configuration_root': values.get(prefix + '_CONFIG_DIR', ''), 'user': user}


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', value):
        raise ValueError('Invalid configuration policy identity')
    return value


def folder_names(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError('Configuration folders must be an array of at most 100 names')
    result = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value) or value in ('.', '..'):
            raise ValueError('Use folder names directly beneath the configuration root')
        if value.casefold() in seen:
            raise ValueError('Duplicate configuration folder name')
        seen.add(value.casefold())
        result.append(value)
    return result


def directory(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('An absolute configuration directory is required')
    path = Path(value)
    if not path.is_absolute() or not path.is_dir() or path.resolve() != path or path == Path(path.anchor):
        raise ValueError('Use an existing absolute configuration directory without symlinks')
    return path


def configuration_directory(value):
    return directory(value)


def inventory(root):
    files = []
    directories = 0
    for current, children, names in os.walk(root, followlinks=False):
        directories += 1
        if directories > 512 or len(Path(current).relative_to(root).parts) > 16:
            raise ValueError('Configuration directory contains too many subdirectories')
        children[:] = sorted(name for name in children if not (Path(current) / name).is_symlink())
        for name in sorted(names):
            path = Path(current) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
                continue
            try:
                item = relative(path.relative_to(root).as_posix())
            except ValueError:
                continue
            files.append(item)
            if len(files) > MAX_FILES:
                raise ValueError('Configuration directory contains too many files')
    return sorted(files)


def update_policy(home, instance, technology, options):
    instance = identity(instance)
    technology = {'wildfly': 'jboss'}.get(technology, technology)
    if technology not in TECHNOLOGIES or not isinstance(options, dict):
        raise ValueError('Use a supported server type and a configuration JSON object')
    allowed = {'config_root', 'folders', 'configuration_directory', 'allowed_files', 'allow_new_files', 'validation_command', 'enabled'}
    if set(options) - allowed:
        raise ValueError('Unsupported configuration policy setting')
    if 'enabled' in options and not isinstance(options['enabled'], bool):
        raise ValueError('enabled must be a boolean')
    home = directory(str(Path(home).resolve()))
    config = home / 'config'
    config.mkdir(mode=0o750, exist_ok=True)
    trusted(config)
    path = config / 'configuration-policy.json'
    with instance_lock(config / 'configuration-policy.lock'):
        policies = {}
        if path.exists():
            trusted(path)
            policies = json.loads(read_bytes(path).decode('utf-8'))
            if not isinstance(policies, dict):
                raise ValueError('Existing configuration policy must be a JSON object')
        previous = policies.get(instance, {})
        if not isinstance(previous, dict):
            raise ValueError('Existing server configuration policy is invalid')
        if previous.get('technology', technology) != technology:
            raise ValueError('Configuration policy belongs to another server type')
        policy = copy.deepcopy(previous)
        if options.get('enabled') is False:
            if not previous:
                return {'success': True, 'instance': instance, 'status': 'not_configured'}
            policy['enabled'] = False
        else:
            root = directory(options.get('config_root', policy.get('config_root', '')))
            if root == home or root in home.parents or home in root.parents:
                raise ValueError('Configuration and agent installation directories must be separate')
            folders = folder_names(options.get('folders', policy.get('folders', [])))
            if not folders and technology == 'tomcat' and options.get('configuration_directory', policy.get('configuration_directory')) is not True and (root / 'conf').is_dir():
                folders = ['conf']
            for folder in folders:
                directory(str(root / folder))
            policy.update(technology=technology, config_root=str(root), folders=folders, enabled=True)
            if 'configuration_directory' in options:
                if not isinstance(options['configuration_directory'], bool):
                    raise ValueError('configuration_directory must be a boolean')
                policy['configuration_directory'] = options['configuration_directory']
            policy.setdefault('configuration_directory', technology == 'tomcat' and root.name.lower() in ('conf', 'config'))
            runtime = home / 'runtime' / 'configuration'
            runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
            trusted(runtime, private=True)
            for key, name in (('staging_root', 'staging'), ('backup_root', 'backups')):
                target = Path(policy.get(key, str(runtime / name)))
                target.mkdir(mode=0o700, exist_ok=True)
                target = directory(str(target))
                trusted(target, private=True)
                if target == root or target in root.parents or root in target.parents:
                    raise ValueError('Configuration, staging and backup directories must be separate')
                policy[key] = str(target)
            if 'allowed_files' in options:
                if not isinstance(options['allowed_files'], list) or len(options['allowed_files']) > MAX_FILES:
                    raise ValueError('allowed_files must be a bounded array of relative paths')
                policy['allowed_files'] = sorted(set(relative(name) for name in options['allowed_files']))
                policy['managed_files'] = False
            elif 'allowed_files' not in policy or policy.get('managed_files') is True:
                policy['allowed_files'] = inventory(root)
                policy['managed_files'] = True
            if 'allow_new_files' in options:
                if not isinstance(options['allow_new_files'], bool):
                    raise ValueError('allow_new_files must be a boolean')
                policy['allow_new_files'] = options['allow_new_files']
            else:
                policy.setdefault('allow_new_files', policy.get('managed_files') is True)
            if 'validation_command' in options:
                command = options['validation_command']
                if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part or '\0' in part for part in command) or not Path(command[0]).is_absolute():
                    raise ValueError('validation_command must be an absolute executable argument list')
                policy['validation_command'] = command
            else:
                policy.setdefault('validation_command', [str(Path(sys.executable).resolve()), str(home / 'runable' / 'configurationpolicy.py'), 'validate', instance, '@CONFIGURATION_ROOT@'])
        policies[instance] = policy
        if len(json.dumps(policies).encode('utf-8')) > MAX_POLICY_BYTES:
            raise ValueError('Configuration policy exceeds the supported size')
        write_json(path, policies)
        return {'success': True, 'instance': instance, 'status': 'updated' if previous else 'configured',
                'configuration_root': policy.get('config_root', ''), 'folders': policy.get('folders', []),
                'enabled': policy.get('enabled', True), 'allowed_files': len(policy.get('allowed_files', []))}


def delete_policy(home, instance, technology):
    instance = identity(instance)
    technology = {'wildfly': 'jboss'}.get(technology, technology)
    if technology not in TECHNOLOGIES:
        raise ValueError('Use a supported server type')
    config = directory(str(Path(home).resolve())) / 'config'
    result = {'success': True, 'instance': instance, 'status': 'not_configured'}
    if not config.exists():
        return result
    trusted(config)
    path = config / 'configuration-policy.json'
    with instance_lock(config / 'configuration-policy.lock'):
        if not path.exists():
            return result
        trusted(path)
        policies = json.loads(read_bytes(path).decode('utf-8'))
        if not isinstance(policies, dict):
            raise ValueError('Existing configuration policy must be a JSON object')
        if instance not in policies:
            return result
        policy = policies[instance]
        if not isinstance(policy, dict) or policy.get('technology') != technology:
            raise ValueError('Configuration policy belongs to another server type')
        del policies[instance]
        write_json(path, policies)
    return dict(result, status='deleted')


def select_policy(policy, request):
    if policy.get('enabled') is False:
        raise ValueError('Configuration deployment is disabled for this server')
    policy = copy.deepcopy(policy)
    policy.pop('configuration_user', None)
    name = request.get('bundle_name')
    if not name:
        return policy
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\.zip(?:\.bundle)?', name, re.I):
        raise ValueError('Use a ZIP named after the configuration folder or domain')
    folder = re.sub(r'\.zip(?:\.bundle)?$', '', name, flags=re.I)
    root = configuration_directory(policy['config_root'])
    folders = folder_names(policy.get('folders', []))
    if folder == root.name and not folders:
        selected = root
    elif folder in folders:
        protected = {'weblogic': ('bin', 'config', 'security', 'servers'), 'ibmwas': ('cells', 'nodes')}
        if folder.lower() in protected.get(policy['technology'], ()):
            raise ValueError('Protected management directories cannot be selected as configuration roots')
        selected = configuration_directory(str(root / folder))
        if policy['technology'] == 'tomcat' and policy.get('configuration_directory') is not True and folder != 'conf':
            raise ValueError('Native Tomcat bundles must target its conf directory')
        policy['allowed_files'] = [item[len(folder) + 1:] for item in policy.get('allowed_files', []) if item.startswith(folder + '/')]
        if policy['technology'] == 'tomcat':
            policy['configuration_directory'] = True
    else:
        raise ValueError('ZIP filename must match the configured folder or domain: ' + ', '.join(folders or [root.name]))
    policy['configuration_base'] = str(root)
    policy['configuration_folder'] = folder
    policy['config_root'] = str(selected)
    return policy


def validate_policy(home, instance, root):
    from modules.statistics.configuration import load_policy
    policy = load_policy(Path(home) / 'config' / 'configuration-policy.json', {'instance': identity(instance)})
    root = directory(root)
    base = directory(policy['config_root'])
    if root != base and (root.parent != base or root.name not in folder_names(policy.get('folders', []))):
        raise ValueError('Validation directory is outside the configured folders')
    validate_directory(root)
    return {'success': True, 'instance': instance, 'status': 'validated'}


def validate_directory(root):
    root = directory(str(root))
    for name in inventory(root):
        if not name.endswith(('.xml', '.properties')) and Path(name).name not in ('jvm.options', 'server.env'):
            continue
        path = root / name
        data = read_bytes(path)
        if len(data) > 524288 or b'\0' in data:
            raise ValueError('Invalid bounded configuration file: ' + name)
        text = data.decode('utf-8')
        if re.search(r'<!DOCTYPE|<!ENTITY', text, re.I):
            raise ValueError('Unsupported XML declarations: ' + name)
        if name.endswith('.xml'):
            try:
                ET.fromstring(text)
            except ET.ParseError:
                raise ValueError('Invalid XML configuration: ' + name)
