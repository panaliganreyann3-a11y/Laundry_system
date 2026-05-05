from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from laundry.models import Customer, Order, Payment, PricingConfig
from laundry.views import (
    customer_required,
    generate_qr_for_order,
    is_admin,
    is_customer_user,
    orders_created_on,
)


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
            return render(request, 'customers/customer_register.html')
        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'customers/customer_register.html')
        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters.")
            return render(request, 'customers/customer_register.html')
        if User.objects.filter(username__iexact=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, 'customers/customer_register.html')

        existing_customer = Customer.objects.filter(
            Q(email__iexact=email) | Q(contact=contact)
        ).first()
        if existing_customer and existing_customer.user_id:
            messages.error(request, "A customer account already exists for this email or contact number.")
            return render(request, 'customers/customer_register.html')

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

    return render(request, 'customers/customer_register.html')


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
    return render(request, 'customers/customer_login.html', {'error': error})


@customer_required
def customer_dashboard(request):
    customer = request.user.customer_profile
    orders = customer.orders.order_by('-created_at')[:10]
    active_orders = customer.orders.exclude(status__in=['COMPLETED', 'CANCELLED']).count()
    return render(request, 'customers/customer_dashboard.html', {
        'customer': customer,
        'orders': orders,
        'active_orders': active_orders,
    })


@customer_required
def customer_order_history(request):
    customer = request.user.customer_profile
    orders = customer.orders.order_by('-created_at')
    return render(request, 'customers/customer_order_history.html', {
        'customer': customer,
        'orders': orders,
    })


@customer_required
def customer_order_detail(request, order_id):
    customer = request.user.customer_profile
    order = get_object_or_404(customer.orders, id=order_id)
    return render(request, 'customers/customer_order_detail.html', {
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
            return render(request, 'customers/customer_new_order.html', {
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
        generate_qr_for_order(order)
        messages.success(request, f"Pickup request #{order.id} submitted.")
        return redirect('customer_order_detail', order_id=order.id)

    return render(request, 'customers/customer_new_order.html', {
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

    return render(request, 'customers/customer_profile.html', {'customer': customer})


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
    reference_number = request.POST.get('reference_number', '').strip()
    proof_image = request.FILES.get('proof_image')
    if not reference_number or not proof_image:
        messages.error(request, "GCash reference number and proof image are required.")
        return redirect('customer_order_detail', order_id=order.id)
    payment = Payment.objects.create(
        order=order,
        payment_method='GCASH',
        amount=amount,
        reference_number=reference_number,
        proof_image=proof_image,
        status='PENDING',
    )
    order.payment_status = 'PENDING_VERIFICATION'
    order.save(update_fields=['payment_status', 'updated_at'])
    messages.success(request, f"GCash payment proof #{payment.id} submitted for verification.")
    return redirect('customer_order_detail', order_id=order.id)
