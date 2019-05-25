# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

def property_to_flags(apps, schema_editor):
    MessageProperty = apps.get_model('api', 'MessageProperty')
    for p in MessageProperty.objects.filter(name='obsoleted-by'):
        p.message.is_obsolete = True
        p.message.save()
    for p in MessageProperty.objects.filter(name='reviewed'):
        p.message.is_reviewed = True
        p.message.save()
    for p in MessageProperty.objects.filter(name='testing.done'):
        p.message.is_tested = True
        p.message.save()
    MessageProperty.objects.filter(name='reviewed').delete()
    MessageProperty.objects.filter(name='testing.done').delete()

def flags_to_property(apps, schema_editor):
    Message = apps.get_model('api', 'Message')
    MessageProperty = apps.get_model('api', 'MessageProperty')
    for m in Message.objects.exclude(flags=''):
        if m.is_reviewed:
            new_prop = MessageProperty(message=p.message, name='reviewed', value=True)
            new_prop.save()
        if m.is_tested:
            new_prop = MessageProperty(message=p.message, name='testing.done', value=True)
            new_prop.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0048_auto_20190506_1423'),
    ]

    operations = [
        migrations.RunPython(property_to_flags,
                             reverse_code=flags_to_property),
    ]
