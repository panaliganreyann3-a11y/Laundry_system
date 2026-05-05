from django.contrib.auth import authenticate, login as auth_login
from django.shortcuts import redirect, render

from laundry.views import is_admin, is_customer_user


def admin_login(request):
    if request.user.is_authenticated:
        if is_customer_user(request.user):
            return redirect('customer_dashboard')
        return redirect('admin_dashboard' if is_admin(request.user) else 'staff_dashboard')
    error = None
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username', '').strip(),
            password=request.POST.get('password', ''),
        )
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
        user = authenticate(
            request,
            username=request.POST.get('username', '').strip(),
            password=request.POST.get('password', ''),
        )
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
