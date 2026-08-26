from django.db import migrations, models
import django.db.models.deletion


def copy_existing_recipe_reference(apps, schema_editor):
    RackRecipe = apps.get_model('production', 'RackRecipe')
    RackRecipeVisionMapping = apps.get_model('production', 'RackRecipeVisionMapping')
    for rack_recipe in RackRecipe.objects.all().iterator():
        mapping = (
            RackRecipeVisionMapping.objects
            .filter(rack_recipe_id=rack_recipe.pk, rack_location_recipe_id__isnull=False)
            .order_by('-updated_at', 'station_position_no', 'layer_no')
            .first()
        )
        if mapping:
            rack_recipe.rack_location_recipe_id = mapping.rack_location_recipe_id
            rack_recipe.save(update_fields=['rack_location_recipe'])


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0005_product_defect_at_product_defect_reason_and_more'),
        ('vision', '0023_rack_location_recipe_rack_level'),
    ]

    operations = [
        migrations.AddField(
            model_name='rackrecipe',
            name='rack_location_recipe',
            field=models.ForeignKey(
                blank=True,
                help_text='整份料架主配方共用的 3D 定位技术配方。',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='rack_master_recipes',
                to='vision.racklocationrecipe',
            ),
        ),
        migrations.RunPython(copy_existing_recipe_reference, migrations.RunPython.noop),
    ]
