import base64
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

from modules.base import configs
from modules.statistics import common
from modules.statistics.configuration import load_policy
from modules.statistics.configuration_policy import configuration_directory, configured_policy, select_policy, validate_directory
from modules.statistics.apache.operations import instance_lock, redact, relative, trusted, write_json

MAX_FILE = 524288
MAX_TOTAL = 8388608
MAX_FILES = 40
ROOT_KEYS = {'tomcat': 'catalinaBase', 'jboss': 'jbossConfigDir', 'weblogic': 'domainHome',
             'ibmwas': 'wasConfigDir', 'liberty': 'libertyServerConfigDir'}


def classify(technology, name):
    name = relative(name)
    if technology == 'jboss' and (name.endswith('.xml') or name == 'logging.properties'):
        return 'BLOCKED_MANAGED_CONFIGURATION', 'JBoss standalone/domain XML and generated logging.properties require explicit native management operations.'
    if technology == 'weblogic' and (name.startswith(('config/', 'security/', 'servers/')) or name.endswith('.xml')):
        return 'BLOCKED_MANAGED_CONFIGURATION', 'WebLogic domain configuration belongs to the Administration Server; managed runtime directories are not writable bundle targets.'
    if technology == 'ibmwas' and (name.startswith(('cells/', 'nodes/')) or name.endswith('.xml')):
        return 'BLOCKED_MANAGED_CONFIGURATION', 'Traditional WAS configuration requires wsadmin and, for ND, deployment-manager ownership and node synchronization.'
    supported = name.endswith(('.xml', '.properties'))
    if technology == 'tomcat':
        supported = name.startswith('conf/') and supported
    elif technology == 'jboss':
        supported = name.endswith('.properties')
    elif technology == 'weblogic':
        supported = name.endswith('.properties') and not name.startswith(('bin/', 'config/', 'security/', 'servers/'))
    elif technology == 'liberty':
        supported = name in ('server.xml', 'bootstrap.properties', 'jvm.options', 'server.env') or name.endswith(('.xml', '.properties'))
    return ('SUPPORTED', '') if supported else ('BLOCKED_UNSUPPORTED_CONFIGURATION', 'This resource has no supported configuration operation.')


def validate_content(name, data, tomcat_users=False):
    if len(data) > MAX_FILE:
        raise ValueError('Configuration entry exceeds size limit')
    text = data.decode('utf-8')
    if '\0' in text or re.search(r'(?i)<!DOCTYPE|<!ENTITY|-----BEGIN .*PRIVATE KEY-----|://[^\s/]+:[^\s@]+@', text):
        raise ValueError('Unsafe configuration content')
    def secret(key, value):
        if re.search(r'(?i)password|passwd|secret|token|credential|(?:store|ssl)pass', key) and value.strip() and not re.fullmatch(r'\$\{[A-Za-z0-9_.:-]+}', value.strip()):
            raise ValueError('Use existing mounted secret references')
    if name.endswith('.xml'):
        root = ET.fromstring(text)
        tomcat_users = tomcat_users and Path(name).name == 'tomcat-users.xml' and root.tag.rsplit('}', 1)[-1] == 'tomcat-users'
        for element in root.iter():
            secret(element.tag, ''.join(element.itertext()))
            for key, value in element.attrib.items():
                if tomcat_users and element.tag.rsplit('}', 1)[-1] == 'user' and key.rsplit('}', 1)[-1] == 'password':
                    continue
                secret(key, value)
            if element.attrib.get('name') or element.attrib.get('key'):
                secret(element.attrib.get('name', element.attrib.get('key', '')), element.attrib.get('value', ''.join(element.itertext())))
    else:
        for line in text.splitlines():
            if line.lstrip().startswith(('#', '!')):
                continue
            if name.endswith('jvm.options'):


                if re.search(r'(?i)-javaagent|-agentpath|-agentlib|OnError|OnOutOfMemoryError', line):
                    raise ValueError('Executable JVM options are not supported')
            if name.endswith('server.env') and re.search(r'[`;]|\$\(|(?:^|\s)(?:source|eval|exec)\s', line):
                raise ValueError('Executable environment settings are not supported')
            match = re.match(r'\s*([^=:]+)\s*[=:]\s*(.*)', line)
            if match:
                secret(match.group(1), match.group(2))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def redact_configuration(text):
    text = re.sub(r'(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[redacted private key]', text)


    sensitive = r'password|passwd|secret|token|credential|(?:store|ssl|key)pass|api.?key|authorization'
    text = re.sub(r'(?is)<([\w:.-]*(?:' + sensitive + r')[\w:.-]*)\b[^>]*>.*?</\1\s*>', '[redacted]', text)
    text = re.sub(r'(?is)<(?:property|variable)\b[^>]*(?:name|key)\s*=\s*["\'][^"\']*(?:' + sensitive + r')[^"\']*["\'][^>]*>.*?</(?:property|variable)\s*>', '[redacted]', text)
    lines = []
    continuing = False
    for line in text.splitlines():
        sensitive_line = continuing or re.search(sensitive, line, re.I)
        lines.append('[redacted]' if sensitive_line else line)
        continuing = bool(sensitive_line and line.rstrip().endswith('\\'))
    text = '\n'.join(lines)
    return redact(text)


