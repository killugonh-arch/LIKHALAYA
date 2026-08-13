from store.models import Category, ContactMessage
from orders.models import Order
from orders.cart import Cart


def global_context(request):
    nav_categories = Category.objects.filter(is_active=True).order_by('order', 'name')[:10]
    cart = Cart(request)
    cart_count = cart.product_count()

    new_orders_count = 0
    new_messages_count = 0

    if request.user.is_authenticated and hasattr(request.user, 'is_staff_user') and request.user.is_staff_user():
        new_orders_count = Order.objects.filter(status='pending').count()
        new_messages_count = ContactMessage.objects.filter(is_read=False).count()

    return {
        'nav_categories': nav_categories,
        'cart_count': cart_count,
        'new_orders_count': new_orders_count,
        'new_messages_count': new_messages_count,
    }