# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2020-01-16 13:36
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0057_remove_message_is_series_head'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='latest',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='api.Message'),
        ),
    ]
