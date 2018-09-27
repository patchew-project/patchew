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
from api.models import Message, Review

class MaintainerModule(PatchewModule):
    """ Project maintainer related tasks """

    name = "maintainer"

    def _update_review_state(self, request, message_id, accept):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        msg = Message.objects.find_series(message_id)
        if not msg:
            raise Http404("Series not found")
        Review.objects.update_or_create(user=request.user, message=msg,
                                        defaults = { 'accept': accept })
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def _delete_review(self, request, message_id):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        msg = Message.objects.find_series(message_id)
        if not msg:
            raise Http404("Series not found")
        r = Review.objects.filter(user=request.user, message=msg)
        r.delete()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

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

    def www_view_mark_accepted(self, request, message_id):
        return self._update_review_state(request, message_id, True)

    def www_view_mark_rejected(self, request, message_id):
        return self._update_review_state(request, message_id, False)

    def www_view_clear_reviewed(self, request, message_id):
        return self._delete_review(request, message_id)

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^mark-as-merged/(?P<message_id>.*)/",
                               self.www_view_mark_as_merged,
                               name="mark-as-merged"))
        urlpatterns.append(url(r"^clear-merged/(?P<message_id>.*)/",
                               self.www_view_clear_merged,
                               name="clear-merged"))
        urlpatterns.append(url(r"^mark-as-accepted/(?P<message_id>.*)/",
                               self.www_view_mark_accepted,
                               name="mark-as-accepted"))
        urlpatterns.append(url(r"^mark-as-rejected/(?P<message_id>.*)/",
                               self.www_view_mark_rejected,
                               name="mark-as-rejected"))
        urlpatterns.append(url(r"^clear-reviewed/(?P<message_id>.*)/",
                               self.www_view_clear_reviewed,
                               name="clear-reviewed"))

    def prepare_message_hook(self, request, message, detailed):
        if not detailed or not request.user.is_authenticated:
            return
        if message.is_series_head:
            if message.is_merged:
                message.extra_ops.append({"url": reverse("clear-merged",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "eraser",
                                          "title": "Clear merged state"})
            else:
                message.extra_ops.append({"url": reverse("mark-as-merged",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "check",
                                          "title": "Mark series as merged"})

        try:
            r = Review.objects.get(user=request.user, message=message)
        except Review.DoesNotExist:
            r = None
        if r and r.accept:
            message.extra_status.append({
                "icon": "fa-check",
                "html": 'The series is marked for merging'
            })
        else:
            if message.is_series_head:
                message.extra_ops.append({"url": reverse("mark-as-accepted",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "check",
                                          "title": "Mark series as accepted"})

        if r and not r.accept:
            message.extra_status.append({
                "icon": "fa-times",
                "html": 'The series is marked as rejected'
            })
        else:
            if message.is_series_head:
                message.extra_ops.append({"url": reverse("mark-as-rejected",
                                                         kwargs={"message_id": message.message_id}),
                                          "icon": "times",
                                          "title": "Mark series as rejected"})

        if r:
            message.extra_ops.append({"url": reverse("clear-reviewed",
                                                     kwargs={"message_id": message.message_id}),
                                      "icon": "eraser",
                                      "title": "Clear review state"})
