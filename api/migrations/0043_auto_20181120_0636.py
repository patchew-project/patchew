# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-20 06:36
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('api', '0042_review_to_queue'),
    ]

    operations = [
        migrations.RenameField(
            model_name='message',
            old_name='reviews',
            new_name='queues',
        ),
        migrations.AddField(
            model_name='queuedseries',
            name='name',
            field=models.CharField(default='accept', help_text='Name of the queue', max_length=1024),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='queuedseries',
            name='accept',
        ),
        migrations.AlterUniqueTogether(
            name='queuedseries',
            unique_together=set([('user', 'message', 'name')]),
        ),
        migrations.AlterIndexTogether(
            name='queuedseries',
            index_together=set([('user', 'message')]),
        ),
    ]
