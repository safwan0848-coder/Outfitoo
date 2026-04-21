from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Coupon

from django.db.models import Sum

def coupon_list(request):
    coupons = Coupon.objects.all().order_by('-created_at')
    
    total_coupons = coupons.count()
    active_coupons = coupons.filter(is_active=True).count()
    active_rate = int((active_coupons / total_coupons) * 100) if total_coupons > 0 else 0
    total_uses = coupons.aggregate(Sum('used_count'))['used_count__sum'] or 0
    savings_given = 0 # Placeholder until linked with Order models mapping real discount subtractions
    
    context = {
        'coupons': coupons,
        'total_coupons': total_coupons,
        'active_coupons': active_coupons,
        'active_rate': active_rate,
        'total_uses': total_uses,
        'savings_given': savings_given
    }
    return render(request, 'admin/coupon_list.html', context)

def add_coupon(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        discount_type = request.POST.get('discount_type')
        discount_value = request.POST.get('discount_value')
        
        min_amount = request.POST.get('min_amount') or 0
        max_discount = request.POST.get('max_discount') or None
        
        usage_limit = request.POST.get('usage_limit') or None
        usage_limit_per_user = request.POST.get('usage_limit_per_user') or 1
        
        start_date = request.POST.get('start_date') or None
        expiry_date = request.POST.get('expiry_date')
        
        is_active = request.POST.get('is_active') == 'on'
        
        if Coupon.objects.filter(code__iexact=code).exists():
            messages.error(request, 'Coupon with this code already exists.')
            return redirect('add_coupon')
            
        Coupon.objects.create(
            code=code.upper(),
            discount_type=discount_type,
            discount_value=discount_value,
            min_amount=min_amount,
            max_discount=max_discount,
            usage_limit=usage_limit,
            usage_limit_per_user=usage_limit_per_user,
            start_date=start_date,
            expiry_date=expiry_date,
            is_active=is_active
        )
        messages.success(request, 'Coupon created successfully.')
        return redirect('coupon_list')

    return render(request, 'admin/add_coupon.html')

def edit_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    
    if request.method == 'POST':
        coupon.code = request.POST.get('code').upper()
        coupon.discount_type = request.POST.get('discount_type')
        coupon.discount_value = request.POST.get('discount_value')
        
        coupon.min_amount = request.POST.get('min_amount') or 0
        coupon.max_discount = request.POST.get('max_discount') or None
        
        coupon.usage_limit = request.POST.get('usage_limit') or None
        coupon.usage_limit_per_user = request.POST.get('usage_limit_per_user') or 1
        
        coupon.start_date = request.POST.get('start_date') or None
        coupon.expiry_date = request.POST.get('expiry_date')
        
        coupon.is_active = request.POST.get('is_active') == 'on'
        
        if Coupon.objects.filter(code__iexact=coupon.code).exclude(pk=coupon.pk).exists():
            messages.error(request, 'Another coupon with this code already exists.')
            return redirect('edit_coupon', pk=coupon.pk)
            
        coupon.save()
        messages.success(request, 'Coupon updated successfully.')
        return redirect('coupon_list')

    return render(request, 'admin/edit_coupon.html', {'coupon': coupon})

def delete_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    coupon.delete()
    messages.success(request, 'Coupon deleted successfully.')
    return redirect('coupon_list')