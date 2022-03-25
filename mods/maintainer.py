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
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from mod import PatchewModule, www_authenticated_op
from api.models import Message, QueuedSeries, Project, WatchedQuery
from django.shortcuts import render
from api.search import SearchEngine
from event import declare_event, register_handler, emit_event
from www.views import render_series_list_page


class MaintainerModule(PatchewModule):
    """Project maintainer related tasks"""

    name = "maintainer"

    def __init__(self):
        register_handler("ResultUpdate", self.on_result_update)
        register_handler("MessageQueued", self.on_queue_change)
        register_handler("MessageDropped", self.on_queue_change)
        register_handler("SeriesComplete", self.on_series_complete)
        register_handler("SeriesMerged", self.on_series_merged)
        register_handler("SeriesReviewed", self.on_series_reviewed)
        declare_event(
            "MessageQueued",
            message="Message added",
            name="Name of the updated queue",
            user="Owner of the queue",
            queue="Queue that message is being added to",
        )
        declare_event(
            "MessageDropped",
            message="Message that has been dropped",
            user="Owner of the queue",
            queue="Queue that message is being removed from",
        )

    def _add_to_queue(self, user, msgs, queue):
        for m in msgs:
            q, created = QueuedSeries.objects.get_or_create(
                user=user, message=m, name=queue
            )
            if created:
                emit_event("MessageQueued", user=user, message=m, queue=q)

    def _drop_all_from_queue(self, query):
        events = [{"user": q.user, "message": q.message, "queue": q} for q in query]
        query.delete()
        for ev in events:
            emit_event("MessageDropped", **ev)

    def _drop_from_queue(self, user, msgs, queue):
        query = QueuedSeries.objects.filter(user=user, message__in=msgs, name=queue)
        self._drop_all_from_queue(query)

    def _update_watch_queue(self, series):
        for wq in WatchedQuery.objects.all():
            se = SearchEngine([wq.query], wq.user)
            if se.query_test_message(series):
                self._add_to_queue(wq.user, [series], "watched")
            else:
                self._drop_from_queue(wq.user, [series], "watched")

    def on_queue_change(self, evt, user, message, queue):
        # Handle changes to e.g. "-nack:me"
        if queue != "watched":
            self._update_watch_queue(message)

    def on_result_update(self, evt, obj, old_status, result):
        if not isinstance(obj, Message):
            return
        if result == obj.git_result and result.status != result.PENDING:
            # By the time of git result update we should have calculated
            # maintainers so redo the watched queue
            self._update_watch_queue(obj)

    def on_series_complete(self, evt, project, series):
        self._update_watch_queue(series)

    def on_series_reviewed(self, evt, series):
        # Handle changes to "is:reviewed"
        self._update_watch_queue(series)

    def on_series_merged(self, evt, project, series):
        # This is a bit of a hack for now.  We probably should hide merged
        # series more aggressively, but I am not sure how to handle that
        # efficiently in the database.
        query = QueuedSeries.objects.filter(
            message=series, name__in=["accept", "reject"]
        )
        self._drop_all_from_queue(query)
        # Handle changes to "is:merged"
        self._update_watch_queue(series)

    def _update_review_state(self, request, project, message_id, accept):
        msg = Message.objects.find_series(message_id, project)
        if not msg:
            raise Http404("Series not found")
        if accept:
            to_create, to_delete = "accept", "reject"
        else:
            to_create, to_delete = "reject", "accept"
        self._drop_from_queue(request.user, [msg], to_delete)
        self._add_to_queue(request.user, [msg], to_create)

    def _delete_review(self, request, project, message_id):
        msg = Message.objects.find_series(message_id, project)
        if not msg:
            raise Http404("Series not found")
        r = QueuedSeries.objects.filter(
            user=request.user, message=msg, name__in=["accept", "reject"]
        )
        self._drop_all_from_queue(r)

    def _update_merge_state(self, request, project, message_id, is_merged):
        s = Message.objects.find_series(message_id, project)
        if not s:
            raise Http404("Series not found")
        if not s.project.maintained_by(request.user):
            return HttpResponseForbidden()
        s.is_merged = is_merged
        s.save()

    @method_decorator(www_authenticated_op)
    def www_view_mark_as_merged(self, request, project, message_id):
        return self._update_merge_state(request, project, message_id, True)

    @method_decorator(www_authenticated_op)
    def www_view_clear_merged(self, request, project, message_id):
        return self._update_merge_state(request, project, message_id, False)

    @method_decorator(www_authenticated_op)
    def www_view_mark_accepted(self, request, project, message_id):
        return self._update_review_state(request, project, message_id, True)

    @method_decorator(www_authenticated_op)
    def www_view_mark_rejected(self, request, project, message_id):
        return self._update_review_state(request, project, message_id, False)

    @method_decorator(www_authenticated_op)
    def www_view_clear_reviewed(self, request, project, message_id):
        return self._delete_review(request, project, message_id)

    @method_decorator(www_authenticated_op)
    def www_view_add_to_queue(self, request, project, message_id):
        m = Message.objects.find_series(message_id, project)
        if not m:
            raise Http404("Series not found")
        queue = request.POST.get("queue")
        if not queue or re.match(r"[^_a-zA-Z0-9\-]", queue):
            return HttpResponseBadRequest("Invalid queue name")
        self._add_to_queue(request.user, [m], queue)

    @method_decorator(www_authenticated_op)
    def www_view_search_drop_from_queue(self, request, queue, project):
        po = Project.objects.filter(name=project).first()
        if not po:
            raise Http404("Project not found")
        if not queue or re.match(r"[^_a-zA-Z0-9\-]", queue):
            return HttpResponseBadRequest("Invalid queue name")
        q = request.POST.get("q")
        se = SearchEngine(["queue:" + queue, q], request.user)
        self._drop_from_queue(
            request.user, se.search_series(Message.objects.series_heads(po.id)), queue
        )

    @method_decorator(www_authenticated_op)
    def www_view_drop_from_queue(self, request, queue, project, message_id):
        m = Message.objects.find_series(message_id, project)
        if not m:
            raise Http404("Series not found")
        self._drop_from_queue(request.user, [m], queue)

    def query_queue(self, request, project, name, can_be_empty=False):
        if not request.user.is_authenticated:
            raise PermissionDenied()

        q = QueuedSeries.objects.filter(user=request.user, name=name)
        if not can_be_empty and not q.first():
            raise Http404("Queue not found")
        po = Project.objects.filter(name=project).first()
        if not po:
            raise Http404("Project not found")
        message_ids = q.values("message_id")
        return Message.objects.series_heads(po.id).filter(id__in=message_ids)

    def www_download_queue_mbox(self, request, project, name):
        query = self.query_queue(request, project, name).filter(is_complete=True)
        mbox_list = []
        for s in query:
            mbox_list.extend(s.get_mboxes_with_tags())
        mbox = b"\n".join(mbox_list)
        return HttpResponse(mbox, content_type="text/plain")

    def www_view_queue(self, request, project, name):
        query = self.query_queue(request, project, name, can_be_empty=True)
        if name == "watched":
            # TODO: make the WatchedQuery per-project
            q = WatchedQuery.objects.filter(user=request.user).first().query
            se = SearchEngine([q], request.user)
            if not se.project():
                q = "project:" + project + " " + q
        else:
            q = "project:" + project + " queue:" + name
        extra = {}
        if name == "accept":
            extra = {
                "button_text": "Remove merged patches",
                "button_data": {"q": "is:merged"},
                "button_url": reverse(
                    "search-drop-from-queue", kwargs={"project": project, "queue": name}
                ),
            }
        elif name not in ["reject", "watched"]:
            extra = {
                "button_text": "Remove accepted/merged/rejected patches",
                "button_data": {"q": "{is:merged review:me}"},
                "button_url": reverse(
                    "search-drop-from-queue", kwargs={"project": project, "queue": name}
                ),
            }
        return render_series_list_page(
            request,
            query,
            search=q,
            project=project,
            title='"' + name + '" queue',
            link_icon="fa fa-download",
            link_text="Download mbox",
            link_url=reverse(
                "maintainer_queue_mbox", kwargs={"project": project, "name": name}
            ),
            **extra,
        )

    def www_view_my_queues(self, request, project=None):
        if not request.user.is_authenticated:
            raise PermissionDenied()
        data = {}
        q = QueuedSeries.objects.filter(user=request.user)
        if project:
            po = Project.objects.filter(name=project).first()
            if not po:
                raise Http404("Project not found")
            q = q.filter(message__project=po)
        else:
            q = q.order_by("message__project")

        for i in q.order_by("name", "message__date"):
            pn = i.message.project.name
            qn = i.name
            data.setdefault(pn, {})
            data[pn].setdefault(qn, [])
            data[pn][qn].append(i.message)

        return render(request, "my-queues.html", context={"projects": data})

    def render_page_hook(self, request, context_data):
        if request.user.is_authenticated and context_data.get("is_search"):
            q = WatchedQuery.objects.filter(user=request.user).first()
            if q and q.query.strip() == context_data.get("search").strip():
                context_data["is_watched_query"] = True
            else:
                context_data.update(
                    {
                        "button_text": "Replace watched query" if q else "Watch query",
                        "button_data": {"q": context_data["search"]},
                        "button_url": reverse("maintainer_watch_query"),
                    }
                )

    @method_decorator(www_authenticated_op)
    def www_view_watch_query(self, request):
        query = request.POST.get("q")
        if not query:
            return HttpResponseBadRequest("Invalid query")
        WatchedQuery.objects.update_or_create(
            defaults={"query": query}, user=request.user
        )

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/mark-as-merged/",
                self.www_view_mark_as_merged,
                name="mark-as-merged",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/clear-merged/",
                self.www_view_clear_merged,
                name="clear-merged",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/mark-as-accepted/",
                self.www_view_mark_accepted,
                name="mark-as-accepted",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/mark-as-rejected/",
                self.www_view_mark_rejected,
                name="mark-as-rejected",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/clear-reviewed/",
                self.www_view_clear_reviewed,
                name="clear-reviewed",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/add-to-queue/",
                self.www_view_add_to_queue,
                name="add-to-queue",
            )
        )
        urlpatterns.append(
            url(
                r"^(?P<project>[^/]*)/(?P<message_id>.*)/drop-from-queue/(?P<queue>[^/]*)/",
                self.www_view_drop_from_queue,
                name="drop-from-queue",
            )
        )
        urlpatterns.append(
            url(
                r"^my-queues/(?P<project>[^/]*)/(?P<queue>[^/]*)/remove/",
                self.www_view_search_drop_from_queue,
                name="search-drop-from-queue",
            )
        )
        urlpatterns.append(
            url(
                r"^my-queues/(?P<project>[^/]*)/(?P<name>[^/]*)/$",
                self.www_view_queue,
                name="maintainer_queue",
            )
        )
        urlpatterns.append(
            url(
                r"^my-queues/(?P<project>[^/]*)/(?P<name>[^/]*)/mbox$",
                self.www_download_queue_mbox,
                name="maintainer_queue_mbox",
            )
        )
        urlpatterns.append(
            url(r"^my-queues/(?P<project>[^/]*)/$", self.www_view_my_queues)
        )
        urlpatterns.append(url(r"^my-queues/$", self.www_view_my_queues))
        urlpatterns.append(
            url(
                r"^watch-query/$",
                self.www_view_watch_query,
                name="maintainer_watch_query",
            )
        )

    def prepare_message_hook(self, request, message, detailed):
        def link_queue(message, queue, text):
            return format_html(
                '<a href="{}">{}</a>',
                reverse(
                    "maintainer_queue",
                    kwargs={"project": message.project, "name": queue},
                ),
                text,
            )

        if message.maintainers:
            message.extra_status.append(
                {
                    "icon": "fa-user",
                    "html": "Maintainers: %s" % ", ".join(message.maintainers),
                }
            )

        if not detailed or not request.user.is_authenticated:
            return
        if not message.is_series_head:
            return
        if message.is_merged:
            message.extra_ops.append(
                {
                    "url": reverse(
                        "clear-merged",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "icon": "eraser",
                    "title": "Clear merged state",
                }
            )
        else:
            message.extra_ops.append(
                {
                    "url": reverse(
                        "mark-as-merged",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "icon": "code-branch fa-flip-vertical",
                    "title": "Mark series as merged",
                }
            )
        accepted = False
        rejected = False
        queues = []
        for r in QueuedSeries.objects.filter(user=request.user, message=message):
            if r.name == "accept":
                message.extra_status.append(
                    {
                        "icon": "fa-check",
                        "html": format_html(
                            "The series is {}",
                            link_queue(message, "accept", "marked for merging"),
                        ),
                    }
                )
                accepted = True
            elif r.name == "reject":
                message.extra_status.append(
                    {
                        "icon": "fa-times",
                        "html": format_html(
                            "The series is {}",
                            link_queue(message, "reject", "marked as rejected"),
                        ),
                    }
                )
                rejected = True
            else:
                queues.append(r.name)
                message.extra_ops.append(
                    {
                        "url": reverse(
                            "drop-from-queue",
                            kwargs={
                                "queue": r.name,
                                "message_id": message.message_id,
                                "project": message.project.name,
                            },
                        ),
                        "icon": "times",
                        "title": "Drop from queue '%s'" % r.name,
                    }
                )
        if not accepted:
            message.extra_ops.append(
                {
                    "url": reverse(
                        "mark-as-accepted",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "icon": "check",
                    "title": "Mark series as accepted",
                }
            )
        if not rejected:
            message.extra_ops.append(
                {
                    "url": reverse(
                        "mark-as-rejected",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "icon": "times",
                    "title": "Mark series as rejected",
                }
            )
        if accepted or rejected:
            message.extra_ops.append(
                {
                    "url": reverse(
                        "clear-reviewed",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "icon": "eraser",
                    "title": "Clear review state",
                }
            )

        if queues:
            queue_links = (link_queue(message, x, x) for x in queues)
            message.extra_status.append(
                {
                    "icon": "fa-bookmark",
                    "html": mark_safe(
                        "The series is queued in: %s" % ", ".join(queue_links)
                    ),
                }
            )
        for q in (
            QueuedSeries.objects.filter(user=request.user).values("name").distinct()
        ):
            qn = q["name"]
            if qn in queues + ["reject", "accept"]:
                continue
            message.extra_ops.append(
                {
                    "url": reverse(
                        "add-to-queue",
                        kwargs={
                            "message_id": message.message_id,
                            "project": message.project.name,
                        },
                    ),
                    "args": {"queue": qn},
                    "icon": "bookmark",
                    "title": "Add to '%s' queue" % qn,
                }
            )

        message.extra_ops.append(
            {
                "url": reverse(
                    "add-to-queue",
                    kwargs={
                        "message_id": message.message_id,
                        "project": message.project.name,
                    },
                ),
                "get_prompt": {"queue": "What is the name of the new queue?"},
                "icon": "bookmark",
                "title": "Add to new queue...",
            }
        )
