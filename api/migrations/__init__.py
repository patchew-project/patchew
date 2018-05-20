#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Paolo Bonzini <pbonzini@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.


import json
from api import blobs

def load_blob_json_safe(name):
    try:
        return json.loads(blobs.load_blob(name))
    except Exception as e:
        return 'Failed to load blob %s: %s' % (name, e)

def get_property_raw(model, name, **kwargs):
    try:
        mp = model.objects.get(name=name, **kwargs)
        return mp
    except model.DoesNotExist:
        return None

def load_property(mp):
    if mp.blob:
        return load_blob_json_safe(mp.value)
    else:
        return json.loads(mp.value)

def get_property(model, name, **kwargs):
    mp = get_property_raw(model, name, **kwargs)
    return load_property(mp) if mp else None

def delete_property_blob(model, name, **kwargs):
    mp = get_property_raw(model, name, **kwargs)
    if mp.blob:
        blobs.delete_blob(mp.value)

def set_property(model, name, value, **kwargs):
    if value is not None:
        value = json.dumps(value)
    mp, created = model.objects.get_or_create(name=name, **kwargs)
    mp.value = value
    mp.blob = False
    mp.save()
