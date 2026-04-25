
from decimal import Decimal
from django.db import transaction

FREE_SHIPPING_THRESHOLD = Decimal('1000')
SHIPPING_CHARGE        = Decimal('50')


def process_wallet_refund(order_item, refund_qty, description, override_amount: "Decimal | None" = None):
    from user_side.wallet.models import Wallet, WalletTransaction
    order = order_item.order
    if order.payment_status != 'paid':
        return False, Decimal('0')
    if order.payment_method not in ('razorpay', 'wallet'):
        return False, Decimal('0')
    if order_item.refund_processed:
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

        if locked_item.refund_processed:
            return False, Decimal('0')

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
        locked_item.refund_processed = True
        locked_item.save(update_fields=['refund_processed'])
        order_item.refund_processed = True

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
