from django.contrib.auth import views as auth_views
from django.urls import path

from . import views


urlpatterns = [
    path('admin-login/', views.admin_login, name='admin_login'),
    path('staff-login/', views.staff_login, name='staff_login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
