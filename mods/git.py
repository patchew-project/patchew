#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import os
import subprocess
import rest_framework
from django.conf.urls import url
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.utils.decorators import method_decorator
from mod import PatchewModule, www_authenticated_op
from event import declare_event, register_handler
from api.models import Message, Project, Result
import api.rest
from api.rest import PluginMethodField, SeriesSerializer, reverse_detail
from api.views import APILoginRequiredView, prepare_series
import schema
from rest_framework import generics, serializers
from rest_framework.fields import CharField, SerializerMethodField

_instance = None


def _get_git_result(msg):
    try:
        return msg.results.get(name="git")
    except:
        return None


Message.git_result = property(_get_git_result)


class ResultDataSerializer(api.rest.ResultDataSerializer):
    # TODO: should be present iff the result is success or failure
    base = CharField(required=False)

    # TODO: should be present iff the result is a success
    repo = CharField(required=False)
    url = CharField(required=False)
    tag = CharField(required=False)

    def create(self, data):
        if "tag" in data and "url" not in data and self.project:
            config = _instance.get_project_config(self.project)
            url_template = config.get("url_template")
            tag = data["tag"]
            if url_template and tag.startswith("refs/tags/"):
                data["url"] = url_template.replace("%t", tag[10:])
        return super(ResultDataSerializer, self).create(data)


