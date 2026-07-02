{% set osname = grains.get('os', '') %}
{% set kernel = grains.get('kernel', '') %}
{% set is_zos = osname|lower in ['zos', 'z/os'] or kernel in ['OS/390', 'z/OS'] %}
{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir', '/u/midleoagent/' if is_zos else '/var/midleoagent/') %}
{% set python_install_dir = salt['pillar.get']('midagent_vars:python_install_dir', '/usr/bin/python3') %}
{% set midleo_mwuser = salt['pillar.get']('midagent_vars:midleo_mwuser', 'MWADMIN' if is_zos else 'mwadmin') %}

midagent_update_existing_config_required:
  test.fail_without_changes:
    - name: Existing {{ agent_install_dir }}config directory is required. Use midagent.installAgent for first install.
    - unless: test -d {{ agent_install_dir }}config

midagent_stop_agent_service:
  service.dead:
    - name: midleoagent

midagent_truncate_agent_log:
  file.managed:
    - name: {{ agent_install_dir }}logs/midleoagent.log
    - contents: ''
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0600'
    - require:
      - service: midagent_stop_agent_service

{% if is_zos %}
midagent_zos_update_client:
  file.managed:
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0750'
    - template: jinja
    - names:
      - {{ agent_install_dir }}midleo_client.py:
        - source: salt://midagent/templates/python/midleo_client.py
      - {{ agent_install_dir }}midleo_actions.py:
        - source: salt://midagent/templates/python/midleo_actions.py
    - require:
      - test: midagent_update_existing_config_required

midagent_zos_update_scripts:
  file.managed:
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0755'
    - template: jinja
    - names:
      - {{ agent_install_dir }}magent.zos.sh:
        - source: salt://midagent/templates/python/magent.zos.sh
      - {{ agent_install_dir }}cronjobs.zos.sh:
        - source: salt://midagent/templates/python/cronjobs.zos.sh
      - {{ agent_install_dir }}midleoagent.zos.sh:
        - source: salt://midagent/templates/python/midleoagent.zos.sh
      - {{ agent_install_dir }}zos_env.sh:
        - source: salt://midagent/templates/python/zos_env.sh
    - context:
        python_install_dir: "{{python_install_dir}}"
    - require:
      - test: midagent_update_existing_config_required

midagent_zos_update_modules:
  file.recurse:
    - name: {{ agent_install_dir }}modules
    - source: salt://midagent/templates/python/modules
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - clean: False
    - include_empty: True
    - exclude_pat: E@.*(__pycache__|\.pyc$).*
    - require:
      - test: midagent_update_existing_config_required

midagent_zos_update_runable:
  file.recurse:
    - name: {{ agent_install_dir }}runable
    - source: salt://midagent/templates/python/runable
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - dir_mode: 2750
    - file_mode: '0755'
    - makedirs: True
    - clean: False
    - include_empty: True
    - exclude_pat: E@.*(__pycache__|\.pyc$).*
    - require:
      - test: midagent_update_existing_config_required

midagent_zos_restart_after_update:
  cmd.run:
    - name: {{ agent_install_dir }}midleoagent.zos.sh restart
    - onlyif: test -x {{ agent_install_dir }}midleoagent.zos.sh
    - python_shell: True
    - onchanges:
      - file: midagent_zos_update_client
      - file: midagent_zos_update_scripts
      - file: midagent_zos_update_modules
      - file: midagent_zos_update_runable
{% else %}
midagent_update_client:
  file.managed:
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0750'
    - template: jinja
    - names:
      - {{ agent_install_dir }}midleo_client.py:
        - source: salt://midagent/templates/python/midleo_client.py
      - {{ agent_install_dir }}midleo_actions.py:
        - source: salt://midagent/templates/python/midleo_actions.py
    - require:
      - test: midagent_update_existing_config_required

midagent_update_scripts:
  file.managed:
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0755'
    - template: jinja
    - names:
      - {{ agent_install_dir }}magent.sh:
        - source: salt://midagent/templates/python/magent.sh
      - {{ agent_install_dir }}magent_docker.sh:
        - source: salt://midagent/templates/python/magent_docker.sh
      - {{ agent_install_dir }}cronjobs.sh:
        - source: salt://midagent/templates/python/cronjobs.sh
    - context:
        python_install_dir: "{{python_install_dir}}"
    - require:
      - test: midagent_update_existing_config_required

midagent_update_modules:
  file.recurse:
    - name: {{ agent_install_dir }}modules
    - source: salt://midagent/templates/python/modules
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - dir_mode: 2750
    - file_mode: '0640'
    - makedirs: True
    - clean: False
    - include_empty: True
    - exclude_pat: E@.*(__pycache__|\.pyc$).*
    - require:
      - test: midagent_update_existing_config_required

midagent_update_runable:
  file.recurse:
    - name: {{ agent_install_dir }}runable
    - source: salt://midagent/templates/python/runable
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - dir_mode: 2750
    - file_mode: '0755'
    - makedirs: True
    - clean: False
    - include_empty: True
    - exclude_pat: E@.*(__pycache__|\.pyc$).*
    - require:
      - test: midagent_update_existing_config_required

midagent_update_agent_service:
  service.running:
    - name: midleoagent
    - enable: True
    - watch:
      - file: midagent_update_client
      - file: midagent_update_scripts
      - file: midagent_update_modules
      - file: midagent_update_runable

midagent_update_actions_service:
  service.running:
    - name: midleoactions
    - enable: True
    - watch:
      - file: midagent_update_client
      - file: midagent_update_scripts
      - file: midagent_update_modules
      - file: midagent_update_runable
{% endif %}
