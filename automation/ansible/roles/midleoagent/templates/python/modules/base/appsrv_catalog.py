
import re


SUPPORTED_KEYS = (
    "ibmmq",
    "fte",
    "ibmiib",
    "ibmace",
    "rabbitmq",
    "tibcoems",
    "activemq",
    "jboss",
    "tomcat",
    "kafka",
    "ibmwas",
    "msiis",
    "weblogic",
    "openshift",
    "zos",
    "aap",
    "axwayst",
    "axwaycft",
    "database",
)


SUPPORTED_APPLICATIONS = {
    "ibmmq": {
        "package_names": (
            "mqseriesserver",
            "mqseries-server",
            "ibmmq-server",
            "ibm-mq-server",
        ),
        "package_regexes": (r"mqseriesserver-u\d+",),
        "preferred_package_regexes": (r"mqseriesserver-u\d+",),
        "windows_rules": (
            (
                r"(?:ibm (?:websphere )?mq|websphere mq)(?: server)?"
                r"(?: [0-9][0-9a-z._-]*)?(?: \([^)]{1,64}\))?",
                ("ibm",),
            ),
        ),
        "version_binaries": (
            {"binary": "dspmqver", "args": ("-f", "2"), "prefer": True},
        ),
    },
    "fte": {
        "package_names": (
            "mqseriesftagent",
            "mqseriesftservice",
            "mqseriesftlogger",
            "ibmmqfte",
            "ibm-mq-fte",
            "ibm-mq-mft",
        ),
        "package_regexes": (r"mqseriesft(?:agent|service|logger)-u\d+",),
        "preferred_package_regexes": (
            r"mqseriesft(?:agent|service|logger)-u\d+",
        ),
        "windows_rules": (
            (
                r"ibm (?:websphere )?mq (?:managed file transfer|fte)"
                r"(?: agent|service|logger)?(?: [0-9][0-9a-z._-]*)?",
                ("ibm",),
            ),
        ),
        "version_binaries": (
            {"binary": "fteDisplayVersion", "args": ()},
        ),
    },
    "ibmiib": {
        "package_names": (
            "iib",
            "ibm-iib",
            "integrationbus",
            "ibm-integration-bus",
        ),
        "package_regexes": (r"iib-(?:9|10)",),
        "windows_rules": (
            (
                r"(?:ibm integration bus|ibm iib|ibm websphere message broker)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("ibm",),
            ),
        ),
    },
    "ibmace": {
        "package_names": (
            "ibm-ace",
            "ibmace",
            "appconnectenterprise",
            "ibm-app-connect-enterprise",
        ),
        "package_regexes": (r"ace-(?:11|12|13)",),
        "windows_rules": (
            (
                r"(?:ibm app connect enterprise|ibm ace)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("ibm",),
            ),
        ),
    },
    "rabbitmq": {
        "package_names": ("rabbitmq-server", "rabbitmq"),
        "windows_rules": (
            (
                r"rabbitmq(?: server)?(?: [0-9][0-9a-z._-]*)?",
                ("rabbitmq", "pivotal", "vmware", "broadcom"),
            ),
        ),
        "version_binaries": (
            {"binary": "rabbitmqctl", "args": ("version",)},
        ),
    },
    "tibcoems": {
        "package_names": ("tibcoems", "tibco-ems", "tibemsd"),
        "windows_rules": (
            (
                r"tibco (?:enterprise message service|ems)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("tibco",),
            ),
        ),
    },
    "activemq": {
        "package_names": (
            "activemq",
            "apache-activemq",
            "activemq-server",
            "activemq-artemis",
        ),
        "windows_rules": (
            (
                r"apache activemq(?: artemis)?(?: [0-9][0-9a-z._-]*)?",
                ("apache",),
            ),
        ),
    },
    "jboss": {
        "package_names": (
            "wildfly",
            "wildfly-preview",
            "jbossas",
            "jboss-as",
            "jboss-eap",
            "eap7-wildfly",
            "eap8-wildfly",
        ),
        "windows_rules": (
            (
                r"(?:(?:red hat )?jboss (?:enterprise application platform|eap|application server)"
                r"|wildfly(?: application server)?)(?: [0-9][0-9a-z._-]*)?",
                ("red hat", "redhat", "jboss"),
            ),
        ),
    },
    "tomcat": {
        "package_names": (
            "tomcat",
            "tomcat8",
            "tomcat9",
            "tomcat10",
            "tomcat11",
            "apache-tomcat",
            "tomcat-server",
        ),
        "package_regexes": (r"tomcat(?:8|9|10|11)",),
        "windows_rules": (
            (
                r"apache tomcat(?: [0-9][0-9a-z._-]*)?(?: \([^)]{1,64}\))?",
                ("apache",),
            ),
        ),
    },
    "kafka": {
        "package_names": ("kafka", "apache-kafka", "kafka-server", "kafka-broker"),
        "windows_rules": (
            (
                r"apache kafka(?: server| broker)?(?: [0-9][0-9a-z._-]*)?",
                ("apache",),
            ),
        ),
    },
    "ibmwas": {
        "package_names": (
            "ibmwas",
            "websphere-application-server",
            "ibm-websphere-application-server",
            "ibm-websphere-liberty",
        ),
        "windows_rules": (
            (
                r"ibm websphere (?:application server|liberty)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("ibm",),
            ),
        ),
        "version_binaries": (
            {"binary": "versionInfo.sh", "args": ()},
        ),
    },
    "msiis": {
        "os": ("windows",),
        "windows_rules": (
            (
                r"microsoft (?:internet information services|iis)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("microsoft",),
            ),
        ),
        "path_hints": (
            r"%SystemRoot%\System32\inetsrv\config\applicationHost.config",
        ),
    },
    "weblogic": {
        "package_names": ("weblogic", "oracle-weblogic", "fmw-weblogic"),
        "windows_rules": (
            (
                r"(?:oracle|bea) weblogic(?: server)?"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("oracle", "bea"),
            ),
        ),
    },
    "openshift": {
        "package_names": (
            "openshift-hyperkube",
            "openshift-kubelet",
            "openshift-sdn",
            "ose-hyperkube",
            "atomic-openshift-node",
            "atomic-openshift-master",
        ),
        "windows_rules": (
            (
                r"red hat openshift(?: container platform)?"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("red hat", "redhat"),
            ),
        ),
    },
    "zos": {
        "os": ("os/390", "z/os"),
        "detect_from_os": True,
    },
    "aap": {
        "package_names": (
            "automation-controller",
            "automation-hub",
            "automation-eda-controller",
            "ansible-automation-platform",
            "ansible-tower",
        ),
        "windows_rules": (
            (
                r"(?:red hat )?(?:ansible automation platform|automation controller|ansible tower)"
                r"(?: [0-9][0-9a-z._-]*)?",
                ("red hat", "redhat", "ansible"),
            ),
        ),
    },
    "axwayst": {
        "package_names": ("axway-securetransport", "axway-st", "axwayst"),
        "windows_rules": (
            (
                r"axway secure ?transport(?: [0-9][0-9a-z._-]*)?",
                ("axway",),
            ),
        ),
    },
    "axwaycft": {
        "package_names": ("axway-cft", "axwaycft", "transfer-cft"),
        "windows_rules": (
            (
                r"axway (?:transfer )?cft(?: [0-9][0-9a-z._-]*)?",
                ("axway",),
            ),
        ),
    },
    "database": {
        "package_names": (
            "mysql-server",
            "mysql-community-server",
            "mysql-commercial-server",
            "mariadb-server",
            "mariadb-galera-server",
            "postgresql",
            "postgresql-server",
            "mssql-server",
            "oracle-database-ee",
            "oracle-database-se",
            "oracle-database-xe",
            "oracle-xe",
            "db2luw",
            "ibm-db2",
        ),
        "package_regexes": (
            r"mysql-server-\d+(?:\.\d+)*",
            r"mariadb-server-\d+(?:\.\d+)*",
            r"postgresql-\d+(?:\.\d+)*",
            r"postgresql-server-\d+(?:\.\d+)*",
        ),
        "windows_rules": (
            (r"mysql server(?: [0-9][0-9a-z._-]*)?", ("mysql", "oracle")),
            (r"mariadb(?: server)?(?: [0-9][0-9a-z._-]*)?", ("mariadb",)),
            (r"postgresql(?: server)?(?: [0-9][0-9a-z._-]*)?", ("postgres", "enterprisedb")),
            (r"microsoft sql server 20\d{2} \((?:32|64)-bit\)", ("microsoft",)),
            (
                r"oracle database(?: [0-9][0-9a-z._-]*)?"
                r"(?: (?:enterprise|standard|express) edition)?",
                ("oracle",),
            ),
            (r"ibm db2(?: server)?(?: [0-9][0-9a-z._-]*)?", ("ibm",)),
        ),
    },
}


