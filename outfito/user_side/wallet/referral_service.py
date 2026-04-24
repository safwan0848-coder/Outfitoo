"""
referral_service.py
Atomic, idempotent referral reward logic.
Call process_referral_reward(order) when an order is marked Delivered.
"""
from decimal import Decimal
from django.db import transaction

REFERRER_BONUS  = Decimal('100.00')   # ₹100 → referrer
NEW_USER_BONUS  = Decimal('50.00')    # ₹50  → new user


def _credit_wallet(user, amount, order, description):
    """
    Add `amount` to `user`'s wallet and record a WalletTransaction.
    Must be called inside an atomic block.
    """
    from user_side.wallet.models import Wallet, WalletTransaction

    wallet, _ = Wallet.objects.select_for_update().get_or_create(user=user)
    wallet.balance += amount
    wallet.save(update_fields=['balance'])

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
    
    # ── Notify User via Email ────────────────────────────
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
    """
    Credit referral bonuses when order is Delivered.

    Returns True if rewards were credited, False if skipped.

    Idempotency guards:
      - order.is_referral_rewarded flag (set atomically)
      - Only fires for the user's FIRST delivered order
      - select_for_update on Wallet prevents race conditions
    """
    # ── Guard 1: already rewarded ──────────────────────────────
    if order.is_referral_rewarded:
        return False

    # ── Guard 2: user has no referrer ──────────────────────────
    user = order.user
    referrer = getattr(user, 'referred_by', None)
    if referrer is None:
        return False

    # ── Guard 3: must be user's first Delivered order ───────────
    from user_side.orders.models import Order as OrderModel
    prior_delivered = OrderModel.objects.filter(
        user         = user,
        order_status = 'Delivered',
        is_referral_rewarded = True,   # already processed
    ).exists()

    if prior_delivered:
        return False

    # Also check it is literally the first delivered order
    first_delivered = (
        OrderModel.objects
        .filter(user=user, order_status='Delivered')
        .order_by('created_at')
        .first()
    )
    if first_delivered is None or first_delivered.pk != order.pk:
        return False

    # ── Atomic reward credit ────────────────────────────────────
    try:
        with transaction.atomic():
            # Re-fetch with lock to prevent concurrent execution
            locked_order = OrderModel.objects.select_for_update().get(pk=order.pk)
            if locked_order.is_referral_rewarded:
                return False   # another process beat us

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
        # Never crash the order status update
        return False
