# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import json
import email.header


def _parse_header(header):
    r = ''
    for h, c in email.header.decode_header(header):
        if isinstance(h, bytes):
            h = h.decode(c or 'utf-8', 'replace')
        r += h
    return r

def fix_utf8_recipients(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Message = apps.get_model('api', 'Message')
    msgs = Message.objects.all()
    msgs = msgs.filter(recipients__contains="?")
    for m in msgs:
        recipients = json.loads(m.recipients)
        recipients = [[_parse_header(x[0]), x[1]] for x in recipients]
        m.recipients = json.dumps(recipients)
        m.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_auto_20180204_0647'),
    ]

    operations = [
        migrations.RunPython(fix_utf8_recipients,
                             reverse_code=migrations.RunPython.noop),
    ]
