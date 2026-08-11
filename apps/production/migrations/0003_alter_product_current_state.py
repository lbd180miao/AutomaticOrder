from django.db import migrations, models


WORKFLOW_STATE_CHOICES = [
    ('CREATED', '已创建'), ('INJECTION_PICKED', '注塑已取件'),
    ('MARKING_READY', '已到打标位'), ('MARKED', '已打标'),
    ('BARCODE_READ', '条码已读取'), ('MES_UPLOADED', 'MES已上传'),
    ('HANDOVER_WAITING', '待交接'), ('HANDOVER_ROBOT_READY', '装箱机器人已就绪'),
    ('HANDOVER_GRIPPED', '装箱机器人已抓牢'),
    ('INJECTION_RELEASED', '注塑机器人已释放'),
    ('RACK_SCAN_READY', '料框扫码就绪'), ('RACK_SCANNED', '料框已扫码'),
    ('RECIPE_LOADED', '配方已加载'), ('RACK_LOCATING', '料架定位中'),
    ('RACK_LOCATED', '料架定位完成'), ('RECIPE_VERIFIED', '配方校验通过'),
    ('BOXING', '装箱中'), ('FOAM_PICKING', '泡棉抓取中'),
    ('FOAM_ATTACHING', '泡棉贴附中'), ('FOAM_INSPECTING', '泡棉检测中'),
    ('COMPLETED', '工序完成'), ('LOCKED', '异常锁定'), ('FAILED', '流程失败'),
]


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0002_alter_product_mark_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='current_state',
            field=models.CharField(
                choices=WORKFLOW_STATE_CHOICES,
                default='CREATED',
                max_length=64,
            ),
        ),
    ]
