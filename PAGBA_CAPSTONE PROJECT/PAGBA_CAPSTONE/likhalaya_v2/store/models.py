import json
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse
from accounts.models import CustomUser


class ActiveManager(models.Manager):
    """Default manager: hides archived (soft-deleted) records. Use
    <Model>.all_objects to include archived records, e.g. on the Archive page."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Archive (soft-delete) ──
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_categories'
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['order', 'name']
        base_manager_name = 'all_objects'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('store:category', kwargs={'slug': self.slug})

    def archive(self, by_user=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = by_user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])


class Product(models.Model):
    SIZE_SMALL = 'S'
    SIZE_MEDIUM = 'M'
    SIZE_LARGE = 'L'
    SIZE_CHOICES = [
        (SIZE_SMALL, 'Small'),
        (SIZE_MEDIUM, 'Medium'),
        (SIZE_LARGE, 'Large'),
    ]

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    price_min = models.DecimalField(max_digits=10, decimal_places=2)
    price_medium = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    price_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    artisan_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Archive (soft-delete) ──
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deleted_products'
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-created_at']
        base_manager_name = 'all_objects'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            n = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        # Auto-fill Medium price if left blank, so it never has to be set manually.
        if self.price_medium is None:
            if self.price_max and self.price_max > self.price_min:
                midpoint = (self.price_min + self.price_max) / 2
                self.price_medium = midpoint.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                self.price_medium = self.price_min
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('store:product_detail', kwargs={'slug': self.slug})

    def archive(self, by_user=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = by_user
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    @property
    def price_display(self):
        if self.price_max and self.price_max != self.price_min:
            return f"₱{self.price_min:.0f}–{self.price_max:.0f}"
        return f"₱{self.price_min:.0f}"

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def has_size_pricing(self):
        """True when the product has a real price range (Small → Large)."""
        return bool(self.price_max and self.price_max > self.price_min)

    @property
    def price_small(self):
        """Small = lowest price in the range."""
        return self.price_min

    @property
    def price_large(self):
        """Large = highest price in the range."""
        return self.price_max if self.price_max else self.price_min

    @property
    def images_by_size_json(self):
        """JSON blob of gallery photos grouped by size, e.g. {"general": [...],
        "S": [...], "M": [...], "L": [...]}. "general" photos (size left blank)
        always show; size-tagged photos only show once that size is picked.
        Used by the front-end image carousel/modal."""
        data = {'general': [], 'S': [], 'M': [], 'L': []}
        if self.image:
            data['general'].append(self.image.url)
        for extra in self.extra_images.all():
            key = extra.size if extra.size in ('S', 'M', 'L') else 'general'
            data[key].append(extra.image.url)
        return json.dumps(data)

    def get_price_for_size(self, size):
        """Return the price for a given size code ('S', 'M', 'L')."""
        prices = {
            self.SIZE_SMALL: self.price_small,
            self.SIZE_MEDIUM: self.price_medium,
            self.SIZE_LARGE: self.price_large,
        }
        return prices.get((size or '').upper(), self.price_min)


class ProductImage(models.Model):
    SIZE_CHOICES = [
        ('', 'All sizes (general)'),
        (Product.SIZE_SMALL, 'Small'),
        (Product.SIZE_MEDIUM, 'Medium'),
        (Product.SIZE_LARGE, 'Large'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='extra_images')
    image = models.ImageField(upload_to='products/gallery/')
    caption = models.CharField(max_length=200, blank=True)
    size = models.CharField(
        max_length=1, choices=SIZE_CHOICES, blank=True,
        help_text="Leave blank to show for every size. Set to Small/Medium/Large to show only when that size is picked."
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        size_label = dict(self.SIZE_CHOICES).get(self.size, 'All sizes')
        return f"Image for {self.product.name} ({size_label})"


class Personnel(models.Model):
    BADGE_CHOICES = [
        ('Command', 'Command'),
        ('Administration', 'Administration'),
        ('Operations', 'Operations'),
        ('Livelihood', 'Livelihood'),
        ('Programs', 'Programs'),
        ('Security', 'Security'),
    ]
    rank = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    title = models.CharField(max_length=200)
    department_badge = models.CharField(max_length=50, choices=BADGE_CHOICES, default='Command')
    emoji = models.CharField(max_length=10, default='👮')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order']
        verbose_name_plural = 'Personnel'

    def __str__(self):
        return f"{self.rank} {self.name}"


class ContactMessage(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} - {self.name}"


class LivelihoodVideo(models.Model):
    """A promo video for BJMP livelihood programs, shown on the About page.
    Supports a YouTube/Facebook link (recommended) or an uploaded video file."""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True, help_text="YouTube or Facebook video link")
    video_file = models.FileField(upload_to='livelihood_videos/', blank=True, null=True,
                                  help_text="Use this only if you don't have a link above")
    thumbnail = models.ImageField(upload_to='livelihood_thumbs/', blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    @property
    def embed_url(self):
        """Converts a normal YouTube/Facebook watch link into an embeddable URL."""
        url = self.video_url or ''
        if 'youtu.be/' in url:
            vid = url.split('youtu.be/')[-1].split('?')[0]
            return f'https://www.youtube.com/embed/{vid}'
        if 'watch?v=' in url:
            vid = url.split('watch?v=')[-1].split('&')[0]
            return f'https://www.youtube.com/embed/{vid}'
        if 'facebook.com' in url:
            from urllib.parse import quote
            return f'https://www.facebook.com/plugins/video.php?href={quote(url, safe="")}&show_text=false'
        return url