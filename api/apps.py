#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.



from django.apps import AppConfig
import mod

_default_groups = ['maintainers', 'testers', 'importers']

def create_default_groups():
    from django.contrib.auth.models import Group
    for grp in _default_groups:
        Group.objects.get_or_create(name=grp)

class ApiConfig(AppConfig):
    name = 'api'
    verbose_name = "Patchew Core"
    def ready(self):
        try:
            mod.load_modules()
            create_default_groups()
        except Exception as e:
            print("Error while loading modules:", e)
