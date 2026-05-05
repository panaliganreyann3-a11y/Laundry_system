from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0015_seed_service_usage_rules'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='customer',
            name='loyalty_points',
        ),
    ]
