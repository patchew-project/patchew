#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from collections import namedtuple
from django.conf.urls import url
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Exists, OuterRef
from mod import PatchewModule
from api.models import Message
from api.rest import PluginMethodField
import rest_framework
from www.views import render_page
import re

_instance = None

PatchInfo = namedtuple('PatchInfo', ['subject', 'link', 'has_replies', 'body'])

class DiffModule(PatchewModule):
    """Diff module"""
    name = "diff"

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self

    def get_other_versions_urls(self, project, message_id, other_versions):
        left = False
        for o in sorted(other_versions, key=lambda y: y.version):
            if o.message_id == message_id:
                left = True
                continue
            # The oldest series always goes on the left
            kwargs={"project": project.name,
                    "series_left": message_id if left else o.message_id,
                    "series_right": o.message_id if left else message_id}
            yield o.version, reverse("series_diff", kwargs=kwargs)

    def get_other_versions(self, message, request, format):
        other_versions = message.get_alternative_revisions()
        return [{'version': o.version,
                 'resource_uri': rest_framework.reverse.reverse("series-detail",
                     kwargs={"projects_pk": o.project.id, "message_id": o.message_id},
                     request=request, format=format)}
                 for o in sorted(other_versions, key=lambda y: y.version)
                 if o.message_id != message.message_id]

    def rest_series_fields_hook(self, request, fields, detailed):
        fields['version'] = rest_framework.fields.IntegerField()
        if detailed:
            fields['other_versions'] = PluginMethodField(obj=self)

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head or not detailed:
            return
        other_versions = message.get_alternative_revisions()
        if len(other_versions) <= 1:
            return
        message.has_other_revisions = True
        html = "Diff against"
        for v, url in self.get_other_versions_urls(message.project, message.message_id, other_versions):
            html = html + format_html(' <a href="{}">v{}</a>', url, v)
        message.extra_links.append({"html": mark_safe(html), "icon": "exchange" })

    def _get_series_for_diff(self, q):
        def _get_message_data(m):
            filtered = ""
            sep = ""
            for l in m.get_body().splitlines():
                for pat, repl in [(r"index [0-9a-f]+\.\.[0-9a-f]+",
                                   r"index XXXXXXX..XXXXXXX"),
                                  (r"@@ -[0-9]+,[0-9]+ \+[0-9]+,[0-9]+ @@ ",
                                   r"@@ -XXX,XX +XXX,XX @@ ")]:
                    l = re.sub(pat, repl, l)
                filtered += sep + l
                sep = "\n"

            return PatchInfo(
                subject=m.subject,
                link=m.get_message_view_url(),
                has_replies=m.has_replies,
                body=filtered)

        def _add_has_replies(q, **kwargs):
            replies = Message.objects.filter(in_reply_to=OuterRef('message_id'), **kwargs)
            return q.annotate(has_replies=Exists(replies))

        q = _add_has_replies(q, is_patch=False)
        s = q.first()

        ret = list()
        data = _get_message_data(s)
        ret.append(data)
        if not s.is_patch:
            for p in _add_has_replies(s.get_patches()):
                data = _get_message_data(p)
                ret.append(data)
        return ret

    def www_view_series_diff(self, request, project, series_left, series_right):
        sl = Message.objects.filter(project__name=project, message_id=series_left)
        sr = Message.objects.filter(project__name=project, message_id=series_right)
        return render_page(request, "series-diff.html",
                           series_left=self._get_series_for_diff(sl),
                           series_right=self._get_series_for_diff(sr))

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^(?P<project>[^/]*)/(?P<series_left>.*)/diff/(?P<series_right>.*)/",
                               self.www_view_series_diff,
                               name="series_diff"))
