from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from decimal import Decimal
from user_side.wallet.refund_utils import FREE_SHIPPING_THRESHOLD, SHIPPING_CHARGE
from .utils import calculate_cart_offers
from .models import Cart, CartItem
from admin_side.variants_management.models import Variant


def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _cart_summary_json(cart):
    items=list(cart.items.select_related('product', 'variant').order_by('id'))
    subtotal=Decimal('0.00')
    for item in items:
        item.base_subtotal = item.variant.price * item.quantity
        subtotal += item.base_subtotal

    offer_data=calculate_cart_offers(items)
    offer_discount=offer_data['total_offer_discount']

    for item in items:
        offer_info = offer_data['item_discounts'].get(item.id, {})
        item.offer_discount = offer_info.get('amount', Decimal('0.00'))
        item.offer_dict = offer_info
        item.final_subtotal = item.base_subtotal - item.offer_discount

    effective_subtotal = subtotal - offer_discount
    shipping = (
        Decimal('0.00')
        if effective_subtotal >= FREE_SHIPPING_THRESHOLD
        else SHIPPING_CHARGE
    )
    total = effective_subtotal + shipping
    item_count = sum(i.quantity for i in items)

    return {
        'subtotal':float(subtotal),
        'effective_subtotal':float(effective_subtotal),
        'discount':float(offer_discount),
        'shipping':float(shipping),
        'total':float(total),
        'item_count':item_count,
        'items': {
            str(item.id): {
                'quantity':item.quantity,
                'base_subtotal': float(item.base_subtotal),
                'disc_subtotal': float(item.final_subtotal),
                'offer_disc':float(item.offer_discount),
                'unit_price':float(item.variant.price),
            }
            for item in items
        },
    }

MAX_QTY = 5


def get_or_create_cart(user):
    if not user.is_authenticated:
        return None

    cart, created = Cart.objects.get_or_create(user=user)
    return cart

def _variant_is_purchasable(variant):
    product=variant.product

    if not variant.is_active:
        return False, "This variant is no longer available."

    if product.is_deleted or not product.is_listed:
        return False, f"'{product.name}' is currently unavailable."

    if variant.stock <= 0:
        return False, f"'{product.name}' ({variant.size} / {variant.color}) is out of stock."

    return True, ""

@login_required
@require_POST
def add_to_cart(request, pk):
    variant=get_object_or_404(Variant, pk=pk)

    try:
        quantity=int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        quantity = 1

    quantity=max(1, quantity)
    action=request.POST.get('action', 'cart')

    if not variant.is_active or variant.stock <= 0:
        msg = "This product is not available."
        if _is_ajax(request):
            return JsonResponse({'ok': False, 'warning': msg})
        messages.error(request, msg)
        return redirect('user_product_list')

    cart=get_or_create_cart(request.user)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        variant=variant,
        defaults={
            'product': variant.product,
            'quantity': 0,
        }
    )

    new_qty=item.quantity + quantity
    warn_msg = None

    if new_qty > variant.stock:
        if item.quantity >= variant.stock:
            warn_msg = f"Maximum available stock ({variant.stock}) already in cart."
            if _is_ajax(request):
                return JsonResponse({'ok': False, 'warning': warn_msg})
            messages.warning(request, warn_msg)
            return redirect(request.META.get('HTTP_REFERER', 'user_product_list'))

        new_qty=variant.stock
        warn_msg = f"Only {variant.stock} available. Quantity adjusted."
        if not _is_ajax(request):
            messages.warning(request, warn_msg)

    MAX_QTY=5
    if new_qty > MAX_QTY:
        new_qty = MAX_QTY
        warn_msg = f"Maximum {MAX_QTY} units allowed."
        if not _is_ajax(request):
            messages.warning(request, warn_msg)

    item.quantity=new_qty
    item.save()

    try:
        from user_side.wishlist.models import Wishlist, WishlistItem
        wishlist = Wishlist.objects.filter(user=request.user).first()
        wishlist_count = 0
        if wishlist:
            WishlistItem.objects.filter(
                wishlist=wishlist,
                product=variant.product
            ).delete()
            wishlist_count = wishlist.items.count()   # count AFTER delete

    except Exception:
        wishlist_count = 0

    msg = f"'{variant.product.name}' added to cart!"
    if not _is_ajax(request):
        messages.success(request, msg)

    if _is_ajax(request):
        cart = get_or_create_cart(request.user)
        summary = _cart_summary_json(cart)
        # Include wishlist_count so the frontend can update the navbar badge instantly
        return JsonResponse({'ok': True, 'message': msg, 'warning': warn_msg,
                             'wishlist_count': wishlist_count, **summary})

    if action == 'buy':
        return redirect('cart_view')

    return redirect(request.META.get('HTTP_REFERER', 'user_product_list'))

@never_cache
@login_required(login_url='login')
def cart_view(request):
    cart=get_or_create_cart(request.user)
    items=list(cart.items.select_related('product', 'variant').order_by('id'))
    subtotal = Decimal('0.00')
    has_oos = False
    item_count = 0

    for item in items:
        v = item.variant
        if (
            not v.is_active or
            v.product.is_deleted or
            not v.product.is_listed or
            v.stock == 0
        ):
            has_oos = True
        
        item.base_subtotal = v.price * item.quantity
        subtotal += item.base_subtotal
        item_count += item.quantity

    offer_data=calculate_cart_offers(items)
    offer_discount = offer_data['total_offer_discount']
    
    for item in items:
        offer_info = offer_data['item_discounts'].get(item.id, {})
        item.offer_discount = offer_info.get('amount', Decimal('0.00'))
        item.offer_dict = offer_info
        item.final_subtotal = item.base_subtotal - item.offer_discount

    effective_subtotal = subtotal - offer_discount
    shipping=Decimal('0.00') if effective_subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_CHARGE
    total=effective_subtotal + shipping

    return render(request, 'user/cart.html', {
        'items':items,
        'item_count':item_count,
        'subtotal':subtotal,
        'effective_subtotal': effective_subtotal,
        'discount': offer_discount,
        'shipping':shipping,
        'total':total,
        'savings':offer_discount,
        'has_oos':has_oos,
        'max_qty':MAX_QTY,
        'applied_offers':offer_data['applied_offer_messages'],
    })

@never_cache
@login_required(login_url='login')
@require_POST
def update_cart_qty(request, item_id):
    item = get_object_or_404( CartItem,id=item_id,cart__user=request.user)
    action = request.POST.get('action', 'increment')
    v = item.variant
    ok, reason = _variant_is_purchasable(v)
    if not ok:
        messages.error(request, reason)
        return redirect('cart_view')

    warn_msg = None

    if action == 'increment':
        if item.quantity >= v.stock:
            warn_msg = f"Only {v.stock} units in stock."
            if not _is_ajax(request):
                messages.warning(request, warn_msg)
        elif item.quantity >= MAX_QTY:
            warn_msg = f"Maximum {MAX_QTY} units per item."
            if not _is_ajax(request):
                messages.warning(request, warn_msg)
        else:
            item.quantity += 1
            item.save()

    elif action == 'decrement':
        if item.quantity <= 1:
            item.delete()
            if _is_ajax(request):
                cart = get_or_create_cart(request.user)
                summary = _cart_summary_json(cart)
                return JsonResponse({'ok': True, 'removed': True,
                                     'item_id': item_id, **summary})
            messages.success(request, "Item removed from cart.")
            return redirect('cart_view')
        item.quantity -= 1
        item.save()

    if _is_ajax(request):
        cart = get_or_create_cart(request.user)
        summary = _cart_summary_json(cart)
        return JsonResponse({
            'ok':      warn_msg is None,
            'warning': warn_msg,
            'item_id': item_id,
            **summary,
        })

    return redirect('cart_view')


@login_required
@require_POST
def remove_item(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    name = item.product.name
    item.delete()
    msg = f"'{name}' removed from cart."
    if _is_ajax(request):
        cart = get_or_create_cart(request.user)
        summary = _cart_summary_json(cart)
        return JsonResponse({'ok': True, 'removed': True,
                             'item_id': item_id, 'message': msg, **summary})
    messages.success(request, msg)
    return redirect('cart_view')

