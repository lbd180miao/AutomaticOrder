from django.db import migrations


def seed(apps, schema_editor):
    mapping = apps.get_model('mes', 'PkgTypeMapping')
    rows = mapping.objects.using(schema_editor.connection.alias)
    for rack_type, value in [('两层', 1), ('三层', 2), ('五层', 3)]:
        rows.filter(rack_type=rack_type, plc_value__isnull=True).update(plc_value=value)
    for code, rack_type, value in [('2LayerRack', '两层', 1), ('3LayerRack', '三层', 2),
                                  ('5LayerRack', '五层', 3), ('5LaverRack', '五层', 3)]:
        rows.get_or_create(pkg_type_code=code, defaults={'rack_type': rack_type, 'plc_value': value})


class Migration(migrations.Migration):
    dependencies = [('mes', '0005_pkgtypemapping_plc_value')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
