import csv
from datetime import date as date_type, datetime, time
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, IntegerField, Q, Sum, When
from django.db.models.functions import TruncDate
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.utils import timezone
import io
import json
import os
import qrcode

from django.conf import settings
from django.core.files.base import ContentFile

from .models import Customer, InventoryCategory, InventoryItem, Order, Payment, PricingConfig, ServiceInventoryUsage, StockMovement

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
def admin_login(request):
    if request.user.is_authenticated:
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(request,
                            username=request.POST.get('username', '').strip(),
                            password=request.POST.get('password', ''))
        if user and is_admin(user):
            auth_login(request, user)
            return redirect('admin_dashboard')
        error = "Invalid credentials or not an admin account."
    return render(request, 'admin_login.html', {'error': error})


def staff_login(request):
    if request.user.is_authenticated:
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(request,
                            username=request.POST.get('username', '').strip(),
                            password=request.POST.get('password', ''))
        if user and is_customer_user(user):
            error = "Please use the customer login page."
        elif user and not is_admin(user):
            auth_login(request, user)
            return redirect('staff_dashboard')
        elif user and is_admin(user):
            error = "Please use the admin login page."
        else:
            error = "Invalid username or password."
    return render(request, 'staff_login.html', {'error': error})


def customer_register(request):
    if request.user.is_authenticated:
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        email = request.POST.get('email', '').strip().lower()
        address = request.POST.get('address', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not all([name, contact, email, address, password1, password2]):
            messages.error(request, "Please complete all required fields.")
            return render(request, 'customer_register.html')
        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'customer_register.html')
        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, 'customer_register.html')
        if User.objects.filter(username__iexact=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, 'customer_register.html')

        existing_customer = Customer.objects.filter(
            Q(email__iexact=email) | Q(contact=contact)
        ).first()
        if existing_customer and existing_customer.user_id:
            messages.error(request, "A customer account already exists for this email or contact number.")
            return render(request, 'customer_register.html')

        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password1,
                first_name=name,
            )
            customer_group, _ = Group.objects.get_or_create(name='Customer')
            user.groups.add(customer_group)

            if existing_customer:
                existing_customer.user = user
                existing_customer.name = name
                existing_customer.contact = contact
                existing_customer.email = email
                existing_customer.address = address
                existing_customer.is_walk_in = False
                existing_customer.save()
                customer = existing_customer
            else:
                customer = Customer.objects.create(
                    user=user,
                    name=name,
                    contact=contact,
                    email=email,
                    address=address,
                    is_walk_in=False,
                )

        auth_login(request, user)
        messages.success(request, f"Welcome, {customer.name}. You can now request pickup and delivery.")
        return redirect('customer_dashboard')

    return render(request, 'customer_register.html')


def customer_login(request):
    if request.user.is_authenticated:
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, username=email, password=password)
        if user and is_customer_user(user):
            auth_login(request, user)
            return redirect('customer_dashboard')
        if user:
            error = "Please use the staff or admin login page."
        else:
            error = "Invalid email or password."
    return render(request, 'customer_login.html', {'error': error})


@customer_required
def customer_dashboard(request):
    customer = request.user.customer_profile
    orders = customer.orders.order_by('-created_at')[:10]
    active_orders = customer.orders.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    return render(request, 'customer_dashboard.html', {
        'customer': customer,
        'orders': orders,
        'active_orders': active_orders,
    })


@customer_required
def customer_order_history(request):
    customer = request.user.customer_profile
    orders = customer.orders.order_by('-created_at')
    return render(request, 'customer_order_history.html', {
        'customer': customer,
        'orders': orders,
    })


@customer_required
def customer_order_detail(request, order_id):
    customer = request.user.customer_profile
    order = get_object_or_404(customer.orders, id=order_id)
    return render(request, 'customer_order_detail.html', {
        'customer': customer,
        'order': order,
        'config': PricingConfig.objects.first(),
    })


@customer_required
def customer_new_order(request):
    customer = request.user.customer_profile
    config = PricingConfig.objects.first()

    if request.method == 'POST':
        service_type = request.POST.get('service_type', 'WASH_DRY_FOLD')
        weight_raw = request.POST.get('weight', '').strip()
        pickup_address = request.POST.get('pickup_address', '').strip()
        delivery_address = request.POST.get('delivery_address', '').strip()
        preferred_pickup_raw = request.POST.get('preferred_pickup_at', '').strip()
        special_instructions = request.POST.get('special_instructions', '').strip() or None
        payment_method = request.POST.get('payment_method', 'CASH_AFTER_DELIVERY')

        if not pickup_address or not delivery_address or not preferred_pickup_raw:
            messages.error(request, "Pickup address, delivery address, and preferred pickup time are required.")
            return render(request, 'customer_new_order.html', {
                'customer': customer,
                'config': config,
                'service_choices': Order.SERVICE_CHOICES,
                'payment_methods': Order.PAYMENT_METHOD_CHOICES,
            })

        try:
            weight = float(weight_raw) if weight_raw else 0
        except ValueError:
            messages.error(request, "Estimated weight must be a number.")
            return redirect('customer_new_order')
        if weight < 0:
            messages.error(request, "Estimated weight cannot be negative.")
            return redirect('customer_new_order')

        preferred_pickup_at = parse_datetime(preferred_pickup_raw)
        if preferred_pickup_at is None:
            messages.error(request, "Invalid preferred pickup time.")
            return redirect('customer_new_order')
        if timezone.is_naive(preferred_pickup_at):
            preferred_pickup_at = timezone.make_aware(preferred_pickup_at)

        today = timezone.now().date()
        queue_number = orders_created_on(today).count() + 1

        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP_DELIVERY',
            status='PENDING_PICKUP',
            service_type=service_type,
            weight=0,
            price=0,
            price_per_kg=config.price_per_kg if config else 30.0,
            total_amount=0,
            amount_paid=0,
            balance=0,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            preferred_pickup_at=preferred_pickup_at,
            estimated_pickup=preferred_pickup_at,
            special_instructions=special_instructions,
            payment_method=payment_method,
            payment_status='UNPAID',
            queue_number=queue_number,
        )
        customer.loyalty_points += 1
        customer.save(update_fields=['loyalty_points'])
        generate_qr_for_order(order)
        messages.success(request, f"Pickup request #{order.id} submitted.")
        return redirect('customer_order_detail', order_id=order.id)

    return render(request, 'customer_new_order.html', {
        'customer': customer,
        'config': config,
        'service_choices': Order.SERVICE_CHOICES,
        'payment_methods': Order.PAYMENT_METHOD_CHOICES,
    })


