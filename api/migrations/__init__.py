#!/usr/bin/env python3
#
# Copyright 2016, 2018 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.conf import settings
from django.db import migrations

import json
import lzma
import os
import uuid


def load_blob(name):
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    return lzma.open(fn, "r").read().decode("utf-8")


def delete_blob(name):
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    try:
        os.remove(fn)
    except FileNotFoundError:
        pass

def load_blob_json_safe(name):
    try:
        return json.loads(load_blob(name))
    except Exception as e:
        return "Failed to load blob %s: %s" % (name, e)


def get_property_raw(model, name, **kwargs):
    try:
        mp = model.objects.get(name=name, **kwargs)
        return mp
    except model.DoesNotExist:
        return None


def load_property(mp):
    if hasattr(mp, "blob") and mp.blob:
        return load_blob_json_safe(mp.value)
    else:
        return json.loads(mp.value)


def get_property(model, name, **kwargs):
    mp = get_property_raw(model, name, **kwargs)
    return load_property(mp) if mp else None


def delete_property_blob(model, name, **kwargs):
    mp = get_property_raw(model, name, **kwargs)
    if hasattr(mp, "blob") and mp.blob:
        delete_blob(mp.value)


def set_property(model, name, value, **kwargs):
    if value is not None:
        value = json.dumps(value)
    mp, created = model.objects.get_or_create(name=name, **kwargs)
    mp.value = value
    if hasattr(mp, "blob"):
        mp.blob = False
    mp.save()


class PostgresOnlyMigration(migrations.Migration):
    def apply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor == "postgresql":
            return super().apply(project_state, schema_editor, collect_sql=collect_sql)
        else:
            return project_state

    def unapply(self, project_state, schema_editor, collect_sql=False):
        if schema_editor.connection.vendor == "postgresql":
            return super().unapply(
                project_state, schema_editor, collect_sql=collect_sql
            )
        else:
            return project_state
