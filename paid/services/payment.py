import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


class RazorpayError(Exception):
    pass


@dataclass
class GatewayOrder:
    gateway_order_id: str
    amount_paise: int
    currency: str = "INR"


class RazorpayAdapter:
    """Production-focused Razorpay integration (orders + signature checks)."""

    api_base = "https://api.razorpay.com/v1"

    def __init__(self):
        self.live_mode = bool(getattr(settings, "RAZORPAY_LIVE_MODE", False))
        self.key_id = self._setting("RAZORPAY_KEY_ID")
        self.key_secret = self._setting("RAZORPAY_KEY_SECRET")
        self.webhook_secret = self._setting("RAZORPAY_WEBHOOK_SECRET", required=False)

    def _setting(self, base: str, required: bool = True) -> str:
        if self.live_mode:
            value = getattr(settings, f"{base}_LIVE", "")
            if value:
                return value
        value = getattr(settings, f"{base}_TEST", "") or getattr(settings, base, "")
        if required and not value:
            raise RazorpayError(f"Missing Razorpay setting: {base}{'_LIVE/_TEST' if self.live_mode else ''}")
        return value

    @property
    def public_key_id(self) -> str:
        return self.key_id

    def _auth_header(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.key_id}:{self.key_secret}".encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Basic {token}"}

    def create_order(self, receipt: str, amount_paise: int, notes: dict[str, Any] | None = None) -> GatewayOrder:
        if amount_paise < 0:
            raise RazorpayError("Amount cannot be negative")
        payload = {
            "amount": int(amount_paise),
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": 1,
            "notes": notes or {},
        }
        response = requests.post(
            f"{self.api_base}/orders",
            headers={**self._auth_header(), "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        if response.status_code >= 400:
            raise RazorpayError(f"Razorpay order create failed: {response.status_code} {response.text}")

        body = response.json()
        return GatewayOrder(
            gateway_order_id=body["id"],
            amount_paise=int(body.get("amount") or amount_paise),
            currency=body.get("currency", "INR"),
        )

    def verify_signature(self, payload: dict[str, Any]) -> bool:
        order_id = (payload.get("razorpay_order_id") or payload.get("gateway_order_id") or "").strip()
        payment_id = (payload.get("razorpay_payment_id") or payload.get("gateway_payment_id") or "").strip()
        signature = (payload.get("razorpay_signature") or payload.get("gateway_signature") or "").strip()
        if not order_id or not payment_id or not signature:
            return False
        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self.webhook_secret or not signature:
            return False
        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
