# Generated by Django 3.1.14 on 2022-04-06 07:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0060_auto_20210106_1120'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='mbox_bytes',
            field=models.BinaryField(null=True),
        ),
    ]
