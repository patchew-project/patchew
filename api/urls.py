#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from rest_auth.views import LoginView, LogoutView

from django.conf.urls import url, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter
from rest_framework.schemas import get_schema_view
from rest_framework import permissions

from . import views
from . import rest
from mod import dispatch_module_hook


def _build_urls(base=None, r=[]):
    for cls in (base or views.APIView).__subclasses__():
        if cls.name:
            # API views should handle the authentication explicitly, disable
            # csrf check to simplify client code
            r.append(url("^" + cls.name + "/", cls.as_view()))
        else:
            _build_urls(cls, r)
    return r


router = DefaultRouter(trailing_slash=True)
router.include_format_suffixes = False
router.register("users", rest.UsersViewSet)
router.register("projects", rest.ProjectsViewSet)
router.register("series", rest.SeriesViewSet, basename="series")
router.register("messages", rest.MessagesViewSet)

projects_router = NestedDefaultRouter(
    router, "projects", lookup="projects", trailing_slash=True
)
projects_router.include_format_suffixes = False
projects_router.register("results", rest.ProjectResultsViewSet, basename="results")
projects_router.register("series", rest.ProjectSeriesViewSet, basename="series")
projects_router.register("messages", rest.ProjectMessagesViewSet, basename="messages")

results_router = NestedDefaultRouter(
    projects_router, "series", lookup="series", trailing_slash=True
)
results_router.include_format_suffixes = False
results_router.register("results", rest.SeriesResultsViewSet, basename="results")

schema_view = get_schema_view(title="API schema",
                              permission_classes=[permissions.AllowAny])

urlpatterns = _build_urls()
dispatch_module_hook("api_url_hook", urlpatterns=urlpatterns)
urlpatterns += [
    url(
        r"^v1/projects/by-name/(?P<name>[^/]*)(?P<tail>/.*|$)",
        rest.ProjectsByNameView.as_view(),
    ),
    url(r"^v1/users/login/$", LoginView.as_view(), name="rest_login"),
    url(r"^v1/users/logout/$", LogoutView.as_view(), name="rest_logout"),
    url(r"^v1/", include(router.urls)),
    url(r"^v1/", include(projects_router.urls)),
    url(r"^v1/", include(results_router.urls)),
    url(r"^v1/schema/$", schema_view),
    # Use the base class's handler by default
    url(r".*", views.APIView.as_view()),
]
