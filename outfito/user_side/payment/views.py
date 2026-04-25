from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
import razorpay
from user_side.orders.models import Order, OrderItem
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from .models import Payment
from admin_side.coupon_management.models import Coupon, CouponUsage
from user_side.address.models import Address
from user_side.cart.models import Cart
from admin_side.coupon_management.models import Coupon


@login_required
def initiate_payment(request):
    pending = request.session.get('pending_razorpay')

    if not pending:
        messages.error(request, "No pending payment found. Please start checkout again.")
        return redirect('checkout')

    context = {
        "razorpay_key": settings.RAZORPAY_KEY_ID.strip(' "\''),
        "razorpay_order_id": pending['razorpay_order_id'],
        "amount":   int(float(pending['total']) * 100),   # paise
        "total_display":  pending['total'],
    }
    return render(request, "user/payment_page.html", context)


@csrf_exempt
@login_required
def verify_payment(request):
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_signature= request.POST.get("razorpay_signature")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        messages.error(request, "Invalid payment request.")
        return redirect('checkout')

    pending = request.session.get('pending_razorpay')
    if not pending or pending.get('razorpay_order_id') != razorpay_order_id:
        messages.error(request, "Payment session mismatch. Please try again.")
        return redirect('checkout')

    key_id = settings.RAZORPAY_KEY_ID.strip(' "\'')
    key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
    client = razorpay.Client(auth=(key_id, key_secret))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id":  razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature":  razorpay_signature,
        })
    except Exception as e:
        print("SIGNATURE VERIFICATION FAILED:", e)
        messages.error(request, "Payment verification failed. Please try again.")
        return redirect('payment_failed')

    address = get_object_or_404(Address, id=pending['address_id'], user=request.user)

    coupon = None
    if pending.get('coupon_id'):
        try:
            coupon = Coupon.objects.get(id=pending['coupon_id'])
        except Coupon.DoesNotExist:
            pass

    cart       = Cart.objects.get(user=request.user)
    cart_items = cart.items.select_related('variant')

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user             = request.user,
                shipping_address = address,
                payment_method   = 'razorpay',
                subtotal         = Decimal(str(pending['subtotal'])),
                tax_amount       = Decimal(str(pending['tax'])),
                discount_amount  = Decimal(str(pending['discount'])),
                delivery_charge  = Decimal(str(pending['delivery'])),
                total_amount     = Decimal(str(pending['total'])),
                coupon           = coupon,
                payment_status   = 'paid',
            )

            for item in cart_items:
                OrderItem.objects.create(
                    order    = order,
                    variant  = item.variant,
                    price    = item.variant.price,
                    quantity = item.quantity,
                )
                item.variant.stock -= item.quantity
                item.variant.save()

            Payment.objects.create(
                order                = order,
                payment_method       = 'razorpay',
                payment_status       = 'success',
                razorpay_order_id    = razorpay_order_id,
                razorpay_payment_id  = razorpay_payment_id,
                razorpay_signature   = razorpay_signature,
                amount               = Decimal(str(pending['total'])),
            )

            if coupon:
                CouponUsage.objects.get_or_create(
                    user=request.user, coupon=coupon, order=order,
                    defaults={'is_used': True, 'is_refunded': False}
                )
                from django.db.models import F as _F
                Coupon.objects.filter(pk=coupon.pk).update(
                    used_count=_F('used_count') + 1
                )

            cart.items.all().delete()
            request.session.pop('pending_razorpay', None)
            request.session.pop('coupon_id', None)

    except Exception as e:
        print("ORDER CREATION ERROR:", e)
        messages.error(request, "Something went wrong while saving your order. Please contact support.")
        return redirect('payment_failed')

    messages.success(request, "Payment successful! Your order is confirmed.")
    return redirect('order_success', order_id=order.id)


@login_required
def payment_failed(request):
    request.session.pop('pending_razorpay', None)
    return render(request, "user/payment_failed.html")
