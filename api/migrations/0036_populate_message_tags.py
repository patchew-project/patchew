# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Count
import json


def tags_from_property(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Message = apps.get_model('api', 'Message')
    MessageProperty = apps.get_model('api', 'MessageProperty')
    messages = Message.objects.filter(properties__name='tags')
    for m in messages:
        mp = m.properties.filter(name='tags')[0]
        m.tags = mp.value
        m.save()
    MessageProperty.objects.filter(name='tags').delete()

def tags_to_property(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Message = apps.get_model('api', 'Message')
    MessageProperty = apps.get_model('api', 'MessageProperty')
    messages = Message.objects.exclude(tags=[])
    for m in messages:
        mp = MessageProperty(message=m,
                             name='tags',
                             value=m.tags,
                             blob=False)
        mp.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0035_message_tags'),
    ]

    operations = [
        migrations.RunPython(tags_from_property,
                             reverse_code=tags_to_property),
    ]
