from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Wallet

User = settings.AUTH_USER_MODEL

@receiver(post_save, sender=User)
def create_wallet(sender, instance, created, **kwargs):
    """Auto-create a Wallet every time a new User is created."""
    if created:
        Wallet.objects.get_or_create(user=instance)
