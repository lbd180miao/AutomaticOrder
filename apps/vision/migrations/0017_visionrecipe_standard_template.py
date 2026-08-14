from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0016_add_local_template_std_to_rack_recipe'),
    ]

    operations = [
        migrations.AddField(
            model_name='visionrecipe',
            name='standard_template_built_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='visionrecipe',
            name='standard_template_config',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='2D泡棉标准模板快照，包含左右掩膜、ROI、分辨率和特征摘要',
            ),
        ),
        migrations.AddField(
            model_name='visionrecipe',
            name='standard_template_version',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
