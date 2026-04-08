from .models import Wishlist, WishlistItem

def wishlist_count(request):
    if request.user.is_authenticated:
        wishlist = Wishlist.objects.filter(user=request.user).first()
        if wishlist:
            count = WishlistItem.objects.filter(wishlist=wishlist).count()
        else:
            count = 0
    else:
        count = 0

    return {'wishlist_count': count}