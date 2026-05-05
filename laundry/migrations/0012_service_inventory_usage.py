from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0011_gcash_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='inventory_deducted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ServiceInventoryUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_type', models.CharField(choices=[('WASH', 'Wash Only'), ('WASH_DRY', 'Wash & Dry'), ('WASH_DRY_FOLD', 'Wash, Dry & Fold'), ('DRY_ONLY', 'Dry Only'), ('DRY_CLEAN', 'Dry Clean'), ('IRON', 'Iron / Press Only'), ('EXPRESS', 'Express Service')], max_length=20)),
                ('quantity_per_kg', models.FloatField(default=0.0)),
                ('fixed_quantity', models.FloatField(default=0.0)),
                ('is_active', models.BooleanField(default=True)),
                ('item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='service_usages', to='laundry.inventoryitem')),
            ],
            options={
                'ordering': ['service_type', 'item__name'],
                'unique_together': {('service_type', 'item')},
            },
        ),
    ]
