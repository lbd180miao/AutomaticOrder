from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('vision', '0023_rack_location_recipe_rack_level')]
    operations = [migrations.AddField(
        model_name='racklocationrecipe', name='positioning_config',
        field=models.JSONField(blank=True, default=dict,
            help_text='rack_3d 定位参数；长度 mm，密度 points/mm³，角度 °。空对象使用默认值。'),
    )]
