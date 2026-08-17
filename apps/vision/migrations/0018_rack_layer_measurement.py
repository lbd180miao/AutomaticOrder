from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0017_visionrecipe_standard_template'),
        ('workflow', '0004_stationcycle'),
    ]

    operations = [
        migrations.CreateModel(
            name='RackMeasurementProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(default='默认料架测量配置', max_length=128)),
                ('camera_code', models.CharField(default='CAM-INSPECT-RACK-01', max_length=64)),
                ('roi_x', models.PositiveIntegerField(default=0)),
                ('roi_y', models.PositiveIntegerField(default=0)),
                ('roi_width', models.PositiveIntegerField(default=0, help_text='0 表示延伸到图像右边界')),
                ('roi_height', models.PositiveIntegerField(default=0, help_text='0 表示延伸到图像下边界')),
                ('mm_per_pixel', models.DecimalField(decimal_places=6, default=1, max_digits=10)),
                ('edge_threshold', models.DecimalField(decimal_places=4, default=0.18, max_digits=5)),
                ('min_peak_distance', models.PositiveIntegerField(default=8)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
            ],
            options={'ordering': ['-is_active', '-updated_at']},
        ),
        migrations.CreateModel(
            name='RackLayerMeasurement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source', models.CharField(choices=[('MANUAL_UPLOAD', '手动上传'), ('MANUAL_CAMERA', '手动拍照'), ('PLC_AUTO', 'PLC 自动触发')], max_length=32)),
                ('input_image_path', models.CharField(blank=True, max_length=512)),
                ('result_image_path', models.CharField(blank=True, max_length=512)),
                ('detected_layer_count', models.PositiveIntegerField(default=0)),
                ('measured_layer_height', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('measured_layer_spacing', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('confidence', models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ('passed', models.BooleanField(blank=True, null=True)),
                ('is_success', models.BooleanField(default=False)),
                ('parameters', models.JSONField(blank=True, default=dict)),
                ('result_data', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True)),
                ('profile', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='measurements', to='vision.rackmeasurementprofile')),
                ('station_cycle', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rack_measurements', to='workflow.stationcycle')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
