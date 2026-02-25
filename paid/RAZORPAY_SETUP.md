# Razorpay Integration Setup (Paid EmoScreen)

## Prerequisites

1. Razorpay account with both **Test** and **Live** credentials.
2. HTTPS-enabled deployment URL (required for production webhooks/checkout best practice).
3. Python dependency:
   - `requests` (already used by backend adapter)
4. Frontend dependency:
   - Razorpay Checkout script: `https://checkout.razorpay.com/v1/checkout.js`

---

## Environment variables / Django settings

Add these in environment variables and load into Django settings:

```python
# mode switch
RAZORPAY_LIVE_MODE = env.bool("RAZORPAY_LIVE_MODE", default=False)

# test credentials
RAZORPAY_KEY_ID_TEST = env("RAZORPAY_KEY_ID_TEST", default="")
RAZORPAY_KEY_SECRET_TEST = env("RAZORPAY_KEY_SECRET_TEST", default="")
RAZORPAY_WEBHOOK_SECRET_TEST = env("RAZORPAY_WEBHOOK_SECRET_TEST", default="")

# live credentials
RAZORPAY_KEY_ID_LIVE = env("RAZORPAY_KEY_ID_LIVE", default="")
RAZORPAY_KEY_SECRET_LIVE = env("RAZORPAY_KEY_SECRET_LIVE", default="")
RAZORPAY_WEBHOOK_SECRET_LIVE = env("RAZORPAY_WEBHOOK_SECRET_LIVE", default="")
```

And map webhook secret (example):

```python
RAZORPAY_WEBHOOK_SECRET = (
    RAZORPAY_WEBHOOK_SECRET_LIVE if RAZORPAY_LIVE_MODE else RAZORPAY_WEBHOOK_SECRET_TEST
)
```

> Never expose `RAZORPAY_KEY_SECRET_*` on frontend.

---

## Backend flow implemented

### 1) Order creation (server-side)
- Endpoint/view: `paid.views.patient_payment`
- Uses `RazorpayAdapter.create_order()` (Orders API).
- Stores gateway order id in `EsPayTransaction.gateway_order_id`.

### 2) Checkout (frontend)
- Template: `paid/templates/paid/patient_payment.html`
- Uses Razorpay Checkout with server-created `order_id` and public `key_id`.
- On success posts `razorpay_payment_id`, `razorpay_order_id`, `razorpay_signature` to backend.

### 3) Signature verification (server-side)
- `RazorpayAdapter.verify_signature()` verifies:
  - HMAC SHA256 of `order_id|payment_id` with `key_secret`.

### 4) Webhook verification
- Endpoint: `POST /payments/razorpay/webhook/`
- View: `paid.views.razorpay_webhook`
- Signature header: `X-Razorpay-Signature`
- Verified using `RazorpayAdapter.verify_webhook_signature()`.

### 5) DB persistence
The following are stored/updated:
- `EsPayTransaction`: `gateway_order_id`, `gateway_payment_id`, `gateway_signature`, `status`, `amount_paise`, `currency`, `raw_payload_json`.
- `EsPayOrder`: status and `paid_at`.
- `EsPayRevenueSplit`: idempotent 50/50 split.
- `EsPayEmailLog`: status and message metadata.

---

## Webhook configuration in Razorpay

1. Go to Razorpay Dashboard → Webhooks.
2. Add webhook URL:
   - `https://<your-domain>/payments/razorpay/webhook/`
3. Subscribe at least to:
   - `payment.captured`
   - `payment.failed`
   - `order.paid`
4. Set secret to match `RAZORPAY_WEBHOOK_SECRET_*`.

---

## Testing in Razorpay test mode

1. Set:
   - `RAZORPAY_LIVE_MODE=False`
   - test keys/secrets
2. Start payment flow from a paid order.
3. Use Razorpay test card(s), e.g.:
   - Card: `4111 1111 1111 1111`
   - Any future expiry, any CVV
4. Confirm:
   - backend marks transaction `SUCCESS`
   - order becomes `PAID`
   - webhook updates are accepted
   - logs show expected `QUEUED/SENT/FAILED` semantics.

---

## Switching to production

1. Enable HTTPS in deployment.
2. Set:
   - `RAZORPAY_LIVE_MODE=True`
   - live key/secret/webhook secret
3. Update Razorpay webhook URL to production domain.
4. Run smoke test with a small real payment.
5. Monitor webhook and email logs.

---

## Security best practices checklist

- [x] Secret key never sent to frontend
- [x] Payment signature verified on backend
- [x] Webhook signature verified
- [x] Order-id mismatch rejected
- [x] Status transitions persisted with audit payload
- [x] Use environment variables for credentials
- [x] Use HTTPS in production
