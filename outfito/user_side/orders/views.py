from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Q, F
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
import json
from django.conf import settings
from django.contrib import messages
from user_side.cart.models import Cart
from user_side.address.models import Address
from .models import Order, OrderItem,ReturnRequest
from xhtml2pdf import pisa
from decimal import Decimal
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from admin_side.coupon_management.models import Coupon
import razorpay
from user_side.payment.models import Payment

VALID_STATUSES = {
    'placed', 'confirmed', 'shipped',
    'delivered', 'returned', 'cancelled', 'pending'
}

from django.utils import timezone

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.db.models import F
from django.utils import timezone

# NOTE: Add your existing imports here (Cart, Address, Coupon, etc.)


@login_required
def checkout_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related('variant', 'variant__product')

    if not cart_items.exists():
        return redirect('cart')

    addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')
    default_address = addresses.filter(is_default=True).first()

    subtotal = sum(item.quantity * item.variant.price for item in cart_items)

    tax = 0
    delivery = 50
    discount = 0

    coupon_id = request.session.get('coupon_id')
    applied_coupon_code = None
    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id, is_active=True)
            if subtotal >= coupon.min_amount:
                applied_coupon_code = coupon.code
                if coupon.discount_type == 'fixed':
                    discount = coupon.discount_value
                else:
                    calculated = (subtotal * coupon.discount_value) / 100
                    if coupon.max_discount:
                        calculated = min(calculated, coupon.max_discount)
                    discount = calculated
            else:
                request.session.pop('coupon_id', None)
        except Coupon.DoesNotExist:
            request.session.pop('coupon_id', None)

    total = subtotal + tax + delivery - discount

    now = timezone.now()
    available_coupons = Coupon.objects.filter(
        is_active=True,
        start_date__lte=now,
        expiry_date__gte=now
    ).exclude(
        usage_limit__isnull=False,
        used_count__gte=F('usage_limit')
    )

    context = {
        "cart_items": cart_items,
        "addresses": addresses,
        "default_address": default_address,
        "subtotal": subtotal,
        "tax": tax,
        "delivery": delivery,
        "discount": discount,
        "total": total,
        "available_coupons": available_coupons,
        "applied_coupon_code": applied_coupon_code,
    }
    return render(request, "user/checkout.html", context)

@login_required
def order_success(request, order_id):
    order=get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "user/success.html", {"order": order})


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


@login_required
def apply_coupon(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            code = data.get('code', '').strip().upper()
            
            cart, _ = Cart.objects.get_or_create(user=request.user)
            cart_items = cart.items.select_related('variant')
            subtotal = sum(item.quantity * item.variant.price for item in cart_items)
            
            if not code:
                request.session.pop('coupon_id', None)
                return JsonResponse({'success': True, 'message': 'Coupon removed', 'discount': 0.0, 'new_total': float(subtotal + 50)})
                
            try:
                coupon = Coupon.objects.get(code__iexact=code, is_active=True)
            except Coupon.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Invalid or expired coupon code.'})
                
            if subtotal < coupon.min_amount:
                return JsonResponse({'success': False, 'message': f'Minimum order amount of ₹{coupon.min_amount} required.'})
                
            if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
                return JsonResponse({'success': False, 'message': 'This coupon usage limit has been reached.'})
                
            if coupon.discount_type == 'fixed':
                discount = coupon.discount_value
            else:
                calculated = (subtotal * coupon.discount_value) / 100
                if coupon.max_discount:
                    calculated = min(calculated, coupon.max_discount)
                discount = calculated
                
            request.session['coupon_id'] = coupon.id
            new_total = float(subtotal + 50 - discount) # assuming tax=0, delivery=50
            return JsonResponse({'success': True, 'message': 'Coupon applied successfully!', 'discount': float(discount), 'new_total': new_total})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@login_required
def place_order(request):
    if request.method != "POST":
        return redirect('checkout')
 
    address_id = request.POST.get("address_id")
    payment_method = request.POST.get("payment_method")
 
    if not address_id:
        messages.error(request, "Select address")
        return redirect('checkout')
 
    if payment_method not in ["razorpay", "wallet", "cod"]:
        messages.error(request, "Invalid payment method")
        return redirect('checkout')
 
    address = get_object_or_404(Address, id=address_id, user=request.user)
 
    cart = Cart.objects.get(user=request.user)
    items = cart.items.select_related('variant')
 
    if not items.exists():
        messages.error(request, "Cart empty")
        return redirect('cart')
 
    subtotal = sum(i.quantity * i.variant.price for i in items)
    delivery = 50
    tax = 0
    discount = 0
 
    # coupon
    coupon = None
    coupon_id = request.session.get('coupon_id')
    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id, is_active=True)
            if subtotal >= coupon.min_amount:
                if coupon.discount_type == 'fixed':
                    discount = coupon.discount_value
                else:
                    calc = (subtotal * coupon.discount_value) / 100
                    if coupon.max_discount:
                        calc = min(calc, coupon.max_discount)
                    discount = calc
            else:
                coupon = None
        except Coupon.DoesNotExist:
            coupon = None
 
    total = max(subtotal + delivery + tax - discount, 0)
 
    # stock check only (no deduction yet)
    for item in items:
        if item.variant.stock < item.quantity:
            messages.error(request, f"Stock issue for {item.variant}")
            return redirect('cart')
 
    # create order (pending)
    order = Order.objects.create(
        user=request.user,
        shipping_address=address,
        payment_method=payment_method,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=discount,
        coupon=coupon,
        delivery_charge=delivery,
        total_amount=total,
        payment_status='pending'
    )
 
    # create order items
    for item in items:
        OrderItem.objects.create(
            order=order,
            variant=item.variant,
            price=item.variant.price,
            quantity=item.quantity
        )
 
    # ---------------- COD ----------------
    if payment_method == "cod":
        Payment.objects.create(
            order=order,
            payment_method='cod',
            payment_status='pending',
            amount=total
        )
 
        for item in items:
            item.variant.stock -= item.quantity
            item.variant.save()
 
        cart.items.all().delete()
        request.session.pop('coupon_id', None)
 
        return redirect('order_success', order_id=order.id)
 
    # ---------------- WALLET ----------------
    if payment_method == "wallet":
        wallet = request.user.wallet
        if wallet.balance < total:
            messages.error(request, "Insufficient wallet balance")
            return redirect('checkout')
 
        wallet.balance -= total
        wallet.save()
 
        Payment.objects.create(
            order=order,
            payment_method='wallet',
            payment_status='success',
            amount=total
        )
 
        order.payment_status = 'paid'
        order.save()
 
        for item in items:
            item.variant.stock -= item.quantity
            item.variant.save()
 
        cart.items.all().delete()
        request.session.pop('coupon_id', None)
 
        return redirect('order_success', order_id=order.id)
 
    # ---------------- RAZORPAY ----------------
    if payment_method == "razorpay":
        payment = Payment.objects.create(
            order=order,
            payment_method='razorpay',
            payment_status='pending',
            amount=total
        )
 
        key_id = settings.RAZORPAY_KEY_ID.strip(' "\'')
        key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
        client = razorpay.Client(auth=(key_id, key_secret))
 
        rp_order = client.order.create({
            "amount": int(total * 100),
            "currency": "INR",
            "payment_capture": "1"
        })
 
        payment.razorpay_order_id = rp_order['id']
        payment.save()
 
        return redirect('payment_page', order_id=order.id)
