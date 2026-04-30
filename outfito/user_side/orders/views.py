from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.db.models import Q, F, Sum
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
import json
import uuid
from django.conf import settings
from django.contrib import messages
from user_side.cart.models import Cart
from user_side.address.models import Address
from .models import Order, OrderItem, ReturnRequest
from xhtml2pdf import pisa
from decimal import Decimal
from django.core.paginator import Paginator
from django.utils import timezone
from django.template.loader import render_to_string
from admin_side.coupon_management.models import Coupon, CouponUsage
import razorpay
from user_side.payment.models import Payment
from user_side.wallet.models import Wallet
from user_side.wallet.refund_utils import (
    process_wallet_refund,
    process_shipping_refund,
    calculate_coupon_adjusted_refund,
    FREE_SHIPPING_THRESHOLD,
    SHIPPING_CHARGE,
)

VALID_STATUSES = {
    'pending', 'shipped', 'out for delivery',
    'delivered', 'cancelled',
}


@login_required
def checkout_view(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related('variant', 'variant__product')

    if not cart_items.exists():
        return redirect('cart_view')
    addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-created_at')
    default_address = addresses.filter(is_default=True).first()

    subtotal = Decimal('0.00')
    for item in cart_items:
        item.base_subtotal = item.variant.price * item.quantity
        subtotal += item.base_subtotal

    from user_side.cart.utils import calculate_cart_offers
    offer_data=calculate_cart_offers(cart_items)
    offer_discount = offer_data['total_offer_discount']
    for item in cart_items:
        offer_info = offer_data['item_discounts'].get(item.id, {})
        item.offer_discount = offer_info.get('amount', Decimal('0.00'))
        item.offer_dict = offer_info
        item.final_subtotal=item.base_subtotal - item.offer_discount
    effective_subtotal=subtotal - offer_discount

    tax = 0
    delivery = 0 if effective_subtotal >= FREE_SHIPPING_THRESHOLD else int(SHIPPING_CHARGE)
    discount = 0

    coupon_id = request.session.get('coupon_id')
    applied_coupon_code = None
    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id, is_active=True)
            if effective_subtotal >= coupon.min_amount:
                applied_coupon_code = coupon.code
                if coupon.discount_type == 'fixed':
                    discount = coupon.discount_value
                else:
                    calculated = (effective_subtotal * coupon.discount_value) / 100
                    if coupon.max_discount:
                        calculated = min(calculated, coupon.max_discount)
                    discount = calculated
            else:
                request.session.pop('coupon_id', None)
        except Coupon.DoesNotExist:
            request.session.pop('coupon_id', None)

    total=effective_subtotal + tax + delivery - discount

    today = timezone.now().date()
    available_coupons = Coupon.objects.filter(
        is_active=True,
        expiry_date__gte=today,         
    ).filter(
        Q(start_date__isnull=True) |   
        Q(start_date__lte=today)        
    ).exclude(
        usage_limit__isnull=False,
        used_count__gte=F('usage_limit') 
    )

    wallet_balance = 0
    try:
        wallet_balance = request.user.wallet.balance
    except Wallet.DoesNotExist:
        wallet_balance = 0

    coupon_usage_info = {}
    for c in available_coupons:
        active_used = c.active_usage_count_for(request.user)
        limit= c.usage_limit_per_user
        remaining = max(limit - active_used, 0)
        coupon_usage_info[c.code] = {
            'used': active_used,
            'limit': limit,
            'remaining': remaining,
            'exhausted': remaining <= 0,
        }
    used_coupon_codes = {
        code for code, info in coupon_usage_info.items() if info['exhausted']
    }

    context = {
        "cart_items":cart_items,
        "addresses":addresses,
        "default_address":default_address,
        "subtotal":subtotal,
        "offer_discount":offer_discount,
        "applied_offers":offer_data['applied_offer_messages'],
        "effective_subtotal": effective_subtotal,
        "tax":tax,
        "delivery":delivery,
        "discount":discount,
        "total": total,
        "available_coupons": available_coupons,
        "applied_coupon_code": applied_coupon_code,
        "wallet_balance": wallet_balance,
        "used_coupon_codes":used_coupon_codes,
        "coupon_usage_info":coupon_usage_info,
    }
    return render(request, "user/checkout.html", context)


