from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
import razorpay
from user_side.orders.models import Order, OrderItem
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import timedelta
from .models import Payment

@login_required
def payment_page(request, order_id):

    order = get_object_or_404(Order, id=order_id, user=request.user)

    payment = order.payments.last()

    # ✅ Ensure payment exists
    if not payment:
        payment = Payment.objects.create(
            order=order,
            amount=order.total_amount,
            payment_method="razorpay",
            payment_status="pending"
        )

    # ✅ Already paid
    if payment.payment_status == "success":
        return redirect("order_success", order_id=order.id)

    # ✅ Timeout check (5 min)
    if timezone.now() > order.created_at + timedelta(minutes=5):
        if order.order_status != "cancelled":
            order.order_status = "cancelled"
            order.save()

        messages.error(request, "Payment retry limit exceeded.")
        return redirect("order_detail", order_id=order.id)

    key_id = settings.RAZORPAY_KEY_ID.strip(' "\'')
    key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
    
    client = razorpay.Client(
        auth=(key_id, key_secret)
    )

    # ✅ Create Razorpay order ONLY ONCE
    if not payment.razorpay_order_id:
        razorpay_order = client.order.create({
            "amount": int(order.total_amount * 100),  # paisa
            "currency": "INR",
            "receipt": str(order.order_number),
            "payment_capture": 1,
        })

        payment.razorpay_order_id = razorpay_order["id"]
        payment.save()

    else:
        razorpay_order = {"id": payment.razorpay_order_id}

    # ✅ Timer logic
    expiration_time = order.created_at + timedelta(minutes=5)
    time_left_seconds = max(0, int((expiration_time - timezone.now()).total_seconds()))

    context = {
        "order": order,
        "payment": payment,
        "razorpay_key": settings.RAZORPAY_KEY_ID.strip(' "\''),
        "razorpay_order_id": razorpay_order["id"],
        "amount": int(order.total_amount * 100),
        "time_left_seconds": time_left_seconds,
    }

    return render(request, "user/payment_page.html", context)

@login_required
@csrf_exempt
def verify_payment(request):

    order_id = request.GET.get("order_id")
    razorpay_order_id = request.POST.get("razorpay_order_id")
    razorpay_payment_id = request.POST.get("razorpay_payment_id")
    razorpay_signature = request.POST.get("razorpay_signature")

    print("DEBUG -> order_id:", order_id)
    print("DEBUG -> razorpay_order_id:", razorpay_order_id)
    print("DEBUG -> razorpay_payment_id:", razorpay_payment_id)
    print("DEBUG -> razorpay_signature:", razorpay_signature)

    if not order_id:
        messages.error(request, "Invalid payment request.")
        return redirect("home")

    # ✅ Secure: ensure user owns order
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # ✅ Correct field
    payment = Payment.objects.filter(
        razorpay_order_id=razorpay_order_id
    ).first()

    if not payment:
        messages.error(request, "Payment record not found.")
        return redirect("home")

    key_id = settings.RAZORPAY_KEY_ID.strip(' "\'')
    key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
    
    client = razorpay.Client(
        auth=(key_id, key_secret)
    )

    try:
        # ✅ Verify signature
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        })

        with transaction.atomic():

            # ✅ Save correct fields
            payment.payment_status = "success"
            payment.razorpay_payment_id = razorpay_payment_id
            payment.razorpay_signature = razorpay_signature
            payment.save()

            order.payment_status = "paid"
            order.save()

            # ✅ Reduce stock
            for item in order.items.all():
                variant = item.variant
                variant.stock -= item.quantity
                variant.save()
                
            # ✅ Clear cart
            from user_side.cart.models import Cart
            Cart.objects.filter(user=order.user).delete()

        messages.success(request, "Payment successful")
        return redirect("order_success", order_id=order.id)

    except Exception as e:
        print("ERROR:", e)

        payment.payment_status = "failed"
        payment.save()

        messages.error(request, "Payment failed")
        return redirect("payment_failed", order_id=order.id)
    
@login_required
def payment_failed(request, order_id):

    order = get_object_or_404(Order, id=order_id, user=request.user)

    # Mark as failed if user abandons/closes the payment
    payment = order.payments.last()

    if payment and payment.payment_status == "pending":
        payment.payment_status = "failed"
        payment.save()

    # Timer logic
    expiration_time = order.created_at + timedelta(minutes=5)
    time_left_seconds = max(0, int((expiration_time - timezone.now()).total_seconds()))
    retry_allowed = time_left_seconds > 0

    # Cancel order if expired
    if not retry_allowed and order.order_status != "Cancelled":
        order.order_status = "Cancelled"
        order.save()

    return render(request, "user/payment_failed.html", {
        "order": order,
        "retry_allowed": retry_allowed,
        "time_left_seconds": time_left_seconds,
    })