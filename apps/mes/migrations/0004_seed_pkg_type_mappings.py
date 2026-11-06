from django.db import migrations


def seed(apps, schema_editor):
    mapping = apps.get_model('mes', 'PkgTypeMapping')
    for start, rack_type in ((31231321, '三层'), (8888812312, '两层')):
        for code in range(start, start + 8):
            mapping.objects.using(schema_editor.connection.alias).get_or_create(
                pkg_type_code=str(code), defaults={'rack_type': rack_type})


class Migration(migrations.Migration):
    dependencies = [('mes', '0003_pkgtypemapping')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
