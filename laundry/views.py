from datetime import datetime, time
from functools import wraps
from urllib.parse import urlencode

from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
import io
import os
import qrcode

from django.conf import settings
from django.core.mail import send_mail
from django.core.files.base import ContentFile

from .models import ActivityLog, Order, RewardTransaction, ServiceInventoryUsage, SiteSettings, StockMovement

ITEMS_PER_PAGE = 20
TRACKING_BASE_URL = settings.TRACKING_BASE_URL
POINTS_PER_COMPLETED_ORDER = 1
POINTS_PER_REWARD = 10
DISCOUNT_PER_REWARD = 50.0
POINT_EXPIRY_DAYS = 183


def build_tracking_url(order):
    separator = '&' if '?' in TRACKING_BASE_URL else '?'
    return f"{TRACKING_BASE_URL}{separator}{urlencode({'tracking_number': order.tracking_number})}"


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
            return redirect('login')
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def customer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_customer_user(request.user):
            return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def log_activity(actor, category, action, description, target=None):
    if actor is not None and not getattr(actor, 'is_authenticated', False):
        actor = None
    target_type = None
    target_id = None
    if target is not None:
        target_type = target._meta.label
        target_id = target.pk
    try:
        ActivityLog.objects.create(
            actor=actor,
            category=category,
            action=action,
            description=description,
            target_type=target_type,
            target_id=target_id,
        )
    except Exception:
        pass


def expire_customer_points(customer):
    if not customer.points_last_transaction_at or customer.loyalty_points <= 0:
        return 0
    expires_at = customer.points_last_transaction_at + timezone.timedelta(days=POINT_EXPIRY_DAYS)
    if timezone.now() < expires_at:
        return 0

    expired_points = customer.loyalty_points
    customer.loyalty_points = 0
    customer.points_last_transaction_at = timezone.now()
    customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])
    RewardTransaction.objects.create(
        customer=customer,
        transaction_type=RewardTransaction.EXPIRE,
        points=-expired_points,
        description='Points expired after 6 months with no reward transaction.',
    )
    return expired_points


def redeem_points_for_order(order, requested_points):
    customer = order.customer
    expire_customer_points(customer)
    customer.refresh_from_db(fields=['loyalty_points', 'points_last_transaction_at'])

    if order.payment_status == 'PAID' or order.amount_paid > 0:
        return False, "Points can only be redeemed before payment is recorded."
    if order.status == 'CANCELLED':
        return False, "Cancelled orders cannot redeem points."

    try:
        requested_points = int(requested_points or 0)
    except (TypeError, ValueError):
        requested_points = 0
    requested_points = max(0, requested_points)
    requested_points = (requested_points // POINTS_PER_REWARD) * POINTS_PER_REWARD
    if requested_points <= 0:
        return False, "Redeem at least 10 points."
    if requested_points > customer.loyalty_points:
        return False, "Customer does not have enough points."

    order.calculate_totals()
    max_discountable = max(order.subtotal + order.pickup_fee + order.delivery_fee - order.discount, 0)
    max_rewards_by_total = int(max_discountable // DISCOUNT_PER_REWARD)
    max_points_by_total = max_rewards_by_total * POINTS_PER_REWARD
    points_to_redeem = min(requested_points, max_points_by_total)
    if points_to_redeem <= 0:
        return False, "Order total is too low for a rewards discount."

    discount_amount = (points_to_redeem // POINTS_PER_REWARD) * DISCOUNT_PER_REWARD
    customer.loyalty_points -= points_to_redeem
    customer.points_last_transaction_at = timezone.now()
    customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])

    order.points_redeemed += points_to_redeem
    order.points_discount = round(order.points_discount + discount_amount, 2)
    order.discount = round(order.discount + discount_amount, 2)
    order.calculate_totals()
    order.save(update_fields=[
        'points_redeemed', 'points_discount', 'discount', 'laundry_fee',
        'subtotal', 'total_amount', 'price', 'balance', 'overpayment',
        'payment_status', 'updated_at',
    ])

    RewardTransaction.objects.create(
        customer=customer,
        order=order,
        transaction_type=RewardTransaction.REDEEM,
        points=-points_to_redeem,
        discount_amount=discount_amount,
        service_type=order.service_type,
        description=f"Redeemed {points_to_redeem} points for Order #{order.id}.",
    )
    return True, f"Redeemed {points_to_redeem} points for a {discount_amount:.2f} discount."


def award_points_for_order(order):
    if (
        order.points_awarded
        or order.status != 'COMPLETED'
        or order.payment_status != 'PAID'
        or order.customer_id is None
    ):
        return False

    customer = order.customer
    expire_customer_points(customer)
    customer.refresh_from_db(fields=['loyalty_points', 'points_last_transaction_at'])

    customer.loyalty_points += POINTS_PER_COMPLETED_ORDER
    customer.points_last_transaction_at = timezone.now()
    customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])
    order.points_awarded = True
    order.save(update_fields=['points_awarded', 'updated_at'])
    RewardTransaction.objects.create(
        customer=customer,
        order=order,
        transaction_type=RewardTransaction.EARN,
        points=POINTS_PER_COMPLETED_ORDER,
        service_type=order.service_type,
        description=f"Earned points from completed paid Order #{order.id}.",
    )
    return True


