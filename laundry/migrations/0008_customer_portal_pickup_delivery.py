import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laundry', '0007_seed_common_laundry_stock'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='user',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='customer_profile',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='delivered_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='order_type',
            field=models.CharField(
                choices=[('WALK_IN', 'Walk-in'), ('PICKUP_DELIVERY', 'Pickup & Delivery')],
                default='WALK_IN',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[
                    ('CASH', 'Cash'),
                    ('GCASH', 'GCash'),
                    ('CARD', 'Card'),
                    ('BANK_TRANSFER', 'Bank Transfer'),
                ],
                default='CASH',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='picked_up_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='pickup_address',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='preferred_pickup_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='price',
            field=models.FloatField(default=0),
        ),
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING_PICKUP', 'Pending Pickup'),
                    ('PICKUP_ASSIGNED', 'Pickup Assigned'),
                    ('PICKED_UP', 'Picked Up'),
                    ('RECEIVED', 'Received'),
                    ('WASHING', 'Washing'),
                    ('DRYING', 'Drying'),
                    ('FOLDING', 'Folding / Ironing'),
                    ('READY', 'Ready for Pickup'),
                    ('OUT_FOR_DELIVERY', 'Out for Delivery'),
                    ('DELIVERED', 'Delivered'),
                    ('CLAIMED', 'Claimed'),
                ],
                default='RECEIVED',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='order',
            name='weight',
            field=models.FloatField(default=0),
        ),
    ]
