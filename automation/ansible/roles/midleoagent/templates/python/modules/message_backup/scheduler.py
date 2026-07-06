import importlib
import json

from modules.base import classes, configs
from modules.message_backup import backend_client, envelope, metrics
from modules.message_backup.outbox import MessageBackupOutbox

_PROVIDER_MAP = {
    "ibmmq": "modules.message_backup.providers.ibmmq.IbmMqMessageBackupProvider",
    "rabbitmq": "modules.message_backup.providers.rabbitmq.RabbitMqMessageBackupProvider",
    "kafka": "modules.message_backup.providers.kafka.KafkaMessageBackupProvider",
    "tibcoems": "modules.message_backup.providers.tibcoems.TibcoEmsMessageBackupProvider",
}
_VALID_ACK_AFTER = frozenset({"backend_persisted", "outbox_handoff"})
_BROKER_JOB_KEYS = frozenset({
    "bootstrap_servers",
    "host",
    "appsrv",
    "port",
    "serverdns",
    "serverip",
    "usr",
    "pwd",
    "srvuser",
    "srvpass",
    "vhost",
    "security",
    "security_protocol",
    "username",
    "password",
    "sasl_mechanism",
    "ssl",
    "sslverify",
    "sslenabled",
    "sslcipher",
    "sslkey",
    "keyrepo",
    "qmchannel",
    "channel",
    "tibcosrv",
    "tibcoport",
    "conntype",
})


def _load_provider(transport, job_cfg, broker_cfg):
    path = _PROVIDER_MAP.get(str(transport).lower())
    if not path:
        raise ValueError("unsupported transport:" + str(transport))
    module_name, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    provider_cls = getattr(module, class_name)
    return provider_cls(job_cfg, broker_cfg)


def _log_envelope(envelope_data, operation, result, error_code=""):
    fields = envelope.log_fields(envelope_data, operation, result, error_code)
    classes.Err(
        "message_backup "
        + json_safe(fields)
    )


