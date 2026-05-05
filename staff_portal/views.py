from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count, ExpressionWrapper, F, FloatField, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from laundry.models import (
    Customer,
    InventoryCategory,
    InventoryItem,
    Order,
    Payment,
    PricingConfig,
    StockMovement,
)
from laundry.views import (
    ITEMS_PER_PAGE,
    advance_order_status,
    deduct_inventory_for_order,
    generate_qr_for_order,
    is_admin,
    log_activity,
    orders_created_on,
    refresh_order_payment_from_verified_records,
    staff_portal_required,
)


@login_required
def staff_dashboard(request):
    if is_admin(request.user):
        return redirect('admin_dashboard')
    return render_staff_task_dashboard(request, 'PICKUP_DELIVERY', 'Pick-up/Delivery Task', 'delivery_tasks')


def render_staff_task_dashboard(request, order_type, task_title, clear_url_name):
    if is_admin(request.user):
        return redirect('admin_dashboard')

    orders = Order.objects.select_related('customer').filter(
        order_type=order_type,
        status__in=[
            'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP',
            'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING',
            'READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED',
        ],
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
        'PENDING_PICKUP': ('Pending Pickup', 'bi-calendar-check', '#f59f00', 'warning'),
        'PICKUP_CONFIRMED': ('Pickup Confirmed', 'bi-person-check', '#0d6efd', 'primary'),
        'PICKED_UP': ('Picked Up', 'bi-truck', '#17a2b8', 'info'),
        'RECEIVED_AT_SHOP': ('Received at Shop', 'bi-inbox', '#6c757d', 'secondary'),
        'WEIGHED': ('Weighed', 'bi-speedometer2', '#17a2b8', 'info'),
        'BILL_SENT': ('Bill Sent', 'bi-receipt', '#0d6efd', 'primary'),
        'PROCESSING': ('Processing Service', 'bi-droplet', '#ffc107', 'warning'),
        'READY_FOR_PICKUP': ('Ready for Pickup', 'bi-bag-check', '#198754', 'success'),
        'READY_FOR_DELIVERY': ('Ready for Delivery', 'bi-bag-check', '#198754', 'success'),
        'OUT_FOR_DELIVERY': ('Out for Delivery', 'bi-truck-front', '#6610f2', 'primary'),
        'DELIVERED': ('Delivered', 'bi-check-circle', '#198754', 'success'),
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
        status__in=[
            'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP', 'RECEIVED_AT_SHOP',
            'WEIGHED', 'BILL_SENT', 'PROCESSING', 'READY_FOR_DELIVERY',
            'OUT_FOR_DELIVERY', 'DELIVERED',
        ],
    ).count()
    walkin_count = Order.objects.filter(
        order_type='WALK_IN',
        status__in=['RECEIVED_AT_SHOP', 'WEIGHED', 'PROCESSING', 'READY_FOR_PICKUP'],
    ).count()

    paginator = Paginator(orders, ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'staff_portal/staff_dashboard.html', {
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
    return render_staff_task_dashboard(request, 'PICKUP_DELIVERY', 'Pick-up/Delivery Task', 'delivery_tasks')


@login_required
def walkin_tasks(request):
    return render_staff_task_dashboard(request, 'WALK_IN', 'Walk-in Task', 'walkin_tasks')


@login_required
def kanban_board(request):
    active = [
        'PENDING_PICKUP', 'PICKUP_CONFIRMED', 'PICKED_UP',
        'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING',
        'READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY', 'DELIVERED',
    ]
    columns = {
        status: Order.objects.filter(status=status)
        .select_related('customer', 'assigned_to')
        .order_by('-is_priority', 'due_date', 'created_at')
        for status in active
    }
    meta = {
        'PENDING_PICKUP': ('Pending Pickup', 'bi-calendar-check', '#f59f00', 'warning'),
        'PICKUP_CONFIRMED': ('Pickup Confirmed', 'bi-person-check', '#0d6efd', 'primary'),
        'PICKED_UP': ('Picked Up', 'bi-truck', '#17a2b8', 'info'),
        'RECEIVED_AT_SHOP': ('Received at Shop', 'bi-inbox', '#6c757d', 'secondary'),
        'WEIGHED': ('Weighed', 'bi-speedometer2', '#17a2b8', 'info'),
        'BILL_SENT': ('Bill Sent', 'bi-receipt', '#0d6efd', 'primary'),
        'PROCESSING': ('Processing Service', 'bi-droplet', '#ffc107', 'warning'),
        'READY_FOR_PICKUP': ('Ready for Pickup', 'bi-bag-check', '#198754', 'success'),
        'READY_FOR_DELIVERY': ('Ready for Delivery', 'bi-bag-check', '#198754', 'success'),
        'OUT_FOR_DELIVERY': ('Out for Delivery', 'bi-truck-front', '#6610f2', 'primary'),
        'DELIVERED': ('Delivered', 'bi-check-circle', '#198754', 'success'),
    }
    kanban_columns = [
        {
            'key': status,
            'label': meta[status][0],
            'icon': meta[status][1],
            'color': meta[status][2],
            'badge': meta[status][3],
            'orders': columns[status],
            'count': columns[status].count(),
        }
        for status in active
    ]
    total_active = sum(column['count'] for column in kanban_columns)
    return render(request, 'staff_portal/kanban.html', {
        'kanban_columns': kanban_columns,
        'total_active': total_active,
        'is_admin': is_admin(request.user),
    })


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

    return render(request, 'staff_portal/customer_list.html', {
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
            return render(request, 'staff_portal/add_customer.html', {'is_admin': is_admin(request.user)})
        customer = Customer.objects.create(
            name=name,
            contact=contact,
            email=request.POST.get('email', '').strip() or None,
            address=request.POST.get('address', '').strip() or None,
            notes=request.POST.get('notes', '').strip() or None,
            is_walk_in='is_walk_in' in request.POST,
        )
        log_activity(
            request.user,
            'ACCOUNT',
            'CREATE',
            f"Added customer profile '{customer.name}'.",
            customer,
        )
        messages.success(request, f"Customer '{name}' added.")
        return redirect('customer_list')
    return render(request, 'staff_portal/add_customer.html', {'is_admin': is_admin(request.user)})


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
        log_activity(
            request.user,
            'ACCOUNT',
            'UPDATE',
            f"Updated customer profile '{customer.name}'.",
            customer,
        )
        messages.success(request, f"Customer '{customer.name}' updated.")
        return redirect('customer_detail', customer_id=customer.id)
    return render(request, 'staff_portal/edit_customer.html', {
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
            return render(request, 'staff_portal/add_order.html', {
                'customers': customers, 'config': config,
                'staff_users': staff_users, 'service_choices': Order.SERVICE_CHOICES,
                'payment_methods': Order.PAYMENT_METHOD_CHOICES, 'is_admin': is_admin(request.user)
            })

        if weight <= 0:
            messages.error(request, "Weight must be greater than 0 kg.")
            return render(request, 'staff_portal/add_order.html', {
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

        generate_qr_for_order(order)
        log_activity(
            request.user,
            'ORDER',
            'CREATE',
            f"Created walk-in Order #{order.id} for {order.customer.name}.",
            order,
        )
        messages.success(request, f"Order #{order.id} (Q#{queue_number}) created for {order.customer.name}!")
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    return render(request, 'staff_portal/add_order.html', {
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
    if next_status == 'PROCESSING' and order.payment_method == 'GCASH' and order.payment_status != 'PAID':
        messages.error(request, "GCash payment must be verified before processing service can start.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    if next_status == 'PROCESSING':
        ok, message = deduct_inventory_for_order(order, request.user)
        if not ok:
            messages.error(request, message)
            return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    if next_status == 'COMPLETED' and order.payment_status != 'PAID':
        messages.error(request, "Payment must be fully paid before completing the order.")
        return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))
    old_status = order.status
    if advance_order_status(order, request.user):
        log_activity(
            request.user,
            'ORDER',
            'STATUS',
            f"Moved Order #{order.id} from {old_status} to {order.status}.",
            order,
        )
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
    log_activity(
        request.user,
        'ORDER',
        'STATUS',
        f"Accepted pickup request for Order #{order.id}.",
        order,
    )
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
    log_activity(
        request.user,
        'ORDER',
        'STATUS',
        f"Declined pickup request for Order #{order.id}: {reason}.",
        order,
    )
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
                old_status = order.status if order else None
                if order and order.status != 'PENDING_PICKUP' and advance_order_status(order, request.user):
                    log_activity(
                        request.user,
                        'ORDER',
                        'STATUS',
                        f"Bulk moved Order #{order.id} from {old_status} to {order.status}.",
                        order,
                    )
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
                    log_activity(
                        request.user,
                        'PAYMENT',
                        'PAYMENT',
                        f"Marked Order #{order.id} as paid during bulk update.",
                        order,
                    )
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
    log_activity(
        request.user,
        'PAYMENT',
        'PAYMENT',
        f"Marked Order #{order.id} as paid.",
        order,
    )
    messages.success(request, f"Order #{order.id} marked as paid.")
    return redirect(request.META.get('HTTP_REFERER', 'admin_dashboard' if is_admin(request.user) else 'staff_dashboard'))

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
    log_activity(
        request.user,
        'PAYMENT',
        'VERIFY',
        f"Verified GCash payment #{payment.id} for Order #{payment.order_id}.",
        payment,
    )
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
    log_activity(
        request.user,
        'PAYMENT',
        'REJECT',
        f"Rejected GCash payment #{payment.id} for Order #{payment.order_id}.",
        payment,
    )
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
    log_activity(
        request.user,
        'PAYMENT',
        'PAYMENT',
        f"Recorded COD payment for Order #{order.id}.",
        order,
    )
    messages.success(request, f"Cash payment recorded for Order #{order.id}.")
    return redirect(request.META.get('HTTP_REFERER', 'staff_dashboard'))


# ── Pricing ───────────────────────────────
# ── Customer Detail ───────────────────────

@login_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    orders = customer.orders.order_by('-created_at')
    return render(request, 'staff_portal/customer_detail.html', {
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
    return render(request, 'staff_portal/receipt.html', {'order': order, 'is_admin': is_admin(request.user)})


# ── Reports ───────────────────────────────
# ── Export CSV ────────────────────────────
# ── Public Tracker ────────────────────────

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
            return render(request, 'staff_portal/edit_order.html', {
                'order': order, 'customers': customers, 'staff_users': staff_users,
                'service_choices': Order.SERVICE_CHOICES, 'payment_methods': Order.PAYMENT_METHOD_CHOICES,
                'is_admin': is_admin(request.user)
            })
        if weight < 0 or (order.order_type == 'WALK_IN' and weight <= 0):
            messages.error(request, "Weight must be greater than 0 kg.")
            return render(request, 'staff_portal/edit_order.html', {
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
        log_activity(
            request.user,
            'ORDER',
            'UPDATE',
            f"Updated Order #{order.id} for {order.customer.name}.",
            order,
        )
        messages.success(request, f"Order #{order.id} updated.")
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')

    return render(request, 'staff_portal/edit_order.html', {
        'order': order,
        'customers': customers,
        'staff_users': staff_users,
        'service_choices': Order.SERVICE_CHOICES,
        'payment_methods': Order.PAYMENT_METHOD_CHOICES,
        'is_admin': is_admin(request.user),
    })


# ── Delete Order ──────────────────────────
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

    return render(request, 'laundry/inventory.html', {
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
def inventory_detail(request, item_id):
    item = get_object_or_404(InventoryItem, id=item_id)
    movements = StockMovement.objects.filter(item=item).select_related(
        'reference_order__customer', 'performed_by'
    ).order_by('-created_at')[:50]
    return render(request, 'laundry/inventory.html', {
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
            return render(request, 'laundry/inventory.html', {
                'section': 'restock', 'item': item, 'is_admin': is_admin(request.user)
            })
        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0.")
            return render(request, 'laundry/inventory.html', {
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
        log_activity(
            request.user,
            'INVENTORY',
            'RESTOCK',
            f"Restocked {quantity} {item.unit} of {item.name}.",
            item,
        )
        messages.success(request, f"+{quantity} {item.unit} added to '{item.name}'. New stock: {item.current_stock}")
        return redirect('inventory_detail', item_id=item.id)
    return render(request, 'laundry/inventory.html', {
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
            return render(request, 'laundry/inventory.html', {
                'section': 'deduct', 'item': item,
                'active_orders': active_orders, 'is_admin': is_admin(request.user)
            })
        if quantity <= 0:
            messages.error(request, "Quantity must be greater than 0.")
            return render(request, 'laundry/inventory.html', {
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
        log_activity(
            request.user,
            'INVENTORY',
            'DEDUCT',
            f"Deducted {quantity} {item.unit} from {item.name}.",
            item,
        )
        messages.success(request, f"-{quantity} {item.unit} from '{item.name}'. Remaining: {item.current_stock}")
        return redirect('inventory_detail', item_id=item.id)
    return render(request, 'laundry/inventory.html', {
        'section': 'deduct', 'item': item,
        'active_orders': active_orders, 'is_admin': is_admin(request.user)
    })

