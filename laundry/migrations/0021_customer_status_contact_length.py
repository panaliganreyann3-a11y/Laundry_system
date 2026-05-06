from django.db import migrations, models


def normalize_contacts(apps, schema_editor):
    Customer = apps.get_model('laundry', 'Customer')
    for customer in Customer.objects.all():
        digits = ''.join(ch for ch in (customer.contact or '') if ch.isdigit())
        clean = digits[:11] if digits else customer.contact[:11]
        if customer.contact != clean:
            customer.contact = clean
            customer.save(update_fields=['contact'])


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0020_sitesettings_userprofile'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE laundry_customer ADD COLUMN IF NOT EXISTS status varchar(12) NOT NULL DEFAULT 'NEW'",
                    reverse_sql="ALTER TABLE laundry_customer DROP COLUMN IF EXISTS status",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='customer',
                    name='status',
                    field=models.CharField(
                        choices=[('NEW', 'New'), ('REGULAR', 'Regular')],
                        default='NEW',
                        max_length=12,
                    ),
                ),
            ],
        ),
        migrations.RunPython(normalize_contacts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customer',
            name='contact',
            field=models.CharField(max_length=11),
        ),
    ]