def notify_customer_order_update(order):
    customer = order.customer
    recipient = (customer.email or '').strip()
    if not recipient:
        return False

    site_name = SiteSettings.load().site_name
    tracking_url = build_tracking_url(order)
    subject = None
    body = None

    if order.order_type == 'PICKUP_DELIVERY' and order.status == 'PICKUP_CONFIRMED':
        subject = f"{site_name}: We are going to pick up your laundry"
        body = (
            f"Hi {customer.name},\n\n"
            f"Your pickup request for order #{order.id} has been accepted. "
            f"Our staff is going to pick up your laundry.\n\n"
            f"You can track it here: {tracking_url}\n\n"
            f"Thank you,\n{site_name}"
        )
    elif order.status == 'PROCESSING':
        subject = f"{site_name}: Your laundry is being processed"
        body = (
            f"Hi {customer.name},\n\n"
            f"Your laundry order #{order.id} is now being washed and processed.\n\n"
            f"You can track it here: {tracking_url}\n\n"
            f"Thank you,\n{site_name}"
        )
    elif order.order_type == 'WALK_IN' and order.status == 'READY_FOR_PICKUP':
        subject = f"{site_name}: Your laundry is ready for pickup"
        body = (
            f"Hi {customer.name},\n\n"
            f"Good news! Your walk-in laundry order #{order.id} is done and ready for pickup.\n\n"
            f"You can track it here: {tracking_url}\n\n"
            f"Thank you,\n{site_name}"
        )
    elif order.order_type == 'PICKUP_DELIVERY' and order.status == 'READY_FOR_DELIVERY':
        subject = f"{site_name}: Your laundry is done processing"
        body = (
            f"Hi {customer.name},\n\n"
            f"Good news! Your laundry order #{order.id} is done washing and processing. "
            f"We are preparing it for delivery.\n\n"
            f"You can track it here: {tracking_url}\n\n"
            f"Thank you,\n{site_name}"
        )
    elif order.order_type == 'PICKUP_DELIVERY' and order.status == 'OUT_FOR_DELIVERY':
        subject = f"{site_name}: Your laundry is out for delivery"
        body = (
            f"Hi {customer.name},\n\n"
            f"Your laundry order #{order.id} is now out for delivery.\n\n"
            f"You can track it here: {tracking_url}\n\n"
            f"Thank you,\n{site_name}"
        )

    if not subject or not body:
        return False

    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
        fail_silently=True,
    )
    return True


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
    summary = ', '.join(f"{quantity} {item.unit} {item.name}" for item, quantity in deductions)
    log_activity(
        user,
        'INVENTORY',
        'DEDUCT',
        f"Auto deducted inventory for Order #{order.id}: {summary}.",
        order,
    )
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
    if next_status == 'OUT_FOR_DELIVERY' and order.payment_method != 'CASH_AFTER_DELIVERY' and order.payment_status != 'PAID':
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
    order.save()
    notify_customer_order_update(order)
    award_points_for_order(order)
    return True


def generate_order_summary_qr_for_order(order):
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


def generate_qr_for_order(order):
    if not order.tracking_number:
        order.tracking_number = Order._meta.get_field('tracking_number').get_default()
        order.save(update_fields=['tracking_number', 'updated_at'])

    tracking_url = build_tracking_url(order)
    qr = qrcode.make(tracking_url)
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
    order.save(update_fields=update_fields)
    award_points_for_order(order)


# ── Auth ──────────────────────────────────
# ── Admin Dashboard ───────────────────────
# ── Staff Dashboard ───────────────────────
# ── Kanban Board ──────────────────────────
# ── Customer List ─────────────────────────
def track_order(request):
    order, error = None, None
    tracking_number = (
        request.GET.get('tracking_number')
        or request.POST.get('tracking_number', '')
    ).strip().upper()
    if tracking_number:
        try:
            order = Order.objects.select_related('customer').get(tracking_number=tracking_number)
        except Order.DoesNotExist:
            error = "No order found with that tracking number."
    return render(request, 'laundry/track_order.html', {
        'order': order,
        'error': error,
        'tracking_number': tracking_number,
    })


# ── Staff List ────────────────────────────
# ── Add Staff ─────────────────────────────
# ── Toggle Staff ──────────────────────────
# ── Reset Password ────────────────────────
# ── Edit Order ────────────────────────────
