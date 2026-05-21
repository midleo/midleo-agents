#install packages

{% set install_pymqi = salt['pillar.get']('INPUT:install_pymqi', False) %}
{% set osfam = grains.get('os_family', '') %}
{% if osfam == 'RedHat' %}
{% set python_dev_package = 'python3-devel' %}
{% else %}
{% set python_dev_package = 'python3-dev' %}
{% endif %}

midagent_install_packages:
  pkg.installed:
    - pkgs:
      - gcc
      - curl
      - jq
      - {{ python_dev_package }}
      - python3-pip
      - python3-setuptools

midagent_install_python_packages:
  pip.installed:
    - pkgs:
      - psutil
      - py-cpuinfo
      - dnspython
      - requests
      - pycryptodome
      - pywinrm
      - netifaces
    - require:
      - pkg: midagent_install_packages

{% if install_pymqi in [True, 'true', 'True', 'TRUE', 'y', 'Y', 'yes', 'YES', '1', 1] %}
midagent_install_pymqi:
  pip.installed:
    - name: pymqi
    - require:
      - pkg: midagent_install_packages
{% endif %}
