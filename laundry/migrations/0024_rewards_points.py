from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0023_order_tracking_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='loyalty_points',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='customer',
            name='points_last_transaction_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='points_redeemed',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='order',
            name='points_discount',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='order',
            name='points_awarded',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='RewardTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('EARN', 'Earned'), ('REDEEM', 'Redeemed'), ('EXPIRE', 'Expired')], max_length=10)),
                ('points', models.IntegerField()),
                ('discount_amount', models.FloatField(default=0.0)),
                ('service_type', models.CharField(blank=True, max_length=20, null=True)),
                ('description', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reward_transactions', to='laundry.customer')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reward_transactions', to='laundry.order')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
