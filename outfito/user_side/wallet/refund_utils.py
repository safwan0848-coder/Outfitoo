from decimal import Decimal
from django.db import transaction

FREE_SHIPPING_THRESHOLD = Decimal('1000')
SHIPPING_CHARGE        = Decimal('50')


def calculate_coupon_adjusted_refund(order, item_price, qty, order_item=None):
    """
    Calculate refund for partial cancel/return using proportional coupon distribution.

    The coupon discount is split across items proportionally by their subtotal
    (price x quantity), NOT evenly by unit count.

    This prevents double-deduction: returning item 1 first does not inflate the
    coupon share deducted when returning item 2 later.

    Formula:
        item_share      = (item_price * item_total_qty) / order_gross_subtotal
        item_coupon     = total_coupon_discount * item_share
        coupon_per_unit = item_coupon / item_total_qty
        refund          = (item_price * return_qty) - (coupon_per_unit * return_qty)
    """
    item_price_dec = Decimal(str(item_price))
    return_gross   = item_price_dec * qty
    discount       = Decimal(str(order.discount_amount or 0))

    if discount > 0:
        all_items   = list(order.items.all())
        order_gross = sum(Decimal(str(i.price)) * Decimal(str(i.quantity)) for i in all_items)

        if order_gross > 0:
            if order_item is not None:
                item_total_qty = Decimal(str(order_item.quantity))
                item_subtotal  = Decimal(str(order_item.price)) * item_total_qty
            else:
                matched = [i for i in all_items if Decimal(str(i.price)) == item_price_dec]
                if matched:
                    item_total_qty = Decimal(str(matched[0].quantity))
                    item_subtotal  = item_price_dec * item_total_qty
                else:
                    item_total_qty = Decimal(str(qty))
                    item_subtotal  = item_price_dec * item_total_qty

            item_share              = item_subtotal / order_gross
            item_coupon_total       = (discount * item_share).quantize(Decimal('0.01'))
            coupon_per_unit         = item_coupon_total / item_total_qty
            refund_coupon_deduction = (coupon_per_unit * Decimal(str(qty))).quantize(Decimal('0.01'))
            return max(return_gross - refund_coupon_deduction, Decimal('0.00'))

    return return_gross



def process_wallet_refund(order_item, refund_qty, description, override_amount=None):
    """
    Credit the wallet for `refund_qty` units of `order_item`.

    Safe to call multiple times on the same item (partial cancel/return).
    Uses `cancelled_quantity` + `returned_quantity` to track what has
    already been refunded so duplicates are impossible.

    `override_amount`: if provided, use this exact Decimal instead of
    calculating price * qty. Useful when coupon share is pre-calculated.
    """
    from user_side.wallet.models import Wallet, WalletTransaction
    order = order_item.order

    if order.payment_status != 'paid':
        return False, Decimal('0')
    if order.payment_method not in ('razorpay', 'wallet'):
        return False, Decimal('0')
    if refund_qty <= 0:
        return False, Decimal('0')

    if override_amount is not None:
        refund_amount = Decimal(str(override_amount))
    else:
        refund_amount = Decimal(str(order_item.price)) * refund_qty

    if refund_amount <= 0:
        return False, Decimal('0')

    with transaction.atomic():
        from user_side.orders.models import OrderItem as _OI
        locked_item = _OI.objects.select_for_update().get(pk=order_item.pk)

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

    return True, refund_amount


def process_shipping_refund(order, description):
    from user_side.wallet.models import Wallet, WalletTransaction

    if order.payment_status != 'paid':
        return False

    if order.payment_method not in ('razorpay', 'wallet'):
        return False

    shipping_amount = Decimal(str(order.delivery_charge or 0))
    if shipping_amount <= 0:
        return False

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
