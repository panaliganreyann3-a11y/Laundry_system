from django.db import migrations, models


def move_walkin_ready_to_pickup(apps, schema_editor):
    Order = apps.get_model('laundry', 'Order')
    Order.objects.filter(order_type='WALK_IN', status='READY_FOR_DELIVERY').update(status='READY_FOR_PICKUP')


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0013_skip_bill_sent_for_walkin'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[('PENDING_PICKUP', 'Pending Pickup'), ('PICKUP_CONFIRMED', 'Pickup Confirmed'), ('PICKED_UP', 'Picked Up'), ('RECEIVED_AT_SHOP', 'Received at Shop'), ('WEIGHED', 'Weighed'), ('BILL_SENT', 'Bill Sent'), ('PROCESSING', 'Processing'), ('READY_FOR_PICKUP', 'Ready for Pickup'), ('READY_FOR_DELIVERY', 'Ready for Delivery'), ('OUT_FOR_DELIVERY', 'Out for Delivery'), ('DELIVERED', 'Delivered'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], default='RECEIVED_AT_SHOP', max_length=25),
        ),
        migrations.RunPython(move_walkin_ready_to_pickup, migrations.RunPython.noop),
    ]
