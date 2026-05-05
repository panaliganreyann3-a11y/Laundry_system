import csv
import json
from datetime import date as date_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Case, Count, F, IntegerField, Sum, When
from django.db.models.functions import TruncDate
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from laundry.models import (
    Customer,
    InventoryCategory,
    InventoryItem,
    Order,
    PricingConfig,
    ServiceInventoryUsage,
    StockMovement,
)
from laundry.views import (
    ITEMS_PER_PAGE,
    is_admin,
    local_day_range,
    orders_created_on,
    staff_portal_required,
)


@login_required
def admin_dashboard(request):
    if not is_admin(request.user):
        return redirect('staff_dashboard')

    today = timezone.now().date()
    today_qs = orders_created_on(today)
    today_stats = {
        'total': today_qs.count(),
        'pending': today_qs.filter(status__in=['PENDING_PICKUP', 'PICKUP_CONFIRMED']).count(),
        'in_progress': today_qs.filter(status__in=['PICKED_UP', 'RECEIVED_AT_SHOP', 'WEIGHED', 'BILL_SENT', 'PROCESSING']).count(),
        'ready': today_qs.filter(status__in=['READY_FOR_PICKUP', 'READY_FOR_DELIVERY', 'OUT_FOR_DELIVERY']).count(),
        'revenue': today_qs.aggregate(t=Sum('total_amount'))['t'] or 0,
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
        'revenue_labels': json.dumps([d.strftime('%b %d') for d in date_range]),
        'revenue_data': json.dumps([float(rev_map.get(d, 0)) for d in date_range]),
        'orders_data': json.dumps([cnt_map.get(d, 0) for d in date_range]),
        'status_labels': json.dumps([s['status'] for s in status_counts]),
        'status_data': json.dumps([s['c'] for s in status_counts]),
        'service_labels': json.dumps([s['service_type'] for s in service_counts]),
        'service_data': json.dumps([s['c'] for s in service_counts]),
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'rush_orders': rush_orders,
        'avg_order_value': avg_value,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
    })


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


@login_required
def staff_list(request):
    if not is_admin(request.user):
        return HttpResponseForbidden()
    return render(request, 'staff_list.html', {
        'staff': User.objects.all().order_by('-date_joined'),
        'is_admin': True,
    })


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

