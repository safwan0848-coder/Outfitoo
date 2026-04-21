from django.urls import path
from . import views

urlpatterns = [
    path('coupons/', views.coupon_list, name='coupon_list'),
    path('coupons/add/', views.add_coupon, name='add_coupon'),
    path('coupons/edit/<int:pk>/', views.edit_coupon, name='edit_coupon'),
    path('coupons/delete/<int:pk>/', views.delete_coupon, name='delete_coupon'),
]