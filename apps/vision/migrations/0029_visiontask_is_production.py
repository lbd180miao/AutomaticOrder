from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vision', '0028_remove_factory_recipe_calibration')]

    operations = [
        migrations.AddField(
            model_name='visiontask',
            name='is_production',
            field=models.BooleanField(default=False),
        ),
    ]