def json_safe(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _root_config(config_data):
    config_data = config_data if isinstance(config_data, dict) else {}
    return config_data.get("message_backup") if isinstance(config_data.get("message_backup"), dict) else config_data


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _is_enabled(data, default=True):
    return _as_bool(data.get("enabled"), default) if isinstance(data, dict) else default


_DEFAULT_BATCH_SIZE = 50


def _batch_size(backend_cfg, ceiling=None, job_cfg=None):
    backend_cfg = backend_cfg if isinstance(backend_cfg, dict) else {}
    job_cfg = job_cfg if isinstance(job_cfg, dict) else {}
    raw = job_cfg.get("batch_size")
    if raw is None:
        raw = backend_cfg.get("batch_size", _DEFAULT_BATCH_SIZE)
    try:
        size = int(raw)
    except Exception:
        size = _DEFAULT_BATCH_SIZE
    size = max(1, size)
    if ceiling:
        size = min(size, max(1, int(ceiling)))
    return size


def _job_label(index, job):
    name = job.get("name") if isinstance(job, dict) else ""
    return str(name or ("job[" + str(index) + "]"))


def _valid_int(value, minimum, maximum):
    try:
        parsed = int(value)
    except Exception:
        return False
    return minimum <= parsed <= maximum


def validate_config(config_data):
    root = _root_config(config_data)
    if not root or not _is_enabled(root, True):
        return []

    errors = []
    cfg = configs.getcfgData() or {}
    identity = configs.getAgentIdentity() or {}
    if not str(cfg.get("MWADMIN", "")).strip():
        errors.append("MWADMIN is required for message backup submit")
    if not (identity.get("agent_id") and identity.get("agent_token")) and not str(cfg.get("INTTOKEN", "")).strip():
        errors.append("agent identity or INTTOKEN is required for message backup submit")

    jobs = root.get("jobs")
    if not isinstance(jobs, list):
        return errors + ["message_backup.jobs must be a list"]

    outbox_cfg = root.get("outbox") if isinstance(root.get("outbox"), dict) else {}
    outbox_enabled = _is_enabled(outbox_cfg, True)
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            errors.append("message_backup job[" + str(index) + "] must be an object")
            continue
        if not _is_enabled(job, True):
            continue

        label = _job_label(index, job)
        transport = str(job.get("transport") or "").strip().lower()
        if transport not in _PROVIDER_MAP:
            errors.append(label + " has unsupported transport")
        if not str(job.get("middleware_instance") or "").strip():
            errors.append(label + " is missing middleware_instance")
        if not str(job.get("source") or "").strip():
            errors.append(label + " is missing source")

        body_mode = str(job.get("body_mode", "none")).strip().lower()
        if body_mode not in envelope.VALID_BODY_MODES:
            errors.append(label + " has invalid body_mode")

        ack_after = str(job.get("ack_after") or job.get("commit_after") or "backend_persisted").strip().lower()
        if ack_after not in _VALID_ACK_AFTER:
            errors.append(label + " has invalid ack_after")
        elif ack_after == "outbox_handoff" and not outbox_enabled:
            errors.append(label + " uses outbox_handoff while outbox is disabled")

        if not _valid_int(job.get("max_messages", 100), 1, 1000):
            errors.append(label + " max_messages must be between 1 and 1000")
        if job.get("batch_size") is not None and not _valid_int(job.get("batch_size"), 1, 1000):
            errors.append(label + " batch_size must be between 1 and 1000")
        if not _valid_int(job.get("timeout_ms", 5000), 100, 300000):
            errors.append(label + " timeout_ms must be between 100 and 300000")

        if transport == "rabbitmq" and _as_bool(job.get("auto_ack"), False):
            errors.append(label + " must not enable RabbitMQ auto_ack")
        if transport == "kafka" and _as_bool(job.get("enable_auto_commit"), False):
            errors.append(label + " must not enable Kafka auto commit")

        broker_cfg = _resolve_broker_config(transport, job, root)
        if transport == "kafka" and not (
            broker_cfg.get("bootstrap_servers") or broker_cfg.get("host") or broker_cfg.get("appsrv")
        ):
            errors.append(label + " requires Kafka bootstrap_servers or host in confmessagebackup.json")
        if transport == "rabbitmq" and not (broker_cfg.get("host") or broker_cfg.get("appsrv")):
            errors.append(label + " requires RabbitMQ host in confmessagebackup.json")
        if transport == "tibcoems":
            errors.append(label + " TIBCO EMS message receive is not implemented")

    return errors


def _process_job(job, global_cfg, outbox):
    if not isinstance(job, dict) or not _is_enabled(job, True):
        return
    transport = str(job.get("transport") or "").lower()
    metrics.increment("message_backup_checked")
    broker_cfg = _resolve_broker_config(transport, job, global_cfg)
    provider = None
    try:
        provider = _load_provider(transport, job, broker_cfg)
        provider.connect()
        if not provider.check_health():
            metrics.increment("message_backup_broker_connection_failed")
            classes.Err("message_backup broker health failed:" + str(job.get("name")))
            return

        max_messages = max(1, min(int(job.get("max_messages", 100)), 1000))
        timeout_ms = max(100, int(job.get("timeout_ms", 5000)))
        body_mode = str(job.get("body_mode", "none")).lower()
        ack_after = str(job.get("ack_after") or job.get("commit_after") or "backend_persisted").lower()
        requeue = _as_bool(job.get("requeue_on_failure"), True)
        backend_cfg = global_cfg.get("backend")
        batch_size = _batch_size(backend_cfg, max_messages, job)

        buffer = []
        for raw in provider.receive(max_messages, timeout_ms, body_mode):
            metrics.increment("message_backup_received")
            item = envelope.build_envelope(
                transport=transport,
                middleware_instance=job.get("middleware_instance"),
                source=job.get("source"),
                raw=raw.get("raw", raw),
                body_bytes=raw.get("body"),
                body_mode=body_mode,
                headers=raw.get("headers"),
                properties=raw.get("properties"),
                delivery_metadata=raw.get("delivery_metadata"),
                timestamp=raw.get("timestamp"),
                message_id=raw.get("message_id"),
                job_config=job,
            )
            buffer.append(item)
            if len(buffer) >= batch_size:
                _submit_batch(buffer, provider, outbox, backend_cfg, ack_after, requeue)
                buffer = []
        _submit_batch(buffer, provider, outbox, backend_cfg, ack_after, requeue)
    except Exception as err:
        metrics.increment("message_backup_broker_connection_failed")
        classes.Err("message_backup job failed:" + str(job.get("name")) + ":" + str(err))
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception:
                pass


def _submit_batch(items, provider, outbox, backend_cfg, ack_after, requeue):
    if not items:
        return
    statuses = backend_client.submit_batch(items, backend_cfg)
    if len(statuses) != len(items):
        statuses = [("temporary_failure", "")] * len(items)

    for item, (status, _error) in zip(items, statuses):
        raw_handle = item.get("_raw_handle") or item
        if status in ("persisted", "duplicate"):
            provider.ack(item)
            metrics.increment("message_backup_acked")
            _log_envelope(item, "submit", status)
            continue

        if status == "temporary_failure":
            if outbox.enqueue(item):
                if ack_after == "outbox_handoff":
                    provider.ack(item)
                    metrics.increment("message_backup_acked")
                _log_envelope(item, "outbox_enqueue", "temporary_failure")
            else:
                provider.nack(raw_handle, requeue=requeue)
                metrics.increment("message_backup_nacked")
                _log_envelope(item, "nack", "temporary_failure", "backend_unavailable")
            continue

        provider.nack(raw_handle, requeue=False)
        metrics.increment("message_backup_nacked")
        _log_envelope(item, "nack", "rejected", "schema_or_auth")


def _resolve_broker_config(transport, job, root=None):
    instance = str(job.get("middleware_instance") or "")
    broker_cfg = {}

    if isinstance(root, dict):
        brokers = root.get("brokers") if isinstance(root.get("brokers"), dict) else {}
        local_transport_cfg = brokers.get(transport) if isinstance(brokers.get(transport), dict) else {}
        if instance and instance in local_transport_cfg:
            broker_cfg.update(dict(local_transport_cfg.get(instance) or {}))

    mon = configs.getmonData() or {}
    transport_cfg = mon.get(transport) if isinstance(mon.get(transport), dict) else {}
    if instance and instance in transport_cfg:
        for key, value in dict(transport_cfg.get(instance) or {}).items():
            broker_cfg.setdefault(key, value)
    elif not instance and transport_cfg and not broker_cfg:
        first = next(iter(transport_cfg.values()), {})
        broker_cfg.update(dict(first or {}))

    for section in ("broker", "connection"):
        if isinstance(job.get(section), dict):
            broker_cfg.update(job.get(section))
    for key in _BROKER_JOB_KEYS:
        if key in job:
            broker_cfg[key] = job[key]
    return broker_cfg


def flush_outbox(global_cfg, outbox):
    backend = global_cfg.get("backend") if isinstance(global_cfg.get("backend"), dict) else {}
    retry = backend.get("retry") if isinstance(backend.get("retry"), dict) else {}
    initial_delay = max(1, int(retry.get("initial_delay_ms", 1000) / 1000))
    metrics.set_gauge("message_backup_outbox_size", outbox.size())
    batch_size = _batch_size(backend)
    due = outbox.list_due()
    for start in range(0, len(due), batch_size):
        chunk = due[start:start + batch_size]
        envelopes = [record.get("envelope") if isinstance(record.get("envelope"), dict) else {} for record in chunk]
        statuses = backend_client.submit_batch(envelopes, backend)
        if len(statuses) != len(chunk):
            statuses = [("temporary_failure", "")] * len(chunk)
        for record, (status, _error) in zip(chunk, statuses):
            if status in ("persisted", "duplicate"):
                outbox.mark_sent(record)
                continue
            delay = min(initial_delay * (2 ** int(record.get("retry_count", 0))), int(retry.get("max_delay_ms", 60000) / 1000))
            outbox.mark_retry(record, status, delay)
            metrics.increment("message_backup_outbox_retry_count")


def run_once(config_data=None):
    config_data = config_data if isinstance(config_data, dict) else configs.getMessageBackupData()
    root = _root_config(config_data)
    if not root or not _is_enabled(root, True):
        return
    validation_errors = validate_config(config_data)
    if validation_errors:
        for error in validation_errors:
            classes.Err("message_backup config invalid:" + error)
        metrics.increment("message_backup_config_invalid")
        metrics.flush()
        return
    outbox = MessageBackupOutbox(root.get("outbox") or {})
    flush_outbox(root, outbox)
    jobs = root.get("jobs") if isinstance(root.get("jobs"), list) else []
    for job in jobs:
        _process_job(job, root, outbox)
    flush_outbox(root, outbox)
    metrics.set_gauge("message_backup_outbox_size", outbox.size())
    metrics.flush()
