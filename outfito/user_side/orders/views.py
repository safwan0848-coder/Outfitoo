from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
from django.contrib import messages
from user_side.cart.models import Cart
from user_side.address.models import Address
from .models import Order, OrderItem,ReturnRequest
from xhtml2pdf import pisa
from decimal import Decimal
from django.core.paginator import Paginator
from django.template.loader import render_to_string

VALID_STATUSES = {
    'placed', 'confirmed', 'shipped',
    'delivered', 'returned', 'cancelled', 'pending'
}

@login_required
def checkout_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items=cart.items.select_related('variant', 'variant__product')

    if not cart_items.exists():
        return redirect('cart')

    addresses=Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')
    default_address=addresses.filter(is_default=True).first()

    subtotal=sum(item.quantity * item.variant.price for item in cart_items)

    tax=0
    delivery=50
    discount=0

    total=subtotal + tax + delivery - discount

    context = {
        "cart_items": cart_items,
        "addresses": addresses,
        "default_address": default_address,
        "subtotal": subtotal,
        "tax": tax,
        "delivery": delivery,
        "discount": discount,
        "total": total,
    }
    return render(request, "user/checkout.html", context)

@login_required
def order_success(request, order_id):
    order=get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "user/success.html", {"order": order})

@login_required
def place_order(request):
    if request.method != "POST":
        return redirect('checkout')

    address_id=request.POST.get("address_id", "").strip()
    payment_method=request.POST.get("payment_method", "").strip()

    if not address_id:
        messages.error(request, "Please select a delivery address.")
        return redirect('checkout')

    VALID_PAYMENT_METHODS = ["razorpay", "wallet", "cod"]
    if payment_method not in VALID_PAYMENT_METHODS:
        messages.error(request, "Please select a valid payment method.")
        return redirect('checkout')

    address=get_object_or_404(Address, id=address_id, user=request.user)

    cart, _=Cart.objects.get_or_create(user=request.user)
    cart_items=cart.items.select_related('variant', 'variant__product')

    if not cart_items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect('cart')

    subtotal=sum(item.quantity * item.variant.price for item in cart_items)
    tax=0
    delivery=50
    discount=0
    total=subtotal + tax + delivery - discount

    try:
        with transaction.atomic():
            for item in cart_items:
                if item.variant.stock < item.quantity:
                    messages.error(request,
                        f"Insufficient stock for {item.variant.product.name}. "
                        f"Only {item.variant.stock} left."
                    )
                    return redirect('cart')

            if payment_method == "wallet":
                wallet=getattr(request.user, 'wallet', None)
                if not wallet or wallet.balance < total:
                    messages.error(request, "Insufficient wallet balance.")
                    return redirect('checkout')

            order=Order.objects.create(
                user=request.user,
                shipping_address=address,
                payment_method=payment_method,
                subtotal=subtotal,
                tax_amount=tax,
                discount_amount=discount,
                delivery_charge=delivery,
                total_amount=total,
            )

            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    variant=item.variant,
                    price=item.variant.price,
                    quantity=item.quantity
                )
                item.variant.stock -= item.quantity
                item.variant.save()

            if payment_method == "wallet":
                wallet=request.user.wallet
                wallet.balance -= total
                wallet.save()
            cart.items.all().delete()

        return redirect('order_success', order_id=order.id)

    except Exception as e:
        messages.error(request, "An error occurred while placing your order. Please try again.")
        return redirect('checkout')


@login_required
def order_list(request):
    q=request.GET.get('q', '').strip()
    status=request.GET.get('status', '').strip().lower()
    page_no=request.GET.get('page', 1)
 
    orders=Order.objects.filter(user=request.user)
 
    if q:
        orders=orders.filter(Q(order_number__icontains=q) |Q(items__variant__product__name__icontains=q)).distinct()
 
    if status and status in VALID_STATUSES:
        orders=orders.filter(payment_status__iexact=status)
 
    orders=orders.order_by('-created_at')
 
    paginator=Paginator(orders, 5)
    page_obj=paginator.get_page(page_no)
 
    return render(request, "user/order_list.html", {
        "orders": page_obj, 
        "search_query": q,
        "status_filter": status,
    })

@login_required
def order_detail(request, order_id):
    order=get_object_or_404(Order.objects.prefetch_related('items__return_requests'),id=order_id,  user=request.user)
    
    for item in order.items.all():
        item.latest_return=item.return_requests.order_by('-id').first()       
    return render(request, "user/order_detail.html", {"order": order})


