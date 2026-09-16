from decimal import Decimal
from django.conf import settings
from store.models import Product, ProductDesign

# Session key holding the single ad-hoc "Buy Now" item, kept completely
# separate from the persistent CART_SESSION_ID cart dict. A Buy Now
# purchase must never be merged into (or removed from) the customer's
# actual cart, so it lives in its own bit of session state.
BUY_NOW_SESSION_ID = 'buy_now_item'


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


def _max_purchasable(product, design):
    """The real stock cap for a cart line. A design's own `stock` is
    authoritative when one applies. Otherwise: a product using the
    Size → Design variant system tracks stock ONLY per design, so a size
    with no active design has zero stock — it must never fall back to the
    product's overall calculated total (that total belongs to whichever
    designs actually have it). Only a plain, variant-less product falls
    back to its own shared `stock` field."""
    if design:
        return max(0, design.stock_for_size(None))
    if product.has_variants:
        return 0
    return max(0, product.stock)


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    @staticmethod
    def make_key(product_id, size=None, design_id=None):
        """
        Cart line key. Product + size + design all combine into one key, so
        the same product in a different size or a different design creates
        a separate cart line (e.g. '12' for no-size/no-design, '12_S' for
        Small only, '12_D3' for a design only, '12_S-D3' for both).
        """
        size = (size or '').upper()
        suffix = size
        if design_id:
            suffix = f"{suffix}-D{design_id}" if suffix else f"D{design_id}"
        return f"{product_id}_{suffix}" if suffix else str(product_id)

    def add(self, product, quantity=1, override_quantity=False, size=None, design=None):
        size = (size or '').upper() or None
        design_id = design.id if design else None
        key = self.make_key(product.id, size, design_id)
        if key not in self.cart:
            price = product.get_price_for_size(size) if size else product.price_min
            self.cart[key] = {
                'product_id': product.id,
                'quantity': 0,
                'price': str(price),
                'name': product.name,
                'size': size or '',
                'design_id': design_id,
                'design_name': design.name if design else '',
            }
        if override_quantity:
            new_quantity = quantity
        else:
            new_quantity = self.cart[key]['quantity'] + quantity
        # Stock is tracked per (design, size) pair when this product has
        # designs; otherwise it falls back to the shared product stock,
        # same as before. A variant product's size with no active design
        # at all has zero stock — see _max_purchasable.
        max_qty = _max_purchasable(product, design)
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

    def _resolve(self, raw_item, products, designs):
        """Shared resolution logic used by __iter__ and get_buy_now_item so
        both paths build the item dict identically."""
        item = dict(raw_item)
        item['product'] = products.get(item.get('product_id'))
        item['price'] = Decimal(item['price'])
        item['total'] = item['price'] * item['quantity']
        item['total_price'] = item['total']  # backward compat
        item.setdefault('size', '')
        item['size_display'] = dict(Product.SIZE_CHOICES).get(item['size'], '')
        item.setdefault('design_id', None)
        item.setdefault('design_name', '')
        item['design'] = designs.get(item.get('design_id'))
        return item

    def __iter__(self):
        product_ids = {item.get('product_id') for item in self.cart.values()}
        design_ids = {item.get('design_id') for item in self.cart.values() if item.get('design_id')}
        products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
        designs = {d.id: d for d in ProductDesign.objects.filter(id__in=design_ids)}
        for key, raw_item in self.cart.items():
            item = self._resolve(raw_item, products, designs)
            item['key'] = key
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

    # --- Buy Now (never touches the cart above) -------------------------

    def set_buy_now(self, product, quantity=1, size=None, design=None):
        """Stash a single ad-hoc item for the "Buy Now" flow. This is stored
        outside of self.cart entirely, so it never merges with an existing
        cart line, never shows up in the cart page/badge, and never affects
        quantities already in the cart."""
        size = (size or '').upper() or None
        design_id = design.id if design else None
        price = product.get_price_for_size(size) if size else product.price_min
        max_qty = _max_purchasable(product, design)
        item = {
            'product_id': product.id,
            'quantity': min(max(1, quantity), max_qty) if max_qty else 0,
            'price': str(price),
            'name': product.name,
            'size': size or '',
            'design_id': design_id,
            'design_name': design.name if design else '',
        }
        self.session[BUY_NOW_SESSION_ID] = item
        self.save()
        return item

    def get_buy_now_item(self):
        """Return the pending Buy Now item (with product/design/total
        resolved), or None if there isn't one / the product is no longer
        available."""
        raw = self.session.get(BUY_NOW_SESSION_ID)
        if not raw:
            return None
        product = Product.objects.filter(id=raw.get('product_id'), is_active=True).first()
        if not product or raw.get('quantity', 0) <= 0:
            return None
        design = None
        if raw.get('design_id'):
            design = ProductDesign.objects.filter(id=raw['design_id']).first()
        item = self._resolve(raw, {product.id: product}, {design.id: design} if design else {})
        item['key'] = self.make_key(item['product_id'], item.get('size'), item.get('design_id'))
        return item

    def clear_buy_now(self):
        if BUY_NOW_SESSION_ID in self.session:
            del self.session[BUY_NOW_SESSION_ID]
            self.save()