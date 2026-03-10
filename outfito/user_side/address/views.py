from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Address
from django.contrib import messages

@login_required
def address_list(request):

    addresses = Address.objects.filter(user=request.user)

    return render(request, "user/address.html", {
        "addresses": addresses
    })



@login_required
def add_address(request):

    if request.method == "POST":

        full_name = request.POST.get("full_name")
        phone = request.POST.get("phone")
        line1 = request.POST.get("line1")
        line2 = request.POST.get("line2") or ""
        city = request.POST.get("city")
        state = request.POST.get("state")
        pincode = request.POST.get("pincode")
        country = request.POST.get("country")
        address_type = request.POST.get("type")   # important
        is_default = request.POST.get("is_default")

        # if user selects default remove old default
        if is_default:
            Address.objects.filter(user=request.user, is_default=True).update(is_default=False)

        Address.objects.create(
            user=request.user,
            full_name=full_name,
            phone_number=phone,
            address_line1=line1,
            address_line2=line2,
            city=city,
            state=state,
            pincode=pincode,
            country=country,
            type=address_type,   # important
            is_default=True if is_default else False
        )

        return redirect("address-list")

    return render(request, "user/add_address.html")


@login_required
def edit_address(request, id):

    address = get_object_or_404(Address, id=id, user=request.user)

    if request.method == "POST":

        address.full_name = request.POST.get("full_name")
        address.phone_number = request.POST.get("phone")
        address.address_line1 = request.POST.get("line1")
        address.address_line2 = request.POST.get("line2") or ""
        address.city = request.POST.get("city")
        address.state = request.POST.get("state")
        address.pincode = request.POST.get("pincode")
        address.country = request.POST.get("country")
        address.type = request.POST.get("type")

        is_default = request.POST.get("is_default")

        if is_default:
            Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
            address.is_default = True
        else:
            address.is_default = False

        address.save()

        return redirect("address-list")

    return render(request, "user/edit_address.html", {"address": address})

@login_required
def set_default_address(request, id):

    address = get_object_or_404(Address, id=id, user=request.user)

    # remove old default
    Address.objects.filter(user=request.user, is_default=True).update(is_default=False)

    # set new default
    address.is_default = True
    address.save()

    return redirect("address-list")

@login_required
def delete_address(request, id):

    address = get_object_or_404(Address, id=id, user=request.user)

    if request.method == "POST":
        address.delete()
        messages.success(request, "Address deleted successfully")
        return redirect("address-list")

    return redirect("address-list")