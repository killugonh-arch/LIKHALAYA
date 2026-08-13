from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST
from store.models import Product
from .cart import Cart, calculate_shipping_fee
from .forms import CheckoutForm
from .models import Order, OrderItem

# Session key holding the shipping/contact info the customer entered on the
# checkout form while they're still on the GCash payment step. No Order row
# exists yet at this point.
GCASH_DRAFT_SESSION_KEY = 'gcash_checkout_draft'


def _create_order(request, cart, selected_ids, payment_method, form_data, extra=None):
    """Create the Order + OrderItems, deduct stock, and clear the cart for
    the given selected items. Shared by the COD path (checkout) and the
    GCash path (after a valid receipt is uploaded)."""
    selected_items = list(cart.iter_selected(selected_ids))
    subtotal = cart.total_price_for(selected_ids)
    shipping_fee = calculate_shipping_fee(subtotal)
    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        full_name=form_data.get('full_name', ''),
        email=form_data.get('email', ''),
        phone=form_data.get('phone', ''),
        address=form_data.get('address', ''),
        city=form_data.get('city', ''),
        province=form_data.get('province', ''),
        zip_code=form_data.get('zip_code', ''),
        notes=form_data.get('notes', ''),
        payment_method=payment_method,
        subtotal=subtotal,
        shipping_fee=shipping_fee,
        total=subtotal + shipping_fee,
        **(extra or {}),
    )
    for item in selected_items:
        OrderItem.objects.create(
            order=order,
            product=item['product'],
            product_name=item['name'],
            product_price=item['price'],
            size=item.get('size', ''),
            quantity=item['quantity'],
        )
        p = item['product']
        p.stock = max(0, p.stock - item['quantity'])
        p.save()
    cart.remove_many(selected_ids)
    request.session.pop('checkout_selected_ids', None)
    return order


@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id, is_active=True)
    buy_now = bool(request.POST.get('buy_now'))

    if buy_now and not request.user.is_authenticated:
        messages.info(request, 'Please create an account to use Buy Now.')
        register_url = reverse('accounts:register')
        return redirect(f'{register_url}?next={product.get_absolute_url()}')

    if buy_now and request.user.is_authenticated and (not request.user.phone or not request.user.address or not request.user.city or not request.user.province):
        messages.warning(request, 'Please add your phone number and complete address to your profile before checking out.')
        profile_url = reverse('accounts:profile')
        return redirect(f'{profile_url}?next={product.get_absolute_url()}')

    quantity = int(request.POST.get('quantity', 1))
    override = request.POST.get('override', False)
    size = request.POST.get('size', '').upper()
    if size not in dict(Product.SIZE_CHOICES):
        size = None
    cart.add(product=product, quantity=quantity, override_quantity=bool(override), size=size)

    if buy_now:
        request.session['checkout_selected_ids'] = [cart.make_key(product.id, size)]
        request.session.modified = True
        return redirect('orders:checkout')

    messages.success(request, f'"{product.name}" added to cart!')
    referer = request.META.get('HTTP_REFERER', '')
    return redirect(referer if referer else 'store:home')


@require_POST
def cart_update(request, item_key):
    cart = Cart(request)
    line = cart.cart.get(item_key)
    if not line:
        return redirect(request.META.get('HTTP_REFERER') or 'orders:cart_detail')
    product = get_object_or_404(Product, id=line['product_id'])
    action = request.POST.get('action', 'increase')
    current_qty = cart.get_quantity(item_key)
    size = line.get('size') or None
    if action == 'increase':
        cart.add(product=product, quantity=1, override_quantity=False, size=size)
    elif action == 'decrease' and current_qty > 1:
        cart.add(product=product, quantity=current_qty - 1, override_quantity=True, size=size)
    referer = request.META.get('HTTP_REFERER', '')
    return redirect(referer if referer else 'orders:cart_detail')


@require_POST
def cart_remove(request, item_key):
    cart = Cart(request)
    cart.remove(item_key)
    messages.info(request, 'Item removed from cart.')
    referer = request.META.get('HTTP_REFERER', '')
    return redirect(referer if referer else 'orders:cart_detail')


def cart_detail(request):
    cart = Cart(request)
    cart_total = cart.get_total_price()
    shipping_fee = calculate_shipping_fee(cart_total)
    amount_for_free_shipping = max(0, 500 - cart_total)
    return render(request, 'orders/cart.html', {
        'cart': cart,
        'cart_items': list(cart),
        'cart_total': cart_total,
        'shipping_fee': shipping_fee,
        'amount_for_free_shipping': amount_for_free_shipping,
    })


