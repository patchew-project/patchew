from django.conf.urls import url
from . import views
from mod import dispatch_module_hook

urlpatterns = []
dispatch_module_hook("www_url_hook", urlpatterns=urlpatterns)

urlpatterns += [
        url(r"^search$", views.view_search, name="search"),
        url(r"^search-help$", views.view_search_help, name="search_help"),
        url(r"^(?P<project>[^/]*)/$", views.view_series_list, name="series_list"),
        url(r"^(?P<project>[^/]*)/info$", views.view_project_detail, name="project_detail"),
        url(r"^(?P<project>[^/]*)/(?P<message_id>[^/]*)/$", views.view_series_detail, name="series_detail"),
        url(r"^(?P<project>[^/]*)/(?P<message_id>[^/]*)/mbox$", views.view_series_mbox),
        url(r"^$", views.view_project_list, name="project_list"),
        ]
