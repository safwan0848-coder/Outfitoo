from django.urls import path
from . import views

urlpatterns = [
    path('checkout/',views.checkout_view, name='checkout'),
    path('payment-success/<int:order_id>/',views.order_success, name='order_success'),
    path('orders/', views.order_list, name='order_list'),
    path('place-order/',views.place_order, name='place_order'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('cancel/<int:order_id>/', views.cancel_order, name='cancel_order'),
    path('return/<int:order_id>/', views.return_order, name='return_order'),
    path('invoice/<int:order_id>/', views.download_invoice, name='download_invoice'),
    path('apply-coupon/', views.apply_coupon, name='apply_coupon'),
]