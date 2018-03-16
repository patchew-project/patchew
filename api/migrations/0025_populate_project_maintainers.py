# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import Count
import json


def maintainers_from_property(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Project = apps.get_model('api', 'Project')
    ProjectProperty = apps.get_model('api', 'ProjectProperty')
    User = apps.get_model('auth', 'User')
    projects = Project.objects.filter(projectproperty__name='maintainers')
    for p in projects:
        p.maintainers.clear()
        pp = p.projectproperty_set.filter(name='maintainers')[0]
        # NOTE: this will fail if the property is a blob
        maintainers = json.loads(pp.value)
        users = User.objects.filter(username__in=maintainers)
        p.maintainers.add(*users)
    ProjectProperty.objects.filter(name='maintainers').delete()

def maintainers_to_property(apps, schema_editor):
    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    Project = apps.get_model('api', 'Project')
    ProjectProperty = apps.get_model('api', 'ProjectProperty')
    User = apps.get_model('auth', 'User')
    projects = Project.objects. \
        annotate(maintainer_count=Count('maintainers')). \
        filter(maintainer_count__gt=0)
    for p in projects:
        maintainers = [u.username for u in p.maintainers.all()]
        pp = ProjectProperty(project=p,
                             name='maintainers',
                             value=json.dumps(maintainers),
                             blob=False)
        pp.save()
        p.maintainers.clear()

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_project_maintainers'),
    ]

    operations = [
        migrations.RunPython(maintainers_from_property,
                             reverse_code=maintainers_to_property),
    ]
