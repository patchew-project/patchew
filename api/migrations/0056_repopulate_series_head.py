# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


def series_head_fill(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    Message.objects.filter(topic__isnull=False).update(is_series_head=True)


class Migration(migrations.Migration):
    dependencies = [("api", "0055_auto_20200116_1034")]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, reverse_code=series_head_fill)
    ]
