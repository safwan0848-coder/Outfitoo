import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'outfito.settings')
django.setup()
from django.conf import settings
import razorpay

key_id = settings.RAZORPAY_KEY_ID.strip(' "\'')
key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
print('ID:', key_id)
print('SECRET:', key_secret)

client = razorpay.Client(auth=(key_id, key_secret))
try:
    print(client.order.all())
    print("AUTH SUCCESS!")
except Exception as e:
    print("AUTH FAILED:", str(e))
