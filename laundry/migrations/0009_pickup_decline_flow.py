from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0008_customer_portal_pickup_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='decline_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='declined_at',
            field=models.DateTimeField(blank=True, null=True),
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
                    ('DECLINED', 'Declined'),
                    ('CLAIMED', 'Claimed'),
                ],
                default='RECEIVED',
                max_length=20,
            ),
        ),
    ]
