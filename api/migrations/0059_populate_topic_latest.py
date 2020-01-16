# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


def topic_fill_latest(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    Topic = apps.get_model("api", "Topic")
    series = Message.objects.filter(topic__isnull=False)
    for m in series.filter(is_obsolete=False):
        m.topic.latest = m
        m.save()
    for m in series.filter(is_obsolete=True):
        if "obsoleted-by" in m.properties:
            del m.properties["obsoleted-by"]
            m.save()


def message_set_obsoleted_by(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    for m in Message.objects.filter(is_obsolete=True, topic__latest__isnull=False):
        m.properties["obsoleted-by"] = m.topic.latest.message_id
        m.save()


class Migration(migrations.Migration):
    dependencies = [("api", "0058_topic_latest")]

    operations = [
        migrations.RunPython(topic_fill_latest, reverse_code=message_set_obsoleted_by)
    ]
