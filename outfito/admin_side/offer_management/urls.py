from django.urls import path
from . import views

urlpatterns = [
    path('offers/', views.offer_list, name='offer_list'),
    path('offers/add/', views.add_offer, name='add_offer'),
    path('offers/edit/<int:pk>/', views.edit_offer, name='edit_offer'),
    path('offers/delete/<int:pk>/', views.delete_offer, name='delete_offer'),
    path('offers/toggle/<int:pk>/', views.toggle_offer_status, name='toggle_offer_status'),
]