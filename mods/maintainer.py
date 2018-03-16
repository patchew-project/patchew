#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from django.conf.urls import url
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from mod import PatchewModule
from api.models import Message

class MaintainerModule(PatchewModule):
    """ Project maintainer related tasks """

    name = "maintainer"

    def _update_merge_state(self, request, message_id, is_merged):
        s = Message.objects.find_series(message_id)
        if not s:
            raise Http404("Series not found")
        if not s.project.maintained_by(request.user):
            return HttpResponseForbidden()
        s.is_merged = is_merged
        s.save()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_view_mark_as_merged(self, request, message_id):
        return self._update_merge_state(request, message_id, True)

    def www_view_clear_merged(self, request, message_id):
        return self._update_merge_state(request, message_id, False)

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^mark-as-merged/(?P<message_id>.*)/",
                               self.www_view_mark_as_merged,
                               name="mark-as-merged"))
        urlpatterns.append(url(r"^clear-merged/(?P<message_id>.*)/",
                               self.www_view_clear_merged,
                               name="clear-merged"))

    def prepare_message_hook(self, request, message, detailed):
        if not detailed:
            return
        if message.is_series_head and request.user.is_authenticated:
            if message.is_merged:
                message.extra_ops.append({"url": reverse("clear-merged",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "times",
                                          "title": "Clear merged state"})
            else:
                message.extra_ops.append({"url": reverse("mark-as-merged",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "check",
                                          "title": "Mark series as merged"})