class GitModule(PatchewModule):
    """Git module"""

    name = "git"
    allowed_groups = ("importers",)
    result_data_serializer_class = ResultDataSerializer

    project_config_schema = schema.ArraySchema(
        "git",
        desc="Configuration for git module",
        members=[
            schema.StringSchema(
                "push_to", "Push remote", desc="Remote to push to", required=True
            ),
            schema.StringSchema(
                "public_repo", "Public repo", desc="Publicly visible repo URL"
            ),
            schema.BooleanSchema(
                "use_git_push_option",
                "Enable git push options",
                desc="Whether the push remote accepts git push options",
            ),
            schema.StringSchema(
                "url_template",
                "URL template",
                desc="Publicly visible URL template for applied branch, where %t will be replaced by the applied tag name",
                required=True,
            ),
        ],
    )

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        # Make sure git is available
        subprocess.check_output(["git", "version"])
        declare_event("ProjectGitUpdate", project="the updated project name")
        declare_event("SeriesApplied", series="the object of applied series")
        register_handler("SeriesComplete", self.on_series_update)
        register_handler("TagsUpdate", self.on_tags_update)

    def mark_as_pending_apply(self, series, data={}):
        r = series.git_result or series.create_result(name="git")
        r.log = None
        r.status = Result.PENDING
        r.data = data
        r.save()

    def on_tags_update(self, event, series, **params):
        if series.is_complete:
            self.mark_as_pending_apply(
                series,
                {
                    "git.push_options": "ci.skip",
                },
            )

    def on_series_update(self, event, series, **params):
        if series.is_complete:
            self.mark_as_pending_apply(series)

    def _is_repo(self, path):
        if not os.path.isdir(path):
            return False
        if 0 != subprocess.call(
            ["git", "rev-parse", "--is-bare-repository"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ):
            return False
        return True

    def get_based_on(self, message, request, format):
        git_base = self.get_base(message)
        return git_base.data if git_base else None

    def get_mirror(self, po, request, format):
        response = {}
        config = self.get_project_config(po)
        if "push_to" in config:
            response["pushurl"] = config["push_to"]
        if "public_repo" in config:
            response["url"] = config["public_repo"]
        head = po.get_property("git.head")
        if head:
            response["head"] = head
        return response

    def rest_project_fields_hook(self, request, fields):
        fields["mirror"] = PluginMethodField(obj=self, required=False)

    def rest_series_fields_hook(self, request, fields, detailed):
        fields["based_on"] = PluginMethodField(obj=self, required=False)

    def get_projects_prepare_hook(self, project, response):
        response["git.head"] = project.get_property("git.head")
        config = self.get_project_config(project)
        if "push_to" in config:
            response["git.push_to"] = config["push_to"]

    def prepare_message_hook(self, request, message, for_message_view):
        if not message.is_series_head:
            return
        # results are prefetched so do not use get_git_result()
        rlist = [r for r in message.results.all() if r.name == "git"]
        if not rlist:
            return
        r = rlist[0]
        if r.is_completed():
            if r.is_failure():
                title = "Failed in applying to current master"
                message.status_tags.append(
                    {"title": title, "type": "secondary", "char": "G"}
                )
            else:
                git_url = r.data.get("url")
                if git_url:
                    git_repo = r.data["repo"]
                    git_tag = r.data["tag"]
                    message.status_tags.append(
                        {
                            "url": git_url,
                            "title": format_html(
                                "Applied as tag {} in repo {}", git_tag, git_repo
                            ),
                            "type": "info",
                            "char": "G",
                        }
                    )
                else:
                    message.status_tags.append(
                        {
                            "title": format_html("Patches applied successfully"),
                            "type": "info",
                            "char": "G",
                        }
                    )
            if request.user.is_authenticated:
                url = reverse("git_reset", kwargs={"series": message.message_id})
                message.extra_ops.append(
                    {
                        "url": url,
                        "icon": "sync",
                        "title": "Git reset",
                        "class": "warning",
                    }
                )

    def render_result(self, result):
        if not result.is_completed():
            return None

        log_url = result.get_log_url()
        html_log_url = result.get_log_url(html=True)
        colorbox_a = format_html(
            '<a class="cbox-log" data-link="{}" href="{}">apply log</a>',
            html_log_url,
            log_url,
        )
        if result.is_failure():
            return format_html("Failed in applying to current master ({})", colorbox_a)
        else:
            if "url" in result.data:
                s = format_html(
                    '<a href="{}">tree</a>, {}', result.data["url"], colorbox_a
                )
            else:
                s = colorbox_a
            s = format_html("Patches applied successfully ({})", s)
            if "repo" in result.data and "tag" in result.data:
                git_repo = result.data["repo"]
                git_tag = result.data["tag"]
                if git_tag.startswith("refs/tags/"):
                    git_tag = git_tag[5:]
                s += format_html("<br/><samp>git fetch {} {}</samp>", git_repo, git_tag)
            return s

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append(
            {
                "title": "Git configuration",
                "class": "info",
                "content_html": self.build_config_html(request, project),
            }
        )

    def get_base(self, series):
        for tag in series.tags:
            if not tag.startswith("Based-on:"):
                continue
            base = Message.objects.find_series_from_tag(tag, series.project)
            if not base:
                return None
            r = base.git_result
            return r if r and r.data.get("repo") else None

    @method_decorator(www_authenticated_op)
    def www_view_git_reset(self, request, series):
        obj = Message.objects.find_series(series)
        if not obj:
            raise Http404("Not found: " + series)
        self.mark_as_pending_apply(obj)

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(
            url(
                r"^git-reset/(?P<series>.*)/", self.www_view_git_reset, name="git_reset"
            )
        )

    def api_url_hook(self, urlpatterns):
        urlpatterns.append(
            url(
                r"^v1/series/unapplied/$",
                UnappliedSeriesView.as_view(),
                name="unapplied",
            )
        )

    def pending_series(self, target_repo):
        q = Message.objects.filter(results__name="git", results__status="pending")

        # Postgres could use JSON fields instead.  Fortunately projects are
        # few so this is cheap
        def match_target_repo(config, target_repo):
            push_to = config.get("git", {}).get("push_to")
            if push_to is None:
                return False
            if target_repo is None or target_repo == "":
                return True
            elif target_repo[-1] != "/":
                return push_to == target_repo or push_to.startswith(target_repo + "/")
            else:
                return push_to.startswith(target_repo)

        projects = Project.objects.values_list("id", "config").all()
        projects = [
            pid for pid, config in projects if match_target_repo(config, target_repo)
        ]
        q = q.filter(project__pk__in=projects)
        return q


class ApplierGetView(APILoginRequiredView):
    name = "applier-get"
    allowed_groups = ["importers"]

    def handle(self, request, target_repo=None):
        m = _instance.pending_series(target_repo).first()
        if not m:
            return None

        response = prepare_series(
            request,
            m,
            fields=["project", "message-id", "patches", "properties", "tags"],
        )

        po = m.project
        config = _instance.get_project_config(po)
        for k, v in config.items():
            response["git." + k] = v
        base = _instance.get_base(m)
        if base:
            response["git.repo"] = base.data["repo"]
            response["git.base"] = base.data["tag"]
        response["project.git"] = po.git
        response["mbox_uri"] = rest_framework.reverse.reverse(
            "series-mbox",
            kwargs={"projects_pk": m.project_id, "message_id": m.message_id},
            request=request,
        )
        response["result_uri"] = reverse_detail(m.git_result, request)
        response["git.push_options"] = m.git_result.data.get("git.push_options")
        return response


class UnappliedSeriesSerializer(SeriesSerializer):
    class Meta:
        model = Message
        fields = SeriesSerializer.Meta.fields + ("mirror", "result_uri", "push_options")

    mirror = SerializerMethodField()
    result_uri = SerializerMethodField()
    push_options = SerializerMethodField()

    def get_push_options(self, obj):
        if obj.project.config.get("git", {}).get("use_git_push_option", False):
            return obj.git_result.data.get("git.push_options")
        else:
            return None

    def get_result_uri(self, obj):
        request = self.context["request"]
        return reverse_detail(obj.git_result, request)

    def get_mirror(self, obj):
        request = self.context["request"]
        mirror = _instance.get_mirror(obj.project, request, None)
        mirror["source"] = obj.project.git
        return mirror


class UnappliedSeriesView(generics.ListAPIView):
    name = "unapplied"
    serializer_class = UnappliedSeriesSerializer

    def get_queryset(self):
        target_repo = self.request.query_params.get("target_repo")
        return _instance.pending_series(target_repo)


class ApplierReportView(APILoginRequiredView):
    name = "applier-report"
    allowed_groups = ["importers"]

    def handle(
        self,
        request,
        project,
        message_id,
        tag,
        url,
        base,
        repo,
        failed,
        log,
        maintainers=[],
    ):
        p = Project.objects.get(name=project)
        r = (
            Message.objects.series_heads()
            .get(project=p, message_id=message_id)
            .git_result
        )
        r.log = log
        r.message.maintainers = maintainers
        r.message.save()
        data = {}
        if failed:
            r.status = Result.FAILURE
        else:
            data["repo"] = repo
            data["tag"] = "refs/tags/" + tag
            if url:
                data["url"] = url
            elif tag:
                config = _instance.get_project_config(p)
                url_template = config.get("url_template")
                if url_template:
                    data["url"] = url_template.replace("%t", tag)
            if base:
                data["base"] = base
            r.status = Result.SUCCESS
        r.data = data
        r.save()