@login_required
def order_success(request, order_id):
    order=get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "user/success.html", {"order": order})


@never_cache
@login_required
def order_list(request):
    q = request.GET.get('q', '').strip()
    status  = request.GET.get('status', '').strip().lower()
    page_no = request.GET.get('page', 1)

    orders = Order.objects.filter(user=request.user).filter(
        Q(payment_method='cod') | Q(payment_status='paid')
    )

    if q:
        orders = orders.filter(
            Q(order_number__icontains=q) |
            Q(items__variant__product__name__icontains=q)
        ).distinct()

    if status and status in VALID_STATUSES:
        orders = orders.filter(order_status__iexact=status)

    orders = orders.order_by('-created_at')

    paginator = Paginator(orders, 5)
    page_obj  = paginator.get_page(page_no)

    return render(request, "user/order_list.html", {
        "orders":page_obj,
        "search_query": q,
        "status_filter": status,
    })


@never_cache
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

    order = get_object_or_404(Order, id=order_id, user=request.user)
    item_id = request.POST.get('item_id', '').strip()   # empty = full-order cancel
    reason = request.POST.get('cancellation_reason', '').strip()
    custom = request.POST.get('custom_reason', '').strip()
    if reason == 'Other' and custom:
        reason = custom
    qty_str = request.POST.get('qty', '').strip()

    with transaction.atomic():

        if not item_id:
            if order.order_status.lower() in ['shipped', 'delivered', 'cancelled']:
                messages.error(request, "This order can no longer be cancelled.")
                return redirect('order_detail', order_id=order.id)

            cancellable = order.items.select_for_update().exclude(
                item_status__in=['cancelled', 'delivered', 'shipped']
            )
            if not cancellable.exists():
                messages.error(request, "No cancellable items found.")
                return redirect('order_detail', order_id=order.id)

            total_refunded = Decimal('0.00')
            for item in cancellable:
                cancel_qty = item.remaining_quantity
                if cancel_qty <= 0:
                    continue
                item.variant.stock += cancel_qty
                item.variant.save()

                item.cancelled_quantity += cancel_qty
                item.item_status        = 'cancelled'
                item.cancellation_reason = reason
                item.save(update_fields=['cancelled_quantity', 'item_status', 'cancellation_reason'])

                net_refund = calculate_coupon_adjusted_refund(order, item.price, cancel_qty, order_item=item)
                ok, credited = process_wallet_refund(
                    order_item= item,
                    refund_qty= cancel_qty,
                    description = f"Refund for cancelled order #{order.order_number}",
                    override_amount = net_refund,
                )
                if ok:
                    total_refunded += credited

            all_done = all(i.item_status == 'cancelled' for i in order.items.all())
            shipping_refunded = Decimal('0.00')
            if all_done:
                order.order_status = 'Cancelled'
                ship_ok = process_shipping_refund(
                    order = order,
                    description = f"Shipping refund — order #{order.order_number} cancelled",
                )
                if ship_ok:
                    shipping_refunded = Decimal(str(order.delivery_charge or 0))

            active_items = order.items.exclude(item_status='cancelled')
            order.subtotal = sum(
                Decimal(str(i.price)) * i.remaining_quantity for i in active_items
            ) or Decimal('0.00')
            order.total_amount = max(
                order.subtotal
                + Decimal(str(order.tax_amount or 0))
                + Decimal(str(order.delivery_charge or 0))
                - Decimal(str(order.discount_amount or 0)),
                Decimal('0.00')
            )
            order.save()

            grand = total_refunded + shipping_refunded
            if grand > 0:
                detail = f"\u20b9{total_refunded:.2f} (products)"
                if shipping_refunded > 0:
                    detail += f" + \u20b9{shipping_refunded:.2f} (shipping)"
                messages.success(request, f"Order cancelled. {detail} credited to your wallet.")
            else:
                messages.success(request, "Order cancelled successfully.")

        else:
            item = get_object_or_404(OrderItem.objects.select_for_update(), id=item_id, order=order)

            if item.item_status.lower() not in ['placed', 'processing', 'confirmed']:
                messages.error(request, "This item can no longer be cancelled.")
                return redirect('order_detail', order_id=order.id)

            if not qty_str.isdigit():
                messages.error(request, "Invalid quantity.")
                return redirect('order_detail', order_id=order.id)

            cancel_qty = int(qty_str)
            remaining  = item.remaining_quantity

            if cancel_qty <= 0 or cancel_qty > remaining:
                messages.error(
                    request,
                    f"You can cancel between 1 and {remaining} unit(s). "
                    f"({item.cancelled_quantity} already cancelled, "
                    f"{item.returned_quantity} returned.)"
                )
                return redirect('order_detail', order_id=order.id)

            item.variant.stock += cancel_qty
            item.variant.save()

            item.cancelled_quantity += cancel_qty
            item.cancellation_reason = reason
            if item.cancelled_quantity >= item.quantity:
                item.item_status = 'cancelled'
            item.save(update_fields=['cancelled_quantity', 'cancellation_reason', 'item_status'])

            net_refund = calculate_coupon_adjusted_refund(order, item.price, cancel_qty, order_item=item)
            ok, credited = process_wallet_refund(
                order_item = item,
                refund_qty= cancel_qty,
                description = f"Partial cancel ({cancel_qty} unit(s)) — order #{order.order_number}",
                override_amount = net_refund,
            )

            order.subtotal = sum(
                Decimal(str(i.price)) * i.remaining_quantity
                for i in order.items.all()
            ) or Decimal('0.00')
            order.total_amount = max(
                order.subtotal
                + Decimal(str(order.tax_amount or 0))
                + Decimal(str(order.delivery_charge or 0))
                - Decimal(str(order.discount_amount or 0)),
                Decimal('0.00')
            )

            all_done = all(
                i.remaining_quantity == 0 or i.item_status == 'cancelled'
                for i in order.items.all()
            )
            shipping_refunded = Decimal('0.00')
            if all_done:
                order.order_status = 'Cancelled'
                ship_ok = process_shipping_refund(
                    order = order,
                    description = f"Shipping refund — order #{order.order_number} fully cancelled",
                )
                if ship_ok:
                    shipping_refunded = Decimal(str(order.delivery_charge or 0))

            order.save()

            refund_amount = credited if ok else Decimal('0.00')
            if ok:
                detail = f"\u20b9{refund_amount:.2f}"
                if order.discount_amount and order.discount_amount > 0:
                    gross = Decimal(str(item.price)) * cancel_qty
                    deducted = (gross - refund_amount).quantize(Decimal('0.01'))
                    if deducted > 0:
                        detail += f" (after \u20b9{deducted:.2f} coupon deduction)"
                if shipping_refunded > 0:
                    detail += f" + \u20b9{shipping_refunded:.2f} (shipping)"
                messages.success(
                    request,
                    f"{cancel_qty} unit(s) cancelled. {detail} credited to your wallet."
                )
            elif order.payment_method in ('razorpay', 'wallet') and order.payment_status == 'paid':
                messages.warning(request, f"{cancel_qty} unit(s) cancelled. Refund could not be processed — please contact support.")
            else:
                messages.success(request, f"{cancel_qty} unit(s) cancelled successfully.")

    return redirect('order_detail', order_id=order.id)


