# Midleo Agent Salt Deployment

This Salt formula installs the Linux Midleo agent service, action service, and cron runner. It also includes a z/OS USS path that installs the Python runtime files, USS wrappers, cron sample, and BPXBATCH started-task samples.

## Quick Start

Create `midagent.conf`:

```bash
midleo_website_base_url="MIDLEO_BASE_URL"
midleo_website_base_url_ssl="y"
group_id="MIDLEO_GROUP_ID"
agent_bootstrap_token="MIDLEO_AGENT_BOOTSTRAP_TOKEN"
update_interval_minutes="5"
install_pymqi="false"

pillar='{"INPUT":{"midleo_website_base_url":"'$midleo_website_base_url'","midleo_website_base_url_ssl":"'$midleo_website_base_url_ssl'","group_id":"'$group_id'","agent_bootstrap_token":"'$agent_bootstrap_token'","update_interval_minutes":"'$update_interval_minutes'","install_pymqi":"'$install_pymqi'"}}'
```

Apply the state:

```bash
. midagent.conf
salt-call -c saltconfig state.apply midagent.installAgent pillar="$pillar"
```

## Pillar Variables

Runtime input:

- `INPUT:midleo_website_base_url`: Midleo Core host or base URL.
- `INPUT:midleo_website_base_url_ssl`: `y` for HTTPS, `n` for HTTP.
- `INPUT:group_id`: Midleo Core group ID.
- `INPUT:agent_bootstrap_token`: bootstrap token used only for first agent registration. Runtime requests use the per-agent identity saved during registration.
- `INPUT:update_interval_minutes`: server inventory update interval.
- `INPUT:install_pymqi`: optional, install `pymqi` on IBM MQ hosts only.

Static defaults are in `pillars/midagent_vars.sls`:

- `agent_install_dir`: default `/var/midleoagent/`
- `python_install_dir`: default `/usr/bin/python3`
- `mwuser`: default `mwadmin`

For z/OS USS, override the static defaults before applying the state:

- `agent_install_dir`: normally `/u/midleoagent/`
- `python_install_dir`: for example `/usr/lpp/IBM/cyp/v3r12/pyz/bin/python3`
- `mwuser`: the RACF user or started-task identity that owns the USS files

Optional z/OS input pillars:

- `INPUT:midleo_zos_python_home`
- `INPUT:midleo_zos_zpymqi_path`
- `INPUT:midleo_zos_steplib`
- `INPUT:midleo_zos_zoau_home`
- `INPUT:install_cron`, default `false`

## Installed Dependencies

System packages:

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

`shlex`, `subprocess`, `asyncio`, and the other base runtime imports are Python standard-library modules and are not installed separately.

On z/OS, package installation is intentionally site managed. Install IBM Open Enterprise SDK for Python or an equivalent supported Python, then install required Python packages such as `pycryptodome` and `requests`. For IBM MQ local statistics, deploy a z/OS-capable PyMQI port such as `zpymqi`, then set `ZOS_ZPYMQI_PATH` and `ZOS_STEPLIB`.

## Services and Files

The state creates:

- `/var/midleoagent/`
- `/var/midleoagent/config/mwagent.config`
- `/var/midleoagent/config/cronjobs.json`
- `/etc/midleo/crypto.secret`
- `/etc/systemd/system/midleoagent.service`
- `/etc/systemd/system/midleoactions.service`
- a per-minute cron entry for the Midleo service user.

On z/OS USS, the state creates:

- `/u/midleoagent/` or the configured install root
- `magent.zos.sh`, `cronjobs.zos.sh`, `midleoagent.zos.sh`, and `zos_env.sh`
- `config/mwagent.config`
- `config/crypto.secret`
- `MIDLEOA.proc` and `MIDLEOAC.proc` BPXBATCH started-task samples
- `midleoagent.zos.crontab`

The state does not copy PROC members to PROCLIB, define RACF STARTED profiles, or start the tasks. Those are site-controlled z/OS system programming actions.

Executable demo app-server registration states are not part of the production install. Register application servers through Midleo Core or explicit Salt states with customer-specific data.

## Vendor Libraries

Create `/midleolibs/lib` and `/midleolibs/vendor` only on hosts that need the related middleware modules.

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

```bash
systemctl status midleoagent midleoactions
crontab -u mwadmin -l
test -f /etc/midleo/crypto.secret
salt-call state.apply midagent.installAgent test=True pillar="$pillar"
```

Before customer rollout, verify TLS trust, firewall rules, `ALLOWED_COMMANDS`, `REMOTE_FILE_ROOTS`, `ACTION_SCRIPT_ROOTS`, and the Midleo Core endpoint. Avoid allowing raw `sudo`, `docker`, shells, or interpreters unless the customer explicitly accepts that operational risk.

For z/OS rollout, also verify the OMVS segment/UID, STARTED class mapping, USS file tags or `_BPXK_AUTOCVT`, port 5550 access, cron authorization, and MQ authority for `RUNMQSC`. ZOAU can be added later for JES job operations; see https://www.ibm.com/docs/en/zoau/1.3.x?topic=apis-jobs.
