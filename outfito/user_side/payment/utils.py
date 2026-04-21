import razorpay
from django.conf import settings


def get_razorpay_client():
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def create_razorpay_order(amount_in_rupees, currency="INR", receipt=None):
   
    client = get_razorpay_client()
    amount_paise = int(float(amount_in_rupees) * 100)
    data = {
        "amount": amount_paise,
        "currency": currency,
        "payment_capture": 1,  
    }
    if receipt:
        data["receipt"] = str(receipt)
    return client.order.create(data=data)


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
  
    client = get_razorpay_client()
    params = {
        "razorpay_order_id": razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }
    try:
        client.utility.verify_payment_signature(params)
        return True
    except razorpay.errors.SignatureVerificationError:
        return False