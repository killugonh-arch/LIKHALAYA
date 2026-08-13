from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from accounts.models import CustomUser
from store.models import Category, Product, ProductImage
from orders.models import Order, OrderItem, Notification


# ── Auth ──────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role + basic profile info directly into the JWT payload so the
    mobile app can route to the right screens without an extra request."""
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['username'] = user.username
        token['full_name'] = user.get_full_name()
        token['is_staff_role'] = user.is_staff_user()
        token['is_admin_role'] = user.is_admin_user()
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['role'] = self.user.role
        data['username'] = self.user.username
        data['full_name'] = self.user.get_full_name()
        data['is_staff_role'] = self.user.is_staff_user()
        data['is_admin_role'] = self.user.is_admin_user()
        return data


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'phone', 'address', 'barangay', 'city', 'province',
            'zip_code', 'avatar', 'bio', 'created_at',
        ]
        read_only_fields = ['id', 'role', 'created_at']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'phone']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data, role='customer')
        user.set_password(password)
        user.is_active = False  # activated after EmailOTP verification
        user.save()
        return user


# ── Store ─────────────────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'order', 'is_active']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'caption']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    extra_images = ProductImageSerializer(many=True, read_only=True)
    price_display = serializers.CharField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    has_size_pricing = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'category', 'category_name', 'name', 'slug', 'description',
            'price_min', 'price_medium', 'price_max', 'price_display',
            'has_size_pricing', 'stock', 'in_stock', 'image', 'extra_images',
            'is_active', 'artisan_name', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']


# ── Orders ────────────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    item_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    size_display = serializers.CharField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product', 'product_name', 'product_price', 'size',
            'size_display', 'quantity', 'item_total',
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    order_number = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user', 'status', 'payment_method',
            'full_name', 'email', 'phone', 'address', 'city', 'province',
            'zip_code', 'notes', 'payment_proof', 'payment_submitted_at',
            'subtotal', 'shipping_fee', 'total', 'items',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'subtotal', 'shipping_fee', 'total',
                             'created_at', 'updated_at']


class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    """Restricted serializer for staff/admin: status changes only."""
    class Meta:
        model = Order
        fields = ['status']


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'order', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'order', 'message', 'created_at']