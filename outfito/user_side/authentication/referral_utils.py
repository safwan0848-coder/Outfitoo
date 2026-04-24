"""
referral_utils.py
Secure referral code generation and assignment utilities.
"""
import secrets
import string
from django.db import transaction, IntegrityError

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits   # A-Z + 0-9
REFERRAL_LENGTH   = 8
MAX_RETRIES       = 10


# ──────────────────────────────────────────────────────────────
# Code Generation
# ──────────────────────────────────────────────────────────────

def generate_referral_code():
    """
    Generate a cryptographically random 8-char uppercase alphanumeric code.
    Retries up to MAX_RETRIES times to guarantee DB-level uniqueness.
    Returns the code string, or raises RuntimeError if all retries fail.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    for _ in range(MAX_RETRIES):
        code = ''.join(secrets.choice(REFERRAL_ALPHABET) for _ in range(REFERRAL_LENGTH))
        if not User.objects.filter(referral_code=code).exists():
            return code

    raise RuntimeError("Could not generate a unique referral code after max retries.")


# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────

def validate_referral_code(code: str):
    """
    Returns the User who owns `code`, or None if invalid / not found.
    """
    if not code or not isinstance(code, str):
        return None

    code = code.strip().upper()
    if len(code) != REFERRAL_LENGTH:
        return None

    from django.contrib.auth import get_user_model
    User = get_user_model()

    return User.objects.filter(referral_code=code).first()


# ──────────────────────────────────────────────────────────────
# Assignment
# ──────────────────────────────────────────────────────────────

def assign_referral(user, code: str) -> bool:
    """
    Validate `code` and, if valid, link `user.referred_by`.
    Silent on errors (returns False) to avoid blocking signup.

    Rules:
      - Code must exist
      - Referrer != user (no self-referral)
      - User must not already have a referrer
    """
    if not code:
        return False

    if user.referred_by is not None:          # already referred
        return False

    referrer = validate_referral_code(code)

    if referrer is None:                      # invalid code
        return False

    if referrer.pk == user.pk:                # self-referral
        return False

    try:
        with transaction.atomic():
            user.referred_by   = referrer
            user.referral_used = True
            user.save(update_fields=['referred_by', 'referral_used'])
        return True
    except Exception:
        return False
