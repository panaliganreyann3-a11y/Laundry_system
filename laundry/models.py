from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class PricingConfig(models.Model):
    price_per_kg = models.FloatField(default=30.0)
    rush_surcharge = models.FloatField(default=50.0)
    delivery_fee = models.FloatField(default=0.0)
    gcash_number = models.CharField(max_length=30, blank=True, null=True)
    gcash_qr = models.ImageField(upload_to='gcash_qr/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Pricing Configuration"

    def __str__(self):
        return f"₱{self.price_per_kg}/kg (Rush: +₱{self.rush_surcharge})"


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=120, default='Spin King Laundry Hub')
    subtitle = models.CharField(max_length=160, default='Laundry Management System')
    logo = models.ImageField(upload_to='branding/', blank=True, null=True)
    footer_description = models.TextField(default="Keeping Bayawan's clothes fresh since day one. Fast, clean, and reliable laundry service.")
    footer_location = models.CharField(max_length=160, default='Bayawan City, Negros Oriental, Philippines')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(id=1)
        return settings

    def __str__(self):
        return self.site_name


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile'
    )
    avatar = models.ImageField(upload_to='user_avatars/', blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} profile"


class Customer(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='customer_profile'
    )
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_walk_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    # AFTER (fixed)
    @property
    def total_orders(self):
        return self.orders.count()

    @property
    def last_order(self):
        return self.orders.order_by('-created_at').first()

    @property
    def total_spent(self):
        from django.db.models import Sum
        return self.orders.aggregate(t=Sum('total_amount'))['t'] or 0


