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

    # Pagination: 10 offers per page
    paginator = Paginator(offers, 10)
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

    if request.method == 'POST':
        offer_name = request.POST.get('offer_name')
        discount_type = request.POST.get('discount_type')
        apply_to = request.POST.get('apply_to')
        discount_value = request.POST.get('discount_value')
        minimum_purchase_amount = request.POST.get('minimum_purchase_amount') or 0
        maximum_discount_amount = request.POST.get('maximum_discount_amount') or None
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        is_active = request.POST.get('is_active') == 'on'

        product_id = request.POST.get('product_id')
        category_id = request.POST.get('category_id')

        # Validation
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date format.')
            return redirect('add_offer')

        if end_date < start_date:
            messages.error(request, 'End date cannot be before start date.')
            return redirect('add_offer')

        try:
            if float(discount_value) <= 0:
                messages.error(request, 'Discount value must be greater than 0.')
                return redirect('add_offer')
        except ValueError:
            messages.error(request, 'Invalid discount value.')
            return redirect('add_offer')

        product = None
        category = None

        if apply_to == 'product':
            if not product_id:
                messages.error(request, 'Please select a product.')
                return redirect('add_offer')
            product = get_object_or_404(Product, id=product_id)
            if is_active and Offer.objects.filter(apply_to='product', product=product, is_active=True).exists():
                messages.error(request, 'An active offer already exists for this product. Deactivate it first.')
                return redirect('add_offer')
        elif apply_to == 'category':
            if not category_id:
                messages.error(request, 'Please select a category.')
                return redirect('add_offer')
            category = get_object_or_404(Category, id=category_id)
            if is_active and Offer.objects.filter(apply_to='category', category=category, is_active=True).exists():
                messages.error(request, 'An active offer already exists for this category. Deactivate it first.')
                return redirect('add_offer')

        Offer.objects.create(
            offer_name=offer_name,
            discount_type=discount_type,
            apply_to=apply_to,
            product=product,
            category=category,
            discount_value=discount_value,
            minimum_purchase_amount=minimum_purchase_amount,
            maximum_discount_amount=maximum_discount_amount if discount_type == 'percentage' else None,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        messages.success(request, 'Offer created successfully.')
        return redirect('offer_list')

    return render(request, 'admin/add_offer.html', {
        'products': products,
        'categories': categories
    })

def edit_offer(request, pk):
    offer = get_object_or_404(Offer, pk=pk)
    products = Product.objects.filter(is_deleted=False)
    categories = Category.objects.filter(is_deleted=False)

    if request.method == 'POST':
        offer.offer_name = request.POST.get('offer_name')
        offer.discount_type = request.POST.get('discount_type')
        offer.apply_to = request.POST.get('apply_to')
        offer.discount_value = request.POST.get('discount_value')
        offer.minimum_purchase_amount = request.POST.get('minimum_purchase_amount') or 0
        offer.maximum_discount_amount = request.POST.get('maximum_discount_amount') or None
        
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        offer.is_active = request.POST.get('is_active') == 'on'

        product_id = request.POST.get('product_id')
        category_id = request.POST.get('category_id')

        try:
            offer.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            offer.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            messages.error(request, 'Invalid date format.')
            return redirect('edit_offer', pk=offer.pk)

        if offer.end_date < offer.start_date:
            messages.error(request, 'End date cannot be before start date.')
            return redirect('edit_offer', pk=offer.pk)

        try:
            if float(offer.discount_value) <= 0:
                messages.error(request, 'Discount value must be greater than 0.')
                return redirect('edit_offer', pk=offer.pk)
        except ValueError:
            messages.error(request, 'Invalid discount value.')
            return redirect('edit_offer', pk=offer.pk)

        offer.product = None
        offer.category = None

        if offer.apply_to == 'product':
            if not product_id:
                messages.error(request, 'Please select a product.')
                return redirect('edit_offer', pk=offer.pk)
            offer.product = get_object_or_404(Product, id=product_id)
            if offer.is_active and Offer.objects.filter(apply_to='product', product=offer.product, is_active=True).exclude(pk=offer.pk).exists():
                messages.error(request, 'An active offer already exists for this product. Deactivate it first.')
                return redirect('edit_offer', pk=offer.pk)
        elif offer.apply_to == 'category':
            if not category_id:
                messages.error(request, 'Please select a category.')
                return redirect('edit_offer', pk=offer.pk)
            offer.category = get_object_or_404(Category, id=category_id)
            if offer.is_active and Offer.objects.filter(apply_to='category', category=offer.category, is_active=True).exclude(pk=offer.pk).exists():
                messages.error(request, 'An active offer already exists for this category. Deactivate it first.')
                return redirect('edit_offer', pk=offer.pk)

        if offer.discount_type == 'flat':
            offer.maximum_discount_amount = None

        offer.save()
        messages.success(request, 'Offer updated successfully.')
        return redirect('offer_list')

    return render(request, 'admin/edit_offer.html', {
        'offer': offer,
        'products': products,
        'categories': categories,
        'start_date_formatted': offer.start_date.strftime('%Y-%m-%d') if offer.start_date else '',
        'end_date_formatted': offer.end_date.strftime('%Y-%m-%d') if offer.end_date else '',
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
        
        # Determine new status from request, handling both JSON and form data
        import json
        try:
            data = json.loads(request.body)
            new_status = data.get('is_active')
        except json.JSONDecodeError:
            new_status = request.POST.get('is_active') == 'true'

        # Validation before toggling to active
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
