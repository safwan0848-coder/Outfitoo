from django.db import models
from admin_side.products_management.models import Product
from admin_side.categories_management.models import Category


class Offer(models.Model):
    DISCOUNT_TYPE = [
        ('percentage', 'Percentage (%)'),
        ('flat', 'Flat (₹)'),
    ]
    APPLY_TO = [
        ('product',  'Product'),
        ('category', 'Category'),
    ]

    offer_name       = models.CharField(max_length=200)
    discount_type    = models.CharField(max_length=20, choices=DISCOUNT_TYPE)
    apply_to         = models.CharField(max_length=20, choices=APPLY_TO)

    # Only one of these will be set based on apply_to
    product          = models.ForeignKey(Product,  on_delete=models.CASCADE, null=True, blank=True, related_name='offers')
    category         = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='offers')

    discount_value          = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                                   help_text="Only for percentage offers")
    start_date = models.DateField()
    end_date   = models.DateField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.offer_name

    @property
    def discount_display(self):
        if self.discount_type == 'percentage':
            return f"{self.discount_value}% Off"
        return f"₹{self.discount_value} Flat"

    @property
    def applies_to_name(self):
        if self.apply_to == 'product' and self.product:
            return self.product.name
        if self.apply_to == 'category' and self.category:
            return self.category.category_name
        return '—'
