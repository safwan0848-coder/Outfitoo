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

    image_side = models.ImageField(upload_to='product_images/', blank=True, null=True)
    image_back = models.ImageField(upload_to='product_images/', blank=True, null=True)

    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def get_active_offer(self):
        variant = self.variants.filter(is_active=True).first()
        if variant:
            return variant.get_active_offer
        return None

