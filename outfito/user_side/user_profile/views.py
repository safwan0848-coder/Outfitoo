from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Profile
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from .forms import ChangePasswordForm
from django.http import HttpResponse
from django.contrib.auth import logout
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from user_side.authentication.models import OTP
from django.conf import settings
from django.contrib.auth.hashers import make_password
User = get_user_model()
from django.utils import timezone

@login_required
def profile(request):

    profile, created = Profile.objects.get_or_create(user=request.user)

    context = {
        "user": request.user,
        "profile": profile
    }

    return render(request, "user/profile.html", context)



@login_required
def edit_profile(request):

    profile, created = Profile.objects.get_or_create(user=request.user)

    error = ""

    if request.method == "POST":

        username = request.POST.get("username")
        email = request.POST.get("email")
        phone = request.POST.get("phone")

        if not username or not email:
            error = "Username and Email required"

        else:

            request.user.username = username
            request.user.email = email
            request.user.save()

            profile.phone = phone

            if request.FILES.get("profile_image"):
                profile.profile_image = request.FILES.get("profile_image")

            profile.save()

            return redirect("profile")

    context = {
        "user": request.user,
        "profile": profile,
        "error": error
    }

    return render(request, "user/edit_profile.html", context)


def logout_view(request):
   logout(request)
   return redirect('landing')

def address(request):
    return HttpResponse('address')
def wallet(request):
    return HttpResponse('wallet')
def orders(request):
    return HttpResponse('orders')
def wishlist(request):
    return HttpResponse('wishlist')


@login_required
def change_password(request):
    if request.method == "POST":
        form = ChangePasswordForm(request.user, request.POST)

        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password updated successfully!")
            return redirect("profile")
    else:
        form = ChangePasswordForm(request.user)

    return render(request, "user/change_password.html", {"form": form})


@login_required
def start_password_reset(request):
    # 1. Set the email in the session
    request.session['reset_email'] = request.user.email
    
    # 2. Force Django to save the session immediately
    request.session.modified = True 

    user = request.user

    # 3. Clear old OTPs and generate a new one
    OTP.objects.filter(user=user).delete()
    otp = OTP.objects.create(user=user)

    # 4. Send the email
    send_mail(
        subject="Password Reset OTP",
        message=f"Your OTP is {otp.code}",
        from_email="outfito0848@gmail.com",
        recipient_list=[user.email],
        fail_silently=False,
    )

    return redirect("profile-reset-verify")


def profile_reset_verify(request):
    # Retrieve the email from the session
    email = request.session.get('reset_email')

    if not email:
        messages.error(request, "Session expired. Please start the reset process again.")
        return redirect('change-password')

    user = User.objects.filter(email=email).first()
    otp = OTP.objects.filter(user=user).last()

    remaining_seconds = 0
    if otp:
        remaining_seconds = int((otp.expired_at - timezone.now()).total_seconds())
        if remaining_seconds < 0:
            remaining_seconds = 0

    if request.method == "POST":
        code = request.POST.get("otp")

        if not otp:
            messages.error(request, "OTP not found. Please request a new one.")
            return redirect('profile-reset-verify')

        if otp.is_expired():
            otp.delete()
            messages.error(request, "OTP has expired. Please request a new one.")
            return redirect('profile-reset-verify')

        # Convert both to strings just in case one is an int and one is a str
        if str(otp.code) != str(code): 
            messages.error(request, "Invalid OTP. Please try again.")
            return redirect('profile-reset-verify')

        # OTP is correct
        otp.delete()
        request.session['otp_verified'] = True
        request.session.modified = True  # Force session save before redirecting

        return redirect('profile-set-new-password')

    return render(request, 'user/profile_reset_verify.html', {
        "email": email,
        "remaining_seconds": remaining_seconds
    })

from django.contrib.auth import login
def profile_set_new_password(request):

    email = request.session.get('reset_email')
    verified = request.session.get('otp_verified')

    if not email or not verified:
        messages.error(request, "Unauthorized access. Please verify OTP first.")
        return redirect('change-password')

    if request.method == "POST":

        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect('profile-set-new-password')

        user = User.objects.filter(email=email).first()

        if not user:
            messages.error(request, "User not found.")
            return redirect('change-password')

        # set new password
        user.set_password(password1)
        user.save()

        # login user again (SPECIFY BACKEND)
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        # clear session
        request.session.pop('reset_email', None)
        request.session.pop('otp_verified', None)

        messages.success(request, "Password reset successful!")

        return redirect('profile')

    return render(request, "user/profile_set_new_password.html")