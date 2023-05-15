# Midleo Agents

source code for MidlEO monitoring agents

## Getting started


```
cd your-folder
git remote add origin https://github.com/midleo/midleo-agents.git
git branch -M master
git pull origin master
```

## Information

- conf folder : configuration about filebeat and logstash module for monitoring purpose
- automation : midleo agents for Windows or Linux server
  - ansible deployment - ex. ansible-playbook -i inventories install_agent_linux.yaml
- ibmmq.pcfget : MidlEO java module for getting information about current queue depth , max age and uncommited messages via PCF
- ibmmq.restget : python agent for getting information about IBM MQ queue/channel depth via REST