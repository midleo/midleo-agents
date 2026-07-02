# Midleo Agent Ansible Deployment

This playbook installs the Midleo agent runtime and schedules collection on middleware servers.

## Quick Start

```bash
cd automation/ansible
ansible-playbook install_midleo_agent.yaml -i inventories/hosts
```

The playbook targets the `middleware` inventory group. Linux hosts are installed under `/var/midleoagent/`; Windows hosts are installed under `D:/apps/midleoagent/`; z/OS USS hosts default to `/u/midleoagent/`.

To update an existing Linux or z/OS USS agent without changing runtime configuration or logs:

```bash
ansible-playbook update_midleo_agent.yaml -i inventories/local-midleo.ini
```

The update playbook requires an existing `config/` directory and does not manage `config/`, `logs/`, `cronjobs.json`, `banned.json`, `mwagent.config`, `agent.identity`, or `crypto.secret`. It updates agent code, wrappers, modules, and runable scripts, then restarts the existing agent services or z/OS USS wrapper.

## Required Inventory Variables

Set these per host or group:

- `group_id`: Midleo Core group ID.
- `midleo_website_base_url`: Midleo Core host or base URL.
- `midleo_website_base_url_ssl`: `y` for HTTPS, `n` for HTTP.
- `update_interval_minutes`: server inventory update interval.
- `midleo_mwuser`: Linux service account, normally `mwadmin`.
- `agent_bootstrap_token`: bootstrap token used only for first agent registration. Runtime requests use the per-agent identity saved during registration.
- `allowed_commands`: command allowlist for remote operations.

Keep server-specific inventories in files matching `automation/ansible/inventories/local-*`; these are ignored by git.

Windows inventory also needs:

- `win_user`
- `win_pass`
- WinRM connection settings appropriate for the customer environment.

z/OS inventory should set:

- `midleo_agent_platform=zos`
- `midleo_zos_agent_install_dir`, default `/u/midleoagent/`
- `midleo_zos_python`, default `/usr/lpp/IBM/cyp/v3r12/pyz/bin/python3`
- `midleo_zos_python_home`, for example `/usr/lpp/IBM/cyp/v3r12/pyz`
- optional `midleo_zos_zpymqi_path`, the parent directory containing the z/OS `pymqi` package
- optional `midleo_zos_steplib`, the IBM MQ load libraries needed by `zpymqi`
- optional `midleo_zos_zoau_home`, if later JES job integration uses ZOAU
- optional `midleo_zos_install_cron=true`, only when USS cron access is approved

## Optional Variables

- `midleo_install_pymqi`: set to `true` only on IBM MQ hosts that have IBM MQ client development libraries installed.

## Installed Dependencies

Linux system packages:

- `gcc`
- `curl`
- `jq`
- `python3-dev` on Debian/Ubuntu or `python3-devel` on RHEL-family hosts
- `python3-pip`
- `python3-setuptools`

Python packages:

- `psutil`
- `py-cpuinfo`
- `dnspython`
- `requests`
- `pycryptodome`
- `pywinrm`
- `netifaces`
- optional: `pymqi`

`shlex` and `subprocess` are Python standard-library modules and are available in Python 3.6 and current Python releases.

z/OS Python dependencies are site managed. Install IBM Open Enterprise SDK for Python or an equivalent supported Python first, then provide required Python packages such as `pycryptodome` and `requests`. `zpymqi` is not installed with `pip`; transfer and unpack it per the local z/OS MQ standard, then set `ZOS_ZPYMQI_PATH` and `ZOS_STEPLIB`.

## Services and Schedule

Linux deployment creates:

- `midleoagent.service`
- `midleoactions.service`
- `/etc/cron.d/midleoagent`

The cron entry runs every minute and executes enabled jobs from `/var/midleoagent/config/cronjobs.json`. Jobs are bounded by `JOB_TIMEOUT_SECONDS`.

z/OS deployment creates USS runtime files and samples:

- `magent.zos.sh`
- `cronjobs.zos.sh`
- `midleoagent.zos.sh`
- `MIDLEOA.proc`
- `MIDLEOAC.proc`
- `midleoagent.zos.crontab`

There is no systemd on z/OS. For a service, review the BPXBATCH PROC samples, copy them to a site PROCLIB, define the RACF STARTED profiles, and start `MIDLEOA` and `MIDLEOAC`. For scheduling, install the sample crontab only after the site allows the agent user to use USS cron.

Linux deployment also creates `/etc/midleo/crypto.secret` once and preserves it across reinstall. This secret is used for local application credential encryption and must not be rotated without re-encrypting stored agent credentials.

## Vendor Libraries

Create `/midleolibs/lib` and `/midleolibs/vendor` on hosts that need Java or vendor-specific statistics modules.

`/midleolibs/lib`:

```text
activemq-client-6.1.6.jar
asm-7.0.jar
gson-2.10.1.jar
jackson-annotations-2.16.2.jar
jackson-core-2.16.2.jar
jackson-databind-2.16.2.jar
jackson-dataformat-yaml-2.16.0.jar
jackson-datatype-jsr310-2.16.0.jar
jaxb-api-2.3.0.jar
jboss-dmr-1.7.0.Final.jar
jetty-client.jar
jetty-http.jar
jetty-io.jar
jetty-util.jar
jffi-1.2.19.jar
jffi-1.2.19-native.jar
jms-2.0.jar
jmsclient.jar
jnr-a64asm-1.0.0.jar
jnr-constants-0.9.12.jar
jnr-enxio-0.21.jar
jnr-ffi-2.1.10.jar
jnr-posix-3.0.50.jar
jnr-unixsocket-0.23.jar
jnr-x86asm-1.0.2.jar
json-20231013.jar
kafka-clients-3.9.0.jar
kafka-schema-registry-client-7.8.0.jar
log4j-1.2.17.jar
org.apache.commons.io.jar
slf4j-api-2.0.9.jar
slf4j-simple-2.0.9.jar
snakeyaml-2.2.jar
websocket-api.jar
websocket-client.jar
websocket-common.jar
wildfly-client-all-35.0.1.Final.jar
wildfly-controller-client-28.0.0.Final.jar
wildfly-protocol-28.0.0.Final.jar
```

`/midleolibs/vendor`:

```text
bipbroker.jar
brokerutil.jar
com.ibm.mq.allclient.jar
com.ibm.mq.jmqi.jar
IntegrationAPI_ACE.jar
IntegrationAPI_IIB.jar
tibemsd_sec.jar
tibjmsadmin.jar
tibjmsapps.jar
tibjms.jar
tibrvjms.jar
```

## Production Checks

After deployment:

```bash
systemctl status midleoagent midleoactions
crontab -u mwadmin -l
test -f /var/midleoagent/config/mwagent.config
test -f /var/midleoagent/config/cronjobs.json
test -f /etc/midleo/crypto.secret
```

Review `ALLOWED_COMMANDS`, `REMOTE_FILE_ROOTS`, `ACTION_SCRIPT_ROOTS`, `SSLVERIFY`, firewall rules, and the Midleo Core endpoint before exposing the service to enterprise networks. Avoid allowing raw `sudo`, `docker`, shells, or interpreters unless the customer explicitly accepts that operational risk.

On z/OS, `magent.zos.sh enabletrackqm|disabletrackqm` runs `RUNMQSC` directly. The USS user or started-task identity must have the MQ/RACF permissions; the Linux `sudo -u mqm` model does not apply.
