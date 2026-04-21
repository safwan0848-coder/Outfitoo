from django.db import models

class Coupon(models.Model):

    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    code = models.CharField(max_length=50, unique=True)

    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES
    )

    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    min_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    max_discount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    is_active = models.BooleanField(default=True)

    expiry_date = models.DateField()

    start_date = models.DateField(null=True, blank=True)

    usage_limit = models.PositiveIntegerField(null=True, blank=True)

    usage_limit_per_user = models.PositiveIntegerField(default=1)

    used_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code