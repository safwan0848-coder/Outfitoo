from django.db import models
from admin_side.products_management.models import Product
from admin_side.variants_management.models import Variant
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

class WishlistItem(models.Model):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
