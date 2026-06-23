# Manual migration to add missing actual_x, actual_y, actual_z columns
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vision', '0005_racklocationresult_confidence_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='racklocationresult',
            name='actual_x',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='racklocationresult',
            name='actual_y',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='racklocationresult',
            name='actual_z',
            field=models.DecimalField(decimal_places=3, default=0, max_digits=10),
        ),
    ]
