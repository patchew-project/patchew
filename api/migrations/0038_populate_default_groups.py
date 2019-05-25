# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


def populate_default_groups(apps, schema_editor):
    from django.contrib.auth.models import Group
    for grp in ['maintainers', 'testers', 'importers']:
        Group.objects.get_or_create(name=grp)

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_auto_20181031_1439'),
    ]

    operations = [
        migrations.RunPython(populate_default_groups),
    ]
