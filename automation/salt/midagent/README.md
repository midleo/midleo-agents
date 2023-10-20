# midleoagent

# installation

- create configuration file <b>midagent.conf</b>

```console
midleo_website_base_url="MIDLEO_BASE_URL"  # the base url of the midleo.CORE website, ex. https://app.midleo.com
midleo_website_base_url_ssl="y"   # is the website accessed via http or https -> https=y
group_id="MIDsf4"                 # the GroupID taken from midleo.CORE website -> Configuration -> Groups -> Edit -> GroupID
update_interval_minutes="5"       # interval in minutes. The agent is getting information about resources and post it to the midleo.CORE website

pillar='{"INPUT":{"midleo_website_base_url":"'$midleo_website_base_url'","midleo_website_base_url_ssl":"'$midleo_website_base_url_ssl'","group_id":"'$group_id'","update_interval_minutes":"'$update_interval_minutes'"}}'
```

- install the agent


```
. midagent.conf
salt-call -c saltconfig state.apply midagent.installAgent pillar="$pillar"
```