from django.shortcuts import render
from django.core.paginator import Paginator
from admin_side.products_management.models import Product
from django.shortcuts import render, get_object_or_404, redirect
from admin_side.variants_management.models import Variant
from django.db.models import Q, Min, Max, Count, Avg
from admin_side.categories_management.models import Category
from user_side.cart.models import Cart
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import ProductReview
from user_side.orders.models import Order, OrderItem
from user_side.wishlist.models import Wishlist, WishlistItem
from user_side.cart.models import Cart

sizes = ["XS", "S", "M", "L", "XL", "XXL"]
types = ["shirt", "pant", "tees", "shorts", "coat"]

def is_user(user):
    return user.is_authenticated and not user.is_staff

@never_cache
def product_list(request):
    query = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', 'default')
    cat_slug = request.GET.get('category', '')
    price_min = request.GET.get('price_min', '')
    price_max = request.GET.get('price_max', '')
    page_num = request.GET.get('page', 1)
    size_filter = request.GET.getlist('size')
    type_filter = request.GET.get('type', '')

    products = (
        Product.objects
        .filter(
            is_deleted=False,
            is_listed=True,
            category__is_active=True,
        )
        .select_related('category')
        .prefetch_related('variants')
        .annotate(min_price=Min('variants__price', filter=Q(variants__is_active=True)))
        .distinct()
    )

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
            variants__stock__gt=0,
        ).distinct()

    if price_min:
        try:
            products = products.filter(min_price__gte=float(price_min))
        except (ValueError, TypeError):
            pass

    if price_max:
        try:
            products = products.filter(min_price__lte=float(price_max))
        except (ValueError, TypeError):
            pass

    SORT_MAP = {
        'price_asc':'min_price',
        'price_desc':'-min_price',
        'name_asc':'name',
        'name_desc':'-name',
        'newest':'-id',
        'discount':'-id',  
        'default':'-id',
    }
    products = products.order_by(SORT_MAP.get(sort_by, '-id'))

    wishlist_items = set()
    if request.user.is_authenticated:
        from user_side.wishlist.models import Wishlist, WishlistItem
        wishlist = Wishlist.objects.filter(user=request.user).first()
        if wishlist:
            wishlist_items = set(
                WishlistItem.objects
                .filter(wishlist=wishlist)
                .values_list('product_id', flat=True)
            )

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
        offer = None
        discounted_price = None
        has_offer = False
        discount = None       

        if variant:
            discounted_price = variant.get_discounted_price 
            offer = variant.get_active_offer

            if offer and discounted_price < variant.price:
                has_offer = True
                try:
                    discount = int(
                        (1 - float(discounted_price) / float(variant.price)) * 100
                    )
                except (ValueError, ZeroDivisionError, TypeError):
                    discount = None
            elif getattr(variant, 'original_price', None):
                try:
                    pct = int(
                        (1 - float(variant.price) / float(variant.original_price)) * 100
                    )
                    if pct > 0:
                        discount = pct
                        has_offer = True
                        discounted_price = variant.price
                except (ValueError, ZeroDivisionError, TypeError):
                    pass

        product_data.append({
            'product':product,
            'variant':variant,
            'offer': offer,
            'discounted_price': discounted_price,
            'has_offer':has_offer,
            'discount':discount,
            'is_new': False,
            'in_wishlist':product.id in wishlist_items,
        })

    if sort_by == 'discount':
        product_data.sort(key=lambda x: x['discount'] or 0, reverse=True)

    categories = Category.objects.filter(
        is_active=True,
        is_deleted=False,
    ).order_by('category_name')

    price_bounds = (
        Product.objects
        .filter(is_deleted=False, is_listed=True, variants__is_active=True)
        .aggregate(
            min_price=Min('variants__price'),
            max_price=Max('variants__price'),
        )
    )
    global_min = int(price_bounds['min_price'] or 0)
    global_max = max(10000, int(price_bounds['max_price'] or 10000))

    paginator = Paginator(product_data, 8)
    page_obj  = paginator.get_page(page_num)

    selected_category = None
    if cat_slug:
        try:
            selected_category = Category.objects.get(id=cat_slug)
        except Category.DoesNotExist:
            pass


    return render(request, 'user/product_list.html', {
        'product_data': page_obj.object_list,
        'page_obj':page_obj,
        'categories': categories,
        'query':query,
        'sort_by': sort_by,
        'price_min':price_min or global_min,
        'price_max':price_max or global_max,
        'global_min':global_min,
        'global_max': global_max,
        'selected_category': selected_category,
        'total_count': paginator.count,
        'cat_slug': cat_slug,
        'type_filter':type_filter,
        'sizes': sizes,
        'types': types,
        'size_filter': size_filter,
    })


