"""PIN hashing + stateless HMAC-signed tokens (no external JWT dependency)."""
import base64
import hashlib
import hmac
import json
import os
import time

SECRET = os.environ.get("ORDERPAD_SECRET", "dev-secret-change-me").encode()
TOKEN_TTL_SECONDS = 12 * 60 * 60


def hash_pin(pin: str) -> str:
    return hashlib.sha256(SECRET + pin.encode()).hexdigest()


def make_token(user_id: int, role: str) -> str:
    payload = json.dumps(
        {"uid": user_id, "role": role,
         "exp": int(time.time()) + TOKEN_TTL_SECONDS}).encode()
    sig = hmac.new(SECRET, payload, hashlib.sha256).digest()
    return (base64.urlsafe_b64encode(payload).decode() + "."
            + base64.urlsafe_b64encode(sig).decode())


def read_token(token: str) -> dict | None:
    try:
        p64, s64 = token.split(".")
        payload = base64.urlsafe_b64decode(p64)
        sig = base64.urlsafe_b64decode(s64)
        expected = hmac.new(SECRET, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(payload)
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None
