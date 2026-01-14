#create folders and install agent

{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir') %}
{% set python_install_dir = salt['pillar.get']('midagent_vars:python_install_dir') %}
{% set mwuser = salt['pillar.get']('midagent_vars:mwuser') %}
{% set midleo_website_base_url = salt['pillar.get']('INPUT:midleo_website_base_url') %}
{% set midleo_website_base_url_ssl = salt['pillar.get']('INPUT:midleo_website_base_url_ssl') %}
{% set group_id = salt['pillar.get']('INPUT:group_id') %}
{% set int_token = salt['pillar.get']('INPUT:int_token') %}
{% set update_interval_minutes = salt['pillar.get']('INPUT:update_interval_minutes') %}
{% set mwtoken = salt['pillar.get']('midagent_vars:mwtoken') %}
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

#add aditional groups if exist
midagent_add_docker:
  user.present:
    - optional_groups:
      - docker
    - remove_groups: False

{{agent_install_dir}}:
  file.directory:
    - name: {{agent_install_dir}}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 755
    - makedirs: True

{% for dir in 'modules', 'logs', 'runable', 'config', 'extchecks' %}
{{agent_install_dir}}{{ dir }}:
  file.directory:
    - name: {{agent_install_dir}}{{ dir }}
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 755
    - makedirs: True
{% endfor %}

midagent_create_client:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}midleo_client.py:
        - source: salt://midagent/templates/python/midleo_client.py

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
    - context:
        python_install_dir: "{{python_install_dir}}"

midagent_create_client_modules:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2775
    - file_mode: '0644'
    - makedirs: True
    - names:
      - {{agent_install_dir}}modules:
        - source: salt://midagent/templates/python/modules

midagent_create_client_runable:
  file.recurse:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - dir_mode: 2775
    - file_mode: '0644'
    - makedirs: True
    - names:
      - {{agent_install_dir}}runable:
        - source: salt://midagent/templates/python/runable

{% if not salt['file.file_exists'](agent_install_dir+'config/mwagent.config') %}
midagent_create_config:
  file.managed:
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0755'
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
        allowed_commands: 
          - dspmq
          - dspmqver
          - runmqsc
          - amqsevt
          {% if osfam == "Linux" %}
          - uptime
          {% endif %}
          {% if osfam == "Windows" %}
          - net
          {% endif %}
        update_interval_minutes: "{{update_interval_minutes}}"
        python_install_dir: "{{python_install_dir}}"
{% endif %}

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
    - user: {{mwuser}}
    - group: {{mwuser}}
    - mode: '0755'
    - template: jinja
    - names:
      - /etc/systemd/system/midleoagent.service:
        - source: salt://midagent/templates/agent_linux_service.j2
    - context:
        agent_install_dir: "{{agent_install_dir}}"
        python_install_dir: "{{python_install_dir}}"
        mwuser: "{{mwuser}}"

midagent.service:
   service.running:
     - name: midleoagent
     - enable: True

midagent.cron:
  cron.present:
    - name: service midleoagent stop && sleep 5 && service midleoagent start \;
    - user: root
    - minute: 00
    - hour: 01
    - daymonth: '*'
    - month: '*'
    - dayweek: '*'

midagent.cronjob:
  cron.present:
    - name: {{agent_install_dir}}cronjobs.sh \;
    - user: {{mwuser}}
    - minute: '*'
    - hour: '*'
    - daymonth: '*'
    - month: '*'
    - dayweek: '*'

#register appserver on mwadmin
midagent_registerappsrv:
  mwagent_ext.register_appsrv:
     - token: {{ mwtoken }}
     - appcode: "TEST"
     - proj: "sys"
     - srvdata: 
         appsrv_type: "ibmiib"  #ibmace/ibmmq/jboss...
         srvname: "INTSRV"      #name of the application server
         app_port: 9999         #the port for the application server
         appuser: "username"    #in case user is used for the app server access
         apppass: "pass"        #in case password is used for the app server access
         
#enable availability
midagent_enableavl:
  cmd.run:
     - runas: {{mwuser}}
     - name: |
         {{agent_install_dir}}magent.sh enableavl {{srvname}} {{appsrv_type}}
        