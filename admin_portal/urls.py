from django.urls import path

from . import views


staff_required = views.staff_portal_required

urlpatterns = [
    path('admin-dashboard/', staff_required(views.admin_dashboard), name='admin_dashboard'),
    path('pricing/', staff_required(views.pricing_settings), name='pricing_settings'),
    path('reports/', staff_required(views.reports), name='reports'),
    path('export-csv/', staff_required(views.export_csv), name='export_csv'),
    path('staff/', staff_required(views.staff_list), name='staff_list'),
    path('staff/add/', staff_required(views.add_staff), name='add_staff'),
    path('staff/toggle/<int:user_id>/', staff_required(views.toggle_staff), name='toggle_staff'),
    path('staff/reset-password/<int:user_id>/', staff_required(views.reset_password), name='reset_password'),
    path('order/delete/<int:order_id>/', staff_required(views.delete_order), name='delete_order'),
    path('inventory/add/', staff_required(views.add_inventory_item), name='add_inventory_item'),
    path('inventory/low-stock/', staff_required(views.low_stock_alert), name='low_stock_alert'),
    path('inventory/history/', staff_required(views.stock_history), name='stock_history'),
    path('inventory/service-usage/', staff_required(views.service_inventory_usage), name='service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/toggle/', staff_required(views.toggle_service_inventory_usage), name='toggle_service_inventory_usage'),
    path('inventory/service-usage/<int:rule_id>/delete/', staff_required(views.delete_service_inventory_usage), name='delete_service_inventory_usage'),
]
