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


class ApiConfig(AppConfig):
    name = 'api'
    verbose_name = "Patchew Core"

    def ready(self):
        from mod import load_modules
        load_modules()
