from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0010_final_order_payment_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingconfig',
            name='gcash_number',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='pricingconfig',
            name='gcash_qr',
            field=models.ImageField(blank=True, null=True, upload_to='gcash_qr/'),
        ),
    ]
