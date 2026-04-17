from django.shortcuts import render
from django.core.paginator import Paginator
from admin_side.products_management.models import Product
from django.shortcuts import render, get_object_or_404
from admin_side.variants_management.models import Variant
from django.db.models import Q, Min, Max,Count,Avg
from admin_side.categories_management.models import Category
from user_side.cart.models import Cart
from django.views.decorators.cache import never_cache
from django.http import JsonResponse

@never_cache
def product_list(request):

    query       = request.GET.get('q', '').strip()
    sort_by     = request.GET.get('sort', 'default')
    cat_slug    = request.GET.get('category', '')
    price_min   = request.GET.get('price_min', '')
    price_max   = request.GET.get('price_max', '')
    page_num    = request.GET.get('page', 1)
    size_filter = request.GET.getlist('size')
    type_filter = request.GET.get('type', '')

    products = (
    Product.objects
    .filter(
        is_deleted=False,
        is_listed=True,
        category__is_active=True  
    )
    .select_related('category')
    .prefetch_related('variants')
)

    products = products.filter(is_listed=True)

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__category_name__icontains=query)
        )

    if cat_slug:
        products = products.filter(category__id=cat_slug)

    if type_filter:
        products = products.filter(product_type=type_filter)

    if size_filter:
        products = products.filter(
            variants__size__in=size_filter,
            variants__is_active=True,
            variants__stock__gt=0
        ).distinct()

    if price_min:
        try:
            products = products.filter(
                variants__price__gte=float(price_min),
                variants__is_active=True
            ).distinct()
        except ValueError:
            pass

    if price_max:
        try:
            products = products.filter(
                variants__price__lte=float(price_max),
                variants__is_active=True
            ).distinct()
        except ValueError:
            pass

    SORT_MAP = {
        'price_asc':  'variants__price',
        'price_desc': '-variants__price',
        'name_asc':   'name',
        'name_desc':  '-name',
        'newest':     '-id',
        'discount':   '-id',
        'default':    '-id',
    }

    order_field = SORT_MAP.get(sort_by, '-id')

    if sort_by in ('price_asc', 'price_desc'):
        products = products.filter(
            variants__is_active=True
        ).order_by(order_field).distinct()
    else:
        products = products.order_by(order_field)

    # Pre-fetch user wishlist if logged in
    wishlist_items = set()
    if request.user.is_authenticated:
        from user_side.wishlist.models import Wishlist, WishlistItem
        wishlist = Wishlist.objects.filter(user=request.user).first()
        if wishlist:
            wishlist_items = set(WishlistItem.objects.filter(wishlist=wishlist).values_list('product_id', flat=True))

    product_data = []

    for product in products:
        variants = product.variants.filter(is_active=True, stock__gt=0)

        variant = None

        if variants.exists():

            if size_filter:
                variant = variants.filter(size__in=size_filter).first()

            if not variant:
                variant = variants.filter(is_default=True).first()

            if not variant:
                variant = variants.first()

        discount = None

        if variant and getattr(variant, 'original_price', None):
            try:
                pct = int((1 - float(variant.price) / float(variant.original_price)) * 100)
                if pct > 0:
                    discount = pct
            except (ValueError, ZeroDivisionError, TypeError):
                pass

        product_data.append({
            'product': product,
            'variant': variant,
            'discount': discount,
            'is_new': False,
            'in_wishlist': product.id in wishlist_items,
        })

    if sort_by == 'discount':
        product_data.sort(
            key=lambda x: x['discount'] or 0,
            reverse=True
        )

    categories = Category.objects.filter(
        is_active=True,is_deleted=False,
    ).order_by('category_name')

    price_bounds = Product.objects.filter(
        is_deleted=False,
        is_listed=True,
        variants__is_active=True
    ).aggregate(
        min_price=Min('variants__price'),
        max_price=Max('variants__price'),
    )

    global_min = int(price_bounds['min_price'] or 0)
    global_max = int(price_bounds['max_price'] or 10000)

    paginator = Paginator(product_data, 8)
    page_obj  = paginator.get_page(page_num)

    selected_category = None
    if cat_slug:
        try:
            selected_category = Category.objects.get(id=cat_slug)
        except Category.DoesNotExist:
            pass

    sizes = ["XS", "S", "M", "L", "XL", "XXL"]

    return render(request, 'user/product_list.html', {
        'product_data':      page_obj.object_list,
        'page_obj':          page_obj,
        'categories':        categories,
        'query':             query,
        'sort_by':           sort_by,
        'price_min':         price_min or global_min,
        'price_max':         price_max or global_max,
        'global_min':        global_min,
        'global_max':        global_max,
        'selected_category': selected_category,
        'total_count':       paginator.count,
        'cat_slug':          cat_slug,
        'type_filter':       type_filter,
        'sizes':             sizes,
        'size_filter':       size_filter,
    })



def is_user(user):
    return user.is_authenticated and not user.is_staff

