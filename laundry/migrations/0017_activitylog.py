from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laundry', '0016_remove_customer_loyalty_points'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('ORDER', 'Order'), ('PAYMENT', 'Payment'), ('INVENTORY', 'Inventory'), ('SERVICE_USAGE', 'Service Usage'), ('PRICING', 'Pricing'), ('ACCOUNT', 'Account')], max_length=30)),
                ('action', models.CharField(choices=[('CREATE', 'Create'), ('UPDATE', 'Update'), ('DELETE', 'Delete'), ('STATUS', 'Status'), ('PAYMENT', 'Payment'), ('RESTOCK', 'Restock'), ('DEDUCT', 'Deduct'), ('VERIFY', 'Verify'), ('REJECT', 'Reject'), ('TOGGLE', 'Toggle')], max_length=30)),
                ('description', models.TextField()),
                ('target_type', models.CharField(blank=True, max_length=100, null=True)),
                ('target_id', models.PositiveBigIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
