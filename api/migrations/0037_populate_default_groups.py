# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Count
import json


def populate_default_groups(apps, schema_editor):
    from django.contrib.auth.models import Group
    for grp in ['maintainers', 'testers', 'importers']:
        Group.objects.get_or_create(name=grp)

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_populate_message_tags'),
    ]

    operations = [
        migrations.RunPython(populate_default_groups),
    ]
