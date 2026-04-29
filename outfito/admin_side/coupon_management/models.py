from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Coupon(models.Model):

    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    code             = models.CharField(max_length=50, unique=True)
    discount_type    = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value   = models.DecimalField(max_digits=10, decimal_places=2)
    min_amount       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active        = models.BooleanField(default=True)
    expiry_date      = models.DateField()
    start_date       = models.DateField(null=True, blank=True)
    usage_limit      = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(default=1)
    used_count       = models.PositiveIntegerField(default=0)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    def clean(self):
        errors = {}
        today = timezone.now().date()

        if self.discount_value is not None:
            if self.discount_value <= 0:
                errors['discount_value'] = "Discount value must be greater than 0."
            if self.discount_type == 'percentage' and self.discount_value > 100:
                errors['discount_value'] = "Percentage discount cannot exceed 100%."

        if self.min_amount is not None and self.min_amount < 0:
            errors['min_amount'] = "Minimum amount cannot be negative."

        if self.max_discount is not None:
            if self.max_discount <= 0:
                errors['max_discount'] = "Maximum discount must be greater than 0."
            if self.discount_type == 'fixed':
                errors['max_discount'] = "Max discount cap is only for percentage coupons."

        if self.expiry_date and self.start_date:
            if self.expiry_date <= self.start_date:
                errors['expiry_date'] = "Expiry date must be after the start date."

        if self.usage_limit is not None and self.usage_limit < 1:
            errors['usage_limit'] = "Usage limit must be at least 1."

        if self.usage_limit_per_user is not None and self.usage_limit_per_user < 1:
            errors['usage_limit_per_user'] = "Per-user usage limit must be at least 1."

        if errors:
            raise ValidationError(errors)

    def active_usage_count_for(self, user):
        """Active (used, not yet refunded) uses of this coupon by a specific user."""
        return self.usage_records.filter(
            user=user, is_used=True
        ).count()

    def is_used_by(self, user):
        """True if the user has reached their per-user limit (active uses only)."""
        return self.active_usage_count_for(user) >= self.usage_limit_per_user


class CouponUsage(models.Model):
    """
    One row per (user, coupon, order).

    Lifecycle:
      - Created with is_used=True when an order is placed/payment confirmed.
      - On full order cancel: is_used -> False, is_refunded -> True.
        (Coupon is freed, but is_refunded prevents a second restoration.)
    """
    coupon      = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='usage_records')
    user        = models.ForeignKey(User,   on_delete=models.CASCADE, related_name='coupon_usages')
    order       = models.ForeignKey(
                      'orders.Order', on_delete=models.CASCADE,
                      related_name='coupon_usage', null=True, blank=True
                  )
    is_used     = models.BooleanField(default=False)
    is_refunded = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'coupon', 'order')
        ordering        = ['-created_at']

    def __str__(self):
        return (
            f"{self.user} | {self.coupon.code} | "
            f"order={self.order_id} | used={self.is_used} | refunded={self.is_refunded}"
        )