_ARCH_SUFFIX_RE = re.compile(r":[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)


def normalize_package_name(value):
    name = str(value or "").strip().lower()
    if name and " " not in name:
        name = _ARCH_SUFFIX_RE.sub("", name)
    return name


def _compile_rules(field):
    expressions = []
    owners = {}
    rule_number = 0
    for key in SUPPORTED_KEYS:
        spec = SUPPORTED_APPLICATIONS[key]
        for rule in spec.get(field) or ():
            publishers = ()
            expression = rule
            if field == "windows_rules":
                expression, publishers = rule
            group = "r" + str(rule_number)
            expressions.append("(?P<" + group + ">" + expression + ")")
            owners[group] = (key, tuple(publishers))
            rule_number += 1
    if not expressions:
        return None, {}
    return re.compile("(?:" + "|".join(expressions) + ")", re.IGNORECASE), owners


_PACKAGE_INDEX = {}
for _key in SUPPORTED_KEYS:
    for _name in SUPPORTED_APPLICATIONS[_key].get("package_names") or ():
        _PACKAGE_INDEX[normalize_package_name(_name)] = _key

_PACKAGE_REGEX, _PACKAGE_REGEX_OWNERS = _compile_rules("package_regexes")
_WINDOWS_REGEX, _WINDOWS_REGEX_OWNERS = _compile_rules("windows_rules")


def _matched_owner(match, owners):
    if match is None or match.lastgroup is None:
        return "", ()
    return owners.get(match.lastgroup, ("", ()))


def match_package_name(name):
    normalized = normalize_package_name(name)
    if not normalized:
        return ""
    exact = _PACKAGE_INDEX.get(normalized)
    if exact:
        return exact
    key, _publishers = _matched_owner(
        _PACKAGE_REGEX.fullmatch(normalized) if _PACKAGE_REGEX else None,
        _PACKAGE_REGEX_OWNERS,
    )
    return key


def match_windows_display_name(name, publisher):
    normalized_name = str(name or "").strip().lower()
    normalized_publisher = str(publisher or "").strip().lower()
    key, publishers = _matched_owner(
        _WINDOWS_REGEX.fullmatch(normalized_name) if _WINDOWS_REGEX else None,
        _WINDOWS_REGEX_OWNERS,
    )
    if not key or not normalized_publisher:
        return ""
    if not any(token in normalized_publisher for token in publishers):
        return ""
    return key


def is_preferred_package(product_key, name):
    normalized = normalize_package_name(name)
    for pattern in SUPPORTED_APPLICATIONS[product_key].get(
        "preferred_package_regexes"
    ) or ():
        if re.fullmatch(pattern, normalized, re.IGNORECASE):
            return True
    return False


def iter_products():
    for key in SUPPORTED_KEYS:
        yield key, SUPPORTED_APPLICATIONS[key]
