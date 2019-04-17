#!/usr/bin/env python3
#
# Copyright 2018 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import re
from django.conf.urls import url
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect, HttpResponseBadRequest
from django.urls import reverse
from mod import PatchewModule
from api.models import Message, QueuedSeries, WatchedQuery
from django.shortcuts import render
from api.search import SearchEngine
from event import declare_event, register_handler, emit_event

class MaintainerModule(PatchewModule):
    """ Project maintainer related tasks """

    name = "maintainer"

    def __init__(self):
        register_handler("ResultUpdate", self.on_result_update)
        declare_event("MessageQueued",
                      message="Message added",
                      name="Name of the updated queue",
                      user="Owner of the queue")
        declare_event("MessageDropping",
                      message="Message to be dropped",
                      queue="Message is about to be dropping from a queue")

    def _add_to_queue(self, user, m, queue):
        for x in [m] + list(m.get_patches()):
            q, created = QueuedSeries.objects.get_or_create(user=user, message=x, name=queue)
            if created:
                emit_event("MessageQueued", user=user, message=x, queue=q)

    def _drop_from_queue(self, user, m, queue):
        query = QueuedSeries.objects.filter(user=user, message__in=m.get_patches() + [m],
                                     name=queue)
        for q in query:
            emit_event("MessageDropping", user=user, message=q.message, queue=q)
        q.delete()

    def _update_watch_queue(self, series):
        se = SearchEngine()
        for wq in WatchedQuery.objects.all():
            if se.query_test_message(wq.query, series):
                self._add_to_queue(wq.user, series, "watched")

    def on_result_update(self, evt, obj, old_status, result):
        if not isinstance(obj, Message):
            return
        if result == obj.git_result and result.status != result.PENDING:
            # By the time of git result update we should have calculated
            # maintainers so redo the watched queue
            self._update_watch_queue(obj)

    def _update_review_state(self, request, message_id, accept):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        msg = Message.objects.find_series(message_id)
        if not msg:
            raise Http404("Series not found")
        if accept:
            to_create, to_delete = 'accept', 'reject'
        else:
            to_create, to_delete = 'reject', 'accept'
        QueuedSeries.objects.filter(user=request.user, message=msg, name=to_delete).delete()
        QueuedSeries.objects.get_or_create(user=request.user, message=msg, name=to_create)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def _delete_review(self, request, message_id):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        msg = Message.objects.find_series(message_id)
        if not msg:
            raise Http404("Series not found")
        r = QueuedSeries.objects.filter(user=request.user, message=msg,
                                 name__in=['accept', 'reject'])
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

    def www_view_add_to_queue(self, request, message_id):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        m = Message.objects.filter(message_id=message_id).first()
        if not m:
            raise Http404("Series not found")
        queue = request.GET.get("queue")
        if not queue or re.match(r'[^_a-zA-Z0-9\-]', queue):
            return HttpResponseBadRequest("Invalid queue name")
        self._add_to_queue(request.user, m, queue)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_view_drop_from_queue(self, request, queue, message_id):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        m = Message.objects.filter(message_id=message_id).first()
        if not m:
            raise Http404("Series not found")
        self._drop_from_queue(request.user, m, queue)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_view_my_queues(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        data = {}
        for i in QueuedSeries.objects.filter(message__is_patch=True,
                                      user=request.user).\
                order_by("message__project", "name", "message__date"):
            pn = i.message.project.name
            qn = i.name
            data.setdefault(pn, {})
            data[pn].setdefault(qn, [])
            data[pn][qn].append(i.message)

        return render(request, "my-queues.html", context={"projects": data})

    def render_page_hook(self, request, context_data):
        if request.user.is_authenticated and context_data.get("is_search"):
            q = WatchedQuery.objects.filter(user=request.user).first()
            if q and q.query == context_data.get("search"):
                context_data["is_watched_query"] = True

    def www_view_watch_query(self, request):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        query = request.GET.get("q")
        if not query:
            return HttpResponseBadRequest("Invalid query")
        WatchedQuery.objects.update_or_create(defaults={"query": query},
                                              user=request.user)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

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
        urlpatterns.append(url(r"^add-to-queue/(?P<message_id>.*)/",
                               self.www_view_add_to_queue,
                               name="add-to-queue"))
        urlpatterns.append(url(r"^drop-from-queue/(?P<queue>[^/]*)/(?P<message_id>.*)/",
                               self.www_view_drop_from_queue,
                               name="drop-from-queue"))
        urlpatterns.append(url(r"^my-queues/", self.www_view_my_queues))
        urlpatterns.append(url(r"^watch-query/", self.www_view_watch_query))

    def prepare_message_hook(self, request, message, detailed):
        if not detailed or not request.user.is_authenticated:
            return
        if not message.is_series_head:
            return
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
        if message.maintainers:
            message.extra_status.append({
                "icon": "fa-user-o",
                "html": 'Maintainers: %s' % ", ".join(message.maintainers),
            })

        accepted = False
        rejected = False
        queues = []
        for r in QueuedSeries.objects.filter(user=request.user, message=message):
            if r.name == 'accept':
                message.extra_status.append({
                    "icon": "fa-check",
                    "html": 'The series is marked for merging'
                })
                accepted = True
            elif r.name == 'reject':
                message.extra_status.append({
                    "icon": "fa-times",
                    "html": 'The series is marked as rejected'
                })
                rejected = True
            else:
                queues.append(r.name)
                message.extra_ops.append({
                    "url": reverse("drop-from-queue",
                                   kwargs={
                                       "queue": r.name,
                                       "message_id": message.message_id
                                   }),
                                   "icon": "remove",
                                   "title": "Drop from queue '%s'" % r.name})
        if not accepted:
            message.extra_ops.append({"url": reverse("mark-as-accepted",
                                                     kwargs={"message_id": message.message_id}),
                                      "icon": "check",
                                      "title": "Mark series as accepted"})
        if not rejected:
            message.extra_ops.append({"url": reverse("mark-as-rejected",
                                                     kwargs={"message_id": message.message_id}),
                                      "icon": "times",
                                      "title": "Mark series as rejected"})
        if accepted or rejected:
            message.extra_ops.append({"url": reverse("clear-reviewed",
                                                     kwargs={"message_id": message.message_id}),
                                      "icon": "eraser",
                                      "title": "Clear review state"})

        if queues:
            message.extra_status.append({
                "icon": "fa-bookmark",
                "html": 'The series is queued in: %s' % ', '.join(queues),
            })
        for q in QueuedSeries.objects.filter(user=request.user).values("name").distinct():
            qn = q["name"]
            if qn in queues + ['reject', 'accept']:
                continue
            message.extra_ops.append({
                "url": "%s?queue=%s" % (\
                        reverse("add-to-queue",
                                kwargs={"message_id": message.message_id}),
                        qn),
                "icon": "bookmark",
                "title": "Add to '%s' queue" % qn})

        message.extra_ops.append({
            "url": reverse("add-to-queue",
                           kwargs={"message_id": message.message_id}),
            "get_prompt": {"queue": "What is the name of the new queue?" },
            "icon": "bookmark",
            "title": "Add to new queue..."})
