from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from admin_side.variants_management.models import Variant
from .models import Wishlist, WishlistItem
from admin_side.products_management.models import Product

def get_or_create_wishlist(user):
    wishlist, _ =Wishlist.objects.get_or_create(user=user)
    return wishlist


@login_required
def wishlist_view(request):
    wishlist=get_or_create_wishlist(request.user)
    items=wishlist.items.select_related('product', 'variant')
    updated_items=[]

    for item in items:
        product=item.product

        if not item.variant:
            variant=Variant.objects.filter(product=product,is_active=True).first()
            item.variant=variant
        updated_items.append(item)

    context = {
        'items': updated_items
    }
    return render(request, 'user/wishlist.html', context)

@login_required
def toggle_wishlist(request, pk):
    product=get_object_or_404(Product, pk=pk)
    wishlist=get_or_create_wishlist(request.user)
    item = WishlistItem.objects.filter(wishlist=wishlist,product=product).first()

    if item:
        item.delete()
        action = 'removed'
        msg = "Removed from wishlist"
    else:
        WishlistItem.objects.create(wishlist=wishlist,product=product)
        action = 'added'
        msg = "Added to wishlist"

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'action': action, 'message': msg, 'wishlist_count': wishlist.items.count()})

    if action == 'removed':
        messages.info(request, msg)
    else:
        messages.success(request, msg)

    return redirect(request.META.get('HTTP_REFERER', 'home'))

@login_required
def add_to_wishlist(request, pk):

    product=get_object_or_404(Product, pk=pk)
    wishlist=get_or_create_wishlist(request.user)

    item, created = WishlistItem.objects.get_or_create( wishlist=wishlist,product=product)
    if created:
        messages.success(request, "Added to wishlist ")
    else:
        messages.info(request, "Already in wishlist")

    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required
def remove_from_wishlist(request, pk):
    wishlist=get_or_create_wishlist(request.user)
    deleted, _=WishlistItem.objects.filter(wishlist=wishlist,product_id=pk).delete()

    if deleted:
        messages.success(request, "Removed from wishlist")
    else:
        messages.warning(request, "Item not found")
    return redirect('wishlist_view')