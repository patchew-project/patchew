#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter

from . import views
from . import rest

def _build_urls(base=None, r=[]):
    for cls in (base or views.APIView).__subclasses__():
        if cls.name:
            # API views should handle the authentication explicitly, disable
            # csrf check to simplify client code
            r.append(url(cls.name + "/", cls.as_view()))
        else:
            _build_urls(cls, r)
    return r

router = DefaultRouter(trailing_slash=True)
router.include_format_suffixes = False
router.register('users', rest.UsersViewSet)
router.register('projects', rest.ProjectsViewSet)
router.register('series', rest.SeriesViewSet, base_name='series')

projects_router = NestedDefaultRouter(router, 'projects', lookup='projects', trailing_slash=True)
projects_router.include_format_suffixes = False
projects_router.register('series', rest.ProjectSeriesViewSet, base_name='series')
projects_router.register('messages', rest.MessagesViewSet, base_name='messages')

urlpatterns = _build_urls() + [
        url(r"v1/", include(router.urls)),
        url(r"v1/", include(projects_router.urls)),
        # Use the base class's handler by default
        url(r".*", views.APIView.as_view())
    ]


