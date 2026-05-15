from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from laundry.views import is_admin, is_customer_user


def role_redirect(user):
    if is_customer_user(user):
        return redirect('customer_dashboard')
    if is_admin(user):
        return redirect('admin_dashboard')
    return redirect('staff_dashboard')


def find_login_username(identifier):
    identifier = identifier.strip()
    if not identifier:
        return identifier
    if '@' not in identifier:
        return identifier
    user = User.objects.filter(email__iexact=identifier).first()
    return user.username if user else identifier.lower()


def login(request):
    if request.user.is_authenticated:
        return role_redirect(request.user)

    error = None
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        user = authenticate(
            request,
            username=find_login_username(identifier),
            password=request.POST.get('password', ''),
        )
        if user:
            auth_login(request, user)
            return role_redirect(user)
        error = "Invalid username/email or password."

    return render(request, 'accounts/login.html', {'error': error})