class BundleConfigurationOperations:
    def __init__(self, policy, runner=None, health_probe=None, encrypt=None, decrypt=None):
        self.policy = policy
        self.technology = policy.get('technology')
        if self.technology not in ROOT_KEYS:
            raise ValueError('Unsupported configuration technology')
        self.runner = runner
        self.health_probe = health_probe
        self.encrypt = encrypt
        self.decrypt = decrypt
        self.configuration_directory = False
        self.file_operations_only = False
        self.root = configuration_directory(policy.get('config_root', ''))
        root_details = self.root.stat()
        self.root_identity = (root_details.st_dev, root_details.st_ino)
        self.allowed = {relative(name) for name in policy.get('allowed_files', [])}
        self.stage_root = self.directory('staging_root', True)
        self.backup_root = self.directory('backup_root', True)
        for a, b in ((self.root, self.stage_root), (self.root, self.backup_root), (self.stage_root, self.backup_root)):
            if a == b or a in b.parents or b in a.parents:
                raise ValueError('Configuration, staging and snapshot roots must be separate')
        self.namespace = digest(str(self.root).encode())
        self.stage = self.stage_root / self.namespace
        self.backups = self.backup_root / self.namespace

    def directory(self, key, private=False):
        path = Path(self.policy.get(key, ''))
        if not path.is_absolute() or not path.is_dir() or path.resolve() != path:
            raise ValueError('Absolute directories without symlinks are required')
        if private:
            trusted(path, private=True)
        return path

    def policy_hash(self):
        details = self.root.stat()
        identity = [details.st_dev, details.st_ino, details.st_uid, details.st_mode]
        return digest(json.dumps(self.policy, sort_keys=True, separators=(',', ':')).encode() +
                      ('%s:%s:%s:%s' % tuple(identity)).encode())

    def resolve_configuration_root(self, request):
        try:
            configs.remoteFilePath(str(self.root), configs.getRemoteFileRoots())
        except ValueError:
            raise ValueError('Add the selected configuration directory to REMOTE_FILE_ROOTS in config/mwagent.config')
        self.configuration_directory = self.technology == 'tomcat' and (request.get('configuration_directory') is True or self.policy.get('configuration_directory') is True)
        self.file_operations_only = request.get('file_operations_only') is True
        override = request.get('configuration_root', '')
        roots = [self.root, Path(self.policy.get('configuration_base', str(self.root)))]
        if self.technology == 'tomcat' and self.policy.get('configuration_defaults_hash') and self.root.name == 'conf' and request.get('configuration_directory') is not True:
            roots.append(self.root.parent)
        if override and (not isinstance(override, str) or Path(override) not in roots):
            raise ValueError('Configuration directory differs from the approved agent policy')
        access = {
            'readable': os.access(str(self.root), os.R_OK | os.X_OK), 'writable': os.access(str(self.root), os.W_OK | os.X_OK)}
        return {'configuration_root': str(self.root), 'field': 'tomcatConfigDir' if self.configuration_directory else ROOT_KEYS[self.technology],
                'readable': access['readable'], 'writable': access['writable'], 'policy_hash': self.policy_hash(),
                'configuration_folder': self.policy.get('configuration_folder', '')}

    @contextmanager
    def parent(self, name, create=False):
        if os.name == 'nt':
            raise ValueError('Safe bundle file operations currently require a POSIX agent')
        pieces = self.configuration_name(name).split('/')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open('/', flags)
        try:


            for piece in self.root.parts[1:]:
                following = os.open(piece, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            details = os.fstat(descriptor)
            if (details.st_dev, details.st_ino) != self.root_identity:
                raise ValueError('Configuration root changed during execution')
            for piece in pieces[:-1]:
                if create:
                    try:
                        os.mkdir(piece, mode=0o750, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                following = os.open(piece, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            yield descriptor, pieces[-1]
        finally:
            os.close(descriptor)

    def validate_configuration_path(self, name):
        relative(name)
        code, reason = self.classify_configuration_change(name)
        if code != 'SUPPORTED':
            return code, reason
        if not self.allowed_configuration(name):
            return 'BLOCKED_UNAUTHORIZED_PATH', 'Resource is not in the selected instance agent allowed_files policy.'
        try:
            with self.parent(name) as (fd, leaf):
                try:
                    info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        return 'BLOCKED_UNSAFE_PATH', 'Destination must be a regular file without symlinks.'
                except FileNotFoundError:
                    pass
        except FileNotFoundError:

            current = self.root
            for piece in self.configuration_name(name).split('/')[:-1]:
                current = current / piece
                if current.is_symlink() or (current.exists() and not current.is_dir()):
                    return 'BLOCKED_UNSAFE_PATH', 'Unsafe configuration parent.'
        except OSError:
            return 'BLOCKED_UNSAFE_PATH', 'Destination contains an inaccessible or unsafe component.'
        return code, reason

    def classify_configuration_change(self, name):
        if self.configuration_directory:
            return classify(self.technology, 'conf/' + self.configuration_name(name))
        return classify(self.technology, self.configuration_name(name))

    def configuration_name(self, name):
        name = relative(name)
        folder = self.policy.get('configuration_folder', '')
        if folder and name.startswith(folder + '/'):
            name = name[len(folder) + 1:]
        return name[5:] if self.configuration_directory and name.startswith('conf/') else name

    def allowed_configuration(self, name):
        if self.policy.get('allow_existing_files') is True and self.policy.get('managed_files') is True:
            return True
        if self.policy.get('allow_new_files') is True and self.classify_configuration_change(name)[0] == 'SUPPORTED':
            return True
        return self.configuration_name(name) in {self.configuration_name(item) for item in self.allowed}

    def writable_configuration_path(self, name):
        parent = self.root / self.configuration_name(name)
        parent = parent.parent
        while not parent.exists() and parent != self.root:
            if parent.is_symlink():
                return False
            parent = parent.parent
        if parent.resolve() != parent or not os.access(str(parent), os.W_OK | os.X_OK):
            return False
        try:
            with self.parent(name) as (fd, leaf):
                try:
                    owner = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    return True
                return os.geteuid() == 0 or (owner.st_uid == os.geteuid() and owner.st_gid in set(os.getgroups() + [os.getegid()]))
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def metadata(self, name, content=False):
        try:
            with self.parent(name) as (fd, leaf):
                descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(descriptor, 'rb') as stream:
                    before = os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE:
                        raise ValueError('Configuration target is not a bounded regular file')
                    checksum = hashlib.sha256()
                    chunks = []
                    size = 0
                    for chunk in iter(lambda: stream.read(65536), b''):
                        size += len(chunk)
                        if size > MAX_FILE:
                            raise ValueError('Configuration target exceeds size limit')
                        checksum.update(chunk)
                        if content:
                            chunks.append(chunk)
                    after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                        raise ValueError('Configuration changed during comparison')
                    result = {'exists': True, 'size': size, 'sha256': checksum.hexdigest()}
                    if content:
                        result['content'] = b''.join(chunks)
                    return result
        except FileNotFoundError:
            return {'exists': False, 'size': 0, 'sha256': ''}

    def entries(self, request):
        entries = request.get('files')
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
            raise ValueError('Select 1 to 40 bundle files')
        seen = set()
        total = 0
        for entry in entries:
            name = relative(entry['target'])
            if self.configuration_name(name).casefold() in seen or not re.fullmatch(r'[a-f0-9]{64}', entry.get('sha256', '')):
                raise ValueError('Invalid bundle file identity')
            size = entry.get('size')
            if type(size) is not int or not 0 <= size <= MAX_FILE:
                raise ValueError('Invalid bundle entry size')
            seen.add(self.configuration_name(name).casefold())
            total += size
        if total > MAX_TOTAL:
            raise ValueError('Bundle exceeds expanded size limit')
        return entries

    def determine_restart_requirement(self, files):
        changed = [f for f in files if f['status'] in ('NEW', 'MODIFIED')]
        if not changed:
            return {'required': False, 'target': None, 'mode': 'none'}


        dynamic = self.policy.get('dynamic_files', []) if self.technology == 'liberty' else []
        restart = any(f['target'] not in dynamic or not f['target'].endswith('.xml') for f in changed)
        target = self.policy.get('restart_target')
        validation = self.policy.get('validation_command')
        reason = ''
        if not isinstance(validation, list) or not validation or (not self.file_operations_only and not self.policy.get('health_url')):
            reason = 'An approved validation command and health URL are required.'
        if not restart and not self.policy.get('dynamic_validation_command'):
            reason = 'Liberty dynamic updates require an approved runtime validation command verifying that the selected server applied the change.'
        if self.file_operations_only:
            return {'required': restart, 'target': None, 'mode': 'restart' if restart else 'dynamic', 'blocked_reason': reason}
        if restart and (not isinstance(target, dict) or target.get('scope') != 'server' or not target.get('server')
                        or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,100}\.service', target.get('service_unit', ''))):
            reason = 'Identify one server and its dedicated service unit in the agent restart_target policy; domain/cell-wide targets are blocked.'
        if restart and target and target.get('exclusive') is not True:
            reason = 'The restart target must explicitly certify that the unit controls exactly the selected server.'
        return {'required': restart, 'target': target if restart else None, 'mode': 'restart' if restart else 'dynamic', 'blocked_reason': reason}

    def compare_configuration_files(self, request):
        resolved = self.resolve_configuration_root(request)
        files = []
        for entry in self.entries(request):
            code, reason = self.validate_configuration_path(entry['target'])


            if self.allowed_configuration(entry['target']):
                try:
                    before = self.metadata(entry['target'])
                except (OSError, ValueError):
                    before = {'exists': None, 'size': None, 'sha256': ''}
                    code, reason = 'BLOCKED_UNSAFE_PATH', 'Unable to compare a safe regular target.'
            else:
                before = {'exists': None, 'size': None, 'sha256': ''}
            identical = before['exists'] and before['size'] == entry['size'] and before['sha256'] == entry['sha256']
            status = 'UNCHANGED' if identical and code in ('SUPPORTED', 'BLOCKED_MANAGED_CONFIGURATION', 'BLOCKED_UNSUPPORTED_CONFIGURATION') else (
                     code if code != 'SUPPORTED' else 'NEW' if not before['exists'] else 'MODIFIED')
            if status in ('NEW', 'MODIFIED') and not self.writable_configuration_path(entry['target']):
                status, reason = 'BLOCKED_PERMISSIONS', 'The agent cannot replace this resource while preserving its ownership and permissions.'
            files.append(dict(entry, status=status, reason=reason, before=before))
        restart = self.determine_restart_requirement(files)
        return dict(resolved, files=files, restart=restart,
                    can_proceed=not restart.get('blocked_reason') and all(not f['status'].startswith('BLOCKED') for f in files),
                    fingerprint=digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()))

    def runtime_directory(self, base, identifier):
        if not re.fullmatch(r'DEP[a-f0-9]{32}', identifier):
            raise ValueError('Invalid deployment identity')
        for path in (base, base / identifier):
            path.mkdir(mode=0o700, exist_ok=True)
            trusted(path, private=True)
        return base / identifier

    def command(self, command):
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or '\0' in x for x in command):
            raise ValueError('An approved command argument list is required')
        binary = Path(command[0])
        if not binary.is_absolute():
            raise ValueError('An absolute approved executable is required')
        if self.runner:
            return self.runner(command)
        if binary.resolve() != binary or not os.access(str(binary), os.X_OK):
            raise ValueError('An absolute approved executable without symlinks is required')
        with tempfile.TemporaryFile() as output:
            run = subprocess.run(command, shell=False, stdout=output, stderr=subprocess.STDOUT, timeout=90)
            if run.returncode:

                raise ValueError('Approved validation or service operation failed (exit %s)' % run.returncode)

    def validate_configuration(self):
        command = self.policy.get('validation_command')
        if command == ['@MIDLEO_CONFIGURATION_VALIDATE@']:
            validate_directory(self.root)
            return
        if isinstance(command, list):
            command = [str(self.root) if argument == '@CONFIGURATION_ROOT@' else argument for argument in command]
        self.command(command)

    def restart_selected_server(self, target):
        if target != self.policy.get('restart_target') or target.get('scope') != 'server':
            raise ValueError('Restart target changed')
        binary = self.policy.get('service_manager', '/usr/bin/systemctl')
        if Path(binary).name != 'systemctl':
            raise ValueError('A dedicated systemctl server service is required')
        self.command([binary, 'restart', target['service_unit']])
        self.command([binary, 'is-active', '--quiet', target['service_unit']])

    def verify_server_health(self):
        if self.health_probe:
            return bool(self.health_probe())
        return common.http_available(common.http_status('', url=self.policy['health_url']), self.policy.get('health_status'))

    def prepare_files(self, request):
        current = self.preview_restore(request) if request.get('restore_source') else self.compare_configuration_files(request)
        if not current['can_proceed'] or current['fingerprint'] != request.get('fingerprint'):
            raise ValueError('Preview changed before snapshot')
        backups = self.runtime_directory(self.backups, request['deployment_id'])
        journal = backups / 'journal.json'
        if journal.exists():
            result = json.loads(journal.read_text())
            if result.get('fingerprint') != current['fingerprint'] or result.get('status') != 'prepared':
                raise ValueError('This deployment already ran; review again')
            return result
        if not request.get('restore_source'):
            self.validate_configuration()
        changed = [f for f in current['files'] if f['status'] in ('NEW', 'MODIFIED', 'DELETED')]
        result = {'success': True, 'status': 'prepared', 'fingerprint': current['fingerprint'], 'files': [],
                  'snapshots': {'before': self.snapshot(backups, 'before', changed)}, 'validation': {'before': 'completed'}}
        result['configuration_backup'] = self.backup_metadata(request['deployment_id'])
        write_json(journal, result)
        return result

    def restore_configuration(self, request):
        self.resolve_configuration_root(request)
        if request.get('policy_hash') != self.policy_hash():
            raise ValueError('Agent policy changed before recovery')
        backups = self.runtime_directory(self.backups, request['deployment_id'])
        journal = backups / 'journal.json'
        result = json.loads(journal.read_text())
        before = self.read_snapshot(request['deployment_id'])
        requested = {entry['target']: entry for entry in self.entries(request)}
        recovery = {'success': True, 'status': 'restored', 'files': []}
        for entry in result.get('files', []):
            name = entry['target']
            try:
                if name not in requested or name not in before or self.validate_configuration_path(name)[0] != 'SUPPORTED':
                    raise ValueError('Unsupported restoration target')
                original = before[name]
                actual = self.metadata(name)
                if actual == {key: original[key] for key in ('exists', 'size', 'sha256')}:
                    recovery['files'].append({'target': name, 'status': 'UNCHANGED'})
                    continue
                expected_delete = requested[name].get('delete') is True
                if (expected_delete and actual['exists']) or (not expected_delete and (not actual['exists'] or actual['sha256'] != requested[name]['sha256'])):
                    raise ValueError('Recovery target changed outside this deployment')
                if original['exists']:
                    data = base64.b64decode(original['content'], validate=True)
                    if digest(data) != original['sha256']:
                        raise ValueError('Before snapshot checksum failed')
                    self.install(name, data, original)
                else:
                    with self.parent(name) as (fd, leaf):
                        os.unlink(leaf, dir_fd=fd)
                        os.fsync(fd)
                if self.metadata(name) != {key: original[key] for key in ('exists', 'size', 'sha256')}:
                    raise ValueError('Restoration verification failed')
                recovery['files'].append({'target': name, 'status': 'RESTORED'})
            except Exception as error:
                recovery.update(success=False, status='restore_failed')
                recovery['files'].append({'target': name, 'status': 'FAILED', 'error': redact(str(error))[:512]})
        result['recovery'] = recovery
        write_json(journal, result)
        return recovery

    def snapshot_files(self, request):
        self.resolve_configuration_root(request)
        if request.get('policy_hash') != self.policy_hash():
            raise ValueError('Agent policy changed before completion')
        backups = self.runtime_directory(self.backups, request['deployment_id'])
        journal = backups / 'journal.json'
        result = json.loads(journal.read_text())
        try:
            label = request.get('snapshot_label', 'after')
            if label not in ('after', 'recovery_after'):
                raise ValueError('Unsupported file snapshot label')
            result['snapshots']['after'] = self.snapshot(backups, label, self.entries(request))
        except Exception as error:
            result.update(success=False, status='failed', snapshot_error=redact(str(error))[:512])
        write_json(journal, result)
        return result

    def snapshot(self, directory, label, files):
        payload = {}
        archive = io.BytesIO()
        zipper = zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED)
        for entry in files:
            current = self.metadata(entry['target'], content=True)
            if current.get('exists'):
                zipper.writestr(entry['target'], current.pop('content'))
                with self.parent(entry['target']) as (fd, leaf):
                    attributes = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                    current.update(uid=attributes.st_uid, gid=attributes.st_gid, mode=stat.S_IMODE(attributes.st_mode))
            payload[entry['target']] = current
        zipper.close()
        payload = {'format': 'configuration_zip_v1', 'manifest': payload, 'archive': base64.b64encode(archive.getvalue()).decode('ascii')}
        if self.encrypt:
            encrypted = self.encrypt(payload)
        else:
            from modules.base import decrypt
            encrypted = decrypt.encrypt(payload, decrypt._derive_key().hex())
        if not encrypted:
            raise ValueError('Encrypted snapshot creation failed')
        path = directory / (label + '.zip.encrypted')
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        return '%s/%s/%s' % (self.namespace, directory.name, label)

    def backup_metadata(self, identifier):
        if not re.fullmatch(r'DEP[a-f0-9]{32}', identifier):
            raise ValueError('Invalid backup deployment identity')
        directory = self.backups / identifier
        trusted(directory, private=True)
        path = directory / 'before.zip.encrypted'
        if not path.exists():
            path = directory / 'before.encrypted'
        trusted(path, private=True)
        if path.stat().st_size > MAX_TOTAL * 4:
            raise ValueError('Backup exceeds size limit')
        return {'deployment_id': identifier, 'configuration_root': str(self.root), 'archive_path': str(path),
                'journal_path': str(directory / 'journal.json'), 'sha256': digest(path.read_bytes()),
                'format': 'encrypted_zip' if path.name.endswith('.zip.encrypted') else 'encrypted_snapshot'}

    def read_snapshot(self, identifier):
        backup = self.backup_metadata(identifier)
        encrypted = Path(backup['archive_path']).read_text()
        if self.decrypt:
            payload = self.decrypt(encrypted)
        else:
            from modules.base import decrypt
            payload = decrypt.decryptit(encrypted, decrypt._derive_key().hex())
        if not isinstance(payload, dict):
            raise ValueError('Unable to decrypt the before snapshot')
        if payload.get('format') == 'configuration_zip_v1':
            manifest = payload.get('manifest')
            if not isinstance(manifest, dict) or len(manifest) > MAX_FILES:
                raise ValueError('Invalid backup manifest')
            data = base64.b64decode(payload['archive'], validate=True)
            if len(data) > MAX_TOTAL * 2:
                raise ValueError('Backup archive exceeds size limit')
            with zipfile.ZipFile(io.BytesIO(data)) as zipper:
                expected = {name for name, entry in manifest.items() if entry.get('exists')}
                if len(zipper.namelist()) != len(expected) or set(zipper.namelist()) != expected:
                    raise ValueError('Backup archive does not match its manifest')
                for name in expected:
                    if zipper.getinfo(name).file_size > MAX_FILE:
                        raise ValueError('Backup file exceeds size limit')
                    manifest[name]['content'] = base64.b64encode(zipper.read(name)).decode('ascii')
            payload = manifest
        if not 1 <= len(payload) <= MAX_FILES:
            raise ValueError('Backup contains no restorable files')
        total = 0
        for name, entry in payload.items():
            relative(name)
            if not isinstance(entry, dict) or type(entry.get('exists')) is not bool:
                raise ValueError('Invalid backup file metadata')
            if entry['exists']:
                data = base64.b64decode(entry['content'], validate=True)
                total += len(data)
                if len(data) > MAX_FILE or len(data) != entry['size'] or digest(data) != entry['sha256']:
                    raise ValueError('Before snapshot checksum failed')
        if total > MAX_TOTAL:
            raise ValueError('Backup exceeds expanded size limit')
        return payload

    def preview_restore(self, request):
        resolved = self.resolve_configuration_root(request)
        source = request.get('restore_source') or {}
        backup = self.backup_metadata(source.get('deployment_id', ''))
        if source.get('sha256') and source['sha256'] != backup['sha256']:
            raise ValueError('Backup changed since the restore was reviewed')
        before = self.read_snapshot(backup['deployment_id'])
        files = []
        for name, original in sorted(before.items()):
            code, reason = self.validate_configuration_path(name)
            current = self.metadata(name)
            desired = {key: original[key] for key in ('exists', 'size', 'sha256')}
            identical = current == desired
            status = 'UNCHANGED' if identical else code if code != 'SUPPORTED' else 'DELETED' if not desired['exists'] else 'MODIFIED' if current['exists'] else 'NEW'
            if not identical and not self.writable_configuration_path(name):
                status, reason = 'BLOCKED_PERMISSIONS', 'The agent cannot restore this resource.'
            if original['exists'] and not identical:
                validate_content(name, base64.b64decode(original['content']), self.technology == 'tomcat')
            files.append({'target': name, 'size': desired['size'], 'sha256': desired['sha256'] or digest(b''),
                          'delete': not desired['exists'], 'desired': desired, 'before': current, 'status': status, 'reason': reason})
        changed = [f for f in files if f['status'] != 'UNCHANGED']
        restart = self.determine_restart_requirement(files)
        if changed:
            restart['required'] = True
            restart['mode'] = 'restart'
            if not self.file_operations_only:
                forced = [dict(f, status='MODIFIED', target='restore.properties') for f in changed]
                restart = self.determine_restart_requirement(forced)
        return dict(resolved, success=True, files=files, restore_source=backup, restart=restart,
                    can_proceed=not restart.get('blocked_reason') and all(not f['status'].startswith('BLOCKED') for f in files),
                    fingerprint=digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()))

    def apply_restore(self, request):
        current = self.preview_restore(request)
        if not current['can_proceed'] or current['fingerprint'] != request.get('fingerprint') or current['policy_hash'] != request.get('policy_hash'):
            raise ValueError('Configuration or backup changed after restore preview')
        directory = self.runtime_directory(self.backups, request['deployment_id'])
        journal = directory / 'journal.json'
        result = json.loads(journal.read_text())
        if result.get('status') != 'prepared' or result.get('fingerprint') != current['fingerprint']:
            raise ValueError('A fresh restore backup is required')
        source = self.read_snapshot(current['restore_source']['deployment_id'])
        result.update(success=False, status='restoring', restore_source=current['restore_source'], files=[],
                      restart={'status': 'not_run', 'target': current['restart']['target']}, health='not_run')
        stopped = False
        target = current['restart']['target']
        try:
            if not self.file_operations_only:
                if Path(self.policy.get('service_manager', '/usr/bin/systemctl')).name != 'systemctl':
                    raise ValueError('A dedicated systemctl server service is required')
                stopped = True
                self.command([self.policy.get('service_manager', '/usr/bin/systemctl'), 'stop', target['service_unit']])
            for entry in current['files']:
                if entry['status'] == 'UNCHANGED':
                    continue
                name = entry['target']
                if self.metadata(name) != entry['before']:
                    raise ValueError('Configuration changed during restoration')
                evidence = {'target': name, 'status': 'RESTORING'}
                result['files'].append(evidence)
                write_json(journal, result)
                if source[name]['exists']:
                    self.install(name, base64.b64decode(source[name]['content'], validate=True), source[name])
                else:
                    with self.parent(name) as (fd, leaf):
                        os.unlink(leaf, dir_fd=fd)
                        os.fsync(fd)
                if self.metadata(name) != entry['desired']:
                    raise ValueError('Restoration verification failed')
                evidence['status'] = 'RESTORED'
                write_json(journal, result)
            self.validate_configuration()
            result['validation']['after'] = 'completed'
            result.update(success=True, status='restored')
        except Exception as error:
            result.update(success=False, status='failed', errorlog=redact(str(error))[:1024])
            if stopped:
                try:
                    write_json(journal, result)
                    result['recovery'] = self.restore_configuration(request)
                except Exception as recovery_error:
                    result['recovery'] = {'success': False, 'status': 'restore_failed', 'error': redact(str(recovery_error))[:512]}
        finally:
            if stopped:
                try:
                    self.command([self.policy.get('service_manager', '/usr/bin/systemctl'), 'start', target['service_unit']])
                    self.command([self.policy.get('service_manager', '/usr/bin/systemctl'), 'is-active', '--quiet', target['service_unit']])
                    result['restart']['status'] = 'completed'
                    result['health'] = 'completed' if self.verify_server_health() else 'failed'
                    if result['health'] != 'completed':
                        result.update(success=False, status='failed', errorlog='Restored server health verification failed')
                except Exception as error:
                    result.update(success=False, status='failed', errorlog=redact(str(error))[:1024])
            if not self.file_operations_only:
                try:
                    result['snapshots']['after'] = self.snapshot(directory, 'after', current['files'])
                except Exception as error:
                    result.update(success=False, status='failed', errorlog=redact(str(error))[:1024])
            write_json(journal, result)
        return result

    def install(self, name, data, attributes=None):
        with self.parent(name, create=True) as (fd, leaf):
            temporary = '.midleo-' + os.urandom(16).hex()
            output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            try:
                info = None
                try:
                    info = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('Unsafe destination during installation')
                except FileNotFoundError:
                    pass
                with os.fdopen(output, 'wb') as stream:
                    stream.write(data)
                    if attributes and all(type(attributes.get(key)) is int for key in ('uid', 'gid', 'mode')):
                        if attributes['uid'] < 0 or attributes['gid'] < 0 or not 0 <= attributes['mode'] <= 0o777:
                            raise ValueError('Invalid backup file ownership or permissions')
                        os.fchown(stream.fileno(), attributes['uid'], attributes['gid'])
                        os.fchmod(stream.fileno(), attributes['mode'])
                    elif info:
                        os.fchown(stream.fileno(), info.st_uid, info.st_gid)
                        os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, leaf, src_dir_fd=fd, dst_dir_fd=fd)
                os.fsync(fd)
            finally:
                try:
                    os.unlink(temporary, dir_fd=fd)
                except FileNotFoundError:
                    pass

    def apply_supported_configuration(self, request):

        self.backups.mkdir(mode=0o700, exist_ok=True)
        trusted(self.backups, private=True)
        with instance_lock(self.backups / 'instance.lock'):
            current = self.compare_configuration_files(request)
            if not current['can_proceed'] or current['policy_hash'] != request.get('policy_hash') or current['fingerprint'] != request.get('fingerprint'):
                raise ValueError('Preview or permissions changed; review again before deployment')
            if not self.file_operations_only and current['restart'] != request.get('restart'):
                raise ValueError('Restart plan changed')
            result = {'success': False, 'files': [], 'management_operations': [], 'snapshots': {},
                      'restart': {'target': current['restart']['target'], 'status': 'not_run' if current['restart']['required'] else 'not_required'},
                      'validation': {'before': 'not_run', 'after': 'not_run'},
                      'health': 'not_run', 'skipped': [f['target'] for f in current['files'] if f['status'] == 'UNCHANGED']}
            files_only = self.file_operations_only
            changed = [f for f in current['files'] if f['status'] in ('NEW', 'MODIFIED')]
            if not changed:
                return dict(result, success=True, status='no_changes')
            stage = self.runtime_directory(self.stage, request['deployment_id'])
            backups = self.runtime_directory(self.backups, request['deployment_id'])
            journal = backups / 'journal.json'
            if journal.exists():
                prepared = json.loads(journal.read_text())
                if prepared.get('status') != 'prepared' or prepared.get('fingerprint') != current['fingerprint']:
                    raise ValueError('Before snapshot is missing or changed')
                result['snapshots'] = prepared['snapshots']
            incoming = {}
            for entry in changed:
                path = stage / (entry['sha256'] + '.config')
                trusted(path, private=True)
                if path.is_symlink() or path.stat().st_size != entry['size']:
                    raise ValueError('Invalid staged configuration')
                data = path.read_bytes()
                if digest(data) != entry['sha256']:
                    raise ValueError('Staged checksum changed')
                validate_content(entry['target'], data, self.technology == 'tomcat')
                incoming[entry['target']] = data

            self.validate_configuration()
            result['validation']['before'] = 'completed'
            if 'before' not in result['snapshots']:
                result['snapshots']['before'] = self.snapshot(backups, 'before', changed)
            result['configuration_backup'] = self.backup_metadata(request['deployment_id'])
            write_json(journal, result)
            try:
                for entry in changed:

                    if self.metadata(entry['target']) != entry['before']:
                        raise ValueError('Configuration changed after preview')
                    evidence = {'target': entry['target'], 'status': 'UPLOADING', 'before_sha256': entry['before']['sha256'], 'after_sha256': entry['sha256']}
                    result['files'].append(evidence)
                    write_json(journal, result)
                    self.install(entry['target'], incoming[entry['target']])
                    actual = self.metadata(entry['target'])
                    verified = actual['sha256'] == entry['sha256'] and actual['size'] == entry['size']
                    evidence.update(status='UPLOADED' if verified else 'VERIFY_FAILED', after_sha256=actual['sha256'])
                    write_json(journal, result)
                    if not verified:
                        raise ValueError('Modification verification failed')
                result['validation']['after'] = 'failed'
                self.validate_configuration()
                result['validation']['after'] = 'completed'
                if files_only:
                    if not current['restart']['required']:
                        self.command(self.policy['dynamic_validation_command'])
                    result.update(success=True, status='uploaded')
                    return result
                if current['restart']['required']:
                    result['restart']['status'] = 'failed'
                    self.restart_selected_server(current['restart']['target'])
                    result['restart']['status'] = 'completed'
                else:
                    self.command(self.policy['dynamic_validation_command'])
                result['health'] = 'failed'
                if not self.verify_server_health():
                    raise ValueError('Selected server health verification failed')
                result['health'] = 'completed'
                result.update(success=True, status='completed')
            except Exception as error:
                result.update(status='failed', errorlog=redact(str(error))[:1024],
                              recovery={'snapshot': result['snapshots']['before'], 'automatic_restore': False})
            finally:
                if not files_only:
                    try:
                        result['snapshots']['after'] = self.snapshot(backups, 'after', changed)
                    except Exception:
                        result.update(success=False, status='failed', errorlog='After snapshot failed; configuration may have changed.')
                write_json(journal, result)
                for entry in changed:
                    (stage / (entry['sha256'] + '.config')).unlink(missing_ok=True)
            return result

    def execute(self, request):
        action = request.get('action')
        if action == 'bundle_resolve':
            return self.resolve_configuration_root(request)
        if action == 'bundle_compare':
            return self.compare_configuration_files(request)
        if action == 'bundle_restore_preview':
            return self.preview_restore(request)
        if action == 'bundle_diff':
            self.resolve_configuration_root(request)
            name = relative(request.get('file', ''))
            if not self.allowed_configuration(name):
                raise ValueError('No permission to read this configuration resource')
            if self.metadata(name)['size'] > 131072:
                raise ValueError('Detailed differences are limited to 128 KiB per remote file; SHA-256 comparison remains available.')
            current = self.metadata(name, content=True)
            data = current.pop('content', b'')
            return dict(current, content=redact_configuration(data.decode('utf-8')))
        if action == 'bundle_prepare':
            self.resolve_configuration_root(request)
            if self.policy_hash() != request.get('policy_hash'):
                raise ValueError('Agent policy changed')
            result = self.prepare_files(request)
            return dict(result, staging_directory=str(self.runtime_directory(self.stage, request['deployment_id'])))
        if action == 'bundle_deploy':
            return self.apply_supported_configuration(request)
        if action == 'bundle_restore_deploy':
            self.backups.mkdir(mode=0o700, exist_ok=True)
            trusted(self.backups, private=True)
            with instance_lock(self.backups / 'instance.lock'):
                return self.apply_restore(request)
        if action in ('bundle_restore', 'bundle_snapshot'):
            self.backups.mkdir(mode=0o700, exist_ok=True)
            trusted(self.backups, private=True)
            with instance_lock(self.backups / 'instance.lock'):
                return self.restore_configuration(request) if action == 'bundle_restore' else self.snapshot_files(request)
        raise ValueError('Unsupported configuration bundle operation')


