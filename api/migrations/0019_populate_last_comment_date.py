# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import json


def populate_last_comment_date(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Message = apps.get_model('api', 'Message')
    msgs = Message.objects.order_by('date')
    msgs = msgs.exclude(in_reply_to="")
    for m in msgs:
        # This is the same as m.get_series_head()
        s = m
        while s:
            if s.is_series_head:
                break
            s = Message.objects.filter(project_id=s.project_id,
                                       message_id=s.in_reply_to).first()

        if s and json.loads(s.sender)[1] != json.loads(m.sender)[1]:
            s.last_comment_date=m.date
            s.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_message_last_comment_date'),
    ]

    operations = [
        migrations.RunPython(populate_last_comment_date,
                             reverse_code=migrations.RunPython.noop),
    ]
