from decimal import Decimal
from django.conf import settings
from store.models import Product


def calculate_shipping_fee(subtotal):
    """
    Shipping rules:
      - subtotal < 500  -> FREE shipping
      - subtotal >= 500 -> ₱50 shipping
    """
    subtotal = Decimal(subtotal)
    if subtotal < Decimal('500'):
        return Decimal('0')
    else:
        return Decimal('50')


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    @staticmethod
    def make_key(product_id, size=None):
        """
        Cart line key. Same product in different sizes gets a different key
        (e.g. '12' for no-size, '12_S' / '12_M' / '12_L' for sized items) so
        ordering the same product in two sizes creates two separate lines.
        """
        size = (size or '').upper()
        return f"{product_id}_{size}" if size else str(product_id)

    def add(self, product, quantity=1, override_quantity=False, size=None):
        size = (size or '').upper() or None
        key = self.make_key(product.id, size)
        if key not in self.cart:
            price = product.get_price_for_size(size) if size else product.price_min
            self.cart[key] = {
                'product_id': product.id,
                'quantity': 0,
                'price': str(price),
                'name': product.name,
                'size': size or '',
            }
        if override_quantity:
            new_quantity = quantity
        else:
            new_quantity = self.cart[key]['quantity'] + quantity
        # Never let the cart hold more than what's currently in stock.
        max_qty = max(0, product.stock)
        self.cart[key]['quantity'] = min(new_quantity, max_qty)
        self.save()

    def save(self):
        self.session.modified = True

    def remove(self, key):
        """Remove a single cart line by its key (see make_key)."""
        key = str(key)
        if key in self.cart:
            del self.cart[key]
            self.save()

    def get_quantity(self, key):
        return self.cart.get(str(key), {}).get('quantity', 0)

    def __iter__(self):
        product_ids = {item.get('product_id') for item in self.cart.values()}
        products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
        for key, raw_item in self.cart.items():
            item = dict(raw_item)
            item['key'] = key
            item['product'] = products.get(item.get('product_id'))
            item['price'] = Decimal(item['price'])
            item['total'] = item['price'] * item['quantity']
            item['total_price'] = item['total']  # backward compat
            item.setdefault('size', '')
            item['size_display'] = dict(Product.SIZE_CHOICES).get(item['size'], '')
            yield item

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def product_count(self):
        """Number of distinct cart lines (a product in 2 sizes counts as 2)."""
        return len(self.cart)

    def get_total_price(self):
        return sum(Decimal(item['price']) * item['quantity'] for item in self.cart.values())

    def iter_selected(self, keys):
        """Like __iter__ but only yields lines whose key is in keys (strings)."""
        keys = set(str(k) for k in keys)
        for item in self:
            if str(item['key']) in keys:
                yield item

    def total_price_for(self, keys):
        keys = set(str(k) for k in keys)
        total = Decimal('0')
        for key, item in self.cart.items():
            if str(key) in keys:
                total += Decimal(item['price']) * item['quantity']
        return total

    def remove_many(self, keys):
        changed = False
        for key in keys:
            key = str(key)
            if key in self.cart:
                del self.cart[key]
                changed = True
        if changed:
            self.save()

    def clear(self):
        if settings.CART_SESSION_ID in self.session:
            del self.session[settings.CART_SESSION_ID]
            self.save()