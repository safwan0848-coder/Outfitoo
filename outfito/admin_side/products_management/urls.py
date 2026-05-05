from django.urls import path
from . import views

urlpatterns = [
    path('product_list/', views.product_list, name='product_list'),
    path('add/', views.add_product, name='add_product'),
    path('products/<int:pk>/edit/',    views.edit_product,   name='edit_product'),
    path('products/<int:pk>/archive/',  views.archive_product, name='archive_product'),
    path('products/archived/', views.archived_product_list, name='archived_product_list'),
    path('products/<int:pk>/restore/', views.restore_product, name='restore_product'),
    path('products/<int:pk>/toggle/', views.toggle_product_status, name='toggle_product_status'),
]