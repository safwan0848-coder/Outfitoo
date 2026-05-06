import re
from django.core.exceptions import ValidationError

def normalize_indian_phone(phone_number):
    """
    Normalizes a phone number string by removing spaces, non-digit characters
    (except +), and common Indian country code prefixes like +91 or 91.
    """
    if not phone_number:
        return phone_number
        
    # Remove all spaces and non-digit characters except '+'
    phone = re.sub(r'[^0-9+]', '', str(phone_number))
    
    # Remove +91 or 91 prefix if it exists and the remaining digits are likely a mobile number
    if phone.startswith('+91'):
        phone = phone[3:]
    elif phone.startswith('91') and len(phone) > 10:
        phone = phone[2:]
        
    return phone

def validate_indian_phone(value):
    """
    Validates that a given phone number is exactly 10 digits long
    and starts with 6, 7, 8, or 9 (standard Indian mobile format).
    Raises ValidationError if invalid.
    """
    if not value:
        return
        
    phone = normalize_indian_phone(value)
    
    if not re.match(r'^[6-9]\d{9}$', phone):
        raise ValidationError("Enter a valid 10-digit Indian mobile number starting with 6-9.")
