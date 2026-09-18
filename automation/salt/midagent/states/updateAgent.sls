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

midagent_render_config_defaults:
  file.managed:
    - name: {{ agent_install_dir }}config/.mwagent.config.desired
    - source: salt://midagent/templates/mwagent.config.merge.j2
    - template: jinja
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0600'
    - context:
        weblogic_home: "{{ salt['pillar.get']('INPUT:weblogic_home', salt['pillar.get']('midagent_vars:weblogic_home', '/opt/oracle/middleware')) }}"
        ibmmq_home: "{{ salt['pillar.get']('INPUT:ibmmq_home', salt['pillar.get']('midagent_vars:ibmmq_home', '/opt/mqm')) }}"
        ibmace_home: "{{ salt['pillar.get']('INPUT:ibmace_home', salt['pillar.get']('midagent_vars:ibmace_home', '/opt/ibm/ace-12/server')) }}"
        ibmiib_home: "{{ salt['pillar.get']('INPUT:ibmiib_home', salt['pillar.get']('midagent_vars:ibmiib_home', '/opt/ibm/iib-10.0.0.11/server')) }}"
        tomcat_home: "{{ salt['pillar.get']('INPUT:tomcat_home', salt['pillar.get']('midagent_vars:tomcat_home', '')) }}"
        jboss_home: "{{ salt['pillar.get']('INPUT:jboss_home', salt['pillar.get']('midagent_vars:jboss_home', '')) }}"
        ibmwas_home: "{{ salt['pillar.get']('INPUT:ibmwas_home', salt['pillar.get']('midagent_vars:ibmwas_home', '')) }}"
        rabbitmq_home: "{{ salt['pillar.get']('INPUT:rabbitmq_home', salt['pillar.get']('midagent_vars:rabbitmq_home', '')) }}"
        tibcoems_home: "{{ salt['pillar.get']('INPUT:tibcoems_home', salt['pillar.get']('midagent_vars:tibcoems_home', '')) }}"
        activemq_home: "{{ salt['pillar.get']('INPUT:activemq_home', salt['pillar.get']('midagent_vars:activemq_home', '')) }}"
        kafka_home: "{{ salt['pillar.get']('INPUT:kafka_home', salt['pillar.get']('midagent_vars:kafka_home', '')) }}"
        msiis_home: "{{ salt['pillar.get']('INPUT:msiis_home', salt['pillar.get']('midagent_vars:msiis_home', '')) }}"
    - require:
      - test: midagent_update_existing_config_required
    - onlyif: test -f {{ agent_install_dir }}config/mwagent.config

midagent_copy_merge_helper:
  file.managed:
    - name: {{ agent_install_dir }}config/.merge_mwagent_config.py
    - source: salt://midagent/files/merge_mwagent_config.py
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0700'
    - require:
      - file: midagent_render_config_defaults
    - onlyif: test -f {{ agent_install_dir }}config/mwagent.config

midagent_merge_config:
  cmd.run:
    - name: |
        {{ python_install_dir }} {{ agent_install_dir }}config/.merge_mwagent_config.py {{ agent_install_dir }}config/mwagent.config {{ agent_install_dir }}config/.mwagent.config.desired
        status=$?
        rm -f {{ agent_install_dir }}config/.mwagent.config.desired {{ agent_install_dir }}config/.merge_mwagent_config.py
        exit $status
    - python_shell: True
    - require:
      - file: midagent_copy_merge_helper
    - onlyif: test -f {{ agent_install_dir }}config/mwagent.config

midagent_secure_config_after_merge:
  file.managed:
    - name: {{ agent_install_dir }}config/mwagent.config
    - user: {{ midleo_mwuser }}
    - group: {{ midleo_mwuser }}
    - mode: '0600'
    - replace: False
    - require:
      - cmd: midagent_merge_config

midagent_stop_agent_service:
  service.dead:
    - name: midleoagent

{% if not is_zos %}
midagent_stop_actions_service:
  service.dead:
    - name: midleoactions
{% endif %}

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

midagent_update_sudoer:
  file.managed:
    - user: root
    - group: root
    - mode: '0440'
    - template: jinja
    - names:
      - /etc/sudoers.d/{{ midleo_mwuser }}.conf:
        - source: salt://midagent/templates/mwadmin.sudo.j2
    - context:
        midleo_mwuser: "{{ midleo_mwuser }}"
        weblogic_home: "{{ salt['pillar.get']('INPUT:weblogic_home', salt['pillar.get']('midagent_vars:weblogic_home', '/opt/oracle/middleware')) }}"
        ibmmq_home: "{{ salt['pillar.get']('INPUT:ibmmq_home', salt['pillar.get']('midagent_vars:ibmmq_home', '/opt/mqm')) }}"
        ibmace_home: "{{ salt['pillar.get']('INPUT:ibmace_home', salt['pillar.get']('midagent_vars:ibmace_home', '/opt/ibm/ace-12/server')) }}"
        ibmiib_home: "{{ salt['pillar.get']('INPUT:ibmiib_home', salt['pillar.get']('midagent_vars:ibmiib_home', '/opt/ibm/iib-10.0.0.11/server')) }}"
        tomcat_home: "{{ salt['pillar.get']('INPUT:tomcat_home', salt['pillar.get']('midagent_vars:tomcat_home', '')) }}"
        jboss_home: "{{ salt['pillar.get']('INPUT:jboss_home', salt['pillar.get']('midagent_vars:jboss_home', '')) }}"
        ibmwas_home: "{{ salt['pillar.get']('INPUT:ibmwas_home', salt['pillar.get']('midagent_vars:ibmwas_home', '')) }}"
        rabbitmq_home: "{{ salt['pillar.get']('INPUT:rabbitmq_home', salt['pillar.get']('midagent_vars:rabbitmq_home', '')) }}"
        tibcoems_home: "{{ salt['pillar.get']('INPUT:tibcoems_home', salt['pillar.get']('midagent_vars:tibcoems_home', '')) }}"
        activemq_home: "{{ salt['pillar.get']('INPUT:activemq_home', salt['pillar.get']('midagent_vars:activemq_home', '')) }}"
        kafka_home: "{{ salt['pillar.get']('INPUT:kafka_home', salt['pillar.get']('midagent_vars:kafka_home', '')) }}"
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
