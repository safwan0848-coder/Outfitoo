import uuid

def generate_sku(product, variant):
    parts = []
    if product.category and product.category.category_name:
        parts.append(product.category.category_name[:3].upper())
    if product.product_type:
        parts.append(product.product_type[:3].upper())
    if variant.color and not variant.color.startswith('#'):
        parts.append(variant.color[:3].upper())
    if variant.size:
        parts.append(variant.size.upper())
    random_part = uuid.uuid4().hex[:6].upper()

    return 'OUT-' + '-'.join(parts) + '-' + random_part