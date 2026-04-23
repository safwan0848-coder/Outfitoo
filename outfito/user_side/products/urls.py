from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='user_product_list'),
    path('ajax/search/', views.search_products_ajax, name='ajax_search'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/review/', views.submit_review, name='submit_review'),
]