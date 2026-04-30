from django.db import models
from django.core.exceptions import ValidationError
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

    offer_name  = models.CharField(max_length=200)
    discount_type= models.CharField(max_length=20, choices=DISCOUNT_TYPE)
    apply_to= models.CharField(max_length=20, choices=APPLY_TO)
    product = models.ForeignKey(Product,  on_delete=models.CASCADE, null=True, blank=True, related_name='offers')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='offers')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    maximum_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,help_text="Only for percentage offers")
    start_date = models.DateField()
    end_date   = models.DateField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.offer_name

    def clean(self):
        errors = {}
        if self.discount_value is not None:
            if self.discount_value <= 0:
                errors['discount_value'] = "Discount value must be greater than 0."
            if self.discount_type == 'percentage' and self.discount_value > 100:
                errors['discount_value'] = "Percentage discount cannot exceed 100%."

        if self.minimum_purchase_amount is not None and self.minimum_purchase_amount < 0:
            errors['minimum_purchase_amount'] = "Minimum purchase amount cannot be negative."

        if self.maximum_discount_amount is not None:
            if self.maximum_discount_amount <= 0:
                errors['maximum_discount_amount'] = "Maximum discount must be greater than 0."
            if self.discount_type == 'flat':
                errors['maximum_discount_amount'] = "Max discount cap only applies to percentage offers."

        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                errors['end_date'] = "End date must be after the start date."

        if self.apply_to == 'product' and not self.product_id:
            errors['product'] = "A product must be selected when 'Apply To' is Product."
        if self.apply_to == 'category' and not self.category_id:
            errors['category'] = "A category must be selected when 'Apply To' is Category."

        if errors:
            raise ValidationError(errors)

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