@customer_required
def customer_profile(request):
    customer = request.user.customer_profile
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        email = request.POST.get('email', '').strip().lower()
        address = request.POST.get('address', '').strip()

        if not all([name, contact, email, address]):
            messages.error(request, "Name, contact, email, and address are required.")
            return redirect('customer_profile')

        email_taken = User.objects.filter(username__iexact=email).exclude(id=request.user.id).exists()
        if email_taken:
            messages.error(request, "That email is already used by another account.")
            return redirect('customer_profile')

        request.user.username = email
        request.user.email = email
        request.user.first_name = name
        request.user.save(update_fields=['username', 'email', 'first_name'])

        customer.name = name
        customer.contact = contact
        customer.email = email
        customer.address = address
        customer.save(update_fields=['name', 'contact', 'email', 'address'])
        messages.success(request, "Profile updated.")
        return redirect('customer_profile')

    return render(request, 'customer_profile.html', {'customer': customer})


# ── Admin Dashboard ───────────────────────
@login_required
def admin_dashboard(request):
    if not is_admin(request.user):
        return redirect('staff_dashboard')

    today = timezone.now().date()
    today_qs = orders_created_on(today)
    today_stats = {
        'total':       today_qs.count(),
        'pending':     today_qs.filter(status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED']).count(),
        'in_progress': today_qs.filter(status__in=['PICKED_UP', 'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING']).count(),
        'ready':       today_qs.filter(status__in=['READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY']).count(),
        'revenue':     today_qs.aggregate(t=Sum('total_amount'))['t'] or 0,
    }

    orders = Order.objects.select_related('customer', 'assigned_to').all().order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        orders = orders.filter(customer__name__icontains=search)

    tab = request.GET.get('tab', '')
    if tab == 'pending':
        orders = orders.filter(status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED'])
    elif tab == 'in_progress':
        orders = orders.filter(status__in=['PICKED_UP', 'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING'])
    elif tab == 'ready':
        orders = orders.filter(status__in=['READY_FOR_PICKUP', 'READY_FOR_DELIVERY'])
    elif tab == 'pickup':
        orders = orders.filter(status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP'])
    elif tab == 'delivery':
        orders = orders.filter(status='OUT_FOR_DELIVERY')
    elif tab == 'delivered':
        orders = orders.filter(status__in=['DELIVERED', 'COMPLETED'])

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    priority_filter = request.GET.get('priority', '')
    if priority_filter == 'rush':
        orders = orders.filter(is_priority=True)
    elif priority_filter == 'standard':
        orders = orders.filter(is_priority=False)

    order_type_filter = request.GET.get('order_type', '')
    if order_type_filter:
        orders = orders.filter(order_type=order_type_filter)

    date_filter = request.GET.get('date', '')
    if date_filter == 'today':
        start, end = local_day_range(today)
        orders = orders.filter(created_at__gte=start, created_at__lt=end)
    elif date_filter == 'week':
        start, _end = local_day_range(today - timezone.timedelta(days=7))
        orders = orders.filter(created_at__gte=start)
    elif date_filter == 'month':
        start, _end = local_day_range(today - timezone.timedelta(days=30))
        orders = orders.filter(created_at__gte=start)

    total_orders = orders.count()
    total_revenue = orders.aggregate(t=Sum('total_amount'))['t'] or 0
    pending_orders = orders.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    total_customers = Customer.objects.count()
    unpaid_orders = orders.filter(payment_status__in=['UNPAID', 'PARTIAL', 'PENDING_VERIFICATION']).exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    unpaid_revenue = orders.filter(payment_status__in=['UNPAID', 'PARTIAL']).aggregate(t=Sum('balance'))['t'] or 0
    recent_orders = Order.objects.select_related('customer').order_by('-created_at')[:5]

    # Weekly chart data
    last_7 = [today - timezone.timedelta(days=i) for i in range(6, -1, -1)]
    daily_rev = (Order.objects.filter(created_at__date__gte=last_7[0])
                 .annotate(d=TruncDate('created_at')).values('d')
                 .annotate(t=Sum('total_amount')).order_by('d'))
    rev_map = {e['d']: e['t'] for e in daily_rev}
    daily_cnt = (Order.objects.filter(created_at__date__gte=last_7[0])
                 .annotate(d=TruncDate('created_at')).values('d')
                 .annotate(c=Count('id')).order_by('d'))
    cnt_map = {e['d']: e['c'] for e in daily_cnt}

    service_counts = Order.objects.values('service_type').annotate(c=Count('id'))

    paginator = Paginator(orders, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'admin_dashboard.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'today_stats': today_stats,
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'pending_orders': pending_orders,
        'total_customers': total_customers,
        'unpaid_orders': unpaid_orders,
        'unpaid_revenue': unpaid_revenue,
        'recent_orders': recent_orders,
        'is_admin': True,
        'search': search,
        'tab': tab,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'order_type_filter': order_type_filter,
        'date_filter': date_filter,
        'status_choices': Order.STATUS_CHOICES,
        'order_type_choices': Order.ORDER_TYPE_CHOICES,
        'week_labels': json.dumps([d.strftime('%b %d') for d in last_7]),
        'week_revenue': json.dumps([float(rev_map.get(d, 0)) for d in last_7]),
        'week_orders': json.dumps([cnt_map.get(d, 0) for d in last_7]),
        'service_labels': json.dumps([s['service_type'] for s in service_counts]),
        'service_data': json.dumps([s['c'] for s in service_counts]),
    })


# ── Staff Dashboard ───────────────────────
@login_required
def staff_dashboard(request):
    if is_admin(request.user):
        return redirect('admin_dashboard')
    return redirect('delivery_tasks')


def render_staff_task_dashboard(request, order_type, task_title, clear_url_name):
    if is_admin(request.user):
        return redirect('admin_dashboard')

    orders = Order.objects.select_related('customer').filter(
        order_type=order_type,
        status__in=[
            'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP',
            'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING',
            'READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED'
        ]
    ).order_by('-is_priority', 'created_at')

    search = request.GET.get('search', '').strip()
    if search:
        orders = orders.filter(customer__name__icontains=search)

    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)

    if order_type == 'PICKUP_DELIVERY':
        workflow_statuses = [
            'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP', 'RECEIVED_AT_SHOP',
            'WEIGHED', 'BILL_SENT', 'PROCESSING', 'READY_FOR_DELIVERY',
            'OUT_FOR_DELIVERY', 'DELIVERED',
        ]
    else:
        workflow_statuses = [
            'RECEIVED_AT_SHOP', 'WEIGHED', 'PROCESSING', 'READY_FOR_PICKUP',
        ]
    workflow_meta = {
        'PENDING_PICKUP':      ('Pending Pickup',   'bi-calendar-check', '#f59f00', 'warning'),
        'PICKUP_CONFIRMED':   ('Pickup Confirmed', 'bi-person-check',   '#0d6efd', 'primary'),
        'PICKED_UP':          ('Picked Up',        'bi-truck',          '#17a2b8', 'info'),
        'RECEIVED_AT_SHOP':   ('Received at Shop', 'bi-inbox',          '#6c757d', 'secondary'),
        'WEIGHED':            ('Weighed',          'bi-speedometer2',   '#17a2b8', 'info'),
        'BILL_SENT':          ('Bill Sent',        'bi-receipt',        '#0d6efd', 'primary'),
        'PROCESSING':         ('Processing',       'bi-droplet',        '#ffc107', 'warning'),
        'READY_FOR_PICKUP':   ('Ready for Pickup', 'bi-bag-check',      '#198754', 'success'),
        'READY_FOR_DELIVERY': ('Ready for Delivery','bi-bag-check',     '#198754', 'success'),
        'OUT_FOR_DELIVERY':   ('Out for Delivery', 'bi-truck-front',    '#6610f2', 'primary'),
        'DELIVERED':          ('Delivered',        'bi-check-circle',   '#198754', 'success'),
    }
    workflow_columns = [
        {
            'key': status,
            'label': workflow_meta[status][0],
            'icon': workflow_meta[status][1],
            'color': workflow_meta[status][2],
            'badge': workflow_meta[status][3],
            'orders': orders.filter(status=status),
            'count': orders.filter(status=status).count(),
        }
        for status in workflow_statuses
    ]

    total_orders = orders.count()
    pending_orders = orders.filter(status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED']).count()
    delivery_count = Order.objects.filter(
        order_type='PICKUP_DELIVERY',
        status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP', 'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED'],
    ).count()
    walkin_count = Order.objects.filter(
        order_type='WALK_IN',
        status__in=['RECEIVED_AT_SHOP', 'WEIGHED', 'PROCESSING', 'READY_FOR_PICKUP'],
    ).count()

    paginator = Paginator(orders, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'staff_dashboard.html', {
        'orders': page_obj,
        'page_obj': page_obj,
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'delivery_count': delivery_count,
        'walkin_count': walkin_count,
        'task_title': task_title,
        'clear_url_name': clear_url_name,
        'task_type': order_type,
        'workflow_columns': workflow_columns,
        'is_admin': False,
        'search': search,
        'status_filter': status_filter,
        'status_choices': Order.STATUS_CHOICES,
    })


@login_required
def delivery_tasks(request):
    return render_staff_task_dashboard(request, 'PICKUP_DELIVERY', 'Delivery Task', 'delivery_tasks')


@login_required
def walkin_tasks(request):
    return render_staff_task_dashboard(request, 'WALK_IN', 'Walk-in Task', 'walkin_tasks')


# ── Kanban Board ──────────────────────────
@login_required
def kanban_board(request):
    active = [
        'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP',
        'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING',
        'READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED'
    ]
    columns = {
        s: Order.objects.filter(status=s)
                .select_related('customer', 'assigned_to')
                .order_by('-is_priority', 'due_date', 'created_at')
        for s in active
    }
    meta = {
        'PENDING_PICKUP':  ('Pending Pickup',   'bi-calendar-check', '#f59f00', 'warning'),
        'PICKUP_CONFIRMED':('Pickup Confirmed', 'bi-person-check',   '#0d6efd', 'primary'),
        'PICKED_UP':       ('Picked Up',        'bi-truck',          '#17a2b8', 'info'),
        'RECEIVED_AT_SHOP':('Received at Shop', 'bi-inbox',          '#6c757d', 'secondary'),
        'WEIGHED':         ('Weighed',          'bi-speedometer2',   '#17a2b8', 'info'),
        'BILL_SENT':       ('Bill Sent',        'bi-receipt',        '#0d6efd', 'primary'),
        'PROCESSING':      ('Processing',       'bi-droplet',        '#ffc107', 'warning'),
        'READY_FOR_PICKUP':  ('Ready for Pickup','bi-bag-check',     '#198754', 'success'),
        'READY_FOR_DELIVERY':('Ready for Delivery','bi-bag-check',   '#198754', 'success'),
        'OUT_FOR_DELIVERY':('Out for Delivery', 'bi-truck-front',    '#6610f2', 'primary'),
        'DELIVERED':       ('Delivered',        'bi-check-circle',   '#198754', 'success'),
    }
    kanban_columns = [
        {
            'key':    s,
            'label':  meta[s][0],
            'icon':   meta[s][1],
            'color':  meta[s][2],
            'badge':  meta[s][3],
            'orders': columns[s],
            'count':  columns[s].count(),
        }
        for s in active
    ]
    total_active = sum(c['count'] for c in kanban_columns)
    return render(request, 'kanban.html', {
        'kanban_columns': kanban_columns,
        'total_active': total_active,
        'is_admin': is_admin(request.user),
    })


# ── Customer List ─────────────────────────
@login_required
def customer_list(request):
    search = request.GET.get('search', '').strip()
    customers = Customer.objects.annotate(
        order_count=Count('orders')
    ).order_by('-created_at')

    if search:
        customers = customers.filter(
            Q(name__icontains=search) | Q(contact__icontains=search) | Q(email__icontains=search)
        )

    paginator = Paginator(customers, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'customer_list.html', {
        'customers': page_obj,
        'page_obj': page_obj,
        'search': search,
        'total_customers': Customer.objects.count(),
        'is_admin': is_admin(request.user),
    })


# ── Add Customer ─────────────────────────
@login_required
def add_customer(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        if not name or not contact:
            messages.error(request, "Name and contact are required.")
            return render(request, 'add_customer.html', {'is_admin': is_admin(request.user)})
        Customer.objects.create(
            name=name,
            contact=contact,
            email=request.POST.get('email', '').strip() or None,
            address=request.POST.get('address', '').strip() or None,
            notes=request.POST.get('notes', '').strip() or None,
            is_walk_in='is_walk_in' in request.POST,
        )
        messages.success(request, f"Customer '{name}' added.")
        return redirect('customer_list')
    return render(request, 'add_customer.html', {'is_admin': is_admin(request.user)})


# ── Edit Customer ─────────────────────────
@login_required
def edit_customer(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.method == 'POST':
        customer.name = request.POST.get('name', customer.name).strip()
        customer.contact = request.POST.get('contact', customer.contact).strip()
        customer.email = request.POST.get('email', '').strip() or None
        customer.address = request.POST.get('address', '').strip() or None
        customer.notes = request.POST.get('notes', '').strip() or None
        customer.is_walk_in = 'is_walk_in' in request.POST
        customer.save()
        messages.success(request, f"Customer '{customer.name}' updated.")
        return redirect('customer_detail', customer_id=customer.id)
    return render(request, 'edit_customer.html', {
        'customer': customer,
        'is_admin': is_admin(request.user),
    })


# ── Add Order ────────────────────────────
@login_required
def add_order(request):
    customers = Customer.objects.all().order_by('name')
    config = PricingConfig.objects.first()
    staff_users = User.objects.filter(is_active=True).order_by('username')

    if request.method == 'POST':
        customer_id = request.POST.get('customer')
        service_type = request.POST.get('service_type', 'WASH_DRY_FOLD')
        is_priority = 'priority' in request.POST
        payment_method = request.POST.get('payment_method', 'CASH_AFTER_DELIVERY')
        amount_paid_raw = request.POST.get('amount_paid', '').strip()
        special_instructions = request.POST.get('special_instructions', '').strip() or None
        assigned_to_id = request.POST.get('assigned_to') or None
        due_date_raw = request.POST.get('due_date', '').strip()

        try:
            weight = float(request.POST.get('weight', 0))
        except ValueError:
            messages.error(request, "Invalid weight.")
            return render(request, 'add_order.html', {
                'customers': customers, 'config': config,
                'staff_users': staff_users, 'service_choices': Order.SERVICE_CHOICES,
                'payment_methods': Order.PAYMENT_METHOD_CHOICES, 'is_admin': is_admin(request.user)
            })

        if weight <= 0:
            messages.error(request, "Weight must be greater than 0 kg.")
            return render(request, 'add_order.html', {
                'customers': customers, 'config': config,
                'staff_users': staff_users, 'service_choices': Order.SERVICE_CHOICES,
                'payment_methods': Order.PAYMENT_METHOD_CHOICES, 'is_admin': is_admin(request.user)
            })

        try:
            amount_paid = float(amount_paid_raw) if amount_paid_raw else 0.0
        except ValueError:
            amount_paid = 0.0

        estimated_pickup = timezone.now() + timezone.timedelta(hours=2 if is_priority else 24)

        due_date = None
        if due_date_raw:
            from django.utils.dateparse import parse_datetime
            due_date = parse_datetime(due_date_raw)

        today = timezone.now().date()
        queue_number = orders_created_on(today).count() + 1

        order = Order.objects.create(
            customer_id=customer_id,
            order_type='WALK_IN',
            status='WEIGHED',
            weight=weight,
            price_per_kg=config.price_per_kg if config else 30.0,
            extra_fee=config.rush_surcharge if (config and is_priority) else (50.0 if is_priority else 0.0),
            is_priority=is_priority,
            service_type=service_type,
            estimated_pickup=estimated_pickup,
            due_date=due_date,
            created_by=request.user,
            assigned_to_id=assigned_to_id,
            payment_method=payment_method,
            payment_status='UNPAID',
            amount_paid=0,
            queue_number=queue_number,
            special_instructions=special_instructions,
        )
        order.calculate_totals()
        if amount_paid > 0:
            Payment.objects.create(
                order=order,
                payment_method=payment_method,
                amount=amount_paid,
                status='VERIFIED',
                received_by=request.user,
                verified_by=request.user if payment_method == 'GCASH' else None,
                paid_at=timezone.now(),
            )
            order.amount_paid = amount_paid
            order.update_payment_status_from_amount()
        order.save()

        # Award 1 loyalty point per order
        order.customer.loyalty_points += 1
        order.customer.save(update_fields=['loyalty_points'])

        generate_qr_for_order(order)
        messages.success(request, f"Order #{order.id} (Q#{queue_number}) created for {order.customer.name}!")
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    return render(request, 'add_order.html', {
        'customers': customers,
        'config': config,
        'staff_users': staff_users,
        'service_choices': Order.SERVICE_CHOICES,
        'payment_methods': Order.PAYMENT_METHOD_CHOICES,
        'is_admin': is_admin(request.user),
    })


# ── Update Status ────────────────────────
@login_required
def update_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status == 'PENDING_PICKUP':
        messages.error(request, "Pending pickup requests must be accepted or declined by staff.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    next_status = order.get_next_status()
    if next_status == 'WEIGHED' and order.weight <= 0:
        messages.error(request, "Staff must enter the actual weight before total amount can be calculated.")
        return redirect('edit_order', order_id=order.id)
    if next_status == 'OUT_FOR_DELIVERY' and order.payment_status != 'PAID':
        messages.error(request, "Payment must be fully paid before the order can go out for delivery.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    if next_status == 'PROCESSING':
        ok, message = deduct_inventory_for_order(order, request.user)
        if not ok:
            messages.error(request, message)
            return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    if next_status == 'COMPLETED' and order.payment_status != 'PAID':
        messages.error(request, "Payment must be fully paid before completing the order.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    if advance_order_status(order, request.user):
        messages.success(request, f"Order #{order.id} → {order.get_status_display()}")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))


@login_required
def accept_pickup_request(request, order_id):
    if is_admin(request.user):
        return HttpResponseForbidden()
    order = get_object_or_404(Order, id=order_id, order_type='PICKUP_DELIVERY')
    if order.status != 'PENDING_PICKUP':
        messages.error(request, "Only pending pickup requests can be accepted.")
        return redirect('staff_dashboard')
    if request.method != 'POST':
        return redirect('staff_dashboard')

    order.status = 'PICKUP_CONFIRMED'
    order.assigned_to = request.user
    order.decline_reason = None
    order.declined_at = None
    order.save(update_fields=['status', 'assigned_to', 'decline_reason', 'declined_at', 'updated_at'])
    messages.success(request, f"Pickup request #{order.id} accepted and assigned to you.")
    return redirect('staff_dashboard')


@login_required
def decline_pickup_request(request, order_id):
    if is_admin(request.user):
        return HttpResponseForbidden()
    order = get_object_or_404(Order, id=order_id, order_type='PICKUP_DELIVERY')
    if order.status != 'PENDING_PICKUP':
        messages.error(request, "Only pending pickup requests can be declined.")
        return redirect('staff_dashboard')
    if request.method != 'POST':
        return redirect('staff_dashboard')

    reason = request.POST.get('decline_reason', '').strip()
    if not reason:
        messages.error(request, "Please enter a reason before declining the pickup request.")
        return redirect('staff_dashboard')

    order.status = 'CANCELLED'
    order.payment_status = 'CANCELLED'
    order.decline_reason = reason
    order.declined_at = timezone.now()
    order.assigned_to = request.user
    order.save(update_fields=['status', 'payment_status', 'decline_reason', 'declined_at', 'assigned_to', 'updated_at'])
    order.payments.filter(status='PENDING').update(status='CANCELLED')
    messages.success(request, f"Pickup request #{order.id} declined.")
    return redirect('staff_dashboard')


# ── Bulk Update ───────────────────────────
@login_required
def bulk_update_status(request):
    if request.method == 'POST':
        order_ids = request.POST.getlist('order_ids')
        action = request.POST.get('bulk_action', '')
        if not order_ids:
            messages.error(request, "No orders selected.")
        elif action == 'advance':
            count = 0
            for oid in order_ids:
                order = Order.objects.filter(id=oid).first()
                if order and order.status != 'PENDING_PICKUP' and advance_order_status(order, request.user):
                    count += 1
            messages.success(request, f"{count} order(s) advanced.")
        elif action == 'mark_paid':
            count = 0
            for oid in order_ids:
                order = Order.objects.filter(id=oid).exclude(payment_status='PAID').first()
                if order and order.total_amount > 0:
                    if order.payment_method == 'GCASH':
                        continue
                    amount = order.balance or order.total_amount
                    Payment.objects.create(
                        order=order,
                        payment_method=order.payment_method,
                        amount=amount,
                        status='VERIFIED',
                        received_by=request.user,
                        verified_by=request.user if order.payment_method == 'GCASH' else None,
                        paid_at=timezone.now(),
                    )
                    refresh_order_payment_from_verified_records(order)
                    count += 1
            messages.success(request, f"{count} order(s) marked as paid.")
    return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')


# ── Mark Paid ─────────────────────────────
@login_required
def mark_paid(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.total_amount <= 0:
        messages.error(request, "Final bill must be calculated before payment can be confirmed.")
        return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))
    if order.payment_method == 'GCASH':
        messages.error(request, "GCash payments must be submitted with proof and verified by staff.")
        return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))
    Payment.objects.create(
        order=order,
        payment_method=order.payment_method,
        amount=order.balance or order.total_amount,
        status='VERIFIED',
        received_by=request.user,
        verified_by=request.user if order.payment_method == 'GCASH' else None,
        paid_at=timezone.now(),
    )
    refresh_order_payment_from_verified_records(order)
    messages.success(request, f"Order #{order.id} marked as paid.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))


@customer_required
def submit_gcash_payment(request, order_id):
    customer = request.user.customer_profile
    order = get_object_or_404(customer.orders, id=order_id, payment_method='GCASH')
    if request.method != 'POST':
        return redirect('customer_order_detail', order_id=order.id)
    try:
        amount = float(request.POST.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        messages.error(request, "Enter the amount paid through GCash.")
        return redirect('customer_order_detail', order_id=order.id)
    payment = Payment.objects.create(
        order=order,
        payment_method='GCASH',
        amount=amount,
        reference_number=request.POST.get('reference_number', '').strip() or None,
        proof_image=request.FILES.get('proof_image'),
        status='PENDING',
    )
    order.payment_status = 'PENDING_VERIFICATION'
    order.save(update_fields=['payment_status', 'updated_at'])
    messages.success(request, f"GCash payment proof #{payment.id} submitted for verification.")
    return redirect('customer_order_detail', order_id=order.id)


@login_required
def verify_payment(request, payment_id):
    if request.method != 'POST':
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
    payment = get_object_or_404(Payment, id=payment_id, payment_method='GCASH', status='PENDING')
    payment.status = 'VERIFIED'
    payment.verified_by = request.user
    payment.paid_at = timezone.now()
    payment.save(update_fields=['status', 'verified_by', 'paid_at', 'updated_at'])
    refresh_order_payment_from_verified_records(payment.order)
    messages.success(request, f"GCash payment #{payment.id} verified.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))


@login_required
def reject_payment(request, payment_id):
    if request.method != 'POST':
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
    payment = get_object_or_404(Payment, id=payment_id, payment_method='GCASH', status='PENDING')
    payment.status = 'REJECTED'
    payment.verified_by = request.user
    payment.save(update_fields=['status', 'verified_by', 'updated_at'])
    order = payment.order
    if not order.payments.filter(status='VERIFIED').exists():
        order.payment_status = 'REJECTED'
        order.save(update_fields=['payment_status', 'updated_at'])
    messages.success(request, f"GCash payment #{payment.id} rejected.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))


@login_required
def confirm_cod_payment(request, order_id):
    if is_admin(request.user):
        return HttpResponseForbidden()
    order = get_object_or_404(Order, id=order_id, payment_method='CASH_AFTER_DELIVERY')
    if request.method != 'POST':
        return redirect('staff_dashboard')
    try:
        amount = float(request.POST.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        messages.error(request, "Enter the cash amount received from the customer.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    Payment.objects.create(
        order=order,
        payment_method='CASH_AFTER_DELIVERY',
        amount=amount,
        status='VERIFIED',
        received_by=request.user,
        paid_at=timezone.now(),
    )
    refresh_order_payment_from_verified_records(order)
    messages.success(request, f"Cash payment recorded for Order #{order.id}.")
    return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))


# ── Pricing ───────────────────────────────
@login_required
def pricing_settings(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    config = PricingConfig.objects.first()
    if request.method == 'POST':
        try:
            ppk = float(request.POST['price_per_kg'])
            rush = float(request.POST['rush_surcharge'])
        except (ValueError, KeyError):
            messages.error(request, "Invalid values.")
            return redirect('pricing_settings')
        if ppk <= 0 or rush < 0:
            messages.error(request, "Price per kg must be positive.")
            return redirect('pricing_settings')
        if config:
            config.price_per_kg = ppk
            config.rush_surcharge = rush
            config.gcash_number = request.POST.get('gcash_number', '').strip() or None
            if request.FILES.get('gcash_qr'):
                config.gcash_qr = request.FILES['gcash_qr']
            config.save()
        else:
            PricingConfig.objects.create(
                price_per_kg=ppk,
                rush_surcharge=rush,
                gcash_number=request.POST.get('gcash_number', '').strip() or None,
                gcash_qr=request.FILES.get('gcash_qr'),
            )
        messages.success(request, "Pricing updated.")
        return redirect('pricing_settings')
    return render(request, 'pricing.html', {'config': config, 'is_admin': True})


# ── Customer Detail ───────────────────────
@login_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    orders = customer.orders.order_by('-created_at')
    return render(request, 'customer_detail.html', {
        'customer': customer,
        'orders': orders,
        'is_admin': is_admin(request.user),
    })


# ── Receipt ───────────────────────────────
@login_required
def order_receipt(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not order.qr_code:
        generate_qr_for_order(order)
        order.refresh_from_db()
    return render(request, 'receipt.html', {'order': order, 'is_admin': is_admin(request.user)})


# ── Reports ───────────────────────────────
@login_required
def reports(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()

    today = timezone.now().date()
    date_from_str = request.GET.get('date_from', '')
    date_to_str = request.GET.get('date_to', '')

    try:
        date_from = date_type.fromisoformat(date_from_str) if date_from_str else today - timezone.timedelta(days=6)
        date_to = date_type.fromisoformat(date_to_str) if date_to_str else today
    except ValueError:
        date_from = today - timezone.timedelta(days=6)
        date_to = today

    if date_from > date_to:
        date_from, date_to = date_to, date_from

    days_count = min((date_to - date_from).days + 1, 90)
    date_from = date_to - timezone.timedelta(days=days_count - 1)
    date_range = [date_from + timezone.timedelta(days=i) for i in range(days_count)]

    rev_qs = (Order.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
              .annotate(d=TruncDate('created_at')).values('d').annotate(t=Sum('total_amount')).order_by('d'))
    cnt_qs = (Order.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
              .annotate(d=TruncDate('created_at')).values('d').annotate(c=Count('id')).order_by('d'))

    rev_map = {e['d']: e['t'] for e in rev_qs}
    cnt_map = {e['d']: e['c'] for e in cnt_qs}

    status_counts = Order.objects.values('status').annotate(c=Count('id'))
    service_counts = Order.objects.values('service_type').annotate(c=Count('id'))

    total_revenue = Order.objects.aggregate(t=Sum('total_amount'))['t'] or 0
    total_orders = Order.objects.count()
    rush_orders = Order.objects.filter(is_priority=True).count()
    avg_value = round(total_revenue / total_orders, 2) if total_orders else 0

    return render(request, 'reports.html', {
        'is_admin': True,
        'revenue_labels':  json.dumps([d.strftime('%b %d') for d in date_range]),
        'revenue_data':    json.dumps([float(rev_map.get(d, 0)) for d in date_range]),
        'orders_data':     json.dumps([cnt_map.get(d, 0) for d in date_range]),
        'status_labels':   json.dumps([s['status'] for s in status_counts]),
        'status_data':     json.dumps([s['c'] for s in status_counts]),
        'service_labels':  json.dumps([s['service_type'] for s in service_counts]),
        'service_data':    json.dumps([s['c'] for s in service_counts]),
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'rush_orders': rush_orders,
        'avg_order_value': avg_value,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
    })


# ── Export CSV ────────────────────────────
@login_required
def export_csv(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="orders_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Queue #', 'Customer', 'Contact', 'Service',
                     'Weight (kg)', 'Total (PHP)', 'Status', 'Priority',
                     'Payment', 'Amount Paid', 'Balance', 'Created At', 'Est. Pickup', 'Completed At'])
    for o in Order.objects.select_related('customer').order_by('-created_at'):
        writer.writerow([
            o.id, o.queue_number, o.customer.name, o.customer.contact,
            o.get_service_type_display(), o.weight, o.total_amount,
            o.get_status_display(), 'Rush' if o.is_priority else 'Standard',
            o.payment_status, o.amount_paid, o.balance,
            o.created_at.strftime('%Y-%m-%d %H:%M'),
            o.estimated_pickup.strftime('%Y-%m-%d %H:%M') if o.estimated_pickup else '',
            o.claimed_at.strftime('%Y-%m-%d %H:%M') if o.claimed_at else '',
        ])
    return response


# ── Public Tracker ────────────────────────
def track_order(request):
    order, error = None, None
    order_id = (request.GET.get('order_id') or request.POST.get('order_id', '')).strip()
    if order_id:
        try:
            order = Order.objects.select_related('customer').get(id=int(order_id))
        except (Order.DoesNotExist, ValueError):
            error = f"No order found with ID #{order_id}."
    return render(request, 'track_order.html', {'order': order, 'error': error})


# ── Staff List ────────────────────────────
@login_required
def staff_list(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    return render(request, 'staff_list.html', {
        'staff': User.objects.all().order_by('-date_joined'),
        'is_admin': True,
    })


# ── Add Staff ─────────────────────────────
@login_required
def add_staff(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        role = request.POST.get('role', 'staff')
        if not username or not password:
            messages.error(request, "Username and password are required.")
            return redirect('add_staff')
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return redirect('add_staff')
        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
            return redirect('add_staff')
        user = User.objects.create_user(username=username, password=password)
        if role == 'admin':
            user.is_superuser = True
            user.is_staff = True
            user.save()
        else:
            group, _ = Group.objects.get_or_create(name='Staff')
            user.groups.add(group)
        messages.success(request, f"Account '{username}' created.")
        return redirect('staff_list')
    return render(request, 'add_staff.html', {'is_admin': True})


# ── Toggle Staff ──────────────────────────
@login_required
def toggle_staff(request, user_id):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        if user == request.user:
            messages.error(request, "Cannot deactivate your own account.")
            return redirect('staff_list')
        user.is_active = not user.is_active
        user.save()
        messages.success(request, f"'{user.username}' {'activated' if user.is_active else 'deactivated'}.")
    return redirect('staff_list')


# ── Reset Password ────────────────────────
@login_required
def reset_password(request, user_id):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        pw = request.POST.get('new_password', '')
        if len(pw) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return redirect('staff_list')
        user.set_password(pw)
        user.save()
        messages.success(request, f"Password for '{user.username}' reset.")
    return redirect('staff_list')


# ── Edit Order ────────────────────────────
@login_required
def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    customers = Customer.objects.all()
    config = PricingConfig.objects.first()
    staff_users = User.objects.filter(is_active=True).order_by('username')

    if request.method == 'POST':
        try:
            weight = float(request.POST.get('weight', 0))
        except ValueError:
            messages.error(request, "Invalid weight.")
            return render(request, 'edit_order.html', {
                'order': order, 'customers': customers, 'staff_users': staff_users,
                'service_choices': Order.SERVICE_CHOICES, 'payment_methods': Order.PAYMENT_METHOD_CHOICES,
                'is_admin': is_admin(request.user)
            })
        if weight < 0 or (order.order_type == 'WALK_IN' and weight <= 0):
            messages.error(request, "Weight must be greater than 0 kg.")
            return render(request, 'edit_order.html', {
                'order': order, 'customers': customers, 'staff_users': staff_users,
                'service_choices': Order.SERVICE_CHOICES, 'payment_methods': Order.PAYMENT_METHOD_CHOICES,
                'is_admin': is_admin(request.user)
            })

        order.customer_id = request.POST.get('customer')
        order.weight = weight
        order.service_type = request.POST.get('service_type', 'WASH_DRY_FOLD')
        order.is_priority = 'priority' in request.POST
        order.payment_method = request.POST.get('payment_method', order.payment_method)
        order.special_instructions = request.POST.get('special_instructions', '').strip() or None
        order.assigned_to_id = request.POST.get('assigned_to') or None
        order.pickup_address = request.POST.get('pickup_address', '').strip() or None
        order.delivery_address = request.POST.get('delivery_address', '').strip() or None
        order.delivery_notes = request.POST.get('delivery_notes', '').strip() or None

        due_date_raw = request.POST.get('due_date', '').strip()
        order.due_date = parse_datetime(due_date_raw) if due_date_raw else None
        if order.due_date and timezone.is_naive(order.due_date):
            order.due_date = timezone.make_aware(order.due_date)

        preferred_pickup_raw = request.POST.get('preferred_pickup_at', '').strip()
        order.preferred_pickup_at = parse_datetime(preferred_pickup_raw) if preferred_pickup_raw else order.preferred_pickup_at
        if order.preferred_pickup_at and timezone.is_naive(order.preferred_pickup_at):
            order.preferred_pickup_at = timezone.make_aware(order.preferred_pickup_at)

        order.price_per_kg = float(request.POST.get('price_per_kg') or (config.price_per_kg if config else 30.0))
        order.pickup_fee = float(request.POST.get('pickup_fee') or 0)
        order.delivery_fee = float(request.POST.get('delivery_fee') or 0)
        order.extra_fee = float(request.POST.get('extra_fee') or 0)
        if order.is_priority and order.extra_fee <= 0:
            order.extra_fee = config.rush_surcharge if config else 50.0
        order.discount = float(request.POST.get('discount') or 0)
        if order.weight > 0:
            order.calculate_totals()
            if order.status in ['RECEIVED_AT_SHOP', 'PICKED_UP', 'PICKUP_CONFIRMED']:
                order.status = 'WEIGHED'
            order.update_balance()

        order.save()
        messages.success(request, f"Order #{order.id} updated.")
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    return render(request, 'edit_order.html', {
        'order': order,
        'customers': customers,
        'staff_users': staff_users,
        'service_choices': Order.SERVICE_CHOICES,
        'payment_methods': Order.PAYMENT_METHOD_CHOICES,
        'is_admin': is_admin(request.user),
    })


# ── Delete Order ──────────────────────────
@login_required
def delete_order(request, order_id):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        num = order.id
        order.delete()
        messages.success(request, f"Order #{num} deleted.")
        return redirect('admin_dashboard')
    return redirect('edit_order', order_id=order.id)


# ═══════════════════════════════════════
# INVENTORY VIEWS
# ═══════════════════════════════════════

@login_required
def inventory_list(request):
    items = InventoryItem.objects.select_related('category').filter(is_active=True)

    search = request.GET.get('search', '').strip()
    if search:
        items = items.filter(Q(name__icontains=search) | Q(category__name__icontains=search))

    category_filter = request.GET.get('category', '')
    if category_filter:
        items = items.filter(category_id=category_filter)

    low_stock_filter = request.GET.get('low_stock', '')
    if low_stock_filter:
        items = items.filter(current_stock__lte=F('minimum_stock'))

    all_items = InventoryItem.objects.filter(is_active=True)
    total_items = all_items.count()
    low_stock_count = all_items.filter(current_stock__lte=F('minimum_stock')).count()
    total_value = all_items.aggregate(
        total=Sum(ExpressionWrapper(F('current_stock') * F('unit_cost'), output_field=FloatField()))
    )['total'] or 0
    categories = InventoryCategory.objects.all()

    return render(request, 'inventory.html', {
        'section': 'list',
        'items': items,
        'categories': categories,
        'total_items': total_items,
        'low_stock_count': low_stock_count,
        'total_value': round(total_value, 2),
        'category_count': categories.count(),
        'category_filter': category_filter,
        'low_stock_filter': low_stock_filter,
        'search': search,
        'is_admin': is_admin(request.user),
    })


@login_required
def add_inventory_item(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    categories = InventoryCategory.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category') or None
        new_cat = request.POST.get('new_category_name', '').strip()
        unit = request.POST.get('unit', 'pcs')

        try:
            current_stock = float(request.POST.get('current_stock', 0))
            minimum_stock = float(request.POST.get('minimum_stock', 0))
            unit_cost = float(request.POST.get('unit_cost', 0))
        except ValueError:
            messages.error(request, "Invalid numeric values.")
            return render(request, 'inventory.html', {
                'section': 'add', 'categories': categories, 'is_admin': True
            })

        if not name:
            messages.error(request, "Item name is required.")
            return render(request, 'inventory.html', {
                'section': 'add', 'categories': categories, 'is_admin': True
            })

        if new_cat:
            cat_obj, _ = InventoryCategory.objects.get_or_create(name=new_cat)
            category_id = cat_obj.id

        item = InventoryItem.objects.create(
            name=name, category_id=category_id, unit=unit,
            current_stock=current_stock, minimum_stock=minimum_stock, unit_cost=unit_cost,
        )
        if current_stock > 0:
            StockMovement.objects.create(
                item=item, movement_type='RESTOCK', quantity=current_stock,
                notes='Initial stock entry', performed_by=request.user,
            )
        messages.success(request, f"'{name}' added to inventory.")
        return redirect('inventory_detail', item_id=item.id)

    return render(request, 'inventory.html', {
        'section': 'add',
        'categories': categories,
        'unit_choices': InventoryItem.UNIT_CHOICES,
        'is_admin': True,
    })


@login_required
def inventory_detail(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    movements = StockMovement.objects.filter(item=item).select_related(
        'reference_order__customer', 'performed_by'
    ).order_by('-created_at')[:50]
    return render(request, 'inventory.html', {
        'section': 'detail',
        'item': item,
        'movements': movements,
        'is_admin': is_admin(request.user),
    })


@login_required
def restock_item(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    if request.method == 'POST':
        try:
            quantity = float(request.POST.get('quantity', 0))
        except ValueError:
            messages.error(request, "Invalid quantity.")
            return render(request, 'inventory.html', {
                'section': 'restock', 'item': item, 'is_admin': is_admin(request.user)
            })
        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0.")
            return render(request, 'inventory.html', {
                'section': 'restock', 'item': item, 'is_admin': is_admin(request.user)
            })
        notes = request.POST.get('notes', '').strip()
        item.current_stock = round(item.current_stock + quantity, 4)
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='RESTOCK', quantity=quantity,
            notes=notes or f"Restocked by {request.user.username}",
            performed_by=request.user,
        )
        messages.success(request, f"+{quantity} {item.unit} added to '{item.name}'. New stock: {item.current_stock}")
        return redirect('inventory_detail', item_id=item.id)
    return render(request, 'inventory.html', {
        'section': 'restock', 'item': item, 'is_admin': is_admin(request.user)
    })


@login_required
def deduct_stock(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    active_orders = Order.objects.filter(
        status__in=['RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING', 'READY_FOR_PICKUP', 'READY_FOR_DELIVERY']
    ).select_related('customer').order_by('-created_at')[:100]

    if request.method == 'POST':
        try:
            quantity = float(request.POST.get('quantity', 0))
        except ValueError:
            messages.error(request, "Invalid quantity.")
            return render(request, 'inventory.html', {
                'section': 'deduct', 'item': item,
                'active_orders': active_orders, 'is_admin': is_admin(request.user)
            })
        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0.")
            return render(request, 'inventory.html', {
                'section': 'deduct', 'item': item,
                'active_orders': active_orders, 'is_admin': is_admin(request.user)
            })
        notes = request.POST.get('notes', '').strip()
        reference_order_id = request.POST.get('reference_order') or None
        item.current_stock = round(max(0, item.current_stock - quantity), 4)
        item.save(update_fields=['current_stock'])
        StockMovement.objects.create(
            item=item, movement_type='DEDUCT', quantity=quantity,
            reference_order_id=reference_order_id,
            notes=notes or f"Deducted by {request.user.username}",
            performed_by=request.user,
        )
        messages.success(request, f"-{quantity} {item.unit} from '{item.name}'. Remaining: {item.current_stock}")
        return redirect('inventory_detail', item_id=item.id)
    return render(request, 'inventory.html', {
        'section': 'deduct', 'item': item,
        'active_orders': active_orders, 'is_admin': is_admin(request.user)
    })


@login_required
def service_inventory_usage(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()

    if request.method == 'POST':
        rule_id = request.POST.get('rule_id')
        service_type = request.POST.get('service_type')
        item_id = request.POST.get('item')
        try:
            quantity_per_kg = float(request.POST.get('quantity_per_kg') or 0)
            fixed_quantity = float(request.POST.get('fixed_quantity') or 0)
        except ValueError:
            messages.error(request, "Invalid quantity.")
            return redirect('service_inventory_usage')

        if service_type and item_id and (quantity_per_kg > 0 or fixed_quantity > 0):
            try:
                if rule_id:
                    usage = get_object_or_404(ServiceInventoryUsage, id=rule_id)
                    usage.service_type = service_type
                    usage.item_id = item_id
                    usage.quantity_per_kg = quantity_per_kg
                    usage.fixed_quantity = fixed_quantity
                    usage.is_active = 'is_active' in request.POST
                    usage.save()
                else:
                    usage, _ = ServiceInventoryUsage.objects.update_or_create(
                        service_type=service_type,
                        item_id=item_id,
                        defaults={
                            'quantity_per_kg': quantity_per_kg,
                            'fixed_quantity': fixed_quantity,
                            'is_active': 'is_active' in request.POST,
                        },
                    )
            except IntegrityError:
                messages.error(request, "A rule already exists for that service and item.")
                return redirect('service_inventory_usage')
            if rule_id:
                messages.success(request, f"Usage rule updated for {usage.get_service_type_display()} - {usage.item.name}.")
            else:
                messages.success(request, f"Usage rule saved for {usage.get_service_type_display()} - {usage.item.name}.")
        else:
            messages.error(request, "Choose a service, item, and at least one quantity.")
        return redirect('service_inventory_usage')

    service_sort = Case(
        When(service_type='WASH_DRY_FOLD', then=0),
        When(service_type='WASH_DRY', then=1),
        When(service_type='WASH', then=2),
        When(service_type='DRY_ONLY', then=3),
        When(service_type='IRON', then=4),
        When(service_type='EXPRESS', then=5),
        When(service_type='DRY_CLEAN', then=6),
        default=99,
        output_field=IntegerField(),
    )
    item_sort = Case(
        When(item__name='Laundry Detergent', then=0),
        When(item__name='Fabric Conditioner', then=1),
        When(item__name='Color-Safe Bleach', then=2),
        When(item__name='Disinfectant', then=3),
        When(item__name='Laundry Plastic Bags', then=4),
        When(item__name='Customer Tags', then=5),
        When(item__name='Dryer Sheets', then=6),
        When(item__name='Hangers', then=7),
        default=99,
        output_field=IntegerField(),
    )
    rules = (
        ServiceInventoryUsage.objects.select_related('item')
        .annotate(service_sort=service_sort, item_sort=item_sort)
        .order_by('service_sort', 'item_sort', 'item__name')
    )
    items = InventoryItem.objects.filter(is_active=True).order_by('name')
    selected_rule = None
    edit_id = request.GET.get('edit')
    if edit_id:
        selected_rule = get_object_or_404(ServiceInventoryUsage.objects.select_related('item'), id=edit_id)

    return render(request, 'service_inventory_usage.html', {
        'rules': rules,
        'items': items,
        'service_choices': Order.SERVICE_CHOICES,
        'selected_rule': selected_rule,
        'is_admin': True,
    })


@login_required
def toggle_service_inventory_usage(request, rule_id):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    rule = get_object_or_404(ServiceInventoryUsage, id=rule_id)
    if request.method == 'POST':
        rule.is_active = not rule.is_active
        rule.save(update_fields=['is_active'])
        messages.success(request, "Usage rule updated.")
    return redirect('service_inventory_usage')


@login_required
def delete_service_inventory_usage(request, rule_id):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    rule = get_object_or_404(ServiceInventoryUsage.objects.select_related('item'), id=rule_id)
    if request.method == 'POST':
        service_name = rule.get_service_type_display()
        item_name = rule.item.name
        rule.delete()
        messages.success(request, f"Removed usage rule for {service_name} - {item_name}.")
    return redirect('service_inventory_usage')


@login_required
def low_stock_alert(request):
    low_items = InventoryItem.objects.filter(
        is_active=True, current_stock__lte=F('minimum_stock')
    ).select_related('category').order_by('current_stock')
    return render(request, 'inventory.html', {
        'section': 'low_stock',
        'low_stock_items': low_items,
        'low_stock_count': low_items.count(),
        'is_admin': is_admin(request.user),
    })


@login_required
def stock_history(request):
    movements = StockMovement.objects.select_related(
        'item', 'reference_order__customer', 'performed_by'
    ).order_by('-created_at')

    type_filter = request.GET.get('type', '')
    if type_filter:
        movements = movements.filter(movement_type=type_filter)

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        movements = movements.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(created_at__date__lte=date_to)

    staff_filter = request.GET.get('staff', '')
    if staff_filter:
        movements = movements.filter(performed_by_id=staff_filter)

    movement_count = movements.count()
    paginator = Paginator(movements, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'inventory.html', {
        'section': 'history',
        'movements': page_obj,
        'page_obj': page_obj,
        'movement_count': movement_count,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'staff_filter': staff_filter,
        'staff_users': User.objects.filter(is_active=True).order_by('username'),
        'is_admin': is_admin(request.user),
    })
