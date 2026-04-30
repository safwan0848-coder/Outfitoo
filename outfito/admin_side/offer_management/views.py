from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Offer
from admin_side.products_management.models import Product
from admin_side.categories_management.models import Category
from datetime import datetime
import traceback

def offer_list(request):
    search_query = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')

    offers = Offer.objects.all().order_by('-created_at')

    if search_query:
        offers = offers.filter(offer_name__icontains=search_query)
    
    if type_filter:
        offers = offers.filter(apply_to=type_filter)
        
    if status_filter:
        if status_filter == 'active':
            offers = offers.filter(is_active=True)
        elif status_filter == 'inactive':
            offers = offers.filter(is_active=False)

    paginator = Paginator(offers, 4)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'offers': page_obj,
        'search_query': search_query,
        'type_filter': type_filter,
        'status_filter': status_filter,
    }
    return render(request, 'admin/offer_list.html', context)

def add_offer(request):
    products = Product.objects.filter(is_deleted=False)
    categories = Category.objects.filter(is_deleted=False)
    today = datetime.now().date()

    if request.method == 'POST':
        offer_name= request.POST.get('offer_name', '').strip()
        discount_type  = request.POST.get('discount_type', '').strip()
        apply_to  = request.POST.get('apply_to', '').strip()
        discount_value = request.POST.get('discount_value', '').strip()
        min_purchase = request.POST.get('minimum_purchase_amount') or 0
        max_discount = request.POST.get('maximum_discount_amount') or None
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        product_id = request.POST.get('product_id')
        category_id = request.POST.get('category_id')
        ctx = {
            'products': products, 'categories': categories,
            'post': request.POST,
        }
        def fail(msg):
            messages.error(request, msg)
            return render(request, 'admin/add_offer.html', ctx)

        if not offer_name:
            return fail('Offer name is required.')

        if discount_type not in ('percentage', 'flat'):
            return fail('Please select a valid discount type.')
        try:
            discount_value = float(discount_value)
            if discount_value <= 0:
                return fail('Discount value must be greater than 0.')
            if discount_type == 'percentage' and discount_value > 100:
                return fail('Percentage discount cannot exceed 100%.')
        except (ValueError, TypeError):
            return fail('Enter a valid discount value.')

        try:
            min_purchase = float(min_purchase)
            if min_purchase < 0:
                return fail('Minimum purchase amount cannot be negative.')
        except (ValueError, TypeError):
            return fail('Enter a valid minimum purchase amount.')

        if max_discount:
            try:
                max_discount = float(max_discount)
                if max_discount <= 0:
                    return fail('Maximum discount must be greater than 0.')
                if discount_type == 'flat':
                    return fail('Maximum discount cap is only valid for percentage offers.')
            except (ValueError, TypeError):
                return fail('Enter a valid maximum discount amount.')
        else:
            max_discount = None

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date   = datetime.strptime(end_date_str,   '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return fail('Invalid date format. Use YYYY-MM-DD.')

        if start_date < today:
            return fail('Start date cannot be in the past.')
        if end_date <= start_date:
            return fail('End date must be strictly after the start date.')

        product  = None
        category = None
        if apply_to == 'product':
            if not product_id:
                return fail('Please select a product.')
            product = get_object_or_404(Product, id=product_id)
            if is_active and Offer.objects.filter(
                apply_to='product', product=product, is_active=True
            ).exists():
                return fail('An active offer already exists for this product. Deactivate it first.')
        elif apply_to == 'category':
            if not category_id:
                return fail('Please select a category.')
            category = get_object_or_404(Category, id=category_id)
            if is_active and Offer.objects.filter(
                apply_to='category', category=category, is_active=True
            ).exists():
                return fail('An active offer already exists for this category. Deactivate it first.')
        else:
            return fail('Please select a valid target (Product or Category).')

        Offer.objects.create(
            offer_name=offer_name,
            discount_type=discount_type,
            apply_to=apply_to,
            product=product,
            category=category,
            discount_value=discount_value,
            minimum_purchase_amount=min_purchase,
            maximum_discount_amount=max_discount if discount_type == 'percentage' else None,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active,
        )
        messages.success(request, f'Offer "{offer_name}" created successfully.')
        return redirect('offer_list')

    return render(request, 'admin/add_offer.html', {
        'products':   products,
        'categories': categories,
    })

def edit_offer(request, pk):
    offer= get_object_or_404(Offer, pk=pk)
    products = Product.objects.filter(is_deleted=False)
    categories = Category.objects.filter(is_deleted=False)

    if request.method == 'POST':
        offer_name = request.POST.get('offer_name', '').strip()
        discount_type = request.POST.get('discount_type', '').strip()
        apply_to = request.POST.get('apply_to', '').strip()
        discount_value = request.POST.get('discount_value', '').strip()
        min_purchase = request.POST.get('minimum_purchase_amount') or 0
        max_discount = request.POST.get('maximum_discount_amount') or None
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        product_id = request.POST.get('product_id')
        category_id = request.POST.get('category_id')
        ctx = {
            'offer': offer, 'products': products, 'categories': categories,
            'post': request.POST,
            'start_date_formatted': start_date_str,
            'end_date_formatted':   end_date_str,
        }
        def fail(msg):
            messages.error(request, msg)
            return render(request, 'admin/edit_offer.html', ctx)

        if not offer_name:
            return fail('Offer name is required.')

        if discount_type not in ('percentage', 'flat'):
            return fail('Please select a valid discount type.')
        try:
            discount_value = float(discount_value)
            if discount_value <= 0:
                return fail('Discount value must be greater than 0.')
            if discount_type == 'percentage' and discount_value > 100:
                return fail('Percentage discount cannot exceed 100%.')
        except (ValueError, TypeError):
            return fail('Enter a valid discount value.')

        try:
            min_purchase = float(min_purchase)
            if min_purchase < 0:
                return fail('Minimum purchase amount cannot be negative.')
        except (ValueError, TypeError):
            return fail('Enter a valid minimum purchase amount.')

        if max_discount:
            try:
                max_discount = float(max_discount)
                if max_discount <= 0:
                    return fail('Maximum discount must be greater than 0.')
                if discount_type == 'flat':
                    return fail('Maximum discount cap is only valid for percentage offers.')
            except (ValueError, TypeError):
                return fail('Enter a valid maximum discount amount.')
        else:
            max_discount = None

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date   = datetime.strptime(end_date_str,   '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return fail('Invalid date format. Use YYYY-MM-DD.')

        if end_date <= start_date:
            return fail('End date must be strictly after the start date.')

        product  = None
        category = None
        if apply_to == 'product':
            if not product_id:
                return fail('Please select a product.')
            product = get_object_or_404(Product, id=product_id)
            if is_active and Offer.objects.filter(
                apply_to='product', product=product, is_active=True
            ).exclude(pk=offer.pk).exists():
                return fail('An active offer already exists for this product. Deactivate it first.')
        elif apply_to == 'category':
            if not category_id:
                return fail('Please select a category.')
            category = get_object_or_404(Category, id=category_id)
            if is_active and Offer.objects.filter(
                apply_to='category', category=category, is_active=True
            ).exclude(pk=offer.pk).exists():
                return fail('An active offer already exists for this category. Deactivate it first.')
        else:
            return fail('Please select a valid target (Product or Category).')

        offer.offer_name  = offer_name
        offer.discount_type = discount_type
        offer.apply_to= apply_to
        offer.product = product
        offer.category = category
        offer.discount_value = discount_value
        offer.minimum_purchase_amount = min_purchase
        offer.maximum_discount_amount = max_discount if discount_type == 'percentage' else None
        offer.start_date = start_date
        offer.end_date = end_date
        offer.is_active = is_active
        offer.save()
        messages.success(request, f'Offer "{offer_name}" updated successfully.')
        return redirect('offer_list')

    return render(request, 'admin/edit_offer.html', {
        'offer':offer,
        'products':products,
        'categories': categories,
        'start_date_formatted': offer.start_date.strftime('%Y-%m-%d') if offer.start_date else '',
        'end_date_formatted':   offer.end_date.strftime('%Y-%m-%d')   if offer.end_date   else '',
    })

def delete_offer(request, pk):
    if request.method == 'POST':
        offer = get_object_or_404(Offer, pk=pk)
        offer.delete()
        messages.success(request, 'Offer deleted successfully.')
    return redirect('offer_list')

def toggle_offer_status(request, pk):
    if request.method == 'POST':
        offer = get_object_or_404(Offer, pk=pk)
        import json
        try:
            data = json.loads(request.body)
            new_status = data.get('is_active')
        except json.JSONDecodeError:
            new_status = request.POST.get('is_active') == 'true'

        if new_status:
            if offer.apply_to == 'product' and offer.product:
                if Offer.objects.filter(apply_to='product', product=offer.product, is_active=True).exclude(pk=offer.pk).exists():
                    return JsonResponse({'success': False, 'error': 'An active offer already exists for this product.'})
            elif offer.apply_to == 'category' and offer.category:
                if Offer.objects.filter(apply_to='category', category=offer.category, is_active=True).exclude(pk=offer.pk).exists():
                    return JsonResponse({'success': False, 'error': 'An active offer already exists for this category.'})
        
        offer.is_active = new_status
        offer.save()
        return JsonResponse({'success': True, 'is_active': offer.is_active})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
