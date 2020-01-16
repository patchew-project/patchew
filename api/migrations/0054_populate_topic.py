# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations


def topic_fill(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    Topic = apps.get_model("api", "Topic")
    for record in (
        Message.objects.filter(is_series_head=True)
        .values("stripped_subject")
        .distinct()
    ):
        topic = Topic()
        topic.save()
        topic_subject = record["stripped_subject"]
        Message.objects.filter(
            is_series_head=True, stripped_subject=topic_subject
        ).update(topic=topic)


class Migration(migrations.Migration):
    dependencies = [("api", "0053_auto_20200116_0955")]

    operations = [
        migrations.RunPython(topic_fill, reverse_code=migrations.RunPython.noop)
    ]
