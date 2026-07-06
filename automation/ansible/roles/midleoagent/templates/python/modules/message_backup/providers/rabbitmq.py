import base64

from modules.base import classes
from modules.message_backup.provider import MessageBackupProvider
from modules.statistics import common

try:
    import pika
except ImportError:
    pika = None


def _decode_password(value):
    if not value:
        return ""
    decrypted = common.decrypt_password(value)
    if decrypted != str(value):
        return decrypted
    try:
        padded = value + "=" * ((4 - len(value) % 4) % 4)
        return base64.b64decode(padded).decode("utf-8")
    except Exception:
        return str(value)


class RabbitMqMessageBackupProvider(MessageBackupProvider):
    def __init__(self, job_cfg, broker_cfg):
        self.job_cfg = dict(job_cfg or {})
        self.broker_cfg = dict(broker_cfg or {})
        self.queue_name = str(self.job_cfg.get("source") or "")
        self.connection = None
        self.channel = None
        self._pending = {}

    def connect(self):
        if pika is None:
            raise RuntimeError("pika is not available")
        host = str(self.broker_cfg.get("host") or self.broker_cfg.get("appsrv") or "localhost")
        port = int(self.broker_cfg.get("port") or self.broker_cfg.get("mngmport") or 5672)
        user = str(self.broker_cfg.get("usr") or self.broker_cfg.get("username") or "guest")
        password = _decode_password(self.broker_cfg.get("pwd") or self.broker_cfg.get("password"))
        vhost = str(self.broker_cfg.get("vhost") or "/")
        credentials = pika.PlainCredentials(user, password)
        params = pika.ConnectionParameters(host=host, port=port, virtual_host=vhost, credentials=credentials)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=max(1, int(self.job_cfg.get("max_messages", 100))))

    def check_health(self):
        return self.connection is not None and self.channel is not None and self.connection.is_open

    def receive(self, max_messages, timeout_ms, body_mode):
        if not self.check_health():
            return
        fetched = 0
        while fetched < max_messages:
            method, properties, body = self.channel.basic_get(queue=self.queue_name, auto_ack=False)
            if method is None:
                break
            fetched += 1
            headers = dict(properties.headers or {}) if properties and properties.headers else {}
            raw = {
                "delivery_tag": method.delivery_tag,
                "message_id": properties.message_id if properties else "",
                "correlation_id": properties.correlation_id if properties else "",
            }
            item = {
                "raw": raw,
                "body": body if body_mode != "none" else None,
                "properties": {
                    "message_id": raw.get("message_id"),
                    "correlation_id": raw.get("correlation_id"),
                },
                "headers": headers,
                "delivery_metadata": {
                    "queue": self.queue_name,
                    "delivery_tag": method.delivery_tag,
                    "redelivered": method.redelivered,
                },
                "message_id": _safe(raw.get("message_id")),
                "timestamp": str(properties.timestamp) if properties and properties.timestamp else "",
            }
            self._pending[method.delivery_tag] = method.delivery_tag
            yield item

    def ack(self, message):
        tag = _delivery_tag(message)
        if tag is None:
            return
        self.channel.basic_ack(delivery_tag=tag)
        self._pending.pop(tag, None)

    def nack(self, message, requeue=True):
        tag = _delivery_tag(message)
        if tag is None:
            return
        self.channel.basic_nack(delivery_tag=tag, requeue=bool(requeue))
        self._pending.pop(tag, None)

    def close(self):
        try:
            if self.channel is not None:
                self.channel.close()
        except Exception as err:
            classes.Err("rabbitmq message_backup channel close:" + str(err))
        try:
            if self.connection is not None:
                self.connection.close()
        except Exception as err:
            classes.Err("rabbitmq message_backup connection close:" + str(err))
        self.channel = None
        self.connection = None


def _safe(value):
    return "" if value is None else str(value)


def _delivery_tag(message):
    if isinstance(message, dict):
        meta = message.get("delivery_metadata") if isinstance(message.get("delivery_metadata"), dict) else {}
        if meta.get("delivery_tag") is not None:
            return meta.get("delivery_tag")
        raw = message.get("_raw_handle") if isinstance(message.get("_raw_handle"), dict) else message.get("raw")
        if isinstance(raw, dict) and raw.get("delivery_tag") is not None:
            return raw.get("delivery_tag")
    return None
