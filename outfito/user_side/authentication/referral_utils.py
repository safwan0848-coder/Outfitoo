import secrets
import string
from django.db import transaction, IntegrityError
from django.contrib.auth import get_user_model
User = get_user_model()

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits
REFERRAL_LENGTH   = 8
MAX_RETRIES       = 10

def generate_referral_code():
    for _ in range(MAX_RETRIES):
        code = ''.join(secrets.choice(REFERRAL_ALPHABET) for _ in range(REFERRAL_LENGTH))
        if not User.objects.filter(referral_code=code).exists():
            return code
    raise RuntimeError("Could not generate a unique referral code after max retries.")


def validate_referral_code(code):
    if not code or not isinstance(code, str):
        return None
    code=code.strip().upper()
    if len(code) != REFERRAL_LENGTH:
        return None
    return User.objects.filter(referral_code=code).first()


def assign_referral(user, code):
    if not code:
        return False
    if user.referred_by is not None:         
        return False
    referrer=validate_referral_code(code)
    if referrer is None:                     
        return False
    if referrer.pk == user.pk:               
        return False
    try:
        with transaction.atomic():
            user.referred_by=referrer
            user.referral_used=True
            user.save(update_fields=['referred_by', 'referral_used'])
        return True
    except Exception:
        return False