@login_required
def return_order(request, order_id):
    if request.method != "POST":
        return redirect('order_detail', order_id=order_id)

    order= get_object_or_404(Order, id=order_id, user=request.user)
    item_id= request.POST.get('item_id', '').strip()
    reason= request.POST.get('return_reason', '').strip()
    custom= request.POST.get('custom_reason', '').strip()
    qty_str=request.POST.get('qty', '').strip()

    if reason == 'Other' and custom:
        reason = custom

    if not reason:
        messages.error(request, "Return reason is required.")
        return redirect('order_detail', order_id=order.id)

    with transaction.atomic():

        if not item_id:
            items = order.items.select_for_update().filter(item_status='delivered')
            if not items.exists():
                messages.error(request, "No delivered items to return.")
                return redirect('order_detail', order_id=order.id)

            created_any = False
            for item in items:
                ret_qty = item.remaining_quantity
                if ret_qty <= 0:
                    continue
                already = ReturnRequest.objects.filter(item=item).aggregate(
                    total=Sum('quantity')
                )['total'] or 0
                if already >= ret_qty:
                    continue
                ReturnRequest.objects.create(
                    order = order,
                    item = item,
                    quantity = ret_qty,
                    reason = reason,
                    description = custom,
                )
                item.returned_quantity += ret_qty
                item.item_status = 'return_requested'
                item.save(update_fields=['returned_quantity', 'item_status'])
                created_any = True

            if created_any:
                messages.success(request, "Return request submitted for all delivered items.")
            else:
                messages.error(request, "A return has already been requested for all delivered items.")

        else:
            item = get_object_or_404(OrderItem.objects.select_for_update(), id=item_id, order=order)

            if item.item_status not in ('delivered', 'return_requested'):
                messages.error(request, "Only delivered items can be returned.")
                return redirect('order_detail', order_id=order.id)

            if qty_str.isdigit():
                ret_qty = int(qty_str)
            else:
                ret_qty = item.remaining_quantity 

            remaining = item.remaining_quantity
            if ret_qty <= 0 or ret_qty > remaining:
                messages.error(
                    request,
                    f"You can return between 1 and {remaining} unit(s). "
                    f"({item.cancelled_quantity} cancelled, {item.returned_quantity} already returned.)"
                )
                return redirect('order_detail', order_id=order.id)

            ReturnRequest.objects.create(
                order= order,
                item = item,
                quantity = ret_qty,
                reason = reason,
                description = custom,
            )
            item.returned_quantity += ret_qty
            if item.returned_quantity + item.cancelled_quantity >= item.quantity:
                item.item_status = 'return_requested'
            else:
                item.item_status = 'return_requested'
            item.save(update_fields=['returned_quantity', 'item_status'])

            messages.success(
                request,
                f"Return request submitted for {ret_qty} unit(s). We will process it shortly."
            )

    return redirect('order_detail', order_id=order.id)


