from django.db import models
from django.conf import settings
from user_side.address.models import Address
from admin_side.variants_management.models import Variant
from admin_side.coupon_management.models import Coupon
import uuid
User = settings.AUTH_USER_MODEL

class Order(models.Model):
    PAYMENT_METHODS = [
    ('cod', 'Cash on Delivery'),
    ('razorpay', 'Razorpay'),
    ('wallet', 'Wallet'),
]
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    ORDER_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Shipped', 'Shipped'),
        ('Out for Delivery', 'Out for Delivery'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]

    user=models.ForeignKey(User, on_delete=models.CASCADE)
    shipping_address=models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    order_number=models.CharField(max_length=20, unique=True, blank=True)
    payment_method = models.CharField(
    max_length=20,
    choices=PAYMENT_METHODS,
    null=True,
    blank=True
)
    payment_status=models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    order_status=models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='Pending')
    subtotal=models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charge=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount=models.DecimalField(max_digits=10, decimal_places=2)
    created_at=models.DateTimeField(auto_now_add=True)
    coupon               = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    is_referral_rewarded = models.BooleanField(default=False)   # True once referral bonus is credited
    
    @property
    def has_return_request(self):
        return self.return_requests.filter(status='Pending').exists()

    @property
    def return_request(self):
        return self.return_requests.filter(status='Pending').first()

    @property
    def can_return_order(self):
        return self.items.filter(item_status='delivered').exclude(return_requests__isnull=False).exists()

    @property
    def computed_subtotal(self):
        from decimal import Decimal
        return sum((Decimal(str(i.price)) * Decimal(str(i.remaining_quantity))) for i in self.items.all())

    @property
    def computed_discount(self):
        from decimal import Decimal
        total_coupon = Decimal(str(self.discount_amount or 0))
        if total_coupon <= 0:
            return Decimal('0.00')
            
        all_items = list(self.items.all())
        order_gross = sum(Decimal(str(i.price)) * Decimal(str(i.quantity)) for i in all_items)
        if order_gross <= 0:
            return Decimal('0.00')
            
        adjusted_discount = Decimal('0.00')
        for item in all_items:
            if item.remaining_quantity > 0:
                item_share = (Decimal(str(item.price)) * Decimal(str(item.quantity))) / order_gross
                coupon_for_item = total_coupon * item_share
                coupon_per_unit = coupon_for_item / Decimal(str(item.quantity))
                adjusted_discount += coupon_per_unit * Decimal(str(item.remaining_quantity))
                
        adjusted_discount = adjusted_discount.quantize(Decimal('0.01'))
        return min(adjusted_discount, self.computed_subtotal)

    @property
    def computed_total(self):
        from decimal import Decimal
        total = self.computed_subtotal + Decimal(str(self.tax_amount or 0)) + Decimal(str(self.delivery_charge or 0)) - self.computed_discount
        return max(total, Decimal('0.00'))

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = str(uuid.uuid4()).replace("-", "")[:12].upper()
        super().save(*args, **kwargs)
    
class OrderItem(models.Model):
    STATUS_CHOICES = [
        ('placed', 'Pending'),
        ('shipped', 'Shipped'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('return_requested', 'Return Requested'),
        ('returned', 'Returned'),
    ]

    order=models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant=models.ForeignKey(Variant, on_delete=models.CASCADE)
    price=models.DecimalField(max_digits=10, decimal_places=2)
    quantity=models.IntegerField()
    item_status=models.CharField(max_length=20, choices=STATUS_CHOICES, default='placed')
    cancellation_reason=models.TextField(blank=True, null=True)
    return_reason=models.TextField(blank=True, null=True)
    return_qty=models.PositiveIntegerField(null=True, blank=True)  # legacy — prefer returned_quantity
    refund_processed=models.BooleanField(default=False)   # ← prevents duplicate refunds
    cancelled_quantity=models.PositiveIntegerField(default=0)  # how many units have been cancelled
    returned_quantity=models.PositiveIntegerField(default=0)   # how many units have been returned

    @property
    def remaining_quantity(self):
        """Units that are neither cancelled nor returned."""
        return max(self.quantity - self.cancelled_quantity - self.returned_quantity, 0)

    def __str__(self):
        return f"{self.order.order_number} - {self.variant}"
    
class ReturnRequest(models.Model):
    STATUS_CHOICES = [
        ('Pending',  'Pending'),
        ('Approved', 'Approved'),
        ('Picked Up', 'Picked Up'),
        ('Rejected', 'Rejected'),
    ]

    order=models.ForeignKey('Order',     on_delete=models.CASCADE, related_name='return_requests')
    item=models.ForeignKey('OrderItem', on_delete=models.CASCADE, related_name='return_requests')
    quantity=models.PositiveIntegerField(default=1)  # how many units this return request covers
    reason=models.CharField(max_length=255)
    description=models.TextField(blank=True)
    status=models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return #{self.id} — {self.order} — qty {self.quantity} — {self.status}"