# Generated by Django 3.1 on 2021-01-06 11:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0059_populate_topic_latest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='is_merged',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
