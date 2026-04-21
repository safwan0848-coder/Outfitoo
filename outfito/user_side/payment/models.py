from django.db import models
from user_side.orders.models import Order


class Payment(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('wallet', 'Wallet'),
        ('cod', 'Cash on Delivery'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')

    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    razorpay_order_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order.order_number} - {self.payment_status}"