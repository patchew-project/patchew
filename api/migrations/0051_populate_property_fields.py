# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, transaction


def do_properties_to_field(obj, propset):
    properties = {}
    props = propset.all()
    for p in props:
        *path, last = p.name.split(".")
        parent = properties
        for item in path:
            parent = parent.setdefault(item, {})
        parent[last] = p.value
    obj.properties = properties
    # print(obj, properties)
    obj.save()
    props.delete()


def properties_to_field(apps, schema_editor):
    Project = apps.get_model("api", "Project")
    for po in Project.objects.all():
        do_properties_to_field(po, po.projectproperty_set)

    # fetching all messages can cause out of memory errors!
    MessageProperty = apps.get_model("api", "MessageProperty")
    while True:
        print(MessageProperty.objects.count())
        mp = MessageProperty.objects.first()
        if not mp:
            break
        m = mp.message
        with transaction.atomic():
            do_properties_to_field(m, m.messageproperty_set)


def flatten_properties(source, prefix, result=None):
    if result is None:
        result = {}
    for k, v in source.items():
        if isinstance(v, dict):
            flatten_properties(v, prefix + k + ".", result)
        else:
            result[prefix + k] = v
    return result


def do_field_to_properties(source, propclass, **kwargs):
    props = flatten_properties(source, "")
    for k, v in props.items():
        # print(k, v)
        new_prop = propclass(name=k, value=v, **kwargs)
        new_prop.save()


def field_to_properties(apps, schema_editor):
    Project = apps.get_model("api", "Project")
    ProjectProperty = apps.get_model("api", "ProjectProperty")
    for po in Project.objects.all():
        with transaction.atomic():
            do_field_to_properties(po.properties, ProjectProperty, project=po)
    Message = apps.get_model("api", "Message")
    MessageProperty = apps.get_model("api", "MessageProperty")
    for m in Message.objects.all():
        with transaction.atomic():
            do_field_to_properties(m.properties, MessageProperty, message=m)


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("api", "0050_auto_20190418_1346")]

    operations = [
        migrations.RunPython(properties_to_field, reverse_code=field_to_properties)
    ]
