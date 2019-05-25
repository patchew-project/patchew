# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from api import blobs


def deblob_properties(apps, schema_editor):
    def do_deblob_properties(model):
        objects = model.objects.filter(blob=True)
        for obj in objects:
            obj.blob = False
            if obj.value is not None:
                obj.value = blobs.load_blob(obj.value)
            obj.save()

    # We can't import the models directly as they may be a newer
    # version than this migration expects. We use the historical version.
    do_deblob_properties(apps.get_model("api", "MessageProperty"))
    do_deblob_properties(apps.get_model("api", "ProjectProperty"))


class Migration(migrations.Migration):

    dependencies = [("api", "0029_populate_testing_results")]

    operations = [
        migrations.RunPython(deblob_properties, reverse_code=migrations.RunPython.noop)
    ]
