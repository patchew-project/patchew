# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Q

def properties_to_config(apps, schema_editor):
    Project = apps.get_model('api', 'Project')
    for po in Project.objects.all():
        q = Q(name__startswith='testing.tests.') | \
            Q(name__startswith='testing.requirements.') | \
            Q(name__startswith='email.notifications.') | \
            Q(name__in=('git.push_to', 'git.url_template', 'git.public_repo'))
        props = po.projectproperty_set.filter(q)
        config = {}
        for p in props:
            *path, last = p.name.split('.')
            parent = config
            for item in path:
                parent = parent.setdefault(item, {})
            parent[last] = p.value
        #print(po, config)
        po.config = config
        po.save()
        props.delete()

def flatten_properties(source, prefix, result=None):
    if result is None:
        result = {}
    for k, v in source.items():
        if isinstance(v, dict):
            flatten_properties(v, prefix + k + '.', result)
        else:
            result[prefix + k] = v
    return result

def config_to_properties(apps, schema_editor):
    Project = apps.get_model('api', 'Project')
    ProjectProperty = apps.get_model('api', 'ProjectProperty')
    for po in Project.objects.all():
        props = flatten_properties(po.config, '')
        for k, v in props.items():
            new_prop = ProjectProperty(project=po, name=k, value=v)
            new_prop.save()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0046_project_config'),
    ]

    operations = [
        migrations.RunPython(properties_to_config,
                             reverse_code=config_to_properties),
    ]
