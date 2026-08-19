from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0018_rack_layer_measurement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='visionrecipe',
            name='recipe_type',
            field=models.CharField(
                choices=[
                    ('FOAM_2D', '泡棉检测配方'),
                    ('EMPTY_RACK_2D', '空箱检测配方'),
                    ('RACK_3D', '料架定位配方'),
                ],
                max_length=32,
            ),
        ),
    ]
