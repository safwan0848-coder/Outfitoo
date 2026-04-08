from django.urls import path
from . import views

urlpatterns = [
    path('wishlist/', views.wishlist_view, name='wishlist_view'),
    path('wishlist/add/<int:pk>/', views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:pk>/', views.remove_from_wishlist, name='remove_from_wishlist'),
    path('wishlist/toggle/<int:pk>/', views.toggle_wishlist, name='toggle_wishlist'),
]
