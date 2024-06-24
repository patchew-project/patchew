# Generated by Django 3.1.14 on 2022-09-19 10:04

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0065_auto_20220411_1153'),
    ]

    operations = [
        migrations.AddField(
            model_name='result',
            name='project_denorm',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+', to='api.project'),
        ),
        migrations.AlterField(
            model_name='projectresult',
            name='project',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='results', to='api.project'),
        ),
    ]