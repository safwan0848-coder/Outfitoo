from django.urls import path
from . import views

urlpatterns = [
    path('orders/', views.admin_order_list, name='admin_order_list'),
    path('orders/<int:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('orders/update-status/<int:order_id>/', views.update_order_status, name='update_order_status'),
    path('return/reject/<int:return_id>/', views.reject_return_request, name='reject_return_request'),
    path('return/approve/<int:return_id>/', views.approve_return_request, name='approve_return_request'),
    path('return/pickup/<int:return_id>/', views.pickup_return_request, name='pickup_return_request'),
    path('returns/', views.admin_returns_list, name='admin_returns_list'),
]



