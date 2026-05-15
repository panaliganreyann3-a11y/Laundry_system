from django.urls import path

from . import views


staff_required = views.staff_portal_required

urlpatterns = [
    path('admin-dashboard/', staff_required(views.admin_dashboard), name='admin_dashboard'),
    path('pricing/', staff_required(views.pricing_settings), name='pricing_settings'),
    path('branding/', staff_required(views.branding_settings), name='branding_settings'),
    path('reports/', staff_required(views.reports), name='reports'),
    path('rewards/', staff_required(views.rewards_history), name='rewards_history'),
    path('activity-log/', staff_required(views.activity_log), name='activity_log'),
    path('export-csv/', staff_required(views.export_csv), name='export_csv'),
    path('accounts/', staff_required(views.account_list), name='account_list'),
    path('accounts/add/', staff_required(views.add_account), name='add_account'),
    path('accounts/toggle/<int:user_id>/', staff_required(views.toggle_account), name='toggle_account'),
    path('accounts/photo/<int:user_id>/', staff_required(views.update_account_photo), name='update_account_photo'),
    path('accounts/reset-password/<int:user_id>/', staff_required(views.reset_password), name='reset_password'),
    path('staff/', staff_required(views.account_list), name='staff_list'),
    path('staff/add/', staff_required(views.add_account), name='add_staff'),
    path('staff/toggle/<int:user_id>/', staff_required(views.toggle_account), name='toggle_staff'),
    path('staff/reset-password/<int:user_id>/', staff_required(views.reset_password), name='staff_reset_password'),
    path('order/delete/<int:order_id>/', staff_required(views.delete_order), name='delete_order'),
    path('inventory/add/', staff_required(views.add_inventory_item), name='add_inventory_item'),
    path('inventory/low-stock/', staff_required(views.low_stock_alert), name='low_stock_alert'),
    path('inventory/history/', staff_required(views.stock_history), name='stock_history'),
    path('inventory/service-usage/', staff_required(views.service_inventory_usage), name='service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/toggle/', staff_required(views.toggle_service_inventory_usage), name='toggle_service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/delete/', staff_required(views.delete_service_inventory_usage), name='delete_service_inventory_usage'),
]
