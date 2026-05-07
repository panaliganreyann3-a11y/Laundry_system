from django.db import migrations, models
import laundry.models
import secrets


def generate_tracking_number():
    return secrets.token_urlsafe(12).replace('-', '').replace('_', '')[:16].upper()


def backfill_tracking_numbers(apps, schema_editor):
    Order = apps.get_model('laundry', 'Order')
    used = set(
        Order.objects.exclude(tracking_number__isnull=True)
        .exclude(tracking_number='')
        .values_list('tracking_number', flat=True)
    )
    for order in Order.objects.filter(models.Q(tracking_number__isnull=True) | models.Q(tracking_number='')):
        tracking_number = generate_tracking_number()
        while tracking_number in used:
            tracking_number = generate_tracking_number()
        used.add(tracking_number)
        order.tracking_number = tracking_number
        order.save(update_fields=['tracking_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0022_merge_20260507_0000'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='tracking_number',
            field=models.CharField(blank=True, db_index=True, max_length=20, null=True),
        ),
        migrations.RunPython(backfill_tracking_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='tracking_number',
            field=models.CharField(
                db_index=True,
                default=laundry.models.generate_tracking_number,
                max_length=20,
                unique=True,
            ),
        ),
    ]
