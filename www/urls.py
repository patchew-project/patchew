#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.urls import re_path  # Changed: use re_path instead of deprecated django.conf.urls.url
from django.contrib.auth import views as auth_views
from . import views
from mod import dispatch_module_hook

urlpatterns = []
dispatch_module_hook("www_url_hook", urlpatterns=urlpatterns)

urlpatterns += [
    re_path(
        r"^login/$",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="login",
    ),
    re_path(r"^logout/$", auth_views.LogoutView.as_view(), name="logout"),
    re_path(
        r"^change-password/$",
        auth_views.PasswordChangeView.as_view(template_name="password-change.html"),
        name="password_change",
    ),
    re_path(
        r"^change-password/done/$",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="password-change-done.html"
        ),
        name="password_change_done",
    ),
    re_path(r"^search$", views.view_search, name="search"),
    re_path(r"^search-help$", views.view_search_help, name="search_help"),
    re_path(r"^(?P<project>[^/]*)/$", views.view_series_list, name="series_list"),
    re_path(r"^(?P<project>[^/]*)/info$", views.view_project_detail, name="project_detail"),
    re_path(
        r"^(?P<project>[^/]*)/logs/(?P<name>.*)/",
        views.ProjectLogViewer.as_view(),
        name="project-result-log",
    ),
    re_path(
        r"^(?P<project>[^/]*)/(?P<message_id>.*)/logs/(?P<name>[^/]*)/",
        views.SeriesLogViewer.as_view(),
        name="series-result-log",
    ),
    re_path(
        r"^(?P<project>[^/]*)/(?P<message_id>[^/]*)/$",
        views.view_series_detail,
        name="series_detail",
    ),
    re_path(
        r"^(?P<project>[^/]*)/(?P<thread_id>[^/]*)/(?P<message_id>[^/]*)/$",
        views.view_series_message,
        name="series_message",
    ),
    re_path(
        r"^(?P<project>[^/]*)/(?P<message_id>[^/]*)/mbox$",
        views.view_mbox,
        name="mbox",
    ),
    re_path(r"^$", views.view_project_list, name="project_list"),
]
