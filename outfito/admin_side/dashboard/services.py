from django.db.models import Sum, Count, F, Q, Func
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.utils import timezone
from datetime import timedelta
from user_side.orders.models import Order, OrderItem
from admin_side.products_management.models import Product

def get_filtered_orders(start_date=None, end_date=None):
    """Get Delivered orders within the specified date range."""
    # Note: Order status "Delivered" means the order as a whole is delivered,
    # or we can check items. Assuming order_status='Delivered' is standard.
    orders = Order.objects.filter(order_status='Delivered')
    if start_date:
        orders = orders.filter(created_at__gte=start_date)
    if end_date:
        # Include the whole end_date
        end_date = end_date + timedelta(days=1)
        orders = orders.filter(created_at__lt=end_date)
    return orders

def get_sales_report_data(start_date=None, end_date=None):
    orders = get_filtered_orders(start_date, end_date)
    
    total_orders = orders.count()
    
    # Calculate Total Revenue (Net after discounts) and Total Discounts
    # We use sum of total_amount
    aggregate_data = orders.aggregate(
        total_revenue=Sum('total_amount'),
        total_discount=Sum('discount_amount')
    )
    
    # Calculate Products Sold
    products_sold = OrderItem.objects.filter(
        order__in=orders, 
        item_status='delivered'
    ).aggregate(total_qty=Sum('quantity'))['total_qty'] or 0

    # Calculate Coupons Used
    coupons_used = orders.filter(coupon__isnull=False).count()

    # Get details of coupons used
    coupon_usage_details = orders.filter(coupon__isnull=False).values(
        'coupon__code',
        'coupon__discount_type',
        'coupon__discount_value',
        'coupon__usage_limit',
        'coupon__is_active'
    ).annotate(times_used=Count('id')).order_by('-times_used')

    return {
        'total_revenue': aggregate_data['total_revenue'] or 0.00,
        'total_orders': total_orders,
        'products_sold': products_sold,
        'total_discount': aggregate_data['total_discount'] or 0.00,
        'coupons_used': coupons_used,
        'coupon_usage_details': coupon_usage_details,
        'orders': orders.order_by('-created_at')
    }

def get_chart_data(period='yearly', year=None):
    """Get data for the Revenue Overview chart with zero-filling for missing dates."""
    orders = Order.objects.filter(order_status='Delivered')
    now = timezone.localtime()
    
    if year:
        target_year = int(year)
        try:
            now = now.replace(year=target_year)
        except ValueError:
            # Handle Feb 29 on non-leap years
            now = now.replace(month=2, day=28, year=target_year)
            
    labels = []
    data_map = {}
    
    if period == 'daily':
        # Last 24 hours
        start_time = now - timedelta(hours=23)
        start_time = start_time.replace(minute=0, second=0, microsecond=0)
        
        for i in range(24):
            dt = start_time + timedelta(hours=i)
            label = dt.strftime('%I %p') # e.g. 01 PM
            labels.append(label)
            data_map[label] = 0.0
            
        for order in orders.filter(created_at__gte=start_time):
            local_dt = timezone.localtime(order.created_at)
            label = local_dt.strftime('%I %p')
            if label in data_map:
                data_map[label] += float(order.total_amount)
                
    elif period == 'weekly':
        # Last 7 days
        start_date = (now - timedelta(days=6)).date()
        
        for i in range(7):
            dt = start_date + timedelta(days=i)
            label = dt.strftime('%a') # Mon, Tue, etc.
            labels.append(label)
            data_map[label] = 0.0
            
        for order in orders.filter(created_at__date__gte=start_date):
            local_dt = timezone.localtime(order.created_at)
            label = local_dt.strftime('%a')
            if label in data_map:
                data_map[label] += float(order.total_amount)
                
    elif period == 'monthly':
        # Current month
        import calendar
        start_date = now.replace(day=1).date()
        _, last_day = calendar.monthrange(start_date.year, start_date.month)
        
        for i in range(1, last_day + 1):
            label = str(i)
            labels.append(label)
            data_map[label] = 0.0
            
        for order in orders.filter(created_at__year=start_date.year, created_at__month=start_date.month):
            local_dt = timezone.localtime(order.created_at)
            label = str(local_dt.day)
            if label in data_map:
                data_map[label] += float(order.total_amount)
                
    else: # yearly by default
        start_date = now.replace(month=1, day=1).date()
        months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        
        for month in months:
            labels.append(month)
            data_map[month] = 0.0
            
        for order in orders.filter(created_at__year=start_date.year):
            local_dt = timezone.localtime(order.created_at)
            label = local_dt.strftime('%b')
            if label in data_map:
                data_map[label] += float(order.total_amount)

    data = [data_map[label] for label in labels]

    return {
        'labels': labels,
        'data': data
    }

def get_top_selling_products(limit=5):
    top_products = OrderItem.objects.filter(item_status='delivered').values(
        'variant__product__id',
        'variant__product__name',
        'variant__product__category__category_name',
        'variant__product__image_side',
        'variant__product__image_back'
    ).annotate(
        total_sales=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'))
    ).order_by('-total_sales')[:limit]
    
    return top_products

def get_top_selling_categories(limit=5):
    top_categories = OrderItem.objects.filter(item_status='delivered').values(
        'variant__product__category__category_name'
    ).annotate(
        total_sales=Sum('quantity'),
        total_revenue=Sum(F('price') * F('quantity'))
    ).order_by('-total_sales')[:limit]
    
    return top_categories

def get_top_selling_brands(limit=5):
    # Depending on if there's a brand model, assuming not based on models, so just categories/products for now.
    pass
