from django.utils import timezone
from decimal import Decimal
from admin_side.offer_management.models import Offer

def get_best_offer(variant, apply_base_amount=None):
    now = timezone.now().date()
    base_price = Decimal(str(apply_base_amount)) if apply_base_amount is not None else variant.price
    
    best_discount = Decimal('0.00')
    best_offer = None
    
    product_offer = Offer.objects.filter(
        apply_to='product',
        product=variant.product,
        is_active=True,
        start_date__lte=now,
        end_date__gte=now,
        minimum_purchase_amount__lte=base_price
    ).first()
    
    if product_offer:
        if product_offer.discount_type == 'percentage':
            discount = (base_price * product_offer.discount_value) / Decimal('100.00')
            if product_offer.maximum_discount_amount:
                discount = min(discount, product_offer.maximum_discount_amount)
        else:
            discount = product_offer.discount_value
            
        if discount > best_discount:
            best_discount = discount
            best_offer = product_offer
            
    category_offer = Offer.objects.filter(
        apply_to='category',
        category=variant.product.category,
        is_active=True,
        start_date__lte=now,
        end_date__gte=now,
        minimum_purchase_amount__lte=base_price
    ).first()
    
    if category_offer:
        if category_offer.discount_type == 'percentage':
            discount = (base_price * category_offer.discount_value) / Decimal('100.00')
            if category_offer.maximum_discount_amount:
                discount = min(discount, category_offer.maximum_discount_amount)
        else:
            discount = category_offer.discount_value
            
        if discount > best_discount:
            best_discount = discount
            best_offer = category_offer
            
    return best_offer, best_discount.quantize(Decimal('0.01'))
