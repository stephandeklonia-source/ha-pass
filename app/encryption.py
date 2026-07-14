"""PIN encryption using AES-256-GCM."""
import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

NONCE_SIZE = 12  # 96 bits recommended for GCM
KEY_SIZE = 32  # 256 bits


def _get_key_bytes() -> bytes:
    if not settings.encryption_key:
        raise ValueError("encryption_key is not configured")
    try:
        key = binascii.unhexlify(settings.encryption_key)
    except binascii.Error as e:
        raise ValueError(f"encryption_key must be valid hex: {e}")
    if len(key) != KEY_SIZE:
        raise ValueError(f"encryption_key must be {KEY_SIZE * 2} hex characters (got {len(settings.encryption_key)})")
    return key


def encrypt_pin(plaintext_pin: str) -> str:
    """Encrypt a PIN, returning base64-encoded (nonce + ciphertext + auth_tag)."""
    key = _get_key_bytes()
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_pin.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_pin(ciphertext_b64: str) -> str:
    key = _get_key_bytes()
    try:
        combined = base64.urlsafe_b64decode(ciphertext_b64)
    except Exception as e:
        raise ValueError(f"Invalid base64 ciphertext: {e}")
    if len(combined) < NONCE_SIZE:
        raise ValueError("Ciphertext too short")
    nonce, ciphertext = combined[:NONCE_SIZE], combined[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
