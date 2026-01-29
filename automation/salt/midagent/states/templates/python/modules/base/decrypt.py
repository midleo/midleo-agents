import base64
import binascii
import json
from modules.base import classes

from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
from pathlib import Path
import base64

_SECRET_PATH = Path("/run/secrets/crypto.secret")
_SECRET: bytes | None = None
_SUFFIX = b"|midleo|v1"

def _get_secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        _SECRET = _SECRET_PATH.read_text(
            encoding="utf-8"
        ).strip().encode("utf-8")
    return _SECRET


def _derive_key() -> bytes:
    return SHA256.new(_get_secret() + _SUFFIX).digest()

def encryptPWD(payload: str) -> str:
    key = _derive_key()
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(payload.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ciphertext).decode("ascii")

def encrypt(data: dict, passphrase) -> str:
    try:
        data_json_64 = base64.b64encode(json.dumps(data).encode())
        key = binascii.unhexlify(passphrase)
        iv = Random.get_random_bytes(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        encrypted, tag = cipher.encrypt_and_digest(data_json_64)
        payload = {
           "iv": base64.b64encode(iv).decode(),
           "data": base64.b64encode(encrypted).decode(),
           "tag": base64.b64encode(tag).decode()
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()
    except Exception as ex:
        classes.Err("Exception:"+str(ex))

def decryptit(data: str, passphrase) -> dict:
    try:
        key = binascii.unhexlify(passphrase)
        encrypted = json.loads(base64.b64decode(data).decode('ascii'))
        encrypted_data = base64.b64decode(encrypted['data'])
        iv = base64.b64decode(encrypted['iv'])
        tag = base64.b64decode(encrypted['tag'])
        cipher = AES.new(key, AES.MODE_GCM, iv)
        decrypted = cipher.decrypt_and_verify(encrypted_data, tag)
        return json.loads(base64.b64decode(decrypted).decode('ascii'))
    except Exception as ex:
        classes.Err("Exception:"+str(ex))