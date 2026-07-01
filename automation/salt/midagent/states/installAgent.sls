{% set osname = grains.get('os', '') %}
{% set kernel = grains.get('kernel', '') %}
{% set is_zos = osname|lower in ['zos', 'z/os'] or kernel in ['OS/390', 'z/OS'] %}

include:
   - midagent.install_packages.init
{% if is_zos %}
   - midagent.service.zos
{% else %}
   - midagent.service.init
{% endif %}
