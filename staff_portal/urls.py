from django.urls import path

from . import views


staff_required = views.staff_portal_required

urlpatterns = [
    path('', staff_required(views.staff_dashboard), name='home'),
    path('staff-dashboard/', staff_required(views.staff_dashboard), name='staff_dashboard'),
    path('delivery-tasks/', staff_required(views.delivery_tasks), name='delivery_tasks'),
    path('walkin-tasks/', staff_required(views.walkin_tasks), name='walkin_tasks'),
    path('kanban/', staff_required(views.kanban_board), name='kanban_board'),
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
    path('customers/', staff_required(views.customer_list), name='customer_list'),
    path('add-customer/', staff_required(views.add_customer), name='add_customer'),
    path('customer/<int:customer_id>/', staff_required(views.customer_detail), name='customer_detail'),
    path('customer/<int:customer_id>/edit/', staff_required(views.edit_customer), name='edit_customer'),
    path('inventory/', staff_required(views.inventory_list), name='inventory_list'),
    path('inventory/<int:item_id>/', staff_required(views.inventory_detail), name='inventory_detail'),
    path('inventory/<int:item_id>/restock/', staff_required(views.restock_item), name='restock_item'),
    path('inventory/<int:item_id>/deduct/', staff_required(views.deduct_stock), name='deduct_stock'),
]
