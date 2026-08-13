from django.contrib import admin
from .models import Category, Product, ProductImage, Personnel, ContactMessage, LivelihoodVideo

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'order', 'is_active', 'created_at']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['order', 'is_active']

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'size', 'caption', 'order']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price_min', 'price_medium', 'price_max', 'stock', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'description', 'artisan_name']
    list_editable = ['is_active', 'stock']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline]

@admin.register(Personnel)
class PersonnelAdmin(admin.ModelAdmin):
    list_display = ['rank', 'name', 'title', 'department_badge', 'order', 'is_active']
    list_editable = ['order', 'is_active']


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'subject', 'created_at', 'is_read']
    list_filter = ['is_read', 'created_at']
    search_fields = ['name', 'email', 'subject', 'message']
    list_editable = ['is_read']


@admin.register(LivelihoodVideo)
class LivelihoodVideoAdmin(admin.ModelAdmin):
    list_display = ['title', 'order', 'is_active', 'created_at']
    list_editable = ['order', 'is_active']