from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0025_update_site_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesettings',
            name='site_name',
            field=models.CharField(default='Spin Clean Laundry Hub', max_length=120),
        ),
    ]