@require_POST
def checkout_select(request):
    cart = Cart(request)
    selected_ids = request.POST.getlist('selected_items')
    if not selected_ids:
        messages.warning(request, 'Please select at least one item to checkout.')
        return redirect('orders:cart_detail')

    if not request.user.is_authenticated:
        messages.info(request, 'Please create an account to checkout.')
        register_url = reverse('accounts:register')
        return redirect(f'{register_url}?next={reverse("orders:cart_detail")}')

    request.session['checkout_selected_ids'] = selected_ids
    request.session.modified = True
    return redirect('orders:checkout')


@cache_control(no_store=True, no_cache=True, must_revalidate=True)
def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, 'Your cart is empty.')
        return redirect('store:shop')

    if not request.user.is_authenticated:
        messages.info(request, 'Please create an account to checkout.')
        register_url = reverse('accounts:register')
        return redirect(f'{register_url}?next={reverse("orders:cart_detail")}')

    all_ids = [str(pid) for pid in cart.cart.keys()]
    selected_ids = request.session.get('checkout_selected_ids') or all_ids
    selected_ids = [pid for pid in selected_ids if pid in all_ids] or all_ids

    if request.user.is_authenticated and (not request.user.phone or not request.user.address or not request.user.city or not request.user.province):
        messages.warning(request, 'Please add your phone number and complete address to your profile before checking out.')
        profile_url = reverse('accounts:profile')
        return redirect(f'{profile_url}?next={reverse("orders:cart_detail")}')

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', 'cod')
        form_data = {
            'full_name': request.POST.get('full_name', ''),
            'email': request.POST.get('email', ''),
            'phone': request.POST.get('phone', ''),
            'address': request.POST.get('address', ''),
            'city': request.POST.get('city', ''),
            'province': request.POST.get('province', ''),
            'zip_code': request.POST.get('zip_code', ''),
            'notes': request.POST.get('notes', ''),
        }

        if payment_method == 'gcash':
            # Don't create the order yet — just remember what the customer
            # entered. The order is only created once they actually send a
            # valid GCash receipt, so backing out here leaves no trace in
            # "My Orders".
            request.session[GCASH_DRAFT_SESSION_KEY] = {
                'form_data': form_data,
                'selected_ids': selected_ids,
            }
            request.session.modified = True
            return redirect('orders:gcash_payment_pending')

        order = _create_order(request, cart, selected_ids, 'cod', form_data)
        messages.success(request, f'Order {order.order_number} placed! Thank you for supporting PDL artisans.')
        return redirect('orders:order_confirmation', pk=order.pk)

    cart_total = cart.total_price_for(selected_ids)
    shipping_fee = calculate_shipping_fee(cart_total)
    return render(request, 'orders/checkout.html', {
        'cart': cart.iter_selected(selected_ids),
        'cart_total': cart_total,
        'shipping_fee': shipping_fee,
        'grand_total': cart_total + shipping_fee,
    })


