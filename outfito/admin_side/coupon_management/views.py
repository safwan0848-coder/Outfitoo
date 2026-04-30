from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils import timezone

from .models import Coupon
from .forms import CouponForm

def coupon_list(request):
    search_query = request.GET.get('search', '').strip()
    coupons_qs = Coupon.objects.all().order_by('-created_at')
    if search_query:
        coupons_qs = coupons_qs.filter(
            Q(code__icontains=search_query) |
            Q(discount_type__icontains=search_query)
        )
    total_coupons = Coupon.objects.count()
    active_coupons = Coupon.objects.filter(is_active=True).count()
    active_rate = int((active_coupons / total_coupons) * 100) if total_coupons > 0 else 0
    total_uses = Coupon.objects.aggregate(Sum('used_count'))['used_count__sum'] or 0
    paginator = Paginator(coupons_qs, 4)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'admin/coupon_list.html', {
        'coupons': page_obj,
        'search_query': search_query,
        'total_coupons':  total_coupons,
        'active_coupons': active_coupons,
        'active_rate':active_rate,
        'total_uses':total_uses,
        'savings_given':  0,
    })

def add_coupon(request):
    form = CouponForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            coupon = form.save(commit=False)
            coupon.code = coupon.code.upper()
            coupon.save()
            messages.success(request, f'Coupon "{coupon.code}" created successfully.')
            return redirect('coupon_list')
        else:
            for field, errs in form.errors.items():
                label = form.fields[field].label if field in form.fields else field.replace('_', ' ').title()
                for err in errs:
                    messages.error(request, f"{label}: {err}")

    return render(request, 'admin/add_coupon.html', {'form': form})

def edit_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    form   = CouponForm(request.POST or None, instance=coupon)
    if request.method == 'POST':
        if form.is_valid():
            updated = form.save(commit=False)
            updated.code = updated.code.upper()
            updated.save()
            messages.success(request, f'Coupon "{updated.code}" updated successfully.')
            return redirect('coupon_list')
        else:
            for field, errs in form.errors.items():
                label = form.fields[field].label if field in form.fields else field.replace('_', ' ').title()
                for err in errs:
                    messages.error(request, f"{label}: {err}")

    return render(request, 'admin/edit_coupon.html', {'form': form, 'coupon': coupon})


def delete_coupon(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(request, f'Coupon "{code}" deleted successfully.')
    return redirect('coupon_list')