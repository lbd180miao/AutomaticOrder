# Generated manually for visual recipe module
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0003_foaminspectionresult_coverage_ratio_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='VisionRecipe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('recipe_type', models.CharField(choices=[('FOAM_2D', '泡棉检测配方'), ('RACK_3D', '料架定位配方')], max_length=32)),
                ('name', models.CharField(max_length=100)),
                ('product_code', models.CharField(blank=True, max_length=100, null=True)),
                ('rack_type', models.CharField(blank=True, max_length=100, null=True)),
                ('camera_side', models.CharField(blank=True, default='both', max_length=20, null=True)),
                ('pos', models.IntegerField(default=0)),
                ('image_width', models.IntegerField(default=1280)),
                ('image_height', models.IntegerField(default=720)),
                ('roi_config', models.JSONField(blank=True, default=dict)),
                ('threshold_config', models.JSONField(blank=True, default=dict)),
                ('algorithm_config', models.JSONField(blank=True, default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('remark', models.TextField(blank=True, null=True)),
            ],
            options={
                'ordering': ['recipe_type', 'pos', '-updated_at'],
            },
        ),
    ]
