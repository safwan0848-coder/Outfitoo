from django.db import models
from admin_side.categories_management.models import Category

class Product(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_listed = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    
    PRODUCT_TYPES = [
    ('shirt', 'Shirt'),
    ('pant', 'Pant'),
    ('tees', 'Tees'),
    ('shorts', 'Shorts'),
    ('coat', 'Coat'),
]
    product_type = models.CharField(max_length=20, choices=PRODUCT_TYPES)

    # ✅ ADD THIS
    image_side = models.ImageField(upload_to='product_images/', blank=True, null=True)
    image_back = models.ImageField(upload_to='product_images/', blank=True, null=True)

    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def get_active_offer(self):
        from admin_side.offer_management.models import Offer
        from django.utils import timezone
        
        now = timezone.now().date()
        
        product_offer = Offer.objects.filter(
            apply_to='product', product=self, is_active=True, 
            start_date__lte=now, end_date__gte=now
        ).first()
        
        category_offer = Offer.objects.filter(
            apply_to='category', category=self.category, is_active=True,
            start_date__lte=now, end_date__gte=now
        ).first()
        
        if not product_offer and not category_offer:
            return None
            
        if product_offer and not category_offer:
            return product_offer
            
        if category_offer and not product_offer:
            return category_offer
            
        # If both exist, prioritize the one with higher value if same type, else product offer
        if product_offer.discount_type == category_offer.discount_type:
            if product_offer.discount_value >= category_offer.discount_value:
                return product_offer
            return category_offer
            
        return product_offer

