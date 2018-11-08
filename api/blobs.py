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


import os
import uuid

from django.conf import settings
import lzma


def save_blob(data, name=None):
    if not name:
        name = str(uuid.uuid4())
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    lzma.open(fn, 'w').write(data.encode("utf-8"))
    return name


def load_blob(name):
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    return lzma.open(fn, 'r').read().decode("utf-8")


def delete_blob(name):
    fn = os.path.join(settings.DATA_DIR, "blob", name + ".xz")
    try:
        os.remove(fn)
    except FileNotFoundError:
        pass
