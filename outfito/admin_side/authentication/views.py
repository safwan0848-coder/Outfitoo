from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.views.decorators.cache import never_cache

@never_cache
def admin_login_view(request):

    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin-user-management')

    error = None

    if request.method == "POST":

        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)


        if user is not None and user.is_staff:
            login(request, user)
            return redirect("admin-user-management")
        else:
            error = "Invalid admin credentials"

    return render(request, "admin/admin_login.html", {"error": error})