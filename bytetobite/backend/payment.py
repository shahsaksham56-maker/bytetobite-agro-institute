"""Razorpay integration — create order + verify signature.

Frontend flow:
  1. Frontend calls POST /api/payments/create-order  →  this file's create_order()
  2. Razorpay Checkout opens, user pays
  3. Razorpay calls back with (order_id, payment_id, signature)
  4. Frontend calls POST /api/payments/verify        →  this file's verify_signature()
  5. If True → escrow milestone recorded, order confirmed.

Keys NEVER leave the backend.
"""

import os
import hmac
import hashlib
from typing import Optional

import razorpay


# ─────────────────────────────────────────────
# CONFIG (read from .env)
# ─────────────────────────────────────────────
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_CURRENCY = "INR"


# ─────────────────────────────────────────────
# LAZY SINGLETON CLIENT
# ─────────────────────────────────────────────
_client: Optional[razorpay.Client] = None


def get_client() -> razorpay.Client:
    """Build the Razorpay client once, reuse across requests."""
    global _client
    if _client is None:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise RuntimeError(
                "Razorpay keys missing — set RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET in your .env"
            )
        _client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    return _client


# ─────────────────────────────────────────────
# CREATE ORDER
# ─────────────────────────────────────────────
def create_order(
    amount_paise: int,
    receipt: str,
    notes: Optional[dict] = None,
) -> dict:
    """Create a Razorpay order. Amount MUST be in paise (₹1 = 100 paise).

    Returns Razorpay's response dict which includes:
        id, amount, currency, receipt, status, created_at
    """
    payload = {
        "amount": int(amount_paise),
        "currency": RAZORPAY_CURRENCY,
        "receipt": receipt,
        "notes": notes or {},
        "payment_capture": 1,  # auto-capture on success
    }
    return get_client().order.create(payload)


def fetch_order(order_id: str) -> dict:
    """Fetch an existing Razorpay order by id."""
    return get_client().order.fetch(order_id)


def fetch_payment(payment_id: str) -> dict:
    """Fetch a payment record (useful for reconciliation)."""
    return get_client().payment.fetch(payment_id)


# ─────────────────────────────────────────────
# VERIFY SIGNATURE
# ─────────────────────────────────────────────
def verify_signature(
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    """Constant-time HMAC-SHA256 verification.

    Razorpay signs `order_id|payment_id` with your secret key.
    We recompute and compare with hmac.compare_digest (timing-safe).
    """
    if not order_id or not payment_id or not signature:
        return False
    if not RAZORPAY_KEY_SECRET:
        return False

    body = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────
# WEBHOOK SIGNATURE (optional, for server-to-server)
# ─────────────────────────────────────────────
def verify_webhook_signature(raw_body: bytes, signature_header: str) -> bool:
    """If you enable Razorpay webhooks, verify them with this helper.

    Set the same RAZORPAY_KEY_SECRET as your webhook secret in the dashboard.
    """
    if not RAZORPAY_KEY_SECRET or not signature_header:
        return False
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def rupees_to_paise(rupees: float) -> int:
    """Convert a rupee amount (float) into integer paise."""
    return int(round(float(rupees) * 100))


def paise_to_rupees(paise: int) -> float:
    """Convert integer paise back into a rupee float."""
    return round(int(paise) / 100.0, 2)


def is_test_mode() -> bool:
    """True if we're using rzp_test_* keys (SIH demo safe)."""
    return RAZORPAY_KEY_ID.startswith("rzp_test_")