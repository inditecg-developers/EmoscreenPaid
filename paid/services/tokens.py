import hashlib
import secrets
from datetime import timedelta

from django.core import signing
from django.utils import timezone


def build_order_token_payload(order, doctor_code: str):
    return {
        "order_code": order.order_code,
        "doctor_code": doctor_code,
        "form_code": order.form_id,
        "amount_paise": order.final_amount_paise,
        "exp": int((timezone.now() + timedelta(days=7)).timestamp()),
        "nonce": secrets.token_hex(8),
    }


def sign_payload(payload: dict) -> str:
    return signing.dumps(payload, salt="paid-order-link")


def unsign_payload(token: str, max_age_seconds: int = 604800) -> dict:
    return signing.loads(token, salt="paid-order-link", max_age=max_age_seconds)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
