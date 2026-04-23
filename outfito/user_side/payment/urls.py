from django.urls import path
from . import views

urlpatterns = [
    # Renders the Razorpay payment page (reads from session, no order_id needed)
    path("initiate-payment/", views.initiate_payment, name="initiate_payment"),

    # Called by Razorpay's JS handler on payment completion
    path("verify-payment/", views.verify_payment, name="verify_payment"),

    # Shown when payment fails / is dismissed (no order_id needed)
    path("payment-failed/", views.payment_failed, name="payment_failed"),
]