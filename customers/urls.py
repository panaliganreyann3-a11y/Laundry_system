from django.urls import path

from . import views


urlpatterns = [
    path('customer/register/', views.customer_register, name='customer_register'),
    path('customer/login/', views.customer_login, name='customer_login'),
    path('customer/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('customer/orders/', views.customer_order_history, name='customer_order_history'),
    path('customer/orders/new/', views.customer_new_order, name='customer_new_order'),
    path('customer/orders/<int:order_id>/', views.customer_order_detail, name='customer_order_detail'),
    path('customer/orders/<int:order_id>/gcash-payment/', views.submit_gcash_payment, name='submit_gcash_payment'),
    path('customer/profile/', views.customer_profile, name='customer_profile'),
]
