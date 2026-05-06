import re
from django.core.exceptions import ValidationError

def normalize_indian_phone(phone_number):
    if not phone_number:
        return phone_number
        
    phone = re.sub(r'[^0-9+]', '', str(phone_number))
    
    if phone.startswith('+91'):
        phone = phone[3:]
    elif phone.startswith('91') and len(phone) > 10:
        phone = phone[2:]
        
    return phone

def validate_indian_phone(value):
    if not value:
        return
        
    phone = normalize_indian_phone(value)
    
    if not re.match(r'^[6-9]\d{9}$', phone):
        raise ValidationError("Enter a valid 10-digit Indian mobile number starting with 6-9.")