def search_products_ajax(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': [], 'has_more': False, 'query': ''})

    products = Product.objects.filter(
        is_deleted=False,
        is_listed=True,
        category__is_active=True
    ).filter(
        Q(name__icontains=query)
    ).prefetch_related('variants').distinct()[:6]

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

    has_more = len(results) > 5
    return JsonResponse({'products': results[:5], 'has_more': has_more, 'query': query})


@never_cache
def product_detail(request, pk):

    request.session['last_viewed_product'] = pk

    product = get_object_or_404( Product,pk=pk,is_deleted=False,is_listed=True)

    all_variants = list(Variant.objects.filter( product=product,is_active=True))

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

    seen_colors = set()
    unique_color_variants = []

    for v in all_variants:
        color_key = v.color.strip().lower()
        if color_key not in seen_colors:
            seen_colors.add(color_key)
            unique_color_variants.append(v)

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


    wishlist_count = 0
    in_wishlist = False

    if request.user.is_authenticated:
        wishlist = Wishlist.objects.filter(user=request.user).first()

        if wishlist:
            wishlist_count = wishlist.items.count()

            in_wishlist = WishlistItem.objects.filter(
                wishlist=wishlist,
                product=product
            ).exists()

    cart_count = 0

    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()

        if cart:
            cart_count = cart.items.count()  


    has_purchased = False
    has_reviewed  = False
    existing_review = None

    if request.user.is_authenticated:
        has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            variant__product=product,
            item_status='delivered'
        ).exists()

        existing_review = ProductReview.objects.filter(
            product=product,
            user=request.user
        ).first()
        has_reviewed = existing_review is not None

    all_reviews = ProductReview.objects.filter(product=product).select_related('user')
    review_count = all_reviews.count()

    rating_agg = all_reviews.aggregate(avg=Avg('rating'))
    avg_rating  = round(rating_agg['avg'] or 0, 1)

    rating_breakdown = []
    for star in range(5, 0, -1):
        cnt = all_reviews.filter(rating=star).count()
        pct = round((cnt / review_count * 100)) if review_count else 0
        rating_breakdown.append((star, cnt, pct))

    reviews = all_reviews[:10] 

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
        'wishlist_count': wishlist_count,
        'in_wishlist': in_wishlist,
        'avg_rating':avg_rating,
        'review_count':review_count,
        'reviews': reviews,
        'rating_breakdown': rating_breakdown,
        'has_purchased':has_purchased,
        'has_reviewed':has_reviewed,
        'existing_review':existing_review,
    })


@login_required
def submit_review(request, pk):
    if request.method != 'POST':
        return redirect('product_detail', pk=pk)

    product = get_object_or_404(Product, pk=pk, is_deleted=False, is_listed=True)

    from user_side.orders.models import OrderItem
    has_purchased = OrderItem.objects.filter(
        order__user=request.user,
        variant__product=product,
        item_status='delivered'
    ).exists()

    if not has_purchased:
        messages.error(request, "You can review this product only after purchase and delivery")
        return redirect('product_detail', pk=pk)

    existing_review = ProductReview.objects.filter(product=product, user=request.user).first()

    try:
        rating = int(request.POST.get('rating', 0))
    except (ValueError, TypeError):
        rating = 0

    comment = request.POST.get('comment', '').strip()
    title   = request.POST.get('title', '').strip()[:150]

    if rating < 1 or rating > 5:
        messages.error(request, "Please select a rating between 1 and 5.")
        return redirect('product_detail', pk=pk)

    if not comment:
        messages.error(request, "Review comment cannot be empty.")
        return redirect('product_detail', pk=pk)

    if existing_review:
        existing_review.rating = rating
        existing_review.title = title
        existing_review.comment = comment
        existing_review.save()
        messages.success(request, "Your review has been updated successfully.")
    else:
        ProductReview.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            title=title,
            comment=comment,
        )
        messages.success(request, "Thank you! Your review has been submitted.")
        
    return redirect('product_detail', pk=pk)