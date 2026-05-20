from django.db import migrations, models


def add_customer_status_column(apps, schema_editor):
    table_name = 'laundry_customer'
    column_name = 'status'
    existing_columns = {
        column.name
        for column in schema_editor.connection.introspection.get_table_description(
            schema_editor.connection.cursor(),
            table_name,
        )
    }

    if column_name in existing_columns:
        return

    schema_editor.execute(
        "ALTER TABLE laundry_customer ADD COLUMN status varchar(12) NOT NULL DEFAULT 'NEW'"
    )


def remove_customer_status_column(apps, schema_editor):
    if schema_editor.connection.vendor == 'sqlite':
        return

    schema_editor.execute("ALTER TABLE laundry_customer DROP COLUMN IF EXISTS status")


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
                migrations.RunPython(add_customer_status_column, remove_customer_status_column),
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
