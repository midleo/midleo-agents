import json
import time

from modules.base import classes, configs, makerequest
from modules.message_backup import envelope as envelope_mod
from modules.message_backup import metrics

VALID_RESULTS = frozenset({"persisted", "duplicate", "rejected", "temporary_failure"})


def _retry_settings(backend_cfg):
    backend_cfg = backend_cfg if isinstance(backend_cfg, dict) else {}
    retry = backend_cfg.get("retry") if isinstance(backend_cfg.get("retry"), dict) else {}
    return {
        "max_attempts": max(1, int(retry.get("max_attempts", 5))),
        "initial_delay_ms": max(100, int(retry.get("initial_delay_ms", 1000))),
        "max_delay_ms": max(1000, int(retry.get("max_delay_ms", 60000))),
    }


def submit_envelope(envelope, backend_cfg=None):
    results = submit_batch([envelope], backend_cfg)
    return results[0][0] if results else "temporary_failure"


def _parse_batch_response(res, count):
    """Returns (per_item_results, is_retryable) where per_item_results is a
    list of (status, error) tuples aligned 1:1 with the submitted envelopes.
    """
    if res is None:
        return [("temporary_failure", "no response")] * count, True

    code = int(res.status_code)
    text = (res.text or "").strip()
    if code >= 500 or code in (408, 429):
        return [("temporary_failure", text[:512])] * count, True
    if code >= 400:
        return [("rejected", text[:512])] * count, False
    if code < 200 or code >= 300:
        return [("temporary_failure", "unexpected HTTP status")] * count, True

    try:
        body = res.json()
    except Exception:
        return [("temporary_failure", "invalid backend JSON")] * count, True
    if not isinstance(body, dict):
        return [("temporary_failure", "invalid backend response")] * count, True
    if body.get("error") is True or body.get("success") is False:
        return [("temporary_failure", "backend reported an application error")] * count, True

    results = body.get("results") if isinstance(body.get("results"), list) else None
    if "results" in body:
        if results is None or len(results) != count:
            return [("temporary_failure", "incomplete batch acknowledgement")] * count, True
        parsed = []
        for item in results:
            item = item if isinstance(item, dict) else {}
            status = str(item.get("status") or "").lower()
            if status not in VALID_RESULTS:
                status = "temporary_failure"
            parsed.append((status, str(item.get("error") or "")[:512]))
        return parsed, False

    # Backward-compatible fallback for a single-envelope-style response
    # (older backend, or a batch of one) that returns a flat status.
    status = str(body.get("status") or "").lower()
    if status not in VALID_RESULTS:
        return [("temporary_failure", "missing backend acknowledgement")] * count, True
    is_retryable = status == "temporary_failure"
    return [(status, str(body.get("error") or "")[:512])] * count, is_retryable


def submit_batch(envelopes, backend_cfg=None):
    """Submits a batch of envelopes in a single HTTP POST to
    /pubapi/submitmessagebackup and returns a list of (status, error) tuples
    aligned 1:1 with the input envelopes so callers can ack/nack/outbox each
    message individually.
    """
    if not envelopes:
        return []

    cfg = configs.getcfgData() or {}
    webssl = cfg.get("SSLENABLED", "y")
    website = cfg.get("MWADMIN", "")
    backend_cfg = backend_cfg if isinstance(backend_cfg, dict) else {}
    retry = _retry_settings(backend_cfg)
    count = len(envelopes)
    payload = {"records": [envelope_mod.envelope_for_submit(item) for item in envelopes]}
    body = json.dumps(payload)

    delay = retry["initial_delay_ms"] / 1000.0
    results = [("temporary_failure", "no response")] * count
    for attempt in range(1, retry["max_attempts"] + 1):
        metrics.increment("message_backup_batches_sent_to_backend")
        metrics.increment("message_backup_sent_to_backend", count)
        res = makerequest.postMessageBackup(webssl, website, body)
        results, retryable = _parse_batch_response(res, count)
        if not retryable:
            break
        metrics.increment("message_backup_backend_delivery_failed", count)
        if attempt < retry["max_attempts"]:
            time.sleep(delay)
            delay = min(delay * 2, retry["max_delay_ms"] / 1000.0)

    for status, _error in results:
        if status == "persisted":
            metrics.increment("message_backup_persisted")
        elif status == "duplicate":
            metrics.increment("message_backup_duplicate")
    return results
