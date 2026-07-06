from modules.base import classes
from modules.message_backup.provider import MessageBackupProvider


class TibcoEmsMessageBackupProvider(MessageBackupProvider):
    """TIBCO EMS receive scaffolding; wire Java/JMS collector when deployed."""

    def __init__(self, job_cfg, broker_cfg):
        self.job_cfg = dict(job_cfg or {})
        self.broker_cfg = dict(broker_cfg or {})
        self.queue_name = str(self.job_cfg.get("source") or "")
        self._connected = False

    def connect(self):
        host = str(self.broker_cfg.get("host") or self.broker_cfg.get("tibcosrv") or "")
        port = str(self.broker_cfg.get("port") or self.broker_cfg.get("tibcoport") or "")
        if not host:
            raise NotImplementedError(
                "TIBCO EMS message backup receive is not implemented in Python; "
                "configure tibcosrv/tibcoport and deploy JMS collector integration"
            )
        classes.Err(
            "tibcoems message_backup connect stub host="
            + host
            + " port="
            + port
            + " queue="
            + self.queue_name
        )
        self._connected = True

    def check_health(self):
        return self._connected

    def receive(self, max_messages, timeout_ms, body_mode):
        raise NotImplementedError(
            "TIBCO EMS message receive requires JMS integration; statistics module connection reused for config only"
        )

    def ack(self, message):
        raise NotImplementedError("TIBCO EMS ack not implemented")

    def nack(self, message, requeue=True):
        raise NotImplementedError("TIBCO EMS nack not implemented")

    def close(self):
        self._connected = False
