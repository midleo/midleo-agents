# Midleo Agents

source code for MidlEO monitoring agents

## Getting started


```
git clone https://github.com/midleo/midleo-agents.git
cd midleo-agents
```

## Information

- monitoring.beats folder : filebeat, fluentbit, logstash, rsyslog configurations for monitoring purpose
- automation : midleo agents for Windows or Linux server
  - ansible deployment - ex. ansible-playbook -i inventories install_agent_linux.yaml
  - salt deployment - ex. salt-call installAgent.sls
