#install packages

midagent_install_packages:
  pkg.installed:
    - pkgs:
      - gcc
      - curl
      - python3-pip
      - python3-setuptools