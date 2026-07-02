{% set osname = grains.get('os', '') %}
{% set kernel = grains.get('kernel', '') %}
{% set is_zos = osname|lower in ['zos', 'z/os'] or kernel in ['OS/390', 'z/OS'] %}
{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir', '/u/midleoagent/' if is_zos else '/var/midleoagent/') %}
{% set midleo_mwuser = salt['pillar.get']('midagent_vars:midleo_mwuser', 'MWADMIN' if is_zos else 'mwadmin') %}
{% set remove_secrets = salt['pillar.get']('INPUT:remove_secrets', False) %}

{% if is_zos %}
midagent_zos_stop_services:
  cmd.run:
    - name: {{ agent_install_dir }}midleoagent.zos.sh stop
    - onlyif: test -x {{ agent_install_dir }}midleoagent.zos.sh
    - python_shell: True
    - ignore_retcode: True

midagent_zos_cron_absent:
  cron.absent:
    - name: {{ agent_install_dir }}cronjobs.zos.sh >> {{ agent_install_dir }}logs/cronjobs.zos.out 2>&1
    - user: {{ midleo_mwuser }}

midagent_zos_runtime_absent:
  file.absent:
    - name: {{ agent_install_dir }}
    - require:
      - cmd: midagent_zos_stop_services
{% else %}
midagent_service_dead:
  service.dead:
    - name: midleoagent
    - enable: False

midagent_actions_service_dead:
  service.dead:
    - name: midleoactions
    - enable: False

midagent_service_file_absent:
  file.absent:
    - name: /etc/systemd/system/midleoagent.service
    - require:
      - service: midagent_service_dead

midagent_actions_service_file_absent:
  file.absent:
    - name: /etc/systemd/system/midleoactions.service
    - require:
      - service: midagent_actions_service_dead

midagent_cron_absent:
  cron.absent:
    - name: {{ agent_install_dir }}cronjobs.sh \;
    - user: {{ midleo_mwuser }}

midagent_sudoer_absent:
  file.absent:
    - name: /etc/sudoers.d/{{ midleo_mwuser }}.conf

midagent_runtime_absent:
  file.absent:
    - name: {{ agent_install_dir }}
    - require:
      - service: midagent_service_dead
      - service: midagent_actions_service_dead

{% if remove_secrets in [True, 'true', 'True', 'TRUE', 'y', 'Y', 'yes', 'YES', '1', 1] %}
midagent_crypto_secret_absent:
  file.absent:
    - name: /etc/midleo/crypto.secret

midagent_crypto_dir_absent:
  file.absent:
    - name: /etc/midleo
    - require:
      - file: midagent_crypto_secret_absent
{% endif %}
{% endif %}
