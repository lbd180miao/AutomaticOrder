from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0022_link_foam_recipes_to_layout'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='racklocationrecipe',
            options={'ordering': ['rack_type', 'recipe_name', '-updated_at']},
        ),
        migrations.RemoveConstraint(
            model_name='racklocationrecipe',
            name='unique_enabled_recipe_per_position_layer',
        ),
    ]
