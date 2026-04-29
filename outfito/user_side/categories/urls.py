from django.urls import path
from . import views


urlpatterns = [
    path('categories/',  views.user_category_list, name='categories_page'),
]
