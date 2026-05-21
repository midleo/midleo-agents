# Midleo Agents

Midleo Agents contains the runtime and deployment assets for installing Midleo monitoring agents on middleware hosts.

The Linux agent runs two services:

- `midleoagent`: TCP agent service used by Midleo Core for approved remote operations.
- `midleoactions`: localhost action service used for controlled remediation actions.

The cron integration runs every minute and executes only the jobs enabled in `config/cronjobs.json`. The actual collection interval is controlled by the agent configuration and per-job schedules.

## Repository Layout

- `automation/ansible`: Ansible playbooks and roles for Linux and Windows deployment.
- `automation/salt/midagent`: Salt states, pillars, execution modules, and state modules for Linux deployment.
- `monitoring.beats`: Filebeat, Fluent Bit, Logstash, and rsyslog examples for forwarding middleware alerts to Midleo Core.

The Ansible and Salt Python template trees are intentionally the same runtime code. Keep changes under both template trees synchronized:

```bash
diff -qr automation/ansible/roles/midleoagent/templates/python automation/salt/midagent/states/templates/python
```

## Runtime Requirements

- Python 3.6 or newer.
- Linux deployment uses systemd and cron.
- Windows deployment uses Windows Scheduled Tasks.
- Required Python packages are installed by the automation: `psutil`, `py-cpuinfo`, `dnspython`, `requests`, `pycryptodome`, `pywinrm`, and `netifaces`.
- `shlex`, `subprocess`, `asyncio`, `json`, and the other base imports used by the agent are Python standard-library modules and do not require separate installation.
- IBM MQ local queue statistics require `pymqi` and IBM MQ client development libraries. Enable this only on MQ hosts.
- MQ event collection requires `amqsevt` and `jq`.

## Security Defaults

- Agent configuration files are deployed with mode `0640`.
- Runtime directories are owned by the Midleo service user and are not world-readable.
- Command execution is allowlist-based through `ALLOWED_COMMANDS`.
- Shell execution is disabled by default with `ALLOW_SHELL_COMMANDS=n`.
- Remote file writes are restricted by `REMOTE_FILE_ROOTS`.
- HTTPS certificate verification is enabled by default with `SSLVERIFY=y`.
- systemd services run with additional hardening options where supported.

## Deployment

Use Ansible for fleet deployment from a control node:

```bash
cd automation/ansible
ansible-playbook install_midleo_agent.yaml -i inventories/hosts
```

Use Salt for minion-local deployment:

```bash
cd automation/salt/midagent
. midagent.conf
salt-call -c saltconfig state.apply midagent.installAgent pillar="$pillar"
```

See the deployment-specific READMEs for required variables and production checks:

- `automation/ansible/README.md`
- `automation/salt/midagent/README.md`

## Operations

Common Linux paths:

- Install root: `/var/midleoagent/`
- Agent config: `/var/midleoagent/config/mwagent.config`
- Cron config: `/var/midleoagent/config/cronjobs.json`
- Logs: `/var/midleoagent/logs/`
- systemd units: `/etc/systemd/system/midleoagent.service`, `/etc/systemd/system/midleoactions.service`

Health checks:

```bash
systemctl status midleoagent midleoactions
systemctl list-timers --all
crontab -u mwadmin -l
tail -n 100 /var/midleoagent/logs/midleoagent.log
```

For production, validate TLS, firewall rules, least-privilege command allowlists, and module-specific vendor libraries before onboarding customer hosts.
