from django.urls import path
from . import views

urlpatterns = [
    path('',                views.wallet_view,            name='wallet'),
    path('order/create/',   views.create_wallet_order,    name='create_wallet_order'),
    path('order/verify/',   views.verify_wallet_payment,  name='verify_wallet_payment'),
]
