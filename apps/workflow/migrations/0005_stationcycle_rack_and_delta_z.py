from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0003_alter_product_current_state'),
        ('workflow', '0004_stationcycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='stationcycle',
            name='rack',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='station_cycles',
                to='production.rack',
            ),
        ),
        migrations.AddField(
            model_name='stationcycle',
            name='position_delta_z',
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=10, null=True,
            ),
        ),
    ]
