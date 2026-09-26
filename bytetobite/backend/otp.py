"""OTP generation + verification for institutional login.

Design:
  - 6-digit random code generated with `secrets` (crypto-safe).
  - Code is NEVER stored in plaintext — only a SHA-256 hash with a server-side pepper.
  - 10-minute expiry window.
  - Any consumer (KYC flows, institutional signup, driver login) can use these helpers.
"""

import hashlib
import os
import secrets
from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
OTP_PEPPER = os.getenv("OTP_PEPPER", "dev-pepper")
OTP_TTL_MINUTES = 10
OTP_LENGTH = 6


# ─────────────────────────────────────────────
# GENERATE
# ─────────────────────────────────────────────
def generate_otp() -> str:
    """Return a cryptographically random 6-digit code as a string.

    Uses secrets.randbelow so it's safe for auth — never use `random`.
    """
    return f"{secrets.randbelow(900000) + 100000}"


# ─────────────────────────────────────────────
# HASH
# ─────────────────────────────────────────────
def hash_otp(code: str, mobile: str) -> str:
    """SHA-256 the code with the server pepper + the mobile it was sent to.

    Binding the mobile into the hash prevents an attacker who steals
    a hash from reusing it against a different mobile number.
    """
    payload = f"{OTP_PEPPER}:{mobile}:{code}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ─────────────────────────────────────────────
# EXPIRY
# ─────────────────────────────────────────────
def expiry() -> datetime:
    """Return the UTC moment when a newly created OTP should stop working."""
    return datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)


def expiry_ms() -> int:
    """Same as expiry() but as milliseconds-since-epoch (frontend-friendly)."""
    return int(expiry().timestamp() * 1000)


# ─────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────
def is_valid_format(code: str) -> bool:
    """Check the OTP is exactly 6 digits — used before hashing to skip work."""
    return isinstance(code, str) and len(code) == OTP_LENGTH and code.isdigit()


# ─────────────────────────────────────────────
# AADHAAR-style KYC HASH (reuses the same pepper)
# ─────────────────────────────────────────────
def hash_kyc_id(raw_id: str, kind: str = "aadhaar") -> str:
    """One-way hash for Aadhaar / GST / Darpan IDs used in KYC endpoints."""
    payload = f"{OTP_PEPPER}:{kind}:{raw_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()