#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

"""
WSGI config for patchew project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/howto/deployment/wsgi/
"""

import os
import sys

## GETTING-STARTED: make sure the next line points to your django project dir:
if "OPENSHIFT_REPO_DIR" in os.environ:
    sys.path.append(os.path.join(os.environ['OPENSHIFT_REPO_DIR'], 'wsgi', 'patchew'))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patchew.settings")

from distutils.sysconfig import get_python_lib
os.environ['PYTHON_EGG_CACHE'] = get_python_lib()

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
