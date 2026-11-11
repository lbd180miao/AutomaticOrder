from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('mes', '0006_seed_plc_mapping_values')]
    operations = [
        migrations.RemoveConstraint(model_name='pkgtypemapping', name='mes_pkg_standard_rack_type'),
        migrations.AlterField(model_name='pkgtypemapping', name='rack_type',
                              field=models.CharField('标准料架类型', max_length=16)),
    ]
