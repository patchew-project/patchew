#! /usr/bin/env python3
from __future__ import unicode_literals

from django.db import migrations, transaction

def remove_null_mbox_messages(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    Topic = apps.get_model("api", "Topic")
    Topic.objects.filter(latest__mbox_bytes=None).update(latest=None)
    Message.objects.filter(mbox_bytes=None).delete()

class Migration(migrations.Migration):

    dependencies = [("api", "0062_deblob_messages")]

    operations = [
        migrations.RunPython(remove_null_mbox_messages, reverse_code=migrations.RunPython.noop)
    ]

