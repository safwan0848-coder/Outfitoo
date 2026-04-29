"""
referral_service.py
Atomic, idempotent referral reward logic.
Call process_referral_reward(order) when an order is marked Delivered.
"""
from decimal import Decimal
from django.db import transaction

REFERRER_BONUS  = Decimal('100.00')   
NEW_USER_BONUS  = Decimal('50.00')   


def _credit_wallet(user, amount, order, description):

    from user_side.wallet.models import Wallet, WalletTransaction

    # Step 1: ensure wallet exists (can't use select_for_update with get_or_create)
    Wallet.objects.get_or_create(user=user)

    # Step 2: lock and update atomically
    wallet = Wallet.objects.select_for_update().get(user=user)
    wallet.balance += amount
    wallet.save(update_fields=['balance', 'updated_at'])

    WalletTransaction.objects.create(
        user             = user,
        order            = order,
        transaction_type = 'credit',
        amount           = amount,
        balance_after    = wallet.balance,
        is_credit        = True,
        description      = description,
        payment_status   = 'success',
    )

    from django.core.mail import send_mail
    try:
        send_mail(
            subject='OUTFITO Wallet Credited!',
            message=f"Hello {user.username},\n\n₹{amount} has been credited to your wallet.\nReason: {description}\n\nThank you for shopping with OUTFITO!",
            from_email='outfito0848@gmail.com',
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass



def process_referral_reward(order) -> bool:
    """Credit ₹50 to the new buyer and ₹100 to their referrer
    when the buyer's FIRST order is delivered. Idempotent — safe to call multiple times."""

    # Guard 1: already rewarded for this order
    if order.is_referral_rewarded:
        return False

    user = order.user
    referrer = getattr(user, 'referred_by', None)

    # Guard 2: this user was not referred by anyone
    if referrer is None:
        return False

    from user_side.orders.models import Order as OrderModel

    # Guard 3: the buyer already got a referral reward on a previous order
    already_rewarded = OrderModel.objects.filter(
        user=user,
        is_referral_rewarded=True,
    ).exists()
    if already_rewarded:
        return False

    # Guard 4: this order must be the user's first delivered order
    first_delivered = (
        OrderModel.objects
        .filter(user=user, order_status='Delivered')
        .order_by('created_at')
        .first()
    )
    if first_delivered is None or first_delivered.pk != order.pk:
        return False

    try:
        with transaction.atomic():
            locked_order = OrderModel.objects.select_for_update().get(pk=order.pk)
            if locked_order.is_referral_rewarded:
                return False  
            _credit_wallet(
                user        = user,
                amount      = NEW_USER_BONUS,
                order       = order,
                description = f"Referral bonus — your first order #{order.order_number}",
            )
            _credit_wallet(
                user        = referrer,
                amount      = REFERRER_BONUS,
                order       = order,
                description = (
                    f"Referral reward — {user.username} completed their "
                    f"first order #{order.order_number}"
                ),
            )

            locked_order.is_referral_rewarded = True
            locked_order.save(update_fields=['is_referral_rewarded'])

        return True

    except Exception:
        return False
