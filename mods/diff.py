#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import os
import shutil
import hashlib
from collections import OrderedDict
from django.conf.urls import url
from django.http import Http404
from django.urls import reverse
from mod import PatchewModule
from api.models import Project, Message
from www.views import render_page
from schema import *
import re

_instance = None

class DiffModule(PatchewModule):
    """Diff module"""
    name = "diff"

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head or not detailed:
            return
        other_versions = message.get_alternative_revisions()
        for o in other_versions:
            if message.message_id == o.message_id:
                continue
            v = o.version
            url = reverse("series_diff",
                          kwargs={"series_right": message.message_id,
                                  "series_left": o.message_id})
            message.extra_ops.append({"url": url,
                                      "title": "Diff against v" + str(v),
                                     })

    def _get_series_for_diff(self, s):
        def _get_message_text(m):
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
            return filtered

        ret = OrderedDict()
        if not s.is_patch:
            ret[s.subject] = _get_message_text(s)
        for p in s.get_patches():
            ret[p.subject] = _get_message_text(p)
        return ret

    def www_view_series_diff(self, request, series_left, series_right):
        sl = Message.objects.filter(message_id=series_left).first()
        sr = Message.objects.filter(message_id=series_right).first()
        return render_page(request, "series-diff.html",
                           series_left=self._get_series_for_diff(sl).items(),
                           series_right=self._get_series_for_diff(sr).items())

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^series-diff/(?P<series_left>.*)/(?P<series_right>.*)/",
                               self.www_view_series_diff,
                               name="series_diff"))