@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    html = render_to_string('user/invoice.html', {'order': order})
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.order_number}.pdf"'
    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse('Error generating PDF')

    return response


@login_required
def apply_coupon(request):
    if request.method == "POST":
        try:
            data=json.loads(request.body)
            code=data.get('code', '').strip().upper()            
            cart, _=Cart.objects.get_or_create(user=request.user)
            cart_items=list(cart.items.select_related('variant', 'variant__product'))
            
            subtotal = Decimal('0.00')
            for item in cart_items:
                item.base_subtotal = item.variant.price * item.quantity
                subtotal += item.base_subtotal

            from user_side.cart.utils import calculate_cart_offers
            offer_data = calculate_cart_offers(cart_items)
            offer_discount = offer_data['total_offer_discount']
            effective_subtotal = subtotal - offer_discount            
            from user_side.wallet.refund_utils import FREE_SHIPPING_THRESHOLD, SHIPPING_CHARGE
            DELIVERY = 0 if effective_subtotal >= FREE_SHIPPING_THRESHOLD else int(SHIPPING_CHARGE)

            if not code:
                request.session.pop('coupon_id', None)
                return JsonResponse({
                    'success':     True,
                    'message':     'Coupon removed.',
                    'coupon_code': '',
                    'discount':    0.0,
                    'subtotal':    float(subtotal),
                    'offer_discount': float(offer_discount),
                    'delivery':    DELIVERY,
                    'new_total':   float(effective_subtotal + DELIVERY),
                })

            try:
                coupon = Coupon.objects.get(code__iexact=code, is_active=True)
            except Coupon.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Invalid or expired coupon code.'})

            from django.utils import timezone as tz
            today = tz.now().date()
            if coupon.start_date and coupon.start_date > today:
                return JsonResponse({'success': False, 'message': 'This coupon is not active yet.'})
            if coupon.expiry_date and coupon.expiry_date < today:
                return JsonResponse({'success': False, 'message': 'This coupon has expired.'})

            used_count = coupon.active_usage_count_for(request.user)
            limit      = coupon.usage_limit_per_user
            remaining  = max(limit - used_count, 0)

            if remaining <= 0:
                return JsonResponse({
                    'success':False,
                    'used_count': used_count,
                    'remaining':0,
                    'limit':limit,
                    'message':"You have reached maximum usage limit for this coupon",
                })

            if effective_subtotal < coupon.min_amount:
                return JsonResponse({'success': False, 'message': f'Minimum order of ₹{coupon.min_amount:.0f} required for this coupon.'})

            if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
                return JsonResponse({'success': False, 'message': 'This coupon\'s usage limit has been reached.'})

            if coupon.discount_type == 'fixed':
                discount = min(float(coupon.discount_value), float(effective_subtotal))
            else:
                calculated = (float(effective_subtotal) * float(coupon.discount_value)) / 100
                if coupon.max_discount:
                    calculated = min(calculated, float(coupon.max_discount))
                discount = calculated

            request.session['coupon_id'] = coupon.id
            new_total = max(float(effective_subtotal) + DELIVERY - discount, 0)
            
            remaining_after = max(remaining - 1, 0)
            
            return JsonResponse({
                'success': True,
                'message': f'🎉 "{coupon.code}" applied! You save ₹{discount:.0f}.',
                'coupon_code': coupon.code,
                'discount':round(discount, 2),
                'subtotal':float(subtotal),
                'offer_discount': float(offer_discount),
                'delivery': DELIVERY,
                'new_total':round(new_total, 2),
                'used_count':used_count,
                'remaining':remaining_after,
                'limit': limit,
            })
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
    items = list(cart.items.select_related('variant', 'variant__product'))
 
    if not items:
        messages.error(request, "Cart empty")
        return redirect('cart_view')
 
    subtotal = Decimal('0.00')
    for item in items:
        item.base_subtotal = item.variant.price * item.quantity
        subtotal += item.base_subtotal

    from user_side.cart.utils import calculate_cart_offers
    offer_data = calculate_cart_offers(items)
    offer_discount = offer_data['total_offer_discount']
    
    for item in items:
        offer_info = offer_data['item_discounts'].get(item.id, {})
        item.offer_discount = offer_info.get('amount', Decimal('0.00'))
        item.offer_dict = offer_info
        item.final_subtotal = item.base_subtotal - item.offer_discount
    effective_subtotal = subtotal - offer_discount
    delivery = 0 if effective_subtotal >= FREE_SHIPPING_THRESHOLD else int(SHIPPING_CHARGE)
    tax = 0
    coupon_discount = 0
 
    coupon = None
    coupon_id = request.session.get('coupon_id')
    if coupon_id:
        try:
            coupon = Coupon.objects.get(id=coupon_id, is_active=True)
            if effective_subtotal >= coupon.min_amount:
                if coupon.discount_type == 'fixed':
                    coupon_discount = coupon.discount_value
                else:
                    calc = (effective_subtotal * coupon.discount_value) / 100
                    if coupon.max_discount:
                        calc = min(calc, coupon.max_discount)
                    coupon_discount = calc
            else:
                coupon = None
        except Coupon.DoesNotExist:
            coupon = None
 
    total = max(effective_subtotal + delivery + tax - coupon_discount, 0)
    total_discount = offer_discount + coupon_discount
 
    for item in items:
        if item.variant.stock < item.quantity:
            messages.error(request, f"Stock issue for {item.variant}")
            return redirect('cart_view')
 
    if payment_method == "cod":
        with transaction.atomic():
            order = Order.objects.create(
                user = request.user,
                shipping_address = address,
                payment_method = 'cod',
                subtotal= subtotal,
                tax_amount= tax,
                discount_amount= total_discount,
                coupon  = coupon,
                delivery_charge = delivery,
                total_amount = total,
                payment_status = 'pending',  
            )
            for item in items:
                OrderItem.objects.create(
                    order    = order,
                    variant  = item.variant,
                    price    = item.variant.price,
                    quantity = item.quantity,
                )
                item.variant.stock -= item.quantity
                item.variant.save()

            Payment.objects.create(
                order = order,
                payment_method = 'cod',
                payment_status = 'pending',
                amount = total,
            )
            if coupon:
                CouponUsage.objects.get_or_create(
                    user=request.user, coupon=coupon, order=order,
                    defaults={'is_used': True, 'is_refunded': False}
                )
                Coupon.objects.filter(pk=coupon.pk).update(
                    used_count=F('used_count') + 1
                )
            cart.items.all().delete()
            request.session.pop('coupon_id', None)

        return redirect('order_success', order_id=order.id)

    if payment_method == "wallet":
        wallet = request.user.wallet
        if wallet.balance < total:
            messages.error(request, "Insufficient wallet balance")
            return redirect('checkout')

        with transaction.atomic():
            order = Order.objects.create(
                user= request.user,
                shipping_address = address,
                payment_method = 'wallet',
                subtotal=subtotal,
                tax_amount=tax,
                discount_amount=total_discount,
                coupon= coupon,
                delivery_charge = delivery,
                total_amount = total,
                payment_status = 'paid',
            )
            for item in items:
                OrderItem.objects.create(
                    order= order,
                    variant= item.variant,
                    price = item.variant.price,
                    quantity = item.quantity,
                )
                item.variant.stock -= item.quantity
                item.variant.save()

            wallet.balance -= total
            wallet.save()

            from user_side.wallet.models import WalletTransaction
            WalletTransaction.objects.create(
                user = request.user,
                order = order,
                transaction_type = 'debit',
                amount= total,
                balance_after = wallet.balance,
                is_credit = False,
                payment_status = 'paid',
                description = f"Payment for Order #{order.order_number}"
            )

            Payment.objects.create(
                order = order,
                payment_method = 'wallet',
                payment_status = 'success',
                amount= total,
            )
            if coupon:
                CouponUsage.objects.get_or_create(
                    user=request.user, coupon=coupon, order=order,
                    defaults={'is_used': True, 'is_refunded': False}
                )
                Coupon.objects.filter(pk=coupon.pk).update(
                    used_count=F('used_count') + 1
                )
            cart.items.all().delete()
            request.session.pop('coupon_id', None)

        return redirect('order_success', order_id=order.id)

    if payment_method == "razorpay":
        key_id     = settings.RAZORPAY_KEY_ID.strip(' "\'')
        key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
        client     = razorpay.Client(auth=(key_id, key_secret))

        try:
            rp_order = client.order.create({
                "amount":int(total * 100),
                "currency": "INR",
                "receipt": str(uuid.uuid4())[:20],
                "payment_capture": 1,
            })
        except Exception as e:
            print("RAZORPAY ORDER CREATE ERROR:", e)
            messages.error(request, "Could not initiate payment. Please try again.")
            return redirect('checkout')

        request.session['pending_razorpay'] = {
            'razorpay_order_id': rp_order['id'],
            'address_id':int(address_id),
            'coupon_id':coupon.id if coupon else None,
            'subtotal':float(subtotal),
            'discount': float(total_discount),
            'delivery': float(delivery),
            'tax':float(tax),
            'total':float(total),
        }

        return redirect('initiate_payment')
