import json
import razorpay
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import Wallet, WalletTransaction

MIN_TOPUP = Decimal('10')       
MAX_TOPUP = Decimal('50000')     


def _razorpay_client():
    key_id     = settings.RAZORPAY_KEY_ID.strip(' "\'')
    key_secret = settings.RAZORPAY_KEY_SECRET.strip(' "\'')
    return razorpay.Client(auth=(key_id, key_secret))


from django.core.paginator import Paginator

@never_cache
@login_required(login_url='login')
def wallet_view(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions_list = WalletTransaction.objects.filter(user=request.user).order_by('-created_at')
    
    paginator = Paginator(transactions_list, 5)
    page_number = request.GET.get('page')
    transactions = paginator.get_page(page_number)

    context = {
        'wallet':        wallet,
        'transactions':  transactions,
        'razorpay_key':  settings.RAZORPAY_KEY_ID.strip(' "\''),
        'quick_amounts': [100, 200, 500, 1000, 2000, 5000],
    }
    return render(request, 'user/wallet.html', context)


@login_required(login_url='login')
@require_POST
def create_wallet_order(request):
    try:
        data   = json.loads(request.body)
        amount = Decimal(str(data.get('amount', 0)))
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    if amount < MIN_TOPUP:
        return JsonResponse({'success': False, 'message': f'Minimum top-up is ₹{MIN_TOPUP}.'})
    if amount > MAX_TOPUP:
        return JsonResponse({'success': False, 'message': f'Maximum top-up is ₹{MAX_TOPUP}.'})
    try:
        client = _razorpay_client()
        rp_order = client.order.create({
            'amount':   int(amount * 100),   # Convert to paise
            'currency': 'INR',
            'receipt':  f'wallet_{request.user.id}',
            'payment_capture': 1,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'Could not create payment order.'}, status=500)

    request.session['wallet_topup'] = {
        'amount':           str(amount),
        'razorpay_order_id': rp_order['id'],
    }

    return JsonResponse({
        'success':          True,
        'razorpay_order_id': rp_order['id'],
        'amount_paise':     int(amount * 100),
        'razorpay_key':     settings.RAZORPAY_KEY_ID.strip(' "\''),
        'user_email':       request.user.email,
        'user_name':        request.user.username,
    })


@login_required(login_url='login')
@require_POST
def verify_wallet_payment(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    razorpay_order_id   = data.get('razorpay_order_id', '').strip()
    razorpay_payment_id = data.get('razorpay_payment_id', '').strip()
    razorpay_signature  = data.get('razorpay_signature', '').strip()

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({'success': False, 'message': 'Missing payment details.'}, status=400)

    pending = request.session.get('wallet_topup')
    if not pending or pending.get('razorpay_order_id') != razorpay_order_id:
        return JsonResponse({'success': False, 'message': 'Session mismatch. Please try again.'}, status=400)

    amount = Decimal(pending['amount'])

    if WalletTransaction.objects.filter(razorpay_payment_id=razorpay_payment_id).exists():
        return JsonResponse({'success': False, 'message': 'This payment has already been processed.'}, status=409)

    try:
        client = _razorpay_client()
        client.utility.verify_payment_signature({
            'razorpay_order_id':   razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        return JsonResponse({'success': False, 'message': 'Payment verification failed. Signature invalid.'}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Payment verification error.'}, status=500)

    try:
        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=request.user)
            wallet.balance += amount
            wallet.save(update_fields=['balance', 'updated_at'])

            WalletTransaction.objects.create(
                user                 = request.user,
                transaction_type     = 'credit',
                amount               = amount,
                balance_after        = wallet.balance,
                is_credit            = True,
                razorpay_payment_id  = razorpay_payment_id,
                razorpay_order_id    = razorpay_order_id,
                payment_status       = 'success',
                description          = f'Wallet top-up via Razorpay',
            )
    except Exception:
        return JsonResponse({'success': False, 'message': 'Failed to credit wallet. Please contact support.'}, status=500)

    request.session.pop('wallet_topup', None)

    return JsonResponse({
        'success':     True,
        'message':     f'₹{amount:.0f} added to your wallet successfully!',
        'new_balance': str(wallet.balance),
    })
