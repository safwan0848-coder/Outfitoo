from django.urls import path, include

urlpatterns = [
    path('', include('admin_side.authentication.urls')),
    path('', include('admin_side.user_management.urls')),
    path('', include('admin_side.products_management.urls')),
    path('', include('admin_side.categories_management.urls')),
    path('', include('admin_side.variants_management.urls')),
    path('', include('admin_side.order_management.urls')),
    path('', include('admin_side.coupon_management.urls')),
    path('', include('admin_side.offer_management.urls')),
    path('', include('admin_side.dashboard.urls')),
]