@cache_control(no_store=True, no_cache=True, must_revalidate=True)
def gcash_payment_pending(request):
    """Step 2 of the GCash flow, before an Order exists. Shows the QR code
    and amount for the draft the customer entered at checkout; only creates
    the real Order once a valid receipt screenshot is uploaded."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    draft = request.session.get(GCASH_DRAFT_SESSION_KEY)
    if not draft:
        messages.info(request, 'Please fill in your order details first.')
        return redirect('orders:checkout')

    cart = Cart(request)
    all_ids = [str(pid) for pid in cart.cart.keys()]
    selected_ids = [pid for pid in draft['selected_ids'] if pid in all_ids]
    if not selected_ids:
        messages.warning(request, 'Your cart changed since you started checkout. Please review your order again.')
        request.session.pop(GCASH_DRAFT_SESSION_KEY, None)
        return redirect('orders:checkout')

    cart_total = cart.total_price_for(selected_ids)
    shipping_fee = calculate_shipping_fee(cart_total)
    draft_total = cart_total + shipping_fee

    MIN_PROOF_SIZE = 100 * 1024   # 100 KB
    MAX_PROOF_SIZE = 500 * 1024   # 500 KB

    if request.method == 'POST':
        proof = request.FILES.get('payment_proof')
        if not proof:
            messages.error(request, 'Please attach a screenshot of your GCash payment before sending.')
            return redirect('orders:gcash_payment_pending')
        elif proof.size < MIN_PROOF_SIZE:
            messages.error(request, 'That image is too small to be a real GCash receipt screenshot (must be at least 100 KB). Please upload a genuine screenshot.')
            return redirect('orders:gcash_payment_pending')
        elif proof.size > MAX_PROOF_SIZE:
            messages.error(request, 'That image is too large (must be under 500 KB). Please upload a genuine GCash receipt screenshot.')
            return redirect('orders:gcash_payment_pending')

        order = _create_order(
            request, cart, selected_ids, 'gcash', draft['form_data'],
            extra={'payment_proof': proof, 'payment_submitted_at': timezone.now()},
        )
        request.session.pop(GCASH_DRAFT_SESSION_KEY, None)
        messages.success(request, 'Verification image received! You can now place your order.')
        return redirect('orders:gcash_payment', pk=order.pk)

    return render(request, 'orders/gcash_payment_pending.html', {
        'draft_total': draft_total,
        'min_proof_kb': MIN_PROOF_SIZE // 1024,
        'max_proof_kb': MAX_PROOF_SIZE // 1024,
    })


@cache_control(no_store=True, no_cache=True, must_revalidate=True)
def gcash_payment(request, pk):
    """Step 3: the Order already exists (created with its receipt attached
    in gcash_payment_pending). Lets the customer review/replace the receipt
    and finish placing the order."""
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    order = get_object_or_404(Order, pk=pk, user=request.user, payment_method='gcash')

    MIN_PROOF_SIZE = 100 * 1024   # 100 KB
    MAX_PROOF_SIZE = 500 * 1024   # 500 KB

    if request.method == 'POST':
        proof = request.FILES.get('payment_proof')
        if not proof:
            messages.error(request, 'Please attach a screenshot of your GCash payment before sending.')
        elif proof.size < MIN_PROOF_SIZE:
            messages.error(request, 'That image is too small to be a real GCash receipt screenshot (must be at least 100 KB). Please upload a genuine screenshot.')
        elif proof.size > MAX_PROOF_SIZE:
            messages.error(request, 'That image is too large (must be under 500 KB). Please upload a genuine GCash receipt screenshot.')
        else:
            order.payment_proof = proof
            order.payment_submitted_at = timezone.now()
            order.save()
            messages.success(request, 'Verification image received! You can now place your order.')
        return redirect('orders:gcash_payment', pk=order.pk)

    return render(request, 'orders/gcash_payment.html', {
        'order': order,
        'min_proof_kb': MIN_PROOF_SIZE // 1024,
        'max_proof_kb': MAX_PROOF_SIZE // 1024,
    })


@require_POST
def gcash_finalize(request, pk):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    order = get_object_or_404(Order, pk=pk, user=request.user, payment_method='gcash')

    if not order.payment_proof:
        messages.error(request, 'Please send your GCash payment verification image first.')
        return redirect('orders:gcash_payment', pk=order.pk)

    messages.success(request, f'Order {order.order_number} placed! Thank you for supporting PDL artisans.')
    return redirect('orders:order_confirmation', pk=order.pk)


def order_confirmation(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'orders/confirmation.html', {'order': order})


def my_orders(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    orders = Order.objects.filter(user=request.user).prefetch_related('items').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(request, 'orders/my_orders.html', {
        'orders': orders,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
    })


def order_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    order = get_object_or_404(Order, pk=pk, user=request.user)
    order.notifications.filter(is_read=False).update(is_read=True)
    status_order = ['pending', 'processing', 'confirmed', 'shipped', 'delivered', 'cancelled']
    reached_status = order.previous_status if order.status == 'cancelled' and order.previous_status else order.status
    status_index = status_order.index(reached_status) + 1 if reached_status in status_order else 1
    return render(request, 'orders/order_detail.html', {
        'order': order,
        'status_index': status_index,
    })


@require_POST
def cancel_order(request, pk):
    if not request.user.is_authenticated:
        return redirect('accounts:login')
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status in ['shipped', 'delivered', 'cancelled']:
        messages.error(request, 'This order can no longer be cancelled.')
    else:
        order.previous_status = order.status
        order.status = 'cancelled'
        order.save()
        order.restock_items()
        messages.success(request, f'Order {order.order_number} has been cancelled.')
    return redirect('orders:order_detail', pk=order.pk)