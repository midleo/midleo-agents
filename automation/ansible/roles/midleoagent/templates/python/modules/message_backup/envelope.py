import base64
import hashlib
import binascii
import json
import socket
from datetime import datetime, timezone

from modules.base import configs

VALID_TRANSPORTS = frozenset({"ibmmq", "rabbitmq", "kafka", "tibcoems"})
VALID_BODY_MODES = frozenset({"full", "none", "hash"})

CORRELATION_HEADER_KEYS = (
    "correlation_id",
    "X-Correlation-ID",
    "x-correlation-id",
    "traceparent",
)

def _utc_iso(value=None):
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def _safe_text(value):
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError:
            return binascii.hexlify(raw).decode("ascii")
    return str(value).strip().replace("\u0000", "")

def _json_safe(value):
    if isinstance(value, dict):
        return {_safe_text(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _safe_text(value)

def _header_lookup(headers, keys):
    if not isinstance(headers, dict):
        return ""
    lowered = {str(k).lower(): v for k, v in headers.items()}
    for key in keys:
        if key in headers and headers[key] not in (None, ""):
            return _safe_text(headers[key])
        low = str(key).lower()
        if low in lowered and lowered[low] not in (None, ""):
            return _safe_text(lowered[low])
    return ""

def extract_correlation_id(transport, raw, properties=None, headers=None, config=None):
    transport = _safe_text(transport).lower()
    properties = properties if isinstance(properties, dict) else {}
    headers = headers if isinstance(headers, dict) else {}
    config = config if isinstance(config, dict) else {}

    if transport == "ibmmq":
        correl = _safe_text(raw.get("CorrelId") or raw.get("correlId"))
        if correl and correl != "0" * len(correl):
            return correl
        for key in ("correlationId", "JMSCorrelationID", "correlation_id"):
            value = _safe_text(properties.get(key))
            if value:
                return value
        return ""

    if transport == "rabbitmq":
        value = _safe_text(raw.get("correlation_id"))
        if value:
            return value
        return _header_lookup(headers, CORRELATION_HEADER_KEYS)

    if transport == "kafka":
        value = _header_lookup(headers, CORRELATION_HEADER_KEYS)
        if value:
            return value
        return _safe_text(raw.get("key"))

    if transport == "tibcoems":
        value = _safe_text(raw.get("JMSCorrelationID") or properties.get("JMSCorrelationID"))
        if value:
            return value
        if config.get("correlation_fallback_enabled"):
            return _safe_text(raw.get("correlation_id") or properties.get("correlation_id"))
        return ""

    return ""

def apply_body_mode(body_mode, body_bytes):
    body_mode = _safe_text(body_mode).lower() or "none"
    if body_mode not in VALID_BODY_MODES:
        body_mode = "none"

    if body_mode == "none":
        return body_mode, None, None

    if not isinstance(body_bytes, (bytes, bytearray)):
        body_bytes = b"" if body_bytes is None else str(body_bytes).encode("utf-8", errors="replace")

    digest = hashlib.sha256(body_bytes).hexdigest()
    if body_mode == "hash":
        return body_mode, None, digest

    try:
        body_value = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        body_value = base64.b64encode(body_bytes).decode("ascii")

    return body_mode, body_value, digest

def idempotency_key(envelope):
    agent_id = _safe_text(envelope.get("agent_id"))
    transport = _safe_text(envelope.get("transport"))
    instance = _safe_text(envelope.get("middleware_instance"))
    source = _safe_text(envelope.get("source"))
    message_id = _safe_text(envelope.get("message_id"))

    if agent_id and transport and instance and source and message_id:
        return "|".join([agent_id, transport, instance, source, message_id])

    correl = _safe_text(envelope.get("correlation_id"))
    delivery = envelope.get("delivery_metadata") if isinstance(envelope.get("delivery_metadata"), dict) else {}
    delivery_json = json.dumps(delivery, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "|".join([agent_id, transport, instance, source, correl, delivery_json])

def build_envelope(
    transport,
    middleware_instance,
    source,
    raw,
    body_bytes=None,
    body_mode="none",
    headers=None,
    properties=None,
    delivery_metadata=None,
    timestamp=None,
    message_id=None,
    job_config=None,
):
    transport = _safe_text(transport).lower()
    if transport not in VALID_TRANSPORTS:
        raise ValueError("unsupported transport")

    raw = raw if isinstance(raw, dict) else {}
    job_config = job_config if isinstance(job_config, dict) else {}
    headers = _json_safe(headers) if isinstance(headers, dict) else {}
    properties = _json_safe(properties) if isinstance(properties, dict) else {}
    delivery_metadata = _json_safe(delivery_metadata) if isinstance(delivery_metadata, dict) else {}

    identity = configs.getAgentIdentity()
    cfg = configs.getcfgData() or {}
    agent_id = _safe_text(identity.get("agent_id") or cfg.get("SRVUID") or "unknown")
    environment = _safe_text(cfg.get("ENVIRONMENT") or cfg.get("ENV") or "")

    correl = extract_correlation_id(transport, raw, properties, headers, job_config)
    body_mode, body_value, body_sha256 = apply_body_mode(body_mode, body_bytes)

    envelope = {
        "agent_id": agent_id,
        "hostname": socket.gethostname(),
        "environment": environment,
        "transport": transport,
        "middleware_instance": _safe_text(middleware_instance),
        "source": _safe_text(source),
        "message_id": _safe_text(message_id or raw.get("message_id") or raw.get("MsgId") or raw.get("msg_id")),
        "correlation_id": correl,
        "timestamp": _safe_text(timestamp) or _utc_iso(),
        "received_at": _utc_iso(),
        "headers": headers,
        "properties": properties,
        "body_mode": body_mode,
        "body": body_value,
        "body_sha256": body_sha256,
        "delivery_metadata": delivery_metadata,
        "_raw_handle": raw,
    }
    envelope["idempotency_key"] = idempotency_key(envelope)
    return envelope

def envelope_for_submit(envelope):
    payload = dict(envelope)
    payload.pop("_raw_handle", None)
    return payload

def log_fields(envelope, operation, result, error_code=""):
    return {
        "agent_id": envelope.get("agent_id"),
        "hostname": envelope.get("hostname"),
        "transport": envelope.get("transport"),
        "middleware_instance": envelope.get("middleware_instance"),
        "source": envelope.get("source"),
        "message_id": envelope.get("message_id"),
        "correlation_id": envelope.get("correlation_id"),
        "body_mode": envelope.get("body_mode"),
        "operation": operation,
        "result": result,
        "error_code": error_code,
    }
