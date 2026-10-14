from __future__ import annotations
import hashlib, hmac, os, secrets

ITERATIONS = 600_000

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if len(password) < 10:
        raise ValueError('Password must contain at least 10 characters.')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS).hex()
    return digest, salt

def verify_password(password: str, expected_hash: str, salt: str) -> bool:
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), ITERATIONS).hex()
    return hmac.compare_digest(actual, expected_hash)
