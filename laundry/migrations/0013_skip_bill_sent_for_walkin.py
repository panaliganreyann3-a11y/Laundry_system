from django.db import migrations


def move_walkin_bill_sent_to_processing(apps, schema_editor):
    Order = apps.get_model('laundry', 'Order')
    Order.objects.filter(order_type='WALK_IN', status='BILL_SENT').update(status='PROCESSING')


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0012_service_inventory_usage'),
    ]

    operations = [
        migrations.RunPython(move_walkin_bill_sent_to_processing, migrations.RunPython.noop),
    ]
