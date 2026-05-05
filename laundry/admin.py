from django.contrib import admin
from .models import ActivityLog, Customer, Order, Payment, PricingConfig, ServiceInventoryUsage

@admin.register(PricingConfig)
class PricingConfigAdmin(admin.ModelAdmin):
    list_display = ['price_per_kg', 'rush_surcharge', 'updated_at']

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact', 'created_at']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'weight', 'total_amount', 'amount_paid', 'balance', 'payment_status', 'created_at']
    list_filter = ['status', 'payment_status', 'payment_method', 'is_priority', 'service_type']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['id', 'order', 'payment_method', 'amount', 'status', 'verified_by', 'received_by', 'paid_at', 'created_at']
    list_filter = ['payment_method', 'status']


@admin.register(ServiceInventoryUsage)
class ServiceInventoryUsageAdmin(admin.ModelAdmin):
    list_display = ['service_type', 'item', 'quantity_per_kg', 'fixed_quantity', 'is_active']
    list_filter = ['service_type', 'is_active']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'actor', 'category', 'action', 'description']
    list_filter = ['category', 'action', 'created_at']
    search_fields = ['description', 'actor__username']
