import re


ENCRYPTED_SECRET_KEYS = {
    "pwd",
    "pass",
    "password",
    "srvpass",
    "cpass",
    "chlpass",
    "tibcopass",
    "token",
}

REDACTED_SECRET_KEYS = ENCRYPTED_SECRET_KEYS | {
    "agent_token",
    "apikey",
    "api_key",
    "authorization",
    "collector_token",
    "inttoken",
    "keystorepass",
    "keypass",
    "optadvisor_token",
    "optadvisor_token_expires_at",
    "optadvisor_token_uid",
    "secret",
    "sslpass",
    "storepass",
    "truststorepass",
}

REMOVED_AUTH_KEYS = {
    "collector_token",
    "optadvisor_token",
    "optadvisor_token_expires_at",
    "optadvisor_token_uid",
    "truststore",
    "truststorepass",
}

_SECRET_TEXT_RE = re.compile(
    r'("?(?:pwd|pass|password|srvpass|cpass|chlpass|tibcopass|truststorepass|'
    r'keystorepass|storepass|keypass|sslpass|inttoken|token|agent_token|'
    r'collector_token|optadvisor_token|optadvisor_token_uid|'
    r'optadvisor_token_expires_at|secret|api_key|apikey|authorization)"?'
    r'\s*[:=]\s*)(".*?"|\'.*?\'|[^,\}\s]+)',
    re.IGNORECASE,
)


def normalize_key(key):
    return str(key or "").strip().lower()


def is_encrypted_secret_key(key):
    return normalize_key(key) in ENCRYPTED_SECRET_KEYS


def is_secret_key(key):
    key = normalize_key(key)
    return (
        key in REDACTED_SECRET_KEYS
        or key.endswith("password")
        or key.endswith("pass")
        or key.endswith("token")
        or key.endswith("secret")
    )


def redact_text(value):
    return _SECRET_TEXT_RE.sub(r'\1"..."', str(value))


def redact_data(value, drop_keys=None):
    drop_keys = {normalize_key(key) for key in (drop_keys or set())}
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_name = normalize_key(key)
            if key_name in drop_keys:
                continue
            if is_secret_key(key_name):
                redacted[key] = "..."
            else:
                redacted[key] = redact_data(item, drop_keys)
        return redacted
    if isinstance(value, list):
        return [redact_data(item, drop_keys) for item in value]
    return value
