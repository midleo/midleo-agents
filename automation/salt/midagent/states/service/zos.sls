# Create folders and install the z/OS USS agent runtime.

{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir', '/u/midleoagent/') %}
{% set python_install_dir = salt['pillar.get']('midagent_vars:python_install_dir', '/usr/lpp/IBM/cyp/v3r12/pyz/bin/python3') %}
{% set mwuser = salt['pillar.get']('midagent_vars:mwuser', 'MWADMIN') %}
{% set midleo_website_base_url = salt['pillar.get']('INPUT:midleo_website_base_url') %}
{% set midleo_website_base_url_ssl = salt['pillar.get']('INPUT:midleo_website_base_url_ssl') %}
{% set group_id = salt['pillar.get']('INPUT:group_id') %}
{% set agent_bootstrap_token = salt['pillar.get']('INPUT:agent_bootstrap_token') %}
{% set update_interval_minutes = salt['pillar.get']('INPUT:update_interval_minutes') %}
{% set install_cron = salt['pillar.get']('INPUT:install_cron', False) %}
{% set agent_unique_id = salt['cmd.run'](cmd=python_install_dir ~ " -c \"import secrets; print(secrets.token_hex(8))\"", python_shell=True) %}

{{agent_install_dir}}:
  file.directory:
    - name: {{agent_install_dir}}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 750
    - makedirs: True

{% for dir in 'modules', 'logs', 'run', 'runable', 'config', 'extchecks' %}
{{agent_install_dir}}{{ dir }}:
  file.directory:
    - name: {{agent_install_dir}}{{ dir }}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 750
    - makedirs: True
{% endfor %}

midagent_zos_private_dirs:
  file.directory:
    - names:
      - {{agent_install_dir}}logs
      - {{agent_install_dir}}config
      - {{agent_install_dir}}run
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 700
    - makedirs: True

midagent_zos_create_client:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0750'
    - template: jinja
    - names:
      - {{agent_install_dir}}midleo_client.py:
        - source: salt://midagent/templates/python/midleo_client.py
      - {{agent_install_dir}}midleo_actions.py:
        - source: salt://midagent/templates/python/midleo_actions.py

midagent_zos_create_script:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}magent.zos.sh:
        - source: salt://midagent/templates/python/magent.zos.sh
      - {{agent_install_dir}}cronjobs.zos.sh:
        - source: salt://midagent/templates/python/cronjobs.zos.sh
      - {{agent_install_dir}}midleoagent.zos.sh:
        - source: salt://midagent/templates/python/midleoagent.zos.sh
      - {{agent_install_dir}}zos_env.sh:
        - source: salt://midagent/templates/python/zos_env.sh

midagent_zos_create_config_files:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0600'
    - template: jinja
    - names:
      - {{agent_install_dir}}config/cronjobs.json:
        - source: salt://midagent/templates/python/config/cronjobs.json
      - {{agent_install_dir}}config/banned.json:
        - source: salt://midagent/templates/python/config/banned.json
    - replace: False

midagent_zos_create_crypto_secret:
  cmd.run:
    - name: umask 077 && {{python_install_dir}} -c "import secrets; print(secrets.token_urlsafe(48))" > {{agent_install_dir}}config/crypto.secret
    - unless: test -f {{agent_install_dir}}config/crypto.secret
    - python_shell: True
    - require:
      - file: midagent_zos_private_dirs

{% if not salt['file.file_exists'](agent_install_dir+'config/mwagent.config') %}
midagent_zos_create_config:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0600'
    - template: jinja
    - names:
      - {{agent_install_dir}}config/mwagent.config:
        - source: salt://midagent/templates/mwagent.config.j2
    - context:
        agent_unique_id: "{{agent_unique_id}}"
        midleo_website_base_url: "{{midleo_website_base_url}}"
        midleo_website_base_url_ssl: "{{midleo_website_base_url_ssl}}"
        group_id: "{{group_id}}"
        agent_bootstrap_token: "{{agent_bootstrap_token}}"
        agent_install_dir: "{{agent_install_dir}}"
        allowed_commands:
          - magent.zos.sh
          - dspmq
          - dspmqver
        update_interval_minutes: "{{update_interval_minutes}}"
        python_install_dir: "{{python_install_dir}}"
        midleo_zos_python_home: "{{ salt['pillar.get']('INPUT:midleo_zos_python_home', '') }}"
        midleo_zos_zpymqi_path: "{{ salt['pillar.get']('INPUT:midleo_zos_zpymqi_path', '') }}"
        midleo_zos_steplib: "{{ salt['pillar.get']('INPUT:midleo_zos_steplib', '') }}"
        midleo_zos_zoau_home: "{{ salt['pillar.get']('INPUT:midleo_zos_zoau_home', '') }}"
{% endif %}

midagent_zos_secure_config:
  file.managed:
    - name: {{agent_install_dir}}config/mwagent.config
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0600'
    - replace: False

midagent_zos_create_client_modules:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - names:
      - {{agent_install_dir}}modules:
        - source: salt://midagent/templates/python/modules

midagent_zos_create_client_runable:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - names:
      - {{agent_install_dir}}runable:
        - source: salt://midagent/templates/python/runable

midagent_zos_create_samples:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0640'
    - template: jinja
    - names:
      - {{agent_install_dir}}MIDLEOA.proc:
        - source: salt://midagent/templates/agent_zos_started_task.j2
      - {{agent_install_dir}}MIDLEOAC.proc:
        - source: salt://midagent/templates/agent_zos_actions_started_task.j2
      - {{agent_install_dir}}midleoagent.zos.crontab:
        - source: salt://midagent/templates/agent_zos_crontab.j2
    - context:
        agent_install_dir: "{{agent_install_dir}}"

{% if install_cron in [True, 'true', 'True', 'TRUE', 'y', 'Y', 'yes', 'YES', '1', 1] %}
midagent_zos_cronjob:
  cron.present:
    - name: {{agent_install_dir}}cronjobs.zos.sh >> {{agent_install_dir}}logs/cronjobs.zos.out 2>&1
    - user: {{mwuser}}
    - minute: '*'
    - hour: '*'
    - daymonth: '*'
    - month: '*'
    - dayweek: '*'
    - require:
      - file: midagent_zos_create_script
{% endif %}
