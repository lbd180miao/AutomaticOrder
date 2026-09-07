from django.db import migrations, models
from django.db.models import F


def populate_existing_binding_times(apps, schema_editor):
    Product = apps.get_model('production', 'Product')
    Product.objects.filter(rack_id__isnull=False, bound_at__isnull=True).update(
        bound_at=F('updated_at'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0006_rack_recipe_rack_location_recipe'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='bound_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='绑定时间'),
        ),
        migrations.RunPython(populate_existing_binding_times, migrations.RunPython.noop),
    ]
