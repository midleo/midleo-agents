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

- download vendor and external libraries (depends on which modules you will use)


```
mkdir -p /midleolibs/{lib,vendor}
libraries in lib folder:
activemq-client-6.1.6.jar
asm-7.0.jar
gson-2.10.1.jar
jackson-annotations-2.16.2.jar
jackson-core-2.16.2.jar
jackson-databind-2.16.2.jar
jackson-dataformat-yaml-2.16.0.jar
jackson-datatype-jsr310-2.16.0.jar
jaxb-api-2.3.0.jar
jboss-dmr-1.7.0.Final.jar
jetty-client.jar
jetty-http.jar
jetty-io.jar
jetty-util.jar
jffi-1.2.19.jar
jffi-1.2.19-native.jar
jms-2.0.jar
jmsclient.jar
jnr-a64asm-1.0.0.jar
jnr-constants-0.9.12.jar
jnr-enxio-0.21.jar
jnr-ffi-2.1.10.jar
jnr-posix-3.0.50.jar
jnr-unixsocket-0.23.jar
jnr-x86asm-1.0.2.jar
json-20231013.jar
kafka-clients-3.9.0.jar
kafka-schema-registry-client-7.8.0.jar
log4j-1.2.17.jar
org.apache.commons.io.jar
slf4j-api-2.0.9.jar
slf4j-simple-2.0.9.jar
snakeyaml-2.2.jar
websocket-api.jar
websocket-client.jar
websocket-common.jar
wildfly-client-all-35.0.1.Final.jar
wildfly-controller-client-28.0.0.Final.jar
wildfly-protocol-28.0.0.Final.jar


libraries in vendor folder:
bipbroker.jar
brokerutil.jar
com.ibm.mq.allclient.jar
com.ibm.mq.jmqi.jar
IntegrationAPI_ACE.jar
IntegrationAPI_IIB.jar
tibemsd_sec.jar
tibjmsadmin.jar
tibjmsapps.jar
tibjms.jar
tibrvjms.jar

```