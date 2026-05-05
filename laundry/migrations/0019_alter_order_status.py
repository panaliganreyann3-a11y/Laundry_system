from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0018_pricingconfig_delivery_fee'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING_PICKUP', 'Pending Pickup'),
                    ('PICKUP_CONFIRMED', 'Pickup Confirmed'),
                    ('PICKED_UP', 'Picked Up'),
                    ('RECEIVED_AT_SHOP', 'Received at Shop'),
                    ('WEIGHED', 'Weighed'),
                    ('BILL_SENT', 'Bill Sent'),
                    ('PROCESSING', 'Processing Service'),
                    ('READY_FOR_PICKUP', 'Ready for Pickup'),
                    ('READY_FOR_DELIVERY', 'Ready for Delivery'),
                    ('OUT_FOR_DELIVERY', 'Out for Delivery'),
                    ('DELIVERED', 'Delivered'),
                    ('COMPLETED', 'Completed'),
                    ('CANCELLED', 'Cancelled'),
                ],
                default='RECEIVED_AT_SHOP',
                max_length=25,
            ),
        ),
    ]
