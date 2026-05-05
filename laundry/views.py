from datetime import datetime, time
from functools import wraps

from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
import io
import os
import qrcode

from django.conf import settings
from django.core.files.base import ContentFile

from .models import Order, ServiceInventoryUsage, StockMovement

ITEMS_PER_PAGE = 20


def local_day_range(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    return start, start + timezone.timedelta(days=1)


def orders_created_on(day):
    start, end = local_day_range(day)
    return Order.objects.filter(created_at__gte=start, created_at__lt=end)


def is_admin(user):
    return user.is_superuser or user.groups.filter(name='Admin').exists()


def is_customer_user(user):
    return (
        user.is_authenticated
        and hasattr(user, 'customer_profile')
        and not is_admin(user)
        and not user.groups.filter(name='Staff').exists()
    )


def staff_portal_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('staff_login')
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def customer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('customer_login')
        if not is_customer_user(request.user):
            return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def deduct_inventory_for_order(order, user):
    if order.inventory_deducted_at:
        return True, "Inventory was already deducted for this order."

    rules = ServiceInventoryUsage.objects.select_related('item').filter(
        service_type=order.service_type,
        is_active=True,
    )
    if not rules.exists():
        return True, "No inventory usage rules configured for this service."

    deductions = []
    for rule in rules:
        quantity = rule.quantity_for_order(order)
        if quantity <= 0:
            continue
        if rule.item.current_stock < quantity:
            return False, (
                f"Not enough {rule.item.name}. Need {quantity} {rule.item.unit}, "
                f"but only {rule.item.current_stock} {rule.item.unit} is available."
            )
        deductions.append((rule.item, quantity))

    for item, quantity in deductions:
        item.current_stock = round(item.current_stock - quantity, 4)
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item,
            movement_type='DEDUCT',
            quantity=quantity,
            reference_order=order,
            notes=f"Auto deducted for {order.get_service_type_display()} order #{order.id}",
            performed_by=user,
        )

    order.inventory_deducted_at = timezone.now()
    order.save(update_fields=['inventory_deducted_at', 'updated_at'])
    return True, f"Inventory deducted for Order #{order.id}."


def advance_order_status(order, user=None):
    if order.status == 'PENDING_PICKUP':
        return False

    next_status = order.get_next_status()
    if not next_status:
        return False
    if next_status == 'WEIGHED' and order.weight <= 0:
        return False
    if next_status == 'WEIGHED':
        order.calculate_totals()
    if next_status == 'PROCESSING' and order.payment_method == 'GCASH' and order.payment_status != 'PAID':
        return False
    if next_status == 'PROCESSING':
        ok, _ = deduct_inventory_for_order(order, user)
        if not ok:
            return False
    if next_status == 'OUT_FOR_DELIVERY' and order.payment_status != 'PAID':
        return False
    if next_status == 'COMPLETED' and order.payment_status != 'PAID':
        return False

    order.status = next_status
    now = timezone.now()
    if next_status == 'PICKED_UP':
        order.picked_up_at = now
    elif next_status == 'COMPLETED':
        order.claimed_at = now
    elif next_status == 'DELIVERED':
        order.delivered_at = now
        if order.payment_status == 'PAID':
            order.status = 'COMPLETED'
            order.claimed_at = now
    order.save()
    return True


def generate_qr_for_order(order):
    qr_data = (
        f"Order #{order.id}\n"
        f"Customer: {order.customer.name}\n"
        f"Service: {order.get_service_type_display()}\n"
        f"Weight: {order.weight}kg\n"
        f"Total: ₱{order.total_amount}\n"
        f"Payment: {order.get_payment_status_display()}\n"
        f"Status: {order.get_status_display()}"
    )
    qr = qrcode.make(qr_data)
    buffer = io.BytesIO()
    qr.save(buffer, format='PNG')
    buffer.seek(0)

    if order.qr_code:
        old_path = os.path.join(settings.MEDIA_ROOT, str(order.qr_code))
        if os.path.exists(old_path):
            os.remove(old_path)
        order.qr_code = None
        order.save()

    order.qr_code.save(f"order_{order.id}.png", ContentFile(buffer.read()), save=True)


def refresh_order_payment_from_verified_records(order):
    paid = order.payments.filter(status='VERIFIED').aggregate(total=Sum('amount'))['total'] or 0
    order.amount_paid = round(paid, 2)
    order.update_payment_status_from_amount()
    update_fields = ['amount_paid', 'balance', 'overpayment', 'payment_status', 'paid_at', 'updated_at']
    if order.status == 'DELIVERED' and order.payment_status == 'PAID':
        order.status = 'COMPLETED'
        order.claimed_at = timezone.now()
        update_fields += ['status', 'claimed_at']
    order.save(update_fields=update_fields)


# ── Auth ──────────────────────────────────
# ── Admin Dashboard ───────────────────────
# ── Staff Dashboard ───────────────────────
# ── Kanban Board ──────────────────────────
# ── Customer List ─────────────────────────
def track_order(request):
    order, error = None, None
    order_id = (request.GET.get('order_id') or request.POST.get('order_id', '')).strip()
    if order_id:
        try:
            order = Order.objects.select_related('customer').get(id=int(order_id))
        except (Order.DoesNotExist, ValueError):
            error = f"No order found with ID #{order_id}."
    return render(request, 'laundry/track_order.html', {'order': order, 'error': error})


# ── Staff List ────────────────────────────
# ── Add Staff ─────────────────────────────
# ── Toggle Staff ──────────────────────────
# ── Reset Password ────────────────────────
# ── Edit Order ────────────────────────────
