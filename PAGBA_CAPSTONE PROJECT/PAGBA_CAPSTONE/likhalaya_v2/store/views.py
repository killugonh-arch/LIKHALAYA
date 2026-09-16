from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Q, Prefetch
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from .models import Product, Category, Personnel, ContactMessage, LivelihoodVideo, ProductDesign
from .forms import ContactForm


def home(request):
    latest_products = Product.objects.filter(is_active=True).select_related('category').order_by('-created_at')[:8]
    categories = Category.objects.filter(is_active=True).order_by('order', 'name')
    active_videos = list(
        LivelihoodVideo.objects.filter(is_active=True, show_on_home=True).order_by('order', '-created_at')[:2]
    )
    featured_video = active_videos[0] if len(active_videos) > 0 else None
    second_video = active_videos[1] if len(active_videos) > 1 else None
    return render(request, 'store/home.html', {
        'latest_products': latest_products,
        'categories': categories,
        'featured_video': featured_video,
        'second_video': second_video,
    })


def shop(request):
    products = Product.objects.filter(is_active=True).select_related('category').prefetch_related(
        'extra_images'
    )
    search_query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()
    sort = request.GET.get('sort', '-created_at')
    in_stock_filter = request.GET.get('in_stock', '')

    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(artisan_name__icontains=search_query)
        )
    if selected_category:
        products = products.filter(category__slug=selected_category)
    if in_stock_filter:
        products = products.filter(stock__gt=0)

    sort_map = {
        'price_min': 'price_min', '-price_min': '-price_min',
        'name': 'name', '-name': '-name',
        '-created_at': '-created_at', 'created_at': 'created_at',
    }
    products = products.order_by(sort_map.get(sort, '-created_at'))

    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    categories = Category.objects.filter(is_active=True).prefetch_related('products').order_by('order', 'name')

    return render(request, 'store/shop.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': categories,
        'search_query': search_query,
        'selected_category': selected_category,
        'sort': sort,
        'in_stock_filter': in_stock_filter,
    })


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.prefetch_related('extra_images', 'sizes__designs'), slug=slug, is_active=True
    )
    related_products = Product.objects.filter(
        category=product.category, is_active=True
    ).exclude(pk=product.pk)[:4]
    return render(request, 'store/product_detail.html', {
        'product': product,
        'related_products': related_products,
    })


def category_view(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    products = Product.objects.filter(category=category, is_active=True).select_related('category')
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'store/category.html', {
        'category': category,
        'products': page_obj,
        'page_obj': page_obj,
    })


def about(request):
    personnel = Personnel.objects.filter(is_active=True)
    videos = LivelihoodVideo.objects.filter(is_active=True).order_by('order', '-created_at')
    return render(request, 'store/about.html', {'personnel': personnel, 'videos': videos})


def contact(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    context_product = None

    if request.method == 'POST':
        form = ContactForm(request.POST, request.FILES)
        if form.is_valid():
            msg = form.save(commit=False)
            if request.user.is_authenticated:
                msg.customer = request.user
            msg.save()
            success_message = 'Thank you! Your request has been received. Our team will review your inquiry and get back to you as soon as possible.'
            if is_ajax:
                return JsonResponse({'ok': True, 'message': success_message})
            messages.success(request, success_message)
            return redirect('store:contact')

        if is_ajax:
            return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
        product_id = request.POST.get('product')
        if product_id:
            context_product = Product.objects.filter(pk=product_id).first()
    else:
        initial = {}
        if request.user.is_authenticated:
            initial['name'] = request.user.get_full_name()
            initial['email'] = request.user.email
            if request.user.phone:
                initial['phone'] = request.user.phone
            # Build location from profile address fields
            loc_parts = [
                getattr(request.user, 'address', ''),
                getattr(request.user, 'city', ''),
                getattr(request.user, 'province', ''),
                getattr(request.user, 'zip_code', ''),
            ]
            location_str = ', '.join(p for p in loc_parts if p)
            if location_str:
                initial['location'] = location_str

        # Opened from a product page ("Ask about this product") — auto-populate
        # the product reference and item name, and pre-select the merged
        # "Product & Custom Orders" category, without forcing the customer to
        # type the product name manually.
        product_id = request.GET.get('product')
        if product_id:
            context_product = Product.objects.filter(pk=product_id, is_active=True).first()
            if context_product:
                initial['product'] = context_product.pk
                initial['item_name'] = context_product.name
                initial['inquiry_type'] = ContactMessage.INQUIRY_CUSTOM_ORDER
                initial['subject'] = f'Product & Custom Order Inquiry — {context_product.name}'

        form = ContactForm(initial=initial)
    return render(request, 'store/contact.html', {'form': form, 'context_product': context_product})


def terms(request):
    return render(request, 'store/terms.html')