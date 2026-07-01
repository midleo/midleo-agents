# Midleo Agents

Midleo Agents contains the runtime and deployment assets for installing Midleo monitoring agents on middleware hosts.

The Linux agent runs two services:

- `midleoagent`: TCP agent service used by Midleo Core for approved remote operations.
- `midleoactions`: localhost action service used for controlled remediation actions.

On z/OS, the same Python services run under UNIX System Services (USS). The repository provides USS wrappers and BPXBATCH started-task samples instead of systemd units.

The cron integration runs every minute and executes only the jobs enabled in `config/cronjobs.json`. The actual collection interval is controlled by the agent configuration and per-job schedules.

## Repository Layout

- `automation/ansible`: Ansible playbooks and roles for Linux, Windows, and z/OS USS deployment.
- `automation/salt/midagent`: Salt states, pillars, execution modules, and state modules for Linux and z/OS USS deployment.
- `monitoring.beats`: Filebeat, Fluent Bit, Logstash, and rsyslog examples for forwarding middleware alerts to Midleo Core.

The Ansible and Salt Python template trees are intentionally the same runtime code. Keep changes under both template trees synchronized:

```bash
diff -qr automation/ansible/roles/midleoagent/templates/python automation/salt/midagent/states/templates/python
```

## Runtime Requirements

- Python 3.6 or newer.
- Linux deployment uses systemd and cron.
- Windows deployment uses Windows Scheduled Tasks.
- z/OS deployment uses USS shell scripts, optional USS cron, and optional BPXBATCH started tasks generated from `MIDLEOA.proc` and `MIDLEOAC.proc` samples.
- Required Python packages are installed by the automation: `psutil`, `py-cpuinfo`, `dnspython`, `requests`, `pycryptodome`, `pywinrm`, and `netifaces`.
- `shlex`, `subprocess`, `asyncio`, `json`, and the other base imports used by the agent are Python standard-library modules and do not require separate installation.
- IBM MQ local queue statistics require `pymqi` and IBM MQ client development libraries. Enable this only on MQ hosts.
- On z/OS, local IBM MQ statistics require a z/OS-capable PyMQI port such as `zpymqi`; set `ZOS_ZPYMQI_PATH` and `ZOS_STEPLIB` in `config/mwagent.config`.
- MQ event collection requires `amqsevt` and `jq`.
- Optimization Advisor telemetry requires two controls: the per-server
  `confapplstat.json` opt-in and a time-limited local runtime window. Enable the
  runtime window manually on the agent with `./magent.sh enableoptadvisor [days]`
  for a maximum of 30 days, disable it with `./magent.sh disableoptadvisor
  [reason]`, and inspect it with `./magent.sh optadvisorstatus`. When the window
  expires, collection remains disabled until the next explicit enablement.
- IBM MQ Optimization Advisor telemetry reuses the existing `confapplstat.json`
  IBM MQ statistics entry. Enable it per queue manager with `optadvisor: true`,
  `appcode`, and `server_id` matching an existing midleo.CORE application/server.
  Existing `queues` and `channels` are reused, and optional `listeners` can be
  supplied as a comma-separated list. The collector sends only safe operational
  counters and never reads or sends message bodies or MQ connection secrets.
- WebLogic Optimization Advisor telemetry reuses the existing WebLogic
  `confapplstat.json` statistics entry and Java JMX connection. Enable it with
  `optadvisor: true`, `appcode`, `server_id`, and optionally `appserver` or
  `managed_server` when the managed server name differs from the connection host
  key. It collects runtime counters for JVM, JDBC, thread pools, and JMS
  destinations without sending WebLogic credentials, JNDI credentials, JMS
  message bodies, or application payloads.
- JBoss/WildFly Optimization Advisor telemetry reuses the existing JBoss
  `confapplstat.json` statistics entry and Java management client. Enable it
  with `optadvisor: true`, `appcode`, `server_id`, and optionally
  `optadvisor_technology: wildfly` when the backend target should be stored
  under WildFly metric definitions. It collects safe JVM, datasource, thread,
  and deployment status metrics without sending credentials, SQL contents,
  payloads, or sensitive application data.
- IBM ACE Optimization Advisor telemetry reuses the `ibmace`
  `confapplstat.json` statistics entry and the existing `midleoace.jar`
  Integration Admin API client. Enable it with `optadvisor: true`, `appcode`,
  `server_id`, and optionally `host`, `port`, and `server` for a specific
  integration server. It currently collects safe integration server and message
  flow status resources, plus safe default queue-manager relationship metadata
  where exposed.
- IBM IIB Optimization Advisor telemetry uses the `ibmiib`
  `confapplstat.json` statistics entry and the existing `midleoiib.jar`
  Integration API client. Enable it with `optadvisor: true`, `appcode`,
  `server_id`, and optionally `host`, `port`, and `server`/`execution_group`.
  It currently collects safe broker, execution-group, and message-flow status
  resources, plus safe default queue-manager metadata where exposed.
- Tibco EMS Optimization Advisor telemetry uses the `tibcoems`
  `confapplstat.json` statistics entry and the existing `midleo_tibco.jar`
  `TibjmsAdmin` client. Enable it with `optadvisor: true`, `appcode`,
  `server_id`, `host`/`tibcosrv`, `port`/`tibcoport`, and encrypted
  `pwd`/`tibcopass`. It collects safe server, queue and topic counters only;
  it never browses, consumes or sends JMS message content.

## Security Defaults

- Agent configuration files are deployed with mode `0640`.
- Runtime directories are owned by the Midleo service user and are not world-readable.
- Command execution is allowlist-based through `ALLOWED_COMMANDS`.
- Shell execution is disabled by default with `ALLOW_SHELL_COMMANDS=n`.
- Remote file writes are restricted by `REMOTE_FILE_ROOTS`.
- Action scripts are restricted by `ACTION_SCRIPT_ROOTS`.
- Application credential encryption uses `/etc/midleo/crypto.secret`, created by Linux automation with root ownership and service-user read access.
- HTTPS certificate verification is enabled by default with `SSLVERIFY=y`.
- systemd services run with additional hardening options where supported.
- z/OS started tasks must be assigned a RACF STARTED profile, OMVS segment/UID, filesystem access, and only the MQ authorities needed by configured collectors.

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

Common z/OS USS paths:

- Install root: `/u/midleoagent/`
- Agent config: `/u/midleoagent/config/mwagent.config`
- Cron sample: `/u/midleoagent/midleoagent.zos.crontab`
- Started-task samples: `/u/midleoagent/MIDLEOA.proc`, `/u/midleoagent/MIDLEOAC.proc`
- USS lifecycle wrapper: `/u/midleoagent/midleoagent.zos.sh`

z/OS service operations:

```sh
/u/midleoagent/midleoagent.zos.sh start
/u/midleoagent/midleoagent.zos.sh status
/u/midleoagent/cronjobs.zos.sh
```

For a true z/OS service, copy the reviewed PROC samples to a site PROCLIB and start them as `S MIDLEOA` and `S MIDLEOAC`. USS cron can run `cronjobs.zos.sh` every minute when the site allows the agent user to use `cron`.

For production, validate TLS, firewall rules, least-privilege command allowlists, and module-specific vendor libraries before onboarding customer hosts.
