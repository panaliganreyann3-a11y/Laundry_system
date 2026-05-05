from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_orders(apps, schema_editor):
    Order = apps.get_model('laundry', 'Order')

    status_map = {
        'PICKUP_ASSIGNED': 'PICKUP_CONFIRMED',
        'RECEIVED': 'RECEIVED_AT_SHOP',
        'WASHING': 'PROCESSING',
        'DRYING': 'PROCESSING',
        'FOLDING': 'PROCESSING',
        'READY': 'READY_FOR_DELIVERY',
        'CLAIMED': 'COMPLETED',
        'DECLINED': 'CANCELLED',
    }
    method_map = {
        'CASH': 'CASH_AFTER_DELIVERY',
        'CARD': 'CASH_AFTER_DELIVERY',
        'BANK_TRANSFER': 'CASH_AFTER_DELIVERY',
    }

    for order in Order.objects.all():
        order.status = status_map.get(order.status, order.status)
        order.payment_method = method_map.get(order.payment_method, order.payment_method)
        order.total_amount = order.price or 0
        order.price_per_kg = 30.0
        order.laundry_fee = order.price or 0
        order.subtotal = order.price or 0
        order.amount_paid = order.amount_paid or 0
        raw_balance = round(order.total_amount - order.amount_paid, 2)
        order.balance = max(raw_balance, 0)
        order.overpayment = abs(raw_balance) if raw_balance < 0 else 0
        if order.status == 'CANCELLED':
            order.payment_status = 'CANCELLED'
        elif order.amount_paid >= order.total_amount and order.total_amount > 0:
            order.payment_status = 'PAID'
        elif order.amount_paid > 0:
            order.payment_status = 'PARTIAL'
        else:
            order.payment_status = 'UNPAID'
        order.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laundry', '0009_pickup_decline_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='balance',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_fee',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='discount',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='extra_fee',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='laundry_fee',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='overpayment',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='pickup_fee',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='price_per_kg',
            field=models.FloatField(default=30.0),
        ),
        migrations.AddField(
            model_name='order',
            name='subtotal',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='total_amount',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_method',
            field=models.CharField(choices=[('GCASH', 'GCash'), ('CASH_AFTER_DELIVERY', 'Cash After Delivery / COD')], default='CASH_AFTER_DELIVERY', max_length=25),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_status',
            field=models.CharField(choices=[('UNPAID', 'Unpaid'), ('PENDING_VERIFICATION', 'Pending Verification'), ('PAID', 'Paid'), ('PARTIAL', 'Partial'), ('REJECTED', 'Rejected'), ('REFUNDED', 'Refunded'), ('CANCELLED', 'Cancelled')], default='UNPAID', max_length=25),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('PENDING_PICKUP', 'Pending Pickup'), ('PICKUP_CONFIRMED', 'Pickup Confirmed'), ('PICKED_UP', 'Picked Up'), ('RECEIVED_AT_SHOP', 'Received at Shop'), ('WEIGHED', 'Weighed'), ('BILL_SENT', 'Bill Sent'), ('PROCESSING', 'Processing'), ('READY_FOR_DELIVERY', 'Ready for Delivery'), ('OUT_FOR_DELIVERY', 'Out for Delivery'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='RECEIVED_AT_SHOP', max_length=25),
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_method', models.CharField(choices=[('GCASH', 'GCash'), ('CASH_AFTER_DELIVERY', 'Cash After Delivery / COD')], max_length=25)),
                ('amount', models.FloatField(default=0.0)),
                ('reference_number', models.CharField(blank=True, max_length=100, null=True)),
                ('proof_image', models.ImageField(blank=True, null=True, upload_to='payment_proofs/')),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('VERIFIED', 'Verified'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled'), ('REFUNDED', 'Refunded')], default='PENDING', max_length=15)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='laundry.order')),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='received_payments', to=settings.AUTH_USER_MODEL)),
                ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.RunPython(migrate_existing_orders, migrations.RunPython.noop),
    ]
