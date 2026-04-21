# from django.urls import path
# from . import views

# urlpatterns = [
#     path('payment/<int:order_id>/', views.payment, name='payment'),
#     path('payment/verify/', views.payment_verify, name='payment_verify'),
#     path('payment/callback/', views.razorpay_callback, name='razorpay_callback'),
# ]


from django.urls import path
from . import views


urlpatterns = [
    
path("payment/<int:order_id>/",views.payment_page, name="payment_page"),
path("verify-payment/", views.verify_payment, name="verify_payment"),
path("payment-failed/<int:order_id>/", views.payment_failed, name="payment_failed"),
]