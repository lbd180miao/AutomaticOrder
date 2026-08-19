from django.db import migrations


def classify_existing_alarms(apps, schema_editor):
    Alarm = apps.get_model('alarms', 'Alarm')
    rules = (
        ('泡棉检测不合格', 'FOAM_INSPECTION_NG'),
        ('配方校验不通过', 'RECIPE_MEASUREMENT_OUT_OF_TOLERANCE'),
        ('POINTCLOUD_ERROR', 'VISION_POINTCLOUD_ERROR'),
        ('定位失败', 'VISION_3D_POSITION_FAILED'),
        ('条码', 'BARCODE_VALIDATION_FAILED'),
        ('MES', 'MES_REQUEST_FAILED'),
        ('通讯', 'DEVICE_COMMUNICATION_FAILED'),
        ('通信', 'DEVICE_COMMUNICATION_FAILED'),
    )
    for alarm in Alarm.objects.all().iterator():
        code = ''
        for marker, candidate in rules:
            if marker in alarm.message:
                code = candidate
                break
        alarm.error_code = code or f'{alarm.source}_ERROR'
        alarm.last_occurred_at = alarm.created_at
        alarm.save(update_fields=['error_code', 'last_occurred_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('alarms', '0003_alarm_context_and_actions'),
    ]

    operations = [
        migrations.RunPython(classify_existing_alarms, migrations.RunPython.noop),
    ]
