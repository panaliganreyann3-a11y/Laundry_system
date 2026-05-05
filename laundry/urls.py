from django.urls import path
from . import views


staff_required = views.staff_portal_required

urlpatterns = [
    # Customer portal
    path('customer/register/', views.customer_register, name='customer_register'),
    path('customer/login/', views.customer_login, name='customer_login'),
    path('customer/dashboard/', views.customer_dashboard, name='customer_dashboard'),
    path('customer/orders/', views.customer_order_history, name='customer_order_history'),
    path('customer/orders/new/', views.customer_new_order, name='customer_new_order'),
    path('customer/orders/<int:order_id>/', views.customer_order_detail, name='customer_order_detail'),
    path('customer/orders/<int:order_id>/gcash-payment/', views.submit_gcash_payment, name='submit_gcash_payment'),
    path('customer/profile/', views.customer_profile, name='customer_profile'),

    # Dashboards
    path('', staff_required(views.staff_dashboard), name='home'),
    path('admin-dashboard/', staff_required(views.admin_dashboard), name='admin_dashboard'),
    path('staff-dashboard/', staff_required(views.staff_dashboard), name='staff_dashboard'),
    path('delivery-tasks/', staff_required(views.delivery_tasks), name='delivery_tasks'),
    path('walkin-tasks/', staff_required(views.walkin_tasks), name='walkin_tasks'),

    # Kanban Board
    path('kanban/', staff_required(views.kanban_board), name='kanban_board'),

    # Orders
    path('add-order/', staff_required(views.add_order), name='add_order'),
    path('update/<int:order_id>/', staff_required(views.update_status), name='update_status'),
    path('bulk-update/', staff_required(views.bulk_update_status), name='bulk_update_status'),
    path('pickup/<int:order_id>/accept/', staff_required(views.accept_pickup_request), name='accept_pickup_request'),
    path('pickup/<int:order_id>/decline/', staff_required(views.decline_pickup_request), name='decline_pickup_request'),
    path('mark-paid/<int:order_id>/', staff_required(views.mark_paid), name='mark_paid'),
    path('payment/<int:payment_id>/verify/', staff_required(views.verify_payment), name='verify_payment'),
    path('payment/<int:payment_id>/reject/', staff_required(views.reject_payment), name='reject_payment'),
    path('payment/<int:order_id>/confirm-cod/', staff_required(views.confirm_cod_payment), name='confirm_cod_payment'),
    path('receipt/<int:order_id>/', staff_required(views.order_receipt), name='order_receipt'),
    path('order/edit/<int:order_id>/', staff_required(views.edit_order), name='edit_order'),
    path('order/delete/<int:order_id>/', staff_required(views.delete_order), name='delete_order'),

    # Customers
    path('customers/', staff_required(views.customer_list), name='customer_list'),
    path('add-customer/', staff_required(views.add_customer), name='add_customer'),
    path('customer/<int:customer_id>/', staff_required(views.customer_detail), name='customer_detail'),
    path('customer/<int:customer_id>/edit/', staff_required(views.edit_customer), name='edit_customer'),

    # Admin only
    path('pricing/', staff_required(views.pricing_settings), name='pricing_settings'),
    path('reports/', staff_required(views.reports), name='reports'),
    path('export-csv/', staff_required(views.export_csv), name='export_csv'),
    path('staff/', staff_required(views.staff_list), name='staff_list'),
    path('staff/add/', staff_required(views.add_staff), name='add_staff'),
    path('staff/toggle/<int:user_id>/', staff_required(views.toggle_staff), name='toggle_staff'),
    path('staff/reset-password/<int:user_id>/', staff_required(views.reset_password), name='reset_password'),

    # Inventory
    path('inventory/', staff_required(views.inventory_list), name='inventory_list'),
    path('inventory/add/', staff_required(views.add_inventory_item), name='add_inventory_item'),
    path('inventory/low-stock/', staff_required(views.low_stock_alert), name='low_stock_alert'),
    path('inventory/history/', staff_required(views.stock_history), name='stock_history'),
    path('inventory/service-usage/', staff_required(views.service_inventory_usage), name='service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/toggle/', staff_required(views.toggle_service_inventory_usage), name='toggle_service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/delete/', staff_required(views.delete_service_inventory_usage), name='delete_service_inventory_usage'),
    path('inventory/<int:item_id>/', staff_required(views.inventory_detail), name='inventory_detail'),
    path('inventory/<int:item_id>/restock/', staff_required(views.restock_item), name='restock_item'),
    path('inventory/<int:item_id>/deduct/', staff_required(views.deduct_stock), name='deduct_stock'),

    # Public
    path('track/', views.track_order, name='track_order'),
]
