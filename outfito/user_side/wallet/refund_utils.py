"""
refund_utils.py
───────────────
Centralised, atomic wallet-refund logic.

Usage
-----
    from user_side.wallet.refund_utils import process_wallet_refund

    refunded = process_wallet_refund(
        order_item  = item,           # OrderItem instance (select_for_update recommended)
        refund_qty  = 2,              # How many units to refund
        description = "Refund for cancelled item",
    )

Returns
-------
    True  → wallet credited, refund_processed = True on the item
    False → skipped (already processed, wrong payment method, etc.)
"""

from decimal import Decimal
from django.db import transaction

# Orders above this amount get free shipping.
FREE_SHIPPING_THRESHOLD = Decimal('1000')
SHIPPING_CHARGE        = Decimal('50')

# Lazy imports inside functions to avoid circular imports at module load time.


def process_wallet_refund(order_item, refund_qty: int, description: str = "", override_amount: "Decimal | None" = None) -> "tuple[bool, Decimal]":
    """
    Atomically credit the wallet for a cancelled or returned order item.

    Safety guarantees
    -----------------
    1. Only fires if ``order.payment_status == 'paid'``.
    2. Only fires for ``razorpay`` or ``wallet`` payment methods
       (COD is excluded — no money was collected upfront).
    3. ``select_for_update()`` on the Wallet row prevents race conditions.
    4. ``refund_processed`` flag prevents duplicate refunds.
    5. Entire operation is wrapped in ``transaction.atomic()``.

    Parameters
    ----------
    order_item : OrderItem
        The item being refunded. Must already be saved with the correct status.
    refund_qty : int
        Quantity of units to refund.
    description : str
        Human-readable description for the WalletTransaction record.
    override_amount : Decimal | None
        If provided, credit this exact amount instead of ``item.price × refund_qty``.
        Use this to pass a coupon-adjusted (actually-paid) amount.

    Returns
    -------
    tuple[bool, Decimal]
        (True, amount_credited)  — wallet credited successfully
        (False, Decimal('0'))    — skipped (already processed / ineligible)
    """
    # ── Deferred imports to avoid circular dependencies ────────────────────
    from user_side.wallet.models import Wallet, WalletTransaction

    order = order_item.order

    # ── Guard 1: Only refund paid orders ──────────────────────────────────
    if order.payment_status != 'paid':
        return False, Decimal('0')

    # ── Guard 2: Only refund online payments (razorpay / wallet) ──────────
    if order.payment_method not in ('razorpay', 'wallet'):
        return False, Decimal('0')

    # ── Guard 3: Duplicate-refund protection ──────────────────────────────
    if order_item.refund_processed:
        return False, Decimal('0')

    # ── Guard 4: Sane quantity ─────────────────────────────────────────────
    if refund_qty <= 0:
        return False, Decimal('0')

    # ── Use override (coupon-adjusted) amount if provided ─────────────────
    if override_amount is not None:
        refund_amount = Decimal(str(override_amount))
    else:
        refund_amount = Decimal(str(order_item.price)) * refund_qty

    if refund_amount <= 0:
        return False, Decimal('0')

    # ── Atomic credit ─────────────────────────────────────────────────────
    with transaction.atomic():
        # Re-read the flag inside the transaction to prevent TOCTOU race
        # (two concurrent requests both seeing refund_processed=False).
        from user_side.orders.models import OrderItem as _OI
        locked_item = _OI.objects.select_for_update().get(pk=order_item.pk)

        if locked_item.refund_processed:
            # Another concurrent request already processed the refund
            return False, Decimal('0')

        # Lock the wallet row
        wallet = Wallet.objects.select_for_update().get(user=order.user)

        wallet.balance += refund_amount
        wallet.save(update_fields=['balance', 'updated_at'])

        WalletTransaction.objects.create(
            user             = order.user,
            order            = order,
            transaction_type = 'credit',
            amount           = refund_amount,
            balance_after    = wallet.balance,
            is_credit        = True,
            payment_status   = 'success',
            description      = description or f"Refund for order #{order.order_number}",
        )

        # Mark the item so this never runs again
        locked_item.refund_processed = True
        locked_item.save(update_fields=['refund_processed'])

        # Keep the in-memory object in sync so callers don't see stale data
        order_item.refund_processed = True

    return True, refund_amount


def process_shipping_refund(order, description: str = "") -> bool:
    """
    Refund the delivery charge to the wallet when an entire order is cancelled.

    Rules
    -----
    - Only fires if the order was paid online (razorpay / wallet).
    - Only fires if delivery_charge > 0 (free-shipping orders have 0 charge).
    - Uses an order-level flag ``shipping_refund_processed`` to prevent duplicates.
      Because Order model may not have this field, we use a WalletTransaction check
      instead: if a CREDIT transaction with description containing 'shipping refund'
      already exists for this order, skip.

    Returns
    -------
    bool  True if shipping was refunded, False if skipped.
    """
    from user_side.wallet.models import Wallet, WalletTransaction

    if order.payment_status != 'paid':
        return False

    if order.payment_method not in ('razorpay', 'wallet'):
        return False

    shipping_amount = Decimal(str(order.delivery_charge or 0))
    if shipping_amount <= 0:
        return False

    # Duplicate guard: check if a shipping refund was already issued for this order
    already_done = WalletTransaction.objects.filter(
        order=order,
        transaction_type='credit',
        description__icontains='shipping refund',
    ).exists()
    if already_done:
        return False

    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(user=order.user)
        wallet.balance += shipping_amount
        wallet.save(update_fields=['balance', 'updated_at'])

        WalletTransaction.objects.create(
            user             = order.user,
            order            = order,
            transaction_type = 'credit',
            amount           = shipping_amount,
            balance_after    = wallet.balance,
            is_credit        = True,
            payment_status   = 'success',
            description      = description or f"Shipping refund — order #{order.order_number}",
        )

    return True
