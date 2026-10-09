import copy
import hashlib
import json
import os
import platform
import re
import shutil
import psutil
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from modules.statistics import common


MAX_FILE = 512 * 1024
ACTIONS = frozenset(('inspect', 'read', 'backup_read', 'prepare', 'validate', 'start', 'stop', 'restart', 'reload', 'deploy', 'rollback'))


def required(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing ' + key)
    return value


def relative(value):
    if not isinstance(value, str) or len(value) > 220 or not re.fullmatch(r'[A-Za-z0-9_./-]+', value):
        raise ValueError('Invalid configuration path')
    if any(part in ('', '.', '..') for part in value.split('/')):
        raise ValueError('Unsafe configuration path')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def redact(text):
    text = re.sub(r'(?im)^.*(?:password|passwd|secret|token|credential|authorization|PRIVATE KEY).*$', '[redacted]', str(text))
    return re.sub(r'(://[^\s/:]+):[^\s@]+@', r'\1:[redacted]@', text)


def safe(text):
    return redact(text)[:4096]


def validate_content(text, baseline=''):
    pattern = r'(?im)^\s*(?:(?:LoadModule|LoadFile|Lua\w*|Perl\w*|Action|ScriptAlias)\b|(?:ErrorLog|CustomLog|TransferLog)\s+"?\|)[^\r\n]*'
    approved = [match.group().strip() for match in re.finditer(pattern, baseline)]
    for match in re.finditer(pattern, text):
        directive = match.group().strip()
        if directive not in approved:
            raise ValueError('Configuration contains unapproved executable directives')
        approved.remove(directive)
    if '\0' in text:
        raise ValueError('Configuration contains unapproved executable directives')
    if re.search(r'(?i)(password|passwd|secret|token|authorization)\s*[:=]|-----BEGIN .*PRIVATE KEY-----|://[^\s/]+:[^\s@]+@', text):
        raise ValueError('Use existing secret files; inline secrets are not permitted')


def trusted(path, private=False):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Trusted paths cannot be symlinks')
    details = path.stat()
    if os.name != 'nt':
        if details.st_uid not in (0, os.geteuid()) or details.st_mode & 0o022:
            raise ValueError('Policy and runtime paths must be owned by root or the agent account without group/world write access')
        if private and details.st_mode & 0o077:
            raise ValueError('Staging and backup directories must be private to the agent account')


def read_bytes(path):
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('A regular configuration file is required')
        data = stream.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError('Configuration file exceeds size limit')
    return data


def sync_directory(path):
    if os.name != 'nt':
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def write_json(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix='.journal-', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, sort_keys=True, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, str(path))
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def instance_lock(path):
    descriptor = os.open(str(path), os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b'0')
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(descriptor)
        raise ValueError('Another Apache operation is running')
    try:
        yield
    finally:
        os.close(descriptor)


class ApacheOperations:
    technology = 'apache'
    binary_key = 'apachectl'
    binary_names = ('apachectl', 'apache2ctl', 'httpd', 'apache2', 'httpd.exe')
    extensions = ('.conf',)

    def __init__(self, policy, runner=None, health_probe=None):
        self.policy = copy.deepcopy(policy)
        self.runner = runner
        self.health_probe = health_probe
        self.steps = []
        if policy.get('technology', 'apache') != self.technology:
            raise ValueError('Configuration policy technology mismatch')
        self.root = self.directory('config_root')
        staging = self.directory('staging_root', private=True)
        backups = self.directory('backup_root', private=True)
        for first, second in ((self.root, staging), (self.root, backups), (staging, backups)):
            if first == second or first in second.parents or second in first.parents:
                raise ValueError('Configuration, staging and backup roots must be separate')
        namespace = digest(str(self.root).encode('utf-8'))
        self.stage = staging / namespace
        self.backups = backups / namespace
        for path in (self.stage, self.backups):
            path.mkdir(mode=0o700, exist_ok=True)
            trusted(path, private=True)
        self.binary = Path(required(policy, self.binary_key))
        if not self.binary.is_absolute():
            raise ValueError('An absolute Apache executable is required')
        self.binary = self.binary.resolve(strict=True)
        if self.binary.name not in self.binary_names or not os.access(str(self.binary), os.X_OK):
            raise ValueError('An approved service executable is required')
        files = policy.get('allowed_files')
        if not isinstance(files, list) or not files:
            raise ValueError('No approved configuration files')
        self.allowed = {relative(name) for name in files}
        self.main = self.target(self.approved(required(policy, 'main_config')))
        self.server_root = Path(policy.get('server_root') or str(self.root))
        if not self.server_root.is_absolute():
            raise ValueError('An absolute Apache server root is required')
        self.server_root = self.server_root.resolve(strict=True)
        health_url = urlsplit(required(policy, 'health_url'))
        if health_url.scheme not in ('http', 'https') or not health_url.hostname or health_url.username or health_url.password:
            raise ValueError('Invalid configured health URL')
        self.expected_status = int(policy['health_status']) if 'health_status' in policy else None
        if self.expected_status is not None and not 100 <= self.expected_status <= 599:
            raise ValueError('Invalid expected HTTP status')

    def directory(self, name, private=False):
        path = Path(required(self.policy, name))
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ValueError('Absolute approved directories are required')
        resolved = path.resolve(strict=True)
        if path != resolved:
            raise ValueError('Approved directories cannot contain symlinks')
        if private:
            trusted(resolved, private=True)
        return resolved

    def approved(self, name):
        name = relative(name)
        name = self.policy.get('file_targets', {}).get(name, name)
        if not name.endswith(self.extensions) or (name not in self.allowed and not self.policy.get('auto_discovered')):
            raise ValueError('Configuration file is not approved')
        if not self.target(name).parent.is_dir():
            raise ValueError('Configuration parent folder does not exist')
        return name

    def target(self, name):
        path = self.root / relative(name)
        for item in (path,) + tuple(path.parents):
            if item == self.root:
                break
            if item.is_symlink() and item != path:
                raise ValueError('Configuration targets cannot be symlinks')
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if self.root not in resolved.parents or not resolved.is_file():
                raise ValueError('Configuration link escapes the instance root')
            return resolved
        return path

    def deployment_directory(self, base, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,50}', identifier):
            raise ValueError('Invalid deployment identifier')
        path = base / identifier
        if path.is_symlink():
            raise ValueError('Invalid deployment directory')
        return path

    def tree_files(self):
        entries = sorted(self.root.rglob('*'))
        for entry in entries:
            if entry.is_symlink():
                if entry.name.endswith(self.extensions) and (self.root not in entry.resolve(strict=True).parents or not entry.is_file()):
                    raise ValueError('Configuration link escapes the instance root')
            elif not (entry.is_file() or entry.is_dir()):
                raise ValueError('Configuration tree contains a special file')
        return entries

    def fingerprint(self):
        fingerprint = hashlib.sha256()
        for path in [self.root] + self.tree_files():
            details = path.lstat()
            fingerprint.update(str(path.relative_to(self.root)).encode('utf-8') + b'\0')
            fingerprint.update(('%s:%s:%s' % (details.st_uid, details.st_gid, details.st_mode)).encode('ascii') + b'\0')
            if path.is_symlink():
                fingerprint.update(os.readlink(str(path)).encode('utf-8'))
            elif path.is_file():
                fingerprint.update(read_bytes(path))
        return fingerprint.hexdigest()

    def policy_hash(self):
        return digest(json.dumps(self.policy, sort_keys=True, separators=(',', ':')).encode('utf-8'))

    def step(self, name, status, output):
        self.steps.append({'name': name, 'status': status, 'output': safe(output), 'at': datetime.now(timezone.utc).isoformat()})

    def command(self, command, timeout=45):
        if self.runner is not None:
            return self.runner(list(command))
        with tempfile.TemporaryFile() as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=timeout, shell=False)
            output.seek(0)
            text = output.read(4097).decode('utf-8', errors='replace')
        if completed.returncode:
            raise RuntimeError(safe(text) or 'Apache command failed')
        return text[:4096]

    def run(self, arguments, name):
        try:
            text = self.command([str(self.binary)] + arguments)
        except Exception as error:
            self.step(name, 'failed', error)
            raise
        self.step(name, 'completed', text)
        return safe(text)

    def config_args(self, main, flags):
        return ['-d', str(self.server_root), '-f', str(main)] + flags

    def validate(self, tree, name):
        main = tree / self.main.relative_to(self.root)
        if not main.is_file():
            raise ValueError('Main configuration is missing')
        self.run(self.config_args(main, ['-t']), name)

    def control(self, action):
        if action not in ('start', 'stop', 'restart', 'reload'):
            raise ValueError('Unsupported Apache control action')
        self.run(self.config_args(self.main, ['-k', 'graceful' if action == 'reload' else action]), action)

    def health(self):
        if self.health_probe is not None:
            return bool(self.health_probe())
        for attempt in range(4):
            result = common.http_status('', url=self.policy['health_url'])
            if common.http_available(result, self.expected_status):
                return True
            if attempt < 3:
                time.sleep(1)
        self.step('health_verification', 'failed', 'Configured HTTP health check failed')
        return False

    def read_configuration(self, request):
        name = self.approved(required(request, 'file'))
        path = self.target(name)
        exists = path.exists()
        if request['action'] == 'backup_read':
            previous = self.deployment_directory(self.backups, required(request, 'restore_id'))
            journal = json.loads(read_bytes(previous / 'journal.json').decode('utf-8'))
            if journal.get('configuration_root') != str(self.root):
                raise ValueError('Backup belongs to another instance')
            entry = next((item for item in journal['files'] if item['target'] == name), None)
            if entry is None:
                raise ValueError('File is absent from deployment backup')
            exists = entry['existed']
            path = previous / name
            if exists and digest(read_bytes(path)) != entry['backup_sha256']:
                raise ValueError('Backup checksum mismatch')
        data = read_bytes(path) if exists else b''
        if len(data) > 131072:
            raise ValueError('Configuration preview exceeds size limit')
        return {'exists': exists, 'size': len(data), 'sha256': digest(data), 'content': redact(data.decode('utf-8'))}

    def inspect(self):
        ports = set()
        for path in self.tree_files():
            if path.is_file() and path.name.endswith('.conf'):
                ports.update(re.findall(r'(?im)^\s*Listen\s+(?:\[[^\]\r\n]+\]:|[^\s:]+:)?([0-9]+)(?:\s|$)', read_bytes(path.resolve()).decode('utf-8')))
        return {'version': self.run(['-v'], 'version'), 'virtualhosts': self.run(self.config_args(self.main, ['-S']), 'virtualhosts'),
                'modules': self.run(self.config_args(self.main, ['-M']), 'modules'), 'runtime': self.run(self.config_args(self.main, ['-t', '-D', 'DUMP_RUN_CFG']), 'runtime'),
                'configuration_directory': str(self.root), 'executable': str(self.binary), 'service': self.policy.get('service', ''), 'os': platform.system(),
                'status': 'running' if self.health() else 'unavailable', 'ports': sorted(ports),
                'files': sorted(self.allowed), 'file_targets': self.policy.get('file_targets', {}), 'main_config_file': str(self.main.relative_to(self.root)),
                'fingerprint': self.fingerprint(), 'policy_hash': self.policy_hash()}

    def rewrite_includes(self, tree):
        pattern = re.compile(r'(?im)^(\s*)(IncludeOptional|Include|ServerRoot)\s+"?([^"\r\n]+?)"?\s*$')
        def replace(match):
            name = match.group(3).strip()
            if '$' in name or '\\' in name or '..' in name.split('/'):
                raise ValueError('Dynamic or unsafe includes require explicit configuration')
            path = Path(name)
            if not path.is_absolute():
                path = self.server_root / path
            if match.group(2).lower() == 'serverroot':
                if path != self.server_root:
                    raise ValueError('ServerRoot must match the instance policy')
            else:
                try:
                    path = tree / path.relative_to(self.root)
                except ValueError:
                    raise ValueError('Includes must stay in the approved configuration tree')
            return match.group(1) + match.group(2) + ' "' + path.as_posix() + '"'
        paths = {path.resolve() for path in tree.rglob('*.conf') if path.is_file()}
        for path in sorted(paths):
            if tree not in path.parents:
                raise ValueError('Staged configuration escapes validation root')
            path.write_text(pattern.sub(replace, read_bytes(path).decode('utf-8')), encoding='utf-8')

    def validate_content(self, name, text, baseline=None):
        target = self.target(name)
        if baseline is None:
            baseline = read_bytes(target).decode('utf-8') if target.exists() else ''
        validate_content(text, baseline)

    def install(self, source, destination, original):
        if not destination.parent.is_dir():
            raise ValueError('Target parent must already exist')
        descriptor, temporary = tempfile.mkstemp(prefix='.midleo-', dir=str(destination.parent))
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(read_bytes(source))
                stream.flush()
                os.fsync(stream.fileno())
            if original.exists():
                attributes = original.stat()
                if os.name != 'nt':
                    current = os.stat(temporary)
                    if (current.st_uid, current.st_gid) != (attributes.st_uid, attributes.st_gid):
                        os.chown(temporary, attributes.st_uid, attributes.st_gid)
                os.chmod(temporary, stat.S_IMODE(attributes.st_mode))
            else:
                os.chmod(temporary, 0o640)
                if os.name != 'nt' and (self.policy.get('owner') or self.policy.get('group')):
                    import pwd
                    import grp
                    owner = pwd.getpwnam(self.policy['owner']).pw_uid if self.policy.get('owner') else -1
                    group = grp.getgrnam(self.policy['group']).gr_gid if self.policy.get('group') else -1
                    os.chown(temporary, owner, group)
            os.replace(temporary, str(destination))
            sync_directory(destination.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def restore(self, backup, changes):
        for change in changes:
            destination = self.target(self.approved(change['target']))
            if change['existed']:
                source = backup / change['target']
                if digest(read_bytes(source)) != change['backup_sha256']:
                    raise ValueError('Backup checksum mismatch')
                self.install(source, destination, source)
            elif destination.exists():
                destination.unlink()
                sync_directory(destination.parent)
        self.validate(self.root, 'rollback_validation')
        self.control('reload')
        if not self.health():
            raise RuntimeError('Rollback health verification failed')
        self.step('rollback', 'completed', 'Previous configuration restored and verified')

    def recover_pending(self):
        for backup in sorted(self.backups.iterdir()):
            if not backup.is_dir() or backup.is_symlink() or not (backup / 'journal.json').exists():
                continue
            journal_path = backup / 'journal.json'
            journal = json.loads(read_bytes(journal_path).decode('utf-8'))
            if journal.get('configuration_root') != str(self.root):
                raise ValueError('Deployment journal belongs to another instance')
            if 'result' not in journal or journal['result'].get('rollback_status') == 'failed':
                self.restore(backup, journal['files'])
                journal['result'] = {'success': False, 'status': 'failed', 'rollback_status': 'completed', 'errorlog': 'Interrupted deployment recovered; review before retry'}
                write_json(journal_path, journal)

    def deploy(self, request):
        backup = self.deployment_directory(self.backups, required(request, 'deployment_id'))
        journal_path = backup / 'journal.json'
        self.recover_pending()
        if journal_path.exists():
            journal = json.loads(read_bytes(journal_path).decode('utf-8'))
            if journal['payload_hash'] != required(request, 'payload_hash'):
                raise ValueError('Deployment identifier was reused')
            return journal['result']
        raw_changes = request.get('files')
        if not isinstance(raw_changes, list) or not 1 <= len(raw_changes) <= 40 or any(not isinstance(item, dict) for item in raw_changes):
            raise ValueError('Select 1 to 40 configuration files')
        changes = [{key: required(item, key) for key in ('target', 'sha256', 'staged')} for item in raw_changes]
        if required(request, 'fingerprint') != self.fingerprint() or required(request, 'policy_hash') != self.policy_hash():
            raise ValueError('Active configuration or policy changed since review')
        incoming = self.deployment_directory(self.stage, request['deployment_id'])
        proposed = incoming / 'effective'
        if proposed.exists() or proposed.is_symlink():
            raise ValueError('Staged validation directory already exists')
        self.tree_files()
        backup.mkdir(mode=0o700)
        incoming.mkdir(mode=0o700, exist_ok=True)
        trusted(incoming, private=True)
        shutil.copytree(str(self.root), str(proposed), symlinks=True)
        for link in sorted(proposed.rglob('*')):
            if link.is_symlink():
                original = self.root / link.relative_to(proposed)
                resolved = original.resolve()
                if self.root in resolved.parents and original.is_file():
                    destination = proposed / resolved.relative_to(self.root)
                    link.unlink()
                    link.symlink_to(os.path.relpath(str(destination), str(link.parent)))
        names = set()
        for change in changes:
            name = self.approved(required(change, 'target'))
            if name in names:
                raise ValueError('Duplicate configuration target')
            names.add(name)
            current = self.target(name)
            saved = backup / name
            saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            change['existed'] = current.exists()
            if change['existed']:
                with saved.open('wb') as stream:
                    stream.write(read_bytes(current))
                    stream.flush()
                    os.fsync(stream.fileno())
                shutil.copystat(str(current), str(saved))
                sync_directory(saved.parent)
            change['backup_sha256'] = digest(read_bytes(saved)) if saved.exists() else ''
            if request['action'] == 'rollback':
                previous = self.deployment_directory(self.backups, required(request, 'restore_id'))
                journal = json.loads(read_bytes(previous / 'journal.json').decode('utf-8'))
                if journal.get('configuration_root') != str(self.root) or journal.get('result', {}).get('status') != 'completed':
                    raise ValueError('Backup is not eligible for rollback')
                original = next((item for item in journal['files'] if item['target'] == name), None)
                if original is None:
                    raise ValueError('Target is absent from backup')
                if not original['existed']:
                    if change['sha256'] != digest(b''):
                        raise ValueError('Rollback no longer matches reviewed content')
                    change['delete'] = True
                    if (proposed / name).exists():
                        (proposed / name).unlink()
                    continue
                source = previous / name
                if digest(read_bytes(source)) != original['backup_sha256']:
                    raise ValueError('Rollback backup checksum mismatch')
            else:
                staged = required(change, 'staged')
                if not re.fullmatch(r'[a-f0-9]{64}\.conf', staged):
                    raise ValueError('Invalid staged file')
                source = incoming / staged
            data = read_bytes(source)
            if digest(data) != required(change, 'sha256'):
                raise ValueError('Staged or backup file checksum mismatch')
            self.validate_content(name, data.decode('utf-8'), data.decode('utf-8') if request['action'] == 'rollback' else None)
            (proposed / name).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            (proposed / name).write_bytes(data)
            frozen = backup / '.incoming' / name
            frozen.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            frozen.write_bytes(data)
            os.chmod(str(frozen), 0o600)
            change['source'] = str(frozen)
        for name in self.policy.get('required_files', []):
            if not (proposed / relative(name)).is_file():
                raise ValueError('Required configuration file is missing')
        self.rewrite_includes(proposed)
        self.validate(proposed, 'proposed_configuration_validation')
        journal = {'configuration_root': str(self.root), 'payload_hash': required(request, 'payload_hash'), 'files': changes}
        write_json(journal_path, journal)
        try:
            for change in changes:
                destination = self.target(change['target'])
                if change.get('delete'):
                    if destination.exists():
                        destination.unlink()
                        sync_directory(destination.parent)
                else:
                    self.install(Path(change['source']), destination, backup / change['target'])
            self.validate(self.root, 'effective_configuration_validation')
            self.control('reload')
            if not self.health():
                raise RuntimeError('Post-deployment HTTP health verification failed')
            self.step('health_verification', 'completed', 'Configured HTTP health check passed')
            result = {'success': True, 'status': 'completed', 'fingerprint': self.fingerprint(), 'rollback_supported': True}
        except Exception as error:
            result = {'success': False, 'status': 'failed', 'errorlog': safe(error)}
            try:
                self.restore(backup, changes)
                result['rollback_status'] = 'completed'
            except Exception as recovery:
                result.update(rollback_status='failed', recovery_error=safe(recovery))
        result['steps'] = self.steps
        journal['result'] = result
        write_json(journal_path, journal)
        return result

    def execute(self, request):
        action = required(request, 'action')
        if action not in ACTIONS or request.get('technology', self.technology) != self.technology:
            raise ValueError('Unsupported Apache operation')
        with instance_lock(self.backups / 'instance.lock'):
            self.steps = []
            if action in ('deploy', 'rollback'):
                return self.deploy(request)
            if action not in ('inspect', 'read', 'backup_read'):
                self.recover_pending()
            if action in ('start', 'stop', 'restart', 'reload') and 'fingerprint' in request:
                if request['fingerprint'] != self.fingerprint() or request.get('policy_hash') != self.policy_hash():
                    raise ValueError('Service operation no longer matches the approved configuration and policy')
            if action == 'inspect':
                result = self.inspect()
            elif action in ('read', 'backup_read'):
                result = self.read_configuration(request)
            elif action == 'prepare':
                directory = self.deployment_directory(self.stage, required(request, 'deployment_id'))
                directory.mkdir(mode=0o700, exist_ok=True)
                trusted(directory, private=True)
                result = {'staging_directory': str(directory)}
            else:
                if action != 'stop':
                    self.validate(self.root, 'configuration_validation')
                if action != 'validate':
                    self.control(action)
                if action not in ('validate', 'stop') and not self.health():
                    raise RuntimeError('Apache control completed but HTTP health verification failed')
                if action == 'stop' and self.health():
                    raise RuntimeError('Apache control completed but the configured instance is still reachable')
                result = {'status': 'stopped' if action == 'stop' else 'completed'}
            result.update(success=True, steps=self.steps)
            return result


def process_instances(port):
    listeners = {}
    try:
        for connection in psutil.net_connections(kind='inet'):
            if connection.status == psutil.CONN_LISTEN and connection.laddr and connection.pid:
                listeners.setdefault(connection.pid, set()).add(connection.laddr.port)
    except (psutil.Error, OSError):
        pass
    instances = {}
    for process in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        try:
            info = process.info
            if info.get('name') not in ('httpd', 'apache2', 'httpd.exe'):
                continue
            args = info.get('cmdline') or []
            def option(flag):
                if flag in args and args.index(flag) + 1 < len(args):
                    return args[args.index(flag) + 1]
                return next((value[len(flag):] for value in args[1:] if value.startswith(flag) and len(value) > len(flag)), '')
            entry = (info.get('exe') or args[0], option('-d'), option('-f'))
            instances.setdefault(entry, set()).update(listeners.get(info['pid'], set()))
        except (psutil.Error, OSError, IndexError):
            continue
    matches = [entry for entry, ports in instances.items() if port in ports]
    if matches:
        instances = {entry: instances[entry] for entry in matches}
    if len(instances) > 1:
        raise ValueError('Multiple Apache instances found; select the listening port of this instance')
    return next(iter(instances), None)


def discover_instance(request):
    connection = dict(request.get('connection') or {})
    server = str(request.get('server') or 'localhost')
    port = int(connection.get('port') or (443 if common.truthy(connection.get('ssl')) else 80))
    if not 1 <= port <= 65535:
        raise ValueError('Invalid Apache listening port')
    process = process_instances(port)
    binary = process[0] if process else None
    if binary and Path(binary).name == 'apache2':
        binary = shutil.which('apache2ctl') or binary
    binary = binary or next((shutil.which(name) for name in ('apache2ctl', 'apachectl', 'httpd', 'apache2') if shutil.which(name)), None)
    if not binary:
        raise ValueError('Apache executable was not found on the selected agent host')
    compiled = subprocess.run([binary, '-V'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, check=False)
    text = compiled.stdout.decode('utf-8', errors='replace')
    def define(name):
        match = re.search(r'\b' + name + r'="([^"]+)"', text)
        return match.group(1) if match else ''
    root = Path((process[1] if process else '') or define('HTTPD_ROOT'))
    main = Path((process[2] if process else '') or define('SERVER_CONFIG_FILE'))
    if not root.is_absolute() or str(main) == '.':
        raise ValueError('Unable to discover Apache ServerRoot and main configuration')
    if not main.is_absolute():
        main = root / main
    root = root.resolve(strict=True)
    server_root = root
    main = main.resolve(strict=True)
    if root not in main.parents:
        root = main.parent
    instance = str(request.get('instance') or '')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', instance):
        raise ValueError('Invalid application server identity')
    targets = {}
    for path in sorted(root.rglob('*.conf')):
        if not path.is_file():
            continue
        destination = path.resolve(strict=True)
        if root not in destination.parents:
            raise ValueError('Apache configuration includes an external configuration link')
        targets[relative(path.relative_to(root).as_posix())] = relative(destination.relative_to(root).as_posix())
    main_name = relative(main.relative_to(root).as_posix())
    targets[main_name] = main_name
    storage = Path(os.getcwd()) / 'data' / 'deployments' / 'apache' / instance
    for directory in (storage / 'staging', storage / 'backups'):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for entry in (directory,) + tuple(directory.parents):
            trusted(entry)
        trusted(directory, private=True)
    connection['port'] = port
    url, _ = common.rest_base_url(server, connection, str(port))
    return {'technology': 'apache', 'config_root': str(root), 'server_root': str(server_root), 'main_config': main_name,
            'apachectl': str(Path(binary).resolve(strict=True)), 'staging_root': str(storage / 'staging'), 'backup_root': str(storage / 'backups'),
            'allowed_files': sorted(set(targets.values())), 'file_targets': targets, 'auto_discovered': True,
            'health_url': url + '/', 'server': server, 'connection': connection}


