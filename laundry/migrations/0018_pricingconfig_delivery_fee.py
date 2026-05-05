from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0017_activitylog'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingconfig',
            name='delivery_fee',
            field=models.FloatField(default=0.0),
        ),
    ]
