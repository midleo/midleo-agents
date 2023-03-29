import base64
import binascii
import json

from Crypto import Random
from Crypto.Cipher import AES


PASSPHRASE = b'';

def encrypt(data: dict, passphrase) -> str:
    data_json_64 = base64.b64encode(json.dumps(data).encode('ascii'))
    try:
        key = binascii.unhexlify(passphrase)
        iv = Random.get_random_bytes(AES.block_size)
        cipher = AES.new(key, AES.MODE_GCM, iv)
        encrypted, tag = cipher.encrypt_and_digest(data_json_64)
        encrypted_64 = base64.b64encode(encrypted).decode('ascii')
        iv_64 = base64.b64encode(iv).decode('ascii')
        tag_64 = base64.b64encode(tag).decode('ascii')
        json_data = {'iv': iv_64, 'data': encrypted_64, 'tag': tag_64}
        return base64.b64encode(json.dumps(json_data).encode('ascii')).decode('ascii')
    except Exception as e:
        print("Cannot encrypt datas...")
        print(e)
        exit(1)

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
    except Exception as e:
        print("Cannot decrypt datas...")
        print(e)
        exit(1)