@login_required
def cancel_order(request, order_id):
    if request.method != "POST":
        return redirect('order_detail', order_id=order_id)

    order=get_object_or_404(Order, id=order_id, user=request.user)
    item_id=request.POST.get('item_id', '').strip()   # empty = full cancel
    reason=request.POST.get('cancellation_reason', '').strip()
    custom=request.POST.get('custom_reason', '').strip()

    if reason == "Other" and custom:
        reason=custom
    qty_str=request.POST.get('qty', '').strip()

    with transaction.atomic():

        if not item_id:
            if order.order_status.lower() in ['shipped', 'delivered', 'cancelled']:
                messages.error(request, "This order can no longer be cancelled.")
                return redirect('order_detail', order_id=order.id)

            cancellable_items=order.items.exclude( item_status__in=['cancelled', 'delivered', 'shipped'])

            if not cancellable_items.exists():
                messages.error(request, "No cancellable items found.")
                return redirect('order_detail', order_id=order.id)

            refund_amount=Decimal('0.00')

            for item in cancellable_items:
                item.variant.stock += item.quantity
                item.variant.save()

                refund_amount += Decimal(str(item.price)) * item.quantity

                item.item_status='cancelled'
                item.cancellation_reason=reason
                item.save()

            all_items=order.items.all()
            all_cancelled = all(i.item_status == 'cancelled' for i in all_items)
            if all_cancelled:
                order.order_status='cancelled'

            active_items=order.items.exclude(item_status='cancelled')
            order.subtotal=sum(
                Decimal(str(i.price)) * i.quantity for i in active_items
            ) or Decimal('0.00')
            order.total_amount=(
                order.subtotal
                + Decimal(str(order.tax_amount or 0))
                + Decimal(str(order.delivery_charge or 0))
                - Decimal(str(order.discount_amount or 0))
            )
            order.save()

            if order.payment_status in ['paid', 'success'] and refund_amount > 0:
                messages.success(request,f"Order cancelled. Refund ₹{refund_amount} will be processed soon.")
            else:
                messages.success(request, "Order cancelled successfully.")

        else:
            item=get_object_or_404(OrderItem, id=item_id, order=order)

            if item.item_status.lower() not in ['placed', 'processing', 'confirmed']:
                messages.error(request, "This item can no longer be cancelled.")
                return redirect('order_detail', order_id=order.id)

            if not qty_str.isdigit():
                messages.error(request, "Invalid quantity.")
                return redirect('order_detail', order_id=order.id)

            cancel_qty=int(qty_str)

            if cancel_qty <= 0 or cancel_qty > item.quantity:
                messages.error(request,f"Quantity must be between 1 and {item.quantity}.")
                return redirect('order_detail', order_id=order.id)

            refund_amount=Decimal(str(item.price)) * cancel_qty

            item.variant.stock += cancel_qty
            item.variant.save()

            if cancel_qty < item.quantity:
                OrderItem.objects.create(
                    order=item.order,
                    variant=item.variant,
                    quantity=cancel_qty,
                    price=item.price,
                    item_status='cancelled',
                    cancellation_reason=reason
                )

                item.quantity -= cancel_qty
                item.save()

            else:
                item.item_status='cancelled'
                item.cancellation_reason=reason
                item.save()

            active_items=order.items.exclude(item_status='cancelled')
            order.subtotal=sum(Decimal(str(i.price)) * i.quantity for i in active_items)
            order.total_amount=(
                order.subtotal
                + Decimal(str(order.tax_amount    or 0))
                + Decimal(str(order.delivery_charge or 0))
                - Decimal(str(order.discount_amount or 0))
            )

            if not active_items.exists():
                order.order_status='cancelled'
            order.save()

            if order.payment_status in ['paid', 'success']:
                messages.success(request,f"Item cancelled. Refund ₹{refund_amount} will be processed soon.")
            else:
                messages.success(request, "Item cancelled successfully.")

    return redirect('order_detail', order_id=order.id)


@login_required
def return_order(request, order_id):
    if request.method != "POST":
        return redirect('order_detail', order_id=order_id)

    order=get_object_or_404(Order, id=order_id, user=request.user)

    item_id=request.POST.get('item_id')
    reason=request.POST.get('return_reason', '').strip()
    custom_reason=request.POST.get('custom_reason', '').strip()

    if custom_reason:
        reason=custom_reason

    if not reason:
        messages.error(request, "Return reason is required.")
        return redirect('order_detail', order_id=order.id)

    with transaction.atomic():

        if not item_id:

            items=order.items.filter(item_status='delivered')

            if not items.exists():
                messages.error(request, "No delivered items to return.")
                return redirect('order_detail', order_id=order.id)

            created_any=False
            for item in items:

                exists=ReturnRequest.objects.filter(item=item).exists()

                if exists:
                    continue

                ReturnRequest.objects.create(
                    order=order,
                    item=item,
                    reason=reason,
                    description=request.POST.get('custom_reason', '').strip()
                )
                
                item.item_status='return_requested'
                item.save()
                created_any=True

            if created_any:
                messages.success(request, "Return request submitted for order.")
            else:
                messages.error(request, "A return has already been processed or requested for all these items.")

        else:
            item=get_object_or_404(OrderItem, id=item_id, order=order)

            if item.item_status != 'delivered':
                messages.error(request, "Only delivered items can be returned.")
                return redirect('order_detail', order_id=order.id)

            exists=ReturnRequest.objects.filter(item=item).exists()

            if exists:
                messages.error(request, "A return has already been processed or requested for this item.")
                return redirect('order_detail', order_id=order.id)

            ReturnRequest.objects.create(
                order=order,
                item=item,
                reason=reason
            )
            
            item.item_status='return_requested'
            item.save()
            messages.success(request, "Return request submitted successfully.")

    return redirect('order_detail', order_id=order.id)


@login_required
def download_invoice(request, order_id):
    # 1. Get order
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # 2. Convert HTML template → string
    html = render_to_string('user/invoice.html', {'order': order})

    # 3. Create PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.order_number}.pdf"'

    # 4. Generate PDF
    pisa_status = pisa.CreatePDF(html, dest=response)

    # 5. Handle error
    if pisa_status.err:
        return HttpResponse('Error generating PDF')

    return response