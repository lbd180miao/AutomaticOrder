from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0013_roi3dtemplate_racklocationroi3denhanced'),
    ]

    operations = [
        migrations.AddField(
            model_name='racklocationresult',
            name='roi_data',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='本次定位使用的ROI快照（像素ROI与三维坐标范围）',
            ),
        ),
    ]
