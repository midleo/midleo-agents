#create folders and install agent

{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir') %}
{% set python_install_dir = salt['pillar.get']('midagent_vars:python_install_dir') %}
{% set mwuser = salt['pillar.get']('midagent_vars:mwuser') %}
{% set midleo_website_base_url = salt['pillar.get']('INPUT:midleo_website_base_url') %}
{% set midleo_website_base_url_ssl = salt['pillar.get']('INPUT:midleo_website_base_url_ssl') %}
{% set group_id = salt['pillar.get']('INPUT:group_id') %}
{% set int_token = salt['pillar.get']('INPUT:int_token') %}
{% set update_interval_minutes = salt['pillar.get']('INPUT:update_interval_minutes') %}
{% set osfam = grains.get('os_family', '') %}
{% set agent_unique_id = salt['cmd.run'](cmd="head -c 8 /dev/urandom | xxd -p", python_shell=True) %}

midagent_create_group:
   group.present:
      - name: {{mwuser}}

midagent_create_user:
   user.present:
      - name: {{mwuser}}
      - fullname: "Middleware admin local user"
      - createhome: True
      - shell: /bin/bash
      - gid: {{mwuser}}
      - allow_gid_change: True
      - groups:
         - {{mwuser}}
      - require:
         - group: midagent_create_group

#add aditional groups if exist
midagent_add_docker:
  user.present:
    - name: {{mwuser}}
    - optional_groups:
      - docker
    - remove_groups: False
    - require:
      - user: midagent_create_user

/etc/midleo:
  file.directory:
    - name: /etc/midleo
    - user: root
    - group: {{mwuser}}
    - dir_mode: 750
    - makedirs: True

midagent_create_crypto_secret:
  cmd.run:
    - name: umask 027 && head -c 48 /dev/urandom | base64 > /etc/midleo/crypto.secret
    - unless: test -f /etc/midleo/crypto.secret
    - require:
      - file: /etc/midleo

midagent_secure_crypto_secret:
  file.managed:
    - name: /etc/midleo/crypto.secret
    - user: root
    - group: {{mwuser}}
    - mode: '0640'
    - replace: False
    - require:
      - cmd: midagent_create_crypto_secret

{{agent_install_dir}}:
  file.directory:
    - name: {{agent_install_dir}}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 750
    - makedirs: True

{% for dir in 'modules', 'logs', 'runable', 'config', 'extchecks' %}
{{agent_install_dir}}{{ dir }}:
  file.directory:
    - name: {{agent_install_dir}}{{ dir }}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 750
    - makedirs: True
{% endfor %}

midagent_create_client:
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

midagent_create_script:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}magent.sh:
        - source: salt://midagent/templates/python/magent.sh
      - {{agent_install_dir}}magent.bat:
        - source: salt://midagent/templates/python/magent.bat
      - {{agent_install_dir}}cronjobs.sh:
        - source: salt://midagent/templates/python/cronjobs.sh
      - {{agent_install_dir}}cronjobs.bat:
        - source: salt://midagent/templates/python/cronjobs.bat
      - {{agent_install_dir}}config/cronjobs.json:
        - source: salt://midagent/templates/python/config/cronjobs.json
    - context:
        python_install_dir: "{{python_install_dir}}"

midagent_secure_cronjobs_config:
  file.managed:
    - name: {{agent_install_dir}}config/cronjobs.json
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0640'
    - replace: False

midagent_create_client_modules:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - names:
      - {{agent_install_dir}}modules:
        - source: salt://midagent/templates/python/modules

midagent_create_client_runable:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - names:
      - {{agent_install_dir}}runable:
        - source: salt://midagent/templates/python/runable

{% if not salt['file.file_exists'](agent_install_dir+'config/mwagent.config') %}
midagent_create_config:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0640'
    - template: jinja
    - names:
      - {{agent_install_dir}}config/mwagent.config:
        - source: salt://midagent/templates/mwagent.config.j2
    - context:
        agent_unique_id: "{{agent_unique_id}}"
        midleo_website_base_url: "{{midleo_website_base_url}}"
        midleo_website_base_url_ssl: "{{midleo_website_base_url_ssl}}"
        group_id: "{{group_id}}"
        inttoken: "{{int_token}}"
        agent_install_dir: "{{agent_install_dir}}"
        allowed_commands: 
          - magent.sh
          - dspmq
          - dspmqver
          {% if osfam == "Linux" %}
          - uptime
          {% endif %}
          {% if osfam == "Windows" %}
          - magent.bat
          - net
          {% endif %}
        update_interval_minutes: "{{update_interval_minutes}}"
        python_install_dir: "{{python_install_dir}}"
{% endif %}

midagent_secure_config:
  file.managed:
    - name: {{agent_install_dir}}config/mwagent.config
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0640'
    - replace: False

midagent_create_sudoer:
  file.managed:
    - user: root
    - group: root
    - mode: '0440'
    - template: jinja
    - names:
      - /etc/sudoers.d/{{mwuser}}.conf:
        - source: salt://midagent/templates/mwadmin.sudo.j2
    - context:
        mwuser: "{{mwuser}}"

/etc/cron.allow:
   file.append:
      - text: '{{mwuser}}'

midagent_create_service:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - template: jinja
    - names:
      - /etc/systemd/system/midleoagent.service:
        - source: salt://midagent/templates/agent_linux_service.j2
    - context:
        agent_install_dir: "{{agent_install_dir}}"
        python_install_dir: "{{python_install_dir}}"
        mwuser: "{{mwuser}}"

midagent_create_actions_service:
  file.managed:
    - user: root
    - group: root
    - mode: '0644'
    - template: jinja
    - names:
      - /etc/systemd/system/midleoactions.service:
        - source: salt://midagent/templates/agent_linux_actions_service.j2
    - context:
        agent_install_dir: "{{agent_install_dir}}"
        python_install_dir: "{{python_install_dir}}"
        mwuser: "{{mwuser}}"

midagent.service:
   service.running:
     - name: midleoagent
     - enable: True
     - require:
       - file: midagent_create_service
       - file: midagent_create_client

midagent.actions.service:
   service.running:
     - name: midleoactions
     - enable: True
     - require:
       - file: midagent_create_actions_service
       - file: midagent_create_client

midagent.legacy_restart_cron:
  cron.absent:
    - name: service midleoagent stop && sleep 5 && service midleoagent start \;
    - user: root

midagent.cronjob:
  cron.present:
    - name: {{agent_install_dir}}cronjobs.sh \;
    - user: {{mwuser}}
    - minute: '*'
    - hour: '*'
    - daymonth: '*'
    - month: '*'
    - dayweek: '*'
    - require:
      - file: midagent_create_script
