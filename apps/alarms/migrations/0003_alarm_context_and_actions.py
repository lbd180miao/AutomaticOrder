from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('alarms', '0002_alter_alarm_level_alter_alarm_source_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='alarm',
            name='context',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='alarm',
            name='error_code',
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name='alarm',
            name='last_occurred_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='alarm',
            name='occurrence_count',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='alarm',
            name='phase',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='alarm',
            name='scene',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.CreateModel(
            name='AlarmAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action', models.CharField(choices=[('ACKNOWLEDGE', '确认报警'), ('CLOSE', '关闭报警')], max_length=32)),
                ('operator', models.CharField(blank=True, max_length=128)),
                ('note', models.TextField(blank=True)),
                ('success', models.BooleanField(default=True)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('alarm', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='alarms.alarm')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
