from modules.base import classes
from modules.message_backup.provider import MessageBackupProvider
from modules.statistics import common
from datetime import datetime, timezone

try:
    from kafka import KafkaConsumer, TopicPartition
    from kafka.structs import OffsetAndMetadata
except ImportError:
    KafkaConsumer = None
    TopicPartition = None
    OffsetAndMetadata = None


class KafkaMessageBackupProvider(MessageBackupProvider):
    def __init__(self, job_cfg, broker_cfg):
        self.job_cfg = dict(job_cfg or {})
        self.broker_cfg = dict(broker_cfg or {})
        self.topic = str(self.job_cfg.get("source") or "")
        self.consumer = None
        self._pending = {}

    def connect(self):
        if KafkaConsumer is None:
            raise NotImplementedError("kafka-python is not installed; Kafka message backup receive is not available")
        bootstrap = self.broker_cfg.get("bootstrap_servers") or (
            str(self.broker_cfg.get("host") or self.broker_cfg.get("appsrv") or "localhost")
            + ":"
            + str(self.broker_cfg.get("port") or "9092")
        )
        group = str(self.job_cfg.get("consumer_group") or "midleo-message-backup")
        consumer_kwargs = {
            "bootstrap_servers": bootstrap,
            "group_id": group,
            "enable_auto_commit": False,
            "consumer_timeout_ms": max(100, int(self.job_cfg.get("timeout_ms", 5000))),
            "security_protocol": str(self.broker_cfg.get("security_protocol") or self.broker_cfg.get("security") or "PLAINTEXT"),
        }
        username = self.broker_cfg.get("username") or self.broker_cfg.get("usr")
        password = self.broker_cfg.get("password") or self.broker_cfg.get("pwd")
        if username and password:
            consumer_kwargs["sasl_plain_username"] = str(username)
            consumer_kwargs["sasl_plain_password"] = common.decrypt_password(password)
            consumer_kwargs["sasl_mechanism"] = str(self.broker_cfg.get("sasl_mechanism") or "PLAIN")
        self.consumer = KafkaConsumer(self.topic, **consumer_kwargs)

    def check_health(self):
        return self.consumer is not None

    def receive(self, max_messages, timeout_ms, body_mode):
        if not self.check_health():
            return
        fetched = 0
        for record in self.consumer:
            if fetched >= max_messages:
                break
            fetched += 1
            headers = {}
            if record.headers:
                for key, value in record.headers:
                    headers[str(key)] = value.decode("utf-8", errors="replace") if isinstance(value, (bytes, bytearray)) else value
            key = record.key.decode("utf-8", errors="replace") if isinstance(record.key, (bytes, bytearray)) else record.key
            value = record.value
            raw = {
                "topic": record.topic,
                "partition": record.partition,
                "offset": record.offset,
                "key": key,
                "message_id": str(record.offset),
            }
            item = {
                "raw": raw,
                "body": value if body_mode != "none" else None,
                "properties": {},
                "headers": headers,
                "delivery_metadata": {
                    "topic": record.topic,
                    "partition": record.partition,
                    "offset": record.offset,
                },
                "message_id": str(record.topic) + ":" + str(record.partition) + ":" + str(record.offset),
                "timestamp": _timestamp_iso(record.timestamp),
            }
            self._pending[(record.topic, record.partition, record.offset)] = record
            yield item

    def ack(self, message):
        record = _record_handle(message, self._pending)
        if record is None or self.consumer is None:
            return
        topic_partition = TopicPartition(record.topic, record.partition)
        self.consumer.commit({topic_partition: OffsetAndMetadata(record.offset + 1, None)})
        self._pending.pop((record.topic, record.partition, record.offset), None)

    def nack(self, message, requeue=True):
        record = _record_handle(message, self._pending)
        if record is not None:
            self._pending.pop((record.topic, record.partition, record.offset), None)
        classes.Err("kafka message_backup nack: offset not committed")

    def close(self):
        if self.consumer is not None:
            try:
                self.consumer.close()
            except Exception as err:
                classes.Err("kafka message_backup close:" + str(err))
            self.consumer = None


def _record_handle(message, pending):
    if isinstance(message, dict):
        raw = message.get("_raw_handle") if isinstance(message.get("_raw_handle"), dict) else message.get("raw")
        if isinstance(raw, dict):
            key = (raw.get("topic"), raw.get("partition"), raw.get("offset"))
            return pending.get(key)
        meta = message.get("delivery_metadata") if isinstance(message.get("delivery_metadata"), dict) else {}
        key = (meta.get("topic"), meta.get("partition"), meta.get("offset"))
        return pending.get(key)
    return None


def _timestamp_iso(value):
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value) / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""
