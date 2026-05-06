from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from user_side.orders.models import Order, OrderItem, ReturnRequest
from django.views.decorators.http import require_POST
from user_side.wallet.refund_utils import process_wallet_refund, process_shipping_refund, calculate_coupon_adjusted_refund
from user_side.wallet.referral_service import process_referral_reward
from decimal import Decimal


def is_admin(user):
    return user.is_authenticated and user.is_staff

@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def admin_order_list(request):

    query=request.GET.get('search', '').strip()
    status_filter=request.GET.get('status', '')
    sort_by=request.GET.get('sort', 'newest')

    orders=Order.objects.select_related('user').all()

    if query:
        orders=orders.filter(Q(order_number__icontains=query) |Q(user__email__icontains=query) |Q(user__username__icontains=query)).distinct()

    if status_filter:
        orders=orders.filter(order_status__iexact=status_filter)

    valid_sorts={
        'newest': '-created_at',
        'oldest':'created_at',
        'amount_high': '-total_amount',
        'amount_low':  'total_amount',
    }

    actual_sort=valid_sorts.get(sort_by, '-created_at')
    orders=orders.order_by(actual_sort)

    total_orders=Order.objects.count()

    aggr=Order.objects.exclude(order_status='Cancelled').aggregate(Sum('total_amount'))

    total_revenue=aggr['total_amount__sum'] or 0

    pending_count=Order.objects.filter(order_status='Pending').count()

    returns_count=OrderItem.objects.filter(item_status__in=['return_requested', 'returned']).count()

    paginator=Paginator(orders, 6)
    page_number=request.GET.get('page')
    page_obj=paginator.get_page(page_number)

    context={
        'orders': page_obj,
        'search_query':   query,
        'current_status': status_filter,
        'current_sort': sort_by,
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'pending_count':  pending_count,
        'returns_count':  returns_count,
    }
    return render(request, 'admin/admin_order_list.html', context)

@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def admin_order_detail(request, order_id):
    order=get_object_or_404(Order.objects.select_related('user', 'shipping_address').prefetch_related('items__variant__product','items__return_requests'),id=order_id)

    for item in order.items.all():
        rrs = item.return_requests.order_by('-id')
        
        item.pending_qty = sum(r.quantity for r in rrs if r.status == 'Pending')
        item.approved_qty = sum(r.quantity for r in rrs if r.status in ('Approved', 'Picked Up'))
        item.rejected_qty = sum(r.quantity for r in rrs if r.status == 'Rejected')
        
        item.latest_pending = next((r for r in rrs if r.status == 'Pending'), None)
        item.latest_approved = next((r for r in rrs if r.status in ('Approved', 'Picked Up')), None)
        item.latest_rejected = next((r for r in rrs if r.status == 'Rejected'), None)

    context={
        'order': order,
    }
    return render(request, 'admin/admin_order_detail.html', context)


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
@require_POST
def update_order_status(request, order_id):
    order=get_object_or_404(Order, id=order_id)
    if order.has_return_request:
        messages.error(request,
            "Order status cannot be changed while a return request is pending. "
            "Please approve or reject the return request first."
        )
        return redirect('admin_order_detail', order_id=order_id)

    new_status=request.POST.get('status', '').strip()
    valid_statuses=dict(Order.ORDER_STATUS_CHOICES).keys()

    if new_status not in valid_statuses:
        messages.error(request, "Invalid status submitted.")
        return redirect('admin_order_detail', order_id=order_id)

    if (
        order.order_status in ['Delivered', 'Cancelled'] and
        new_status != order.order_status
    ):
        messages.error( request, f"Cannot change the status of a {order.order_status.lower()} order." )
        return redirect('admin_order_detail', order_id=order_id)
        
    if order.order_status == 'Shipped' and new_status == 'Pending':
        messages.error(request,"Cannot change the status of a shipped order back to pending.")
        return redirect('admin_order_detail', order_id=order_id)
        
    if order.order_status == 'Out for Delivery' and new_status in ['Pending', 'Shipped']:
        messages.error(request,"Cannot revert status from out for delivery.")
        return redirect('admin_order_detail', order_id=order_id)

    order.order_status=new_status
    order.save()

    item_status_map={
        'Pending':'placed',
        'Shipped':'shipped',
        'Out for Delivery': 'out_for_delivery',
        'Delivered':'delivered',
        'Cancelled':'cancelled',
    }
    mapped=item_status_map.get(new_status)

    if mapped:
        for item in order.items.all():
            if item.item_status in ['returned', 'return_requested', 'cancelled']:
                continue

            if mapped == 'cancelled':
                item.variant.stock += item.quantity
                item.variant.save()

            item.item_status = mapped
            item.save()

            if mapped == 'cancelled':
                process_wallet_refund(
                    order_item  = item,
                    refund_qty  = item.quantity,
                    description = f"Admin cancelled order #{order.order_number} — wallet refund",
                )
    if mapped == 'cancelled':
        process_shipping_refund(
            order       = order,
            description = f"Shipping refund — admin cancelled order #{order.order_number}",
        )

    messages.success(request, f"Order status updated to '{new_status}'.")
    if new_status == 'Delivered':
        rewarded = process_referral_reward(order)
        if rewarded:
            messages.success(
                request,
                "✨ Referral reward credited: ₹50 to buyer, ₹100 to referrer."
            )

    return redirect('admin_order_detail', order_id=order_id)


