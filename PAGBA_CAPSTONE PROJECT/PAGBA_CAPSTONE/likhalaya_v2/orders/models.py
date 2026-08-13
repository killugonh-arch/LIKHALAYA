from django.db import models
from accounts.models import CustomUser
from store.models import Product

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('gcash', 'GCash'),
        ('bank', 'Bank Transfer'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    previous_status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cod')
    # Shipping info
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10)
    notes = models.TextField(blank=True)
    # GCash payment verification
    payment_proof = models.ImageField(upload_to='payment_proofs/', null=True, blank=True)
    payment_submitted_at = models.DateTimeField(null=True, blank=True)
    # Totals
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.pk} – {self.full_name}"

    @property
    def order_number(self):
        return f"LKL-{self.pk:05d}"

    def restock_items(self):
        """Add each item's quantity back to its product's stock. Call once,
        right when an order transitions into 'cancelled' status."""
        for item in self.items.select_related('product').all():
            if item.product:
                item.product.stock += item.quantity
                item.product.save(update_fields=['stock'])


class OrderItem(models.Model):
    SIZE_CHOICES = Product.SIZE_CHOICES

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)
    product_price = models.DecimalField(max_digits=10, decimal_places=2)
    size = models.CharField(max_length=1, choices=SIZE_CHOICES, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity}x {self.product_name}"

    @property
    def item_total(self):
        return self.product_price * self.quantity

    @property
    def size_display(self):
        return dict(self.SIZE_CHOICES).get(self.size, '')


class Notification(models.Model):
    """A per-customer notification, e.g. 'Your order has been shipped.'"""
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='notifications')
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user}: {self.message}"

    @property
    def url(self):
        if self.order_id:
            from django.urls import reverse
            return reverse('orders:order_detail', args=[self.order_id])
        return '#'