def search_products_ajax(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': []})

    products = Product.objects.filter(
        is_deleted=False,
        is_listed=True,
        category__is_active=True
    ).filter(
        Q(name__icontains=query) |
        Q(description__icontains=query) |
        Q(category__category_name__icontains=query)
    ).prefetch_related('variants').distinct()[:10]

    results = []
    for product in products:
        variant = product.variants.filter(is_active=True, stock__gt=0).first()
        if not variant:
            variant = product.variants.filter(is_active=True).first()

        price = variant.price if variant else 0

        image_url = ""
        if product.image_side:
            image_url = product.image_side.url
        elif variant and variant.image:
            image_url = variant.image.url

        results.append({
            'id': product.id,
            'name': product.name,
            'price': str(price),
            'image_url': image_url,
            'url': f"/products/products/{product.id}/"
        })

    return JsonResponse({'products': results})


@never_cache
def product_detail(request, pk):

    request.session['last_viewed_product'] = pk

    product = get_object_or_404(
        Product,
        pk=pk,
        is_deleted=False,
        is_listed=True
    )

    all_variants = list(
        Variant.objects.filter(
            product=product,
            is_active=True
        )
    )

    selected_size  = request.GET.get('size', '').strip()
    selected_color = request.GET.get('color', '').strip()

    display_variant = next(
        (v for v in all_variants if v.is_default),
        None
    ) or (all_variants[0] if all_variants else None)

    if display_variant:
        if not selected_size:
            selected_size = display_variant.size
        if not selected_color:
            selected_color = display_variant.color

    if selected_size and selected_color:
        v = next(
            (v for v in all_variants
             if v.size == selected_size and v.color.lower() == selected_color.lower()),
            None
        )
        if v:
            display_variant = v
        else:
            v = next((v for v in all_variants if v.size == selected_size), None)
            if v:
                display_variant = v
                selected_color = v.color
            else:
                v = next(
                    (v for v in all_variants if v.color.lower() == selected_color.lower()),
                    None
                )
                if v:
                    display_variant = v
                    selected_size = v.size

    elif selected_size:
        v = next((v for v in all_variants if v.size == selected_size), None)
        if v:
            display_variant = v
            selected_color = v.color

    elif selected_color:
        v = next((v for v in all_variants if v.color.lower() == selected_color.lower()), None)
        if v:
            display_variant = v
            selected_size = v.size

    if display_variant:
        selected_size  = display_variant.size
        selected_color = display_variant.color

    # ==============================
    # COLORS
    # ==============================

    seen_colors = set()
    unique_color_variants = []

    for v in all_variants:
        color_key = v.color.strip().lower()
        if color_key not in seen_colors:
            seen_colors.add(color_key)
            unique_color_variants.append(v)

    # ==============================
    # SIZES
    # ==============================

    SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
    size_variant_map = {}

    for v in all_variants:
        sz = v.size

        if sz not in size_variant_map:
            size_variant_map[sz] = v
        else:
            existing = size_variant_map[sz]

            if v.color.lower() == selected_color.lower() and existing.color.lower() != selected_color.lower():
                size_variant_map[sz] = v
            elif v.stock > 0 and existing.stock == 0:
                size_variant_map[sz] = v

    available_sizes = []

    for sz in SIZE_ORDER:
        if sz in size_variant_map:
            best_v = size_variant_map[sz]
            available_sizes.append((sz, best_v.stock > 0, best_v.color))

    # ==============================
    # RELATED PRODUCTS
    # ==============================

    related_qs = Product.objects.filter(
        category=product.category,
        is_deleted=False,
        is_listed=True
    ).exclude(pk=product.pk).prefetch_related('variants')[:4]

    related_products = []

    for rp in related_qs:
        variants = list(rp.variants.filter(is_active=True))
        rp.display_variant = next(
            (v for v in variants if v.is_default),
            None
        ) or (variants[0] if variants else None)

        related_products.append(rp)

    # ==============================
    # ✅ FIXED WISHLIST + CART
    # ==============================

    wishlist_count = 0
    in_wishlist = False

    if request.user.is_authenticated:
        from user_side.wishlist.models import Wishlist, WishlistItem

        wishlist = Wishlist.objects.filter(user=request.user).first()

        if wishlist:
            wishlist_count = wishlist.items.count()  # ✅ FIX

            in_wishlist = WishlistItem.objects.filter(
                wishlist=wishlist,
                product=product
            ).exists()  # ✅ FIX

    cart_count = 0

    if request.user.is_authenticated:
        from user_side.cart.models import Cart

        cart = Cart.objects.filter(user=request.user).first()

        if cart:
            cart_count = cart.items.count()  # ✅ FIX

    # ==============================
    # REVIEWS
    # ==============================

    avg_rating = 4.2
    review_count = 3

    reviews = [
        {"user": "Rahul Menon", "rating": 5, "comment": "Great quality product!", "created_at": "March 1, 2025", "helpful_count": 2},
        {"user": "Aisha Khan", "rating": 4, "comment": "Nice fit and color.", "created_at": "March 5, 2025", "helpful_count": 1},
        {"user": "Arjun Nair", "rating": 3, "comment": "Average product.", "created_at": "March 10, 2025", "helpful_count": 0},
    ]

    rating_breakdown = [
        (5, 1, 33),
        (4, 1, 33),
        (3, 1, 33),
        (2, 0, 0),
        (1, 0, 0),
    ]

    return render(request, 'user/product_detail.html', {
        'product': product,
        'display_variant': display_variant,
        'all_variants': all_variants,
        'unique_color_variants': unique_color_variants,
        'available_sizes': available_sizes,
        'selected_size': selected_size,
        'selected_color': selected_color,
        'related_products': related_products,
        'cart_count': cart_count,
        'wishlist_count': wishlist_count,   # ✅ added
        'in_wishlist': in_wishlist,         # ✅ fixed
        'avg_rating': avg_rating,
        'review_count': review_count,
        'reviews': reviews,
        'rating_breakdown': rating_breakdown,
    })