@login_required(login_url='login')
@require_POST
def create_return_request(request, item_id):
    item=get_object_or_404(OrderItem, id=item_id, order__user=request.user)

    if ReturnRequest.objects.filter(item=item, status='Pending').exists():
        messages.error(request, "A return request for this item is already pending.")
        return redirect('orders_page')

    ReturnRequest.objects.create(
        order=item.order,
        item=item,
        reason=request.POST.get('reason', '').strip(),
        description=request.POST.get('description', '').strip(),
    )

    messages.success(request, "Your return request has been submitted successfully.")
    return redirect('orders_page')


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
@require_POST
def approve_return_request(request, return_id):
    return_req = get_object_or_404(ReturnRequest, id=return_id)

    return_req.status = 'Approved'
    return_req.save()
    return_req.item.variant.stock += return_req.quantity
    return_req.item.variant.save()

    still_pending = return_req.item.return_requests.filter(status='Pending').exists()
    if still_pending:
        return_req.item.item_status = 'return_requested'
    else:
        if return_req.item.returned_quantity + return_req.item.cancelled_quantity >= return_req.item.quantity:
            return_req.item.item_status = 'returned'
        else:
            return_req.item.item_status = 'delivered'
    return_req.item.save(update_fields=['item_status'])

    messages.success(request, f"Return request #{return_req.id} approved. Item marked as returned.")
    return redirect('admin_order_detail', order_id=return_req.order.id)


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
@require_POST
def pickup_return_request(request, return_id):
    return_req=get_object_or_404(ReturnRequest, id=return_id)

    if return_req.status != 'Approved':
        messages.error(request, "Return must be approved before marking as Picked Up.")
        return redirect('admin_order_detail', order_id=return_req.order.id)

    return_req.status='Picked Up'
    return_req.save()

    item = return_req.item
    order= return_req.order

    # Aggregate total returned quantities (Picked Up)
    total_returned_qty = ReturnRequest.objects.filter(
        item=item,
        status='Picked Up'
    ).aggregate(total_returned=Sum('quantity'))['total_returned'] or 0

    new_refund_qty = total_returned_qty - item.refunded_quantity

    if new_refund_qty > 0:
        # Calculate refund for the TOTAL returned quantity
        net_refund_for_total = calculate_coupon_adjusted_refund(order, item.price, total_returned_qty, order_item=item)
        
        # Determine proportional refund for just the newly refunded quantity
        if total_returned_qty > 0:
            refund_amount = (net_refund_for_total * Decimal(str(new_refund_qty)) / Decimal(str(total_returned_qty))).quantize(Decimal('0.01'))
        else:
            refund_amount = Decimal('0.00')

        ok, credited = process_wallet_refund(
            order_item = item,
            refund_qty= new_refund_qty,
            description = f"Return refund — order #{order.order_number} (item picked up, qty {new_refund_qty})",
            override_amount = refund_amount,
        )
        if ok:
            item.refunded_quantity += new_refund_qty
            item.save(update_fields=['refunded_quantity'])
            messages.success(
                request,
                f"Return #{return_req.id} marked as Picked Up. "
                f"₹{credited:.2f} has been credited to the customer's wallet."
            )
        else:
            messages.success(request, f"Return request #{return_req.id} marked as Picked Up (Refund failed or not required).")
    else:
        messages.success(request, f"Return request #{return_req.id} marked as Picked Up. (Already refunded)")

    still_pending = item.return_requests.filter(status='Pending').exists()
    if still_pending:
        item.item_status = 'return_requested'
    else:
        if item.returned_quantity + item.cancelled_quantity >= item.quantity:
            item.item_status = 'returned'
        else:
            item.item_status = 'delivered'
    item.save(update_fields=['item_status'])

    return redirect('admin_order_detail', order_id=return_req.order.id)


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
@require_POST
def reject_return_request(request, return_id):
    return_req=get_object_or_404(ReturnRequest, id=return_id)

    return_req.status='Rejected'
    return_req.save()
    return_req.item.returned_quantity = max(return_req.item.returned_quantity - return_req.quantity, 0)
    
    still_pending = return_req.item.return_requests.filter(status='Pending').exists()
    if still_pending:
        return_req.item.item_status = 'return_requested'
    else:
        if return_req.item.returned_quantity + return_req.item.cancelled_quantity >= return_req.item.quantity:
            return_req.item.item_status = 'returned'
        else:
            return_req.item.item_status = 'delivered'
            
    return_req.item.save(update_fields=['returned_quantity', 'item_status'])

    messages.success(request,f"Return request #{return_req.id} has been rejected.")
    return redirect('admin_order_detail', order_id=return_req.order.id)


@never_cache
@login_required(login_url='login')
@user_passes_test(is_admin, login_url='login')
def admin_returns_list(request):
    query=request.GET.get('search', '').strip()
    returns=ReturnRequest.objects.select_related('order','item__variant__product', 'order__user').order_by('-id')

    if query:
        returns = returns.filter(
            Q(order__order_number__icontains=query) |
            Q(order__user__username__icontains=query) |
            Q(order__user__email__icontains=query) |
            Q(item__variant__product__name__icontains=query)
        ).distinct()

    paginator=Paginator(returns, 5)
    page_number=request.GET.get('page')
    page_obj=paginator.get_page(page_number)

    context={
        'returns': page_obj,
        'search_query': query,
    }
    return render(request, 'admin/admin_returns_list.html', context)