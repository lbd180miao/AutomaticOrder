from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0003_alter_product_current_state'),
        ('vision', '0019_alter_visionrecipe_recipe_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='rackrecipe',
            name='full_condition',
            field=models.CharField(
                choices=[
                    ('QUANTITY_REACHED', '达到总装箱数量'),
                    ('PLC_OR_QUANTITY', 'PLC满框信号或达到数量'),
                ],
                default='QUANTITY_REACHED',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='rackrecipe',
            name='loading_direction',
            field=models.CharField(
                choices=[
                    ('BOTTOM_UP_LEFT_RIGHT', '从下到上、从左到右'),
                    ('BOTTOM_UP_RIGHT_LEFT', '从下到上、从右到左'),
                    ('TOP_DOWN_LEFT_RIGHT', '从上到下、从左到右'),
                    ('TOP_DOWN_RIGHT_LEFT', '从上到下、从右到左'),
                ],
                default='BOTTOM_UP_LEFT_RIGHT',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='rackrecipe',
            name='mes_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='rackrecipe',
            name='product_code',
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name='rackrecipe',
            name='station_position_count',
            field=models.PositiveIntegerField(default=2),
        ),
        migrations.AddField(
            model_name='rackrecipe',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name='RackRecipeVisionMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('station_position_no', models.PositiveIntegerField(default=1)),
                ('layer_no', models.PositiveIntegerField(default=1)),
                ('robot_target_code', models.CharField(blank=True, max_length=64)),
                ('enabled', models.BooleanField(default=True)),
                ('rack_location_recipe', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='rack_recipe_mappings',
                    to='vision.racklocationrecipe',
                )),
                ('rack_recipe', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vision_mappings',
                    to='production.rackrecipe',
                )),
            ],
            options={
                'ordering': ['rack_recipe_id', 'station_position_no', 'layer_no'],
            },
        ),
        migrations.AddConstraint(
            model_name='rackrecipevisionmapping',
            constraint=models.UniqueConstraint(
                fields=('rack_recipe', 'station_position_no', 'layer_no'),
                name='unique_rack_recipe_position_layer_mapping',
            ),
        ),
    ]
