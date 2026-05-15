from django.db import migrations


def update_site_name(apps, schema_editor):
    SiteSettings = apps.get_model('laundry', 'SiteSettings')
    SiteSettings.objects.filter(site_name='Spin King Laundry Hub').update(
        site_name='Spin Clean Laundry Hub'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0024_rewards_points'),
    ]

    operations = [
        migrations.RunPython(update_site_name, migrations.RunPython.noop),
    ]
