#create folders and install agent

{% set agent_install_dir = salt['pillar.get']('midagent_vars:agent_install_dir') %}
{% set python_install_dir = salt['pillar.get']('midagent_vars:python_install_dir') %}
{% set midleo_website_base_url = salt['pillar.get']('INPUT:midleo_website_base_url') %}
{% set midleo_website_base_url_ssl = salt['pillar.get']('INPUT:midleo_website_base_url_ssl') %}
{% set group_id = salt['pillar.get']('INPUT:group_id') %}
{% set update_interval_minutes = salt['pillar.get']('INPUT:update_interval_minutes') %}

{% set agent_unique_id = salt['random.get_str'](length=16,chars='abcdefABCDEF0123456789') %}

{{agent_install_dir}}:
  file.directory:
    - name: {{agent_install_dir}}
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: True

{% for dir in 'modules', 'logs', 'config' %}
{{agent_install_dir}}{{ dir }}:
  file.directory:
    - name: {{agent_install_dir}}{{ dir }}
    - user: root
    - group: root
    - dir_mode: 755
    - makedirs: True
{% endfor %}

midagent_create_client:
  file.managed:
    - user: root
    - group: root
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}midleo_client.py:
        - source: salt://midagent/templates/python/midleo_client.py

midagent_create_script:
  file.managed:
    - user: root
    - group: root
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}magent.sh:
        - source: salt://midagent/templates/python/magent.sh

{% for file in '__init__', 'certcheck', 'classes', 'decrypt', 'configs', 'file_utils', 'lin_packages', 'statarr', 'lin_utils', 'makerequest', 'win_utils' %}
midagent_create_client_{{file}}:
  file.managed:
    - user: root
    - group: root
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}modules/{{file}}.py:
        - source: salt://midagent/templates/python/modules/{{file}}.py
{% endfor %}

midagent_create_config:
  file.managed:
    - user: root
    - group: root
    - mode: '0755'
    - template: jinja
    - names:
      - {{agent_install_dir}}config/agentConfig.json:
        - source: salt://midagent/templates/agentConfig.json.j2
    - context:
        agent_unique_id: "{{agent_unique_id}}"
        midleo_website_base_url: "{{midleo_website_base_url}}"
        midleo_website_base_url_ssl: "{{midleo_website_base_url_ssl}}"
        group_id: "{{group_id}}"
        update_interval_minutes: "{{update_interval_minutes}}"

midagent_create_service:
  file.managed:
    - user: root
    - group: root
    - mode: '0755'
    - template: jinja
    - names:
      - /etc/systemd/system/midleoagent.service:
        - source: salt://midagent/templates/agent_linux_service.j2
    - context:
        agent_install_dir: "{{agent_install_dir}}"
        python_install_dir: "{{python_install_dir}}"

midagent.service:
   service.running:
     - name: midleoagent
     - enable: True

midagent.cron:
  cron.present:
    - name: service midleoagent restart \;
    - user: root
    - minute: 00
    - hour: 01
    - daymonth: '*'
    - month: '*'
    - dayweek: '*'