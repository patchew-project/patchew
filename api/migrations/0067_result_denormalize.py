# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
from django.db.models import F, Subquery, OuterRef


def populate_denormalized_project(apps, schema_editor):
    Message = apps.get_model("api", "Message")
    MessageResult = apps.get_model("api", "MessageResult")
    ProjectResult = apps.get_model("api", "ProjectResult")
    ProjectResult.objects.filter(project_denorm__isnull=True).update(
        project_denorm=
            Subquery(ProjectResult.objects.filter(result_ptr_id=OuterRef('pk')).values('project')[:1]))
    MessageResult.objects.filter(project_denorm__isnull=True).update(
        project_denorm=
            Subquery(MessageResult.objects.filter(result_ptr_id=OuterRef('pk')).values('message__project')[:1]))


def populate_projectresult_project(apps, schema_editor):
    ProjectResult = apps.get_model("api", "ProjectResult")
    ProjectResult.update(project=F('project_denorm'))


class Migration(migrations.Migration):

    dependencies = [("api", "0066_auto_20220919_1004")]

    operations = [
        migrations.RunPython(populate_denormalized_project, populate_projectresult_project)
    ]