class Order(models.Model):

    STATUS_CHOICES = [
        ('PENDING_PICKUP', 'Pending Pickup'),
        ('PICKUP_CONFIRMED', 'Pickup Confirmed'),
        ('PICKED_UP', 'Picked Up'),
        ('RECEIVED_AT_SHOP', 'Received at Shop'),
        ('WEIGHED', 'Weighed'),
        ('BILL_SENT', 'Bill Sent'),
        ('PROCESSING', 'Processing Service'),
        ('READY_FOR_PICKUP', 'Ready for Pickup'),
        ('READY_FOR_DELIVERY', 'Ready for Delivery'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    ORDER_TYPE_CHOICES = [
        ('WALK_IN', 'Walk-in'),
        ('PICKUP_DELIVERY', 'Pickup & Delivery'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('GCASH', 'GCash'),
        ('CASH_AFTER_DELIVERY', 'Cash After Delivery / COD'),
    ]

    SERVICE_CHOICES = [
        ('WASH', 'Wash Only'),
        ('WASH_DRY', 'Wash & Dry'),
        ('WASH_DRY_FOLD', 'Wash, Dry & Fold'),
        ('DRY_ONLY', 'Dry Only'),
        ('DRY_CLEAN', 'Dry Clean'),
        ('IRON', 'Iron / Press Only'),
        ('EXPRESS', 'Express Service'),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='orders'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders_created'
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_orders'
    )

    service_type = models.CharField(
        max_length=20, choices=SERVICE_CHOICES, default='WASH_DRY_FOLD'
    )
    order_type = models.CharField(
        max_length=20, choices=ORDER_TYPE_CHOICES, default='WALK_IN'
    )
    weight = models.FloatField(default=0)
    price = models.FloatField(default=0)
    price_per_kg = models.FloatField(default=30.0)
    pickup_fee = models.FloatField(default=0.0)
    delivery_fee = models.FloatField(default=0.0)
    extra_fee = models.FloatField(default=0.0)
    discount = models.FloatField(default=0.0)
    laundry_fee = models.FloatField(default=0.0)
    subtotal = models.FloatField(default=0.0)
    total_amount = models.FloatField(default=0.0)
    balance = models.FloatField(default=0.0)
    overpayment = models.FloatField(default=0.0)
    is_priority = models.BooleanField(default=False)
    queue_number = models.PositiveIntegerField(default=0)
    special_instructions = models.TextField(blank=True, null=True)
    pickup_address = models.TextField(blank=True, null=True)
    delivery_address = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=25, choices=STATUS_CHOICES, default='RECEIVED_AT_SHOP'
    )
    preferred_pickup_at = models.DateTimeField(null=True, blank=True)
    estimated_pickup = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    inventory_deducted_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True, null=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True, null=True)

    qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    PAYMENT_STATUS_CHOICES = [
        ('UNPAID', 'Unpaid'),
        ('PENDING_VERIFICATION', 'Pending Verification'),
        ('PAID', 'Paid'),
        ('PARTIAL', 'Partial'),
        ('REJECTED', 'Rejected'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]
    payment_status = models.CharField(
        max_length=25, choices=PAYMENT_STATUS_CHOICES, default='UNPAID'
    )
    payment_method = models.CharField(
        max_length=25, choices=PAYMENT_METHOD_CHOICES, default='CASH_AFTER_DELIVERY'
    )
    amount_paid = models.FloatField(default=0.0)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_priority', 'created_at']

    def __str__(self):
        tag = " [RUSH]" if self.is_priority else ""
        return f"Order #{self.id}{tag} — {self.customer.name}"

    def get_next_status(self):
        flow = {
            'PICKUP_CONFIRMED': 'PICKED_UP',
            'PICKED_UP': 'RECEIVED_AT_SHOP',
            'RECEIVED_AT_SHOP': 'WEIGHED',
            'BILL_SENT': 'PROCESSING',
            'OUT_FOR_DELIVERY': 'DELIVERED',
            'DELIVERED': 'COMPLETED',
        }
        if self.status == 'WEIGHED':
            return 'BILL_SENT' if self.order_type == 'PICKUP_DELIVERY' else 'PROCESSING'
        if self.status == 'PROCESSING':
            return 'READY_FOR_DELIVERY' if self.order_type == 'PICKUP_DELIVERY' else 'READY_FOR_PICKUP'
        if self.status == 'READY_FOR_PICKUP':
            return 'COMPLETED'
        if self.status == 'READY_FOR_DELIVERY':
            return 'OUT_FOR_DELIVERY' if self.order_type == 'PICKUP_DELIVERY' else 'COMPLETED'
        return flow.get(self.status, None)

    def get_next_status_label(self):
        next_status = self.get_next_status()
        if not next_status:
            return ''
        return dict(self.STATUS_CHOICES).get(next_status, next_status)

    def is_complete(self):
        return self.status in ('COMPLETED', 'CANCELLED')

    def is_overdue(self):
        if self.due_date and not self.is_complete() and self.status not in ('READY_FOR_PICKUP', 'READY_FOR_DELIVERY'):
            return timezone.now() > self.due_date
        return False

    def is_urgent(self):
        if self.due_date and not self.is_complete() and self.status not in ('READY_FOR_PICKUP', 'READY_FOR_DELIVERY'):
            from datetime import timedelta
            return timezone.now() > self.due_date - timedelta(hours=2)
        return self.is_priority

    def status_badge_color(self):
        colors = {
            'PENDING_PICKUP': 'warning',
            'PICKUP_CONFIRMED': 'primary',
            'PICKED_UP': 'info',
            'RECEIVED_AT_SHOP': 'secondary',
            'WEIGHED': 'info',
            'BILL_SENT': 'primary',
            'PROCESSING': 'warning',
            'READY_FOR_PICKUP': 'success',
            'READY_FOR_DELIVERY': 'success',
            'OUT_FOR_DELIVERY': 'primary',
            'DELIVERED': 'success',
            'COMPLETED': 'dark',
            'CANCELLED': 'danger',
        }
        return colors.get(self.status, 'secondary')

    def urgency_label(self):
        if self.is_overdue():
            return ('danger', 'Overdue')
        if self.is_priority or self.is_urgent():
            return ('warning', 'Rush')
        return ('success', 'Normal')

    def calculate_totals(self):
        self.laundry_fee = round(max(self.weight, 0) * max(self.price_per_kg, 0), 2)
        self.subtotal = round(self.laundry_fee + max(self.extra_fee, 0), 2)
        total = self.subtotal + max(self.pickup_fee, 0) + max(self.delivery_fee, 0) - max(self.discount, 0)
        self.total_amount = round(max(total, 0), 2)
        self.price = self.total_amount
        self.update_balance()

    def update_balance(self):
        raw_balance = round(self.total_amount - self.amount_paid, 2)
        self.balance = max(raw_balance, 0)
        self.overpayment = abs(raw_balance) if raw_balance < 0 else 0

    def update_payment_status_from_amount(self):
        self.update_balance()
        if self.amount_paid <= 0:
            self.payment_status = 'UNPAID'
            self.paid_at = None
        elif self.amount_paid < self.total_amount:
            self.payment_status = 'PARTIAL'
            self.paid_at = None
        else:
            self.payment_status = 'PAID'
            self.paid_at = timezone.now()

    def can_complete(self):
        return self.status == 'DELIVERED' and self.payment_status == 'PAID'

    def complete_if_paid(self):
        if not self.can_complete():
            return False
        self.status = 'COMPLETED'
        return True

    def cancel_order(self):
        self.status = 'CANCELLED'
        self.payment_status = 'CANCELLED'
        self.payments.filter(status='PENDING').update(status='CANCELLED')


class Payment(models.Model):
    PAYMENT_RECORD_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('REFUNDED', 'Refunded'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.CharField(max_length=25, choices=Order.PAYMENT_METHOD_CHOICES)
    amount = models.FloatField(default=0.0)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    proof_image = models.ImageField(upload_to='payment_proofs/', blank=True, null=True)
    status = models.CharField(max_length=15, choices=PAYMENT_RECORD_STATUS_CHOICES, default='PENDING')
    verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_payments'
    )
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_payments'
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.id} for Order #{self.order_id} - {self.status}"


# ─────────────────────────────────────────
# INVENTORY
# ─────────────────────────────────────────

class ActivityLog(models.Model):
    CATEGORY_CHOICES = [
        ('ORDER', 'Order'),
        ('PAYMENT', 'Payment'),
        ('INVENTORY', 'Inventory'),
        ('SERVICE_USAGE', 'Service Usage'),
        ('PRICING', 'Pricing'),
        ('ACCOUNT', 'Account'),
    ]

    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('STATUS', 'Status'),
        ('PAYMENT', 'Payment'),
        ('RESTOCK', 'Restock'),
        ('DEDUCT', 'Deduct'),
        ('VERIFY', 'Verify'),
        ('REJECT', 'Reject'),
        ('TOGGLE', 'Toggle'),
    ]

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activity_logs'
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField()
    target_type = models.CharField(max_length=100, blank=True, null=True)
    target_id = models.PositiveBigIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        actor = self.actor.username if self.actor else 'System'
        return f"{actor} - {self.get_action_display()} - {self.description[:60]}"


class InventoryCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Inventory Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    UNIT_CHOICES = [
        ('ml', 'Milliliters (ml)'),
        ('L', 'Liters (L)'),
        ('g', 'Grams (g)'),
        ('kg', 'Kilograms (kg)'),
        ('pcs', 'Pieces'),
        ('rolls', 'Rolls'),
        ('bottles', 'Bottles'),
        ('boxes', 'Boxes'),
        ('sachets', 'Sachets'),
    ]

    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        InventoryCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='items'
    )
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='pcs')
    current_stock = models.FloatField(default=0)
    minimum_stock = models.FloatField(default=0)
    unit_cost = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.current_stock} {self.unit})"

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock

    @property
    def stock_status(self):
        if self.current_stock <= 0:
            return ('danger', 'Out of Stock')
        if self.current_stock <= self.minimum_stock:
            return ('warning', 'Low Stock')
        return ('success', 'In Stock')

    @property
    def total_value(self):
        return round(self.current_stock * self.unit_cost, 2)


class ServiceInventoryUsage(models.Model):
    service_type = models.CharField(max_length=20, choices=Order.SERVICE_CHOICES)
    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='service_usages'
    )
    quantity_per_kg = models.FloatField(default=0.0)
    fixed_quantity = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['service_type', 'item__name']
        unique_together = ('service_type', 'item')

    def __str__(self):
        return f"{self.get_service_type_display()} uses {self.item.name}"

    def quantity_for_order(self, order):
        return round((max(order.weight, 0) * self.quantity_per_kg) + self.fixed_quantity, 4)


class StockMovement(models.Model):
    MOVEMENT_CHOICES = [
        ('RESTOCK',    'Restock'),
        ('DEDUCT',     'Deduction'),
        ('ADJUSTMENT', 'Adjustment'),
    ]

    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    quantity = models.FloatField()
    reference_order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements'
    )
    notes = models.TextField(blank=True, null=True)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='stock_movements'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        sign = '+' if self.movement_type == 'RESTOCK' else '-'
        return f"{self.movement_type} {sign}{self.quantity} {self.item.unit} — {self.item.name}"
