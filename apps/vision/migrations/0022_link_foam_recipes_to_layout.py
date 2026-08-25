from django.db import migrations, models
import django.db.models.deletion


def link_existing_foam_recipes(apps, schema_editor):
    RackSpec = apps.get_model('vision', 'FoamRackSpec')
    ProductLayout = apps.get_model('vision', 'FoamProductLayout')
    Recipe = apps.get_model('vision', 'VisionRecipe')

    defaults = (
        ('RACK-2L', '二层标准料架', 2),
        ('RACK-3L', '三层标准料架', 3),
        ('RACK-4L', '四层标准料架', 4),
    )
    specs = {}
    for rack_type, name, layer_count in defaults:
        spec, _ = RackSpec.objects.get_or_create(
            rack_type=rack_type,
            defaults={'name': name, 'layer_count': layer_count, 'remark': '系统初始化规格'},
        )
        specs[rack_type] = spec

    default_layout, _ = ProductLayout.objects.get_or_create(
        rack_spec=specs['RACK-3L'],
        product_code='PROD-A',
        defaults={'product_name': 'A 产品', 'qty_per_layer': 5},
    )

    for recipe in Recipe.objects.filter(recipe_type='FOAM_2D', foam_product_layout__isnull=True):
        rack_type = (recipe.rack_type or '').strip()
        product_code = (recipe.product_code or '').strip()
        layout = None
        if rack_type and product_code:
            layout = ProductLayout.objects.filter(
                rack_spec__rack_type=rack_type,
                product_code=product_code,
            ).first()
        if layout is None:
            layout = default_layout
        recipe.foam_product_layout_id = layout.id
        recipe.rack_type = layout.rack_spec.rack_type
        recipe.product_code = layout.product_code
        recipe.save(update_fields=['foam_product_layout', 'rack_type', 'product_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0021_add_foam_rack_spec_product_layout'),
    ]

    operations = [
        migrations.AddField(
            model_name='foamrackspec',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True, verbose_name='启用'),
        ),
        migrations.AddField(
            model_name='foamproductlayout',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True, verbose_name='启用'),
        ),
        migrations.AddField(
            model_name='visionrecipe',
            name='foam_product_layout',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recipes',
                to='vision.foamproductlayout',
                verbose_name='2D泡棉产品布局',
            ),
        ),
        migrations.RunPython(link_existing_foam_recipes, migrations.RunPython.noop),
    ]
