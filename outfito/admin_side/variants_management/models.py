from django.db import models
from admin_side.products_management.models import Product


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=100, unique=True)
    size = models.CharField(max_length=20)
    color = models.CharField(max_length=50, db_index=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.sku
    
    @property
    def get_active_offer(self):
        from admin_side.offer_management.models import Offer
        from django.utils import timezone
        from decimal import Decimal
        
        now = timezone.now().date()
        base_price = self.price
        
        best_discount = Decimal('0.00')
        best_offer = None
        
        # 1. Product Offer
        product_offer = Offer.objects.filter(
            apply_to='product',
            product=self.product,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            minimum_purchase_amount__lte=base_price
        ).first()
        
        if product_offer:
            if product_offer.discount_type == 'percentage':
                discount = (base_price * product_offer.discount_value) / 100
                if product_offer.maximum_discount_amount:
                    discount = min(discount, product_offer.maximum_discount_amount)
            else:
                discount = product_offer.discount_value
            if discount > best_discount:
                best_discount = discount
                best_offer = product_offer
                
        # 2. Category Offer
        category_offer = Offer.objects.filter(
            apply_to='category',
            category=self.product.category,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            minimum_purchase_amount__lte=base_price
        ).first()
        
        if category_offer:
            if category_offer.discount_type == 'percentage':
                discount = (base_price * category_offer.discount_value) / 100
                if category_offer.maximum_discount_amount:
                    discount = min(discount, category_offer.maximum_discount_amount)
            else:
                discount = category_offer.discount_value
            if discount > best_discount:
                best_discount = discount
                best_offer = category_offer
                
        return best_offer

    @property
    def get_discounted_price(self):
        from admin_side.offer_management.models import Offer
        from django.utils import timezone
        from decimal import Decimal
        
        now = timezone.now().date()
        base_price = self.price
        best_discount = Decimal('0.00')
        
        # 1. Product Offer
        product_offer = Offer.objects.filter(
            apply_to='product',
            product=self.product,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            minimum_purchase_amount__lte=base_price
        ).first()
        
        if product_offer:
            if product_offer.discount_type == 'percentage':
                discount = (base_price * product_offer.discount_value) / 100
                if product_offer.maximum_discount_amount:
                    discount = min(discount, product_offer.maximum_discount_amount)
            else:
                discount = product_offer.discount_value
            best_discount = max(best_discount, discount)
            
        # 2. Category Offer
        category_offer = Offer.objects.filter(
            apply_to='category',
            category=self.product.category,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            minimum_purchase_amount__lte=base_price
        ).first()
        
        if category_offer:
            if category_offer.discount_type == 'percentage':
                discount = (base_price * category_offer.discount_value) / 100
                if category_offer.maximum_discount_amount:
                    discount = min(discount, category_offer.maximum_discount_amount)
            else:
                discount = category_offer.discount_value
            best_discount = max(best_discount, discount)
            
        final_price = base_price - best_discount
        return max(final_price, Decimal('0.00'))


    def save(self, *args, **kwargs):
        if self.color:
            self.color = self.color.strip().lower()
        super().save(*args, **kwargs)
    

    
