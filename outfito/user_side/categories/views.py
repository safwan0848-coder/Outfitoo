from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q
 
from admin_side.products_management.models import Product
from admin_side.categories_management.models import Category

 
def user_category_list(request):
    categories = (
    Category.objects
    .filter(is_active=True, is_deleted=False)
    .annotate(product_count=Count(
        'products',
        filter=Q(
            products__is_listed=True,
            products__is_deleted=False,
            products__category__is_active=True
        )
    ))
    .order_by('category_name')
)
 
    return render(request, 'user/categories.html', {
        'categories': categories,
    })
 