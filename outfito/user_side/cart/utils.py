from decimal import Decimal
from django.utils import timezone
from collections import defaultdict
from admin_side.offer_management.models import Offer

def calculate_cart_offers(cart_items):
    """
    Evaluates product and category offers based on minimum_purchase_amount 
    applied to the CART subtotal of eligible items.
    
    Returns:
      - total_offer_discount (Decimal)
      - item_discounts (dict): mapping cart_item.id -> Decimal (discount for that item)
      - applied_offer_messages (list): list of strings describing the applied offers
    """
    now = timezone.now().date()
    total_offer_discount = Decimal('0.00')
    item_discounts = {}
    applied_offer_messages = set()

    # 1. Calculate subtotals per product and category
    category_subtotals = defaultdict(Decimal)
    product_subtotals = defaultdict(Decimal)

    for item in cart_items:
        subtotal = item.variant.price * item.quantity
        product = item.variant.product
        product_subtotals[product] += subtotal
        category_subtotals[product.category] += subtotal

    # 2. Find eligible offers for each product/category
    # Cache active offers to avoid N+1 queries
    active_offers = list(Offer.objects.filter(
        is_active=True,
        start_date__lte=now,
        end_date__gte=now
    ).select_related('product', 'category'))

    product_offers = [o for o in active_offers if o.apply_to == 'product']
    category_offers = [o for o in active_offers if o.apply_to == 'category']

    for item in cart_items:
        base_subtotal = item.variant.price * item.quantity
        product = item.variant.product
        category = product.category
        
        best_discount = Decimal('0.00')
        best_offer_msg = None

        # Check Product Offers
        for po in product_offers:
            if po.product == product:
                min_amount = po.minimum_purchase_amount or Decimal('0.00')
                if product_subtotals[product] >= min_amount:
                    # Calculate discount for THIS item's subtotal
                    if po.discount_type == 'percentage':
                        discount = (base_subtotal * po.discount_value) / Decimal('100.00')
                        if po.maximum_discount_amount:
                            # Prorate the maximum discount based on this item's share of the product subtotal
                            share = base_subtotal / product_subtotals[product]
                            max_disc = po.maximum_discount_amount * share
                            discount = min(discount, max_disc)
                    else:
                        # Flat discount: prorate it
                        share = base_subtotal / product_subtotals[product]
                        discount = po.discount_value * share

                    if discount > best_discount:
                        best_discount = discount
                        best_offer_msg = po.offer_name

        # Check Category Offers
        for co in category_offers:
            if co.category == category:
                min_amount = co.minimum_purchase_amount or Decimal('0.00')
                if category_subtotals[category] >= min_amount:
                    if co.discount_type == 'percentage':
                        discount = (base_subtotal * co.discount_value) / Decimal('100.00')
                        if co.maximum_discount_amount:
                            share = base_subtotal / category_subtotals[category]
                            max_disc = co.maximum_discount_amount * share
                            discount = min(discount, max_disc)
                    else:
                        share = base_subtotal / category_subtotals[category]
                        discount = co.discount_value * share

                    if discount > best_discount:
                        best_discount = discount
                        best_offer_msg = co.offer_name

        item_discounts[item.id] = best_discount.quantize(Decimal('0.01'))
        total_offer_discount += best_discount

        if best_offer_msg:
            applied_offer_messages.add(f"Applied: {best_offer_msg}")

    return {
        'total_offer_discount': total_offer_discount.quantize(Decimal('0.01')),
        'item_discounts': item_discounts,
        'applied_offer_messages': list(applied_offer_messages)
    }