def execute(request):
    policy = configured_policy(Path(os.getcwd()), request)
    if policy is None:
        try:
            policy = load_policy(Path(os.getcwd()) / 'config' / 'configuration-policy.json', request)
        except (FileNotFoundError, KeyError):
            if request.get('action') != 'bundle_resolve':
                raise ValueError('Configure the server type with magent setconfig or save its configuration directory in Midleo')
            return detect_configuration_root(request)
    if policy.get('technology') != request.get('technology'):
        raise ValueError('Configuration policy belongs to another server technology')
    result = BundleConfigurationOperations(select_policy(policy, request)).execute(request)
    result.setdefault('success', True)
    return result


def detect_configuration_root(request):
    technology = request.get('technology')
    if technology not in ROOT_KEYS:
        raise ValueError('Unsupported configuration technology')
    connection = request.get('connection', {})
    mode = connection.get('management_mode', 'standalone')
    candidates = {
        'tomcat': [os.environ.get('CATALINA_BASE'), '/opt/tomcat'],
        'jboss': [os.environ.get('JBOSS_CONFIG_DIR'),
                  str(Path(os.environ['JBOSS_HOME']) / ('domain' if mode == 'domain' else 'standalone') / 'configuration') if os.environ.get('JBOSS_HOME') else None,
                  '/opt/jboss/%s/configuration' % ('domain' if mode == 'domain' else 'standalone')],
        'weblogic': [os.environ.get('DOMAIN_HOME'), '/opt/oracle/user_projects/domains/base_domain'],
        'ibmwas': [str(Path(os.environ['WAS_PROFILE_ROOT']) / 'config') if os.environ.get('WAS_PROFILE_ROOT') else None,
                   '/opt/IBM/WebSphere/AppServer/profiles/AppSrv01/config'],
        'liberty': [str(Path(os.environ['WLP_USER_DIR']) / 'servers' / connection.get('waslibsrv', 'defaultServer')) if os.environ.get('WLP_USER_DIR') else None,
                    '/opt/ibm/wlp/usr/servers/' + connection.get('waslibsrv', 'defaultServer')]
    }[technology]
    override = request.get('configuration_root')
    directory = technology == 'tomcat' and request.get('configuration_directory') is True
    if directory and not override:
        override = connection.get('tomcatConfigDir')
        if not override:
            raise ValueError('Enter the agent-visible mounted Tomcat configuration directory')
    if override:
        candidates = [override]
    found = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_absolute() and path.is_dir() and path.resolve() == path and str(path) not in found:
            found.append(str(path))
    if len(found) != 1:
        raise ValueError('No unambiguous standard directory found; enter a manual directory and verify it.')
    path = found[0]
    return {'success': True, 'configuration_root': path, 'field': 'tomcatConfigDir' if directory else ROOT_KEYS[technology], 'readable': os.access(path, os.R_OK | os.X_OK),
            'writable': os.access(path, os.W_OK | os.X_OK), 'policy_hash': '', 'execution_policy_required': True}
