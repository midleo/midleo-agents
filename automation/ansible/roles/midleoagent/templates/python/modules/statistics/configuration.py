import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from modules.statistics import common
from modules.statistics.apache.operations import ApacheOperations, read_bytes, required, trusted


def load_policy(path, request):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('An absolute configuration policy path is required')
    for entry in (path,) + tuple(path.parents):
        trusted(entry)
    policies = json.loads(read_bytes(path).decode('utf-8'))
    instance = request.get('policy_instance') or required(request, 'instance')
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,80}', instance):
        raise ValueError('Invalid configuration policy identity')
    return policies[instance]


class NativeConfigurationOperations(ApacheOperations):
    binary_key = 'service_manager'
    binary_names = ('systemctl',)
    extensions = ('.xml', '.properties')

    def __init__(self, policy, runner=None, health_probe=None):
        self.technology = policy.get('technology')
        if self.technology not in ('tomcat', 'jboss'):
            raise ValueError('Unsupported native configuration technology')
        self.service_unit = required(policy, 'service_unit')
        if not re.fullmatch(r'[A-Za-z0-9_.@-]{1,100}\.service', self.service_unit):
            raise ValueError('An approved service unit is required')
        super().__init__(policy, runner, health_probe)

    def validate_content(self, name, text, baseline=None):
        if '\0' in text or re.search(r'(?i)<!DOCTYPE|<!ENTITY|-----BEGIN .*PRIVATE KEY-----|://[^\s/]+:[^\s@]+@', text):
            raise ValueError('Unsafe native configuration content')
        def secret(key, value):
            if re.search(r'(?i)password|passwd|secret|token|credential|(?:store|ssl)pass', key) and value.strip() and not re.fullmatch(r'\$\{[A-Za-z0-9_.:-]+}', value.strip()):
                raise ValueError('Use existing mounted secret references')
        if name.endswith('.xml'):
            for element in ET.fromstring(text).iter():
                secret(element.tag, ''.join(element.itertext()))
                for key, value in element.attrib.items():
                    secret(key, value)
        else:
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith(('#', '!')):
                    continue
                match = re.fullmatch(r'\s*([A-Za-z0-9_.-]+)(?:\s*(?:[=:]|\s)\s*(.*))?', line)
                if match is None or re.search(r'\\\s*$', line):
                    raise ValueError('Use simple properties keys without escapes or continuations')
                secret(match.group(1), match.group(2) or '')

    def rewrite_includes(self, tree):
        return

    def validate(self, tree, name):
        if not (tree / self.main.relative_to(self.root)).is_file():
            raise ValueError('Main configuration is missing')
        for filename in self.allowed:
            path = tree / filename
            if path.exists():
                self.validate_content(filename, read_bytes(path).decode('utf-8'))
        self.step(name, 'completed', 'Native XML/properties configuration validated')

    def control(self, action):
        if action != 'reload':
            raise ValueError('Use existing native management APIs for service controls')
        self.run(['restart', self.service_unit], 'service_activation')

    def inspect(self):
        return {'configuration_directory': str(self.root), 'files': sorted(self.allowed), 'fingerprint': self.fingerprint(),
                'policy_hash': self.policy_hash(), 'status': 'running' if self.health() else 'unavailable'}

    def execute(self, request):
        if request.get('action') not in ('inspect', 'read', 'backup_read', 'prepare', 'validate', 'deploy', 'rollback'):
            raise ValueError('Use existing native management APIs for service controls')
        return super().execute(request)


def execute(request):
    policy_path = Path(os.getcwd()) / 'config' / 'configuration-policy.json'
    try:
        policy = load_policy(policy_path, request)
    except (FileNotFoundError, KeyError):
        raise ValueError('Configure the existing agent configuration policy for this native server')
    if policy.get('technology') != request.get('technology'):
        raise ValueError('Configuration policy belongs to another server technology')
    return NativeConfigurationOperations(policy).execute(request)
