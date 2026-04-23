from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Wallet(models.Model):
    """One wallet per user — created automatically via signal on user creation."""
    user    = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet({self.user.email}) | ₹{self.balance}"


class WalletTransaction(models.Model):
    """
    Records every ADD (top-up via Razorpay) and USE (spent on order) transaction.

    Lifecycle — ADD (top-up):
      - razorpay_payment_id is set and UNIQUE → prevents duplicate credit
      - payment_status: 'success' | 'failed'
      - transaction_type: 'credit'

    Lifecycle — USE (order payment):
      - transaction_type: 'debit'
      - razorpay_payment_id: None (not a Razorpay transaction)
    """

    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'Credit'),   # Money added
        ('debit',  'Debit'),    # Money spent
    ]

    PAYMENT_STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed',  'Failed'),
        ('pending', 'Pending'),
    ]

    user                 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallet_transactions')
    order                = models.ForeignKey(
                               'orders.Order', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='wallet_transactions'
                           )
    transaction_type     = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    amount               = models.DecimalField(max_digits=10, decimal_places=2)   # Always positive
    balance_after        = models.DecimalField(max_digits=10, decimal_places=2)   # Snapshot after txn
    is_credit            = models.BooleanField(default=False)                      # Kept for compat

    # ── Razorpay fields (only for top-up transactions) ─────────────────────────
    razorpay_payment_id  = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_order_id    = models.CharField(max_length=100, null=True, blank=True)
    payment_status       = models.CharField(
                               max_length=10, choices=PAYMENT_STATUS_CHOICES,
                               default='pending'
                           )

    description          = models.CharField(max_length=255, blank=True)
    created_at           = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (
            f"{self.transaction_type.upper()} | {self.user.email} | "
            f"₹{self.amount} | balance={self.balance_after}"
        )

    class Meta:
        ordering = ['-created_at']
