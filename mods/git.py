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
import hashlib
import json
from django.conf.urls import url
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from django.db.models import Q
from mod import PatchewModule
from event import declare_event, register_handler, emit_event
from api.models import (Message, MessageProperty, Project,
        ProjectProperty, Result)
from api.rest import PluginMethodField, reverse_detail
from api.views import APILoginRequiredView, prepare_series
from patchew.logviewer import LogView
from schema import *
from rest_framework import serializers
from rest_framework.fields import CharField

_instance = None

def _get_git_result(msg):
    try:
        return msg.results.get(name="git")
    except:
        return None
Message.git_result = property(_get_git_result)


class GitLogViewer(LogView):
    def get_result(self, request, **kwargs):
        series = kwargs['series']
        obj = Message.objects.find_series(series)
        if not obj:
            raise Http404("Object not found: " + series)
        return obj.git_result

class ResultDataSerializer(serializers.Serializer):
    # TODO: should be present iff the result is success or failure
    base = CharField(required=False)

    # TODO: should be present iff the result is a success
    repo = CharField(required=False)
    url = CharField(required=False)
    tag = CharField(required=False)

class GitModule(PatchewModule):
    """Git module"""

    name = "git"
    allowed_groups = ('importers', )
    result_data_serializer_class = ResultDataSerializer

    project_config_schema = \
        ArraySchema("git", desc="Configuration for git module",
                    members=[
                        StringSchema("push_to", "Push remote",
                                     desc="Remote to push to",
                                     required=True),
                        StringSchema("public_repo", "Public repo",
                                     desc="Publicly visible repo URL"),
                        StringSchema("url_template", "URL template",
                                     desc="Publicly visible URL template for applied branch, where %t will be replaced by the applied tag name",
                                     required=True),
                   ])

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        # Make sure git is available
        subprocess.check_output(["git", "version"])
        declare_event("ProjectGitUpdate", project="the updated project name")
        declare_event("SeriesApplied", series="the object of applied series")
        register_handler("SeriesComplete", self.on_series_update)
        register_handler("TagsUpdate", self.on_series_update)

    def mark_as_pending_apply(self, series):
        r = series.git_result or series.create_result(name='git')
        r.log = None
        r.status = Result.PENDING
        r.data = {}
        r.save()

    def on_series_update(self, event, series, **params):
        if series.is_complete:
            self.mark_as_pending_apply(series)

    def _is_repo(self, path):
        if not os.path.isdir(path):
            return False
        if 0 != subprocess.call(["git", "rev-parse", "--is-bare-repository"],
                                cwd=path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE):
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
        fields['mirror'] = PluginMethodField(obj=self, required=False)

    def rest_series_fields_hook(self, request, fields, detailed):
        fields['based_on'] = PluginMethodField(obj=self, required=False)

    def get_projects_prepare_hook(self, project, response):
        response["git.head"] = project.get_property("git.head")
        config = self.get_project_config(project)
        if "push_to" in config:
            response["git.push_to"] = config["push_to"]

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head:
            return
        r = message.git_result
        if r and r.is_completed():
            if r.is_failure():
                title = "Failed in applying to current master"
                message.status_tags.append({
                    "title": title,
                    "type": "default",
                    "char": "G",
                    })
            else:
                git_url = r.data.get('url')
                if git_url:
                    git_repo = r.data['repo']
                    git_tag = r.data['tag']
                    message.status_tags.append({
                        "url": git_url,
                        "title": format_html("Applied as tag {} in repo {}", git_tag, git_repo),
                        "type": "info",
                        "char": "G",
                        })
                else:
                    message.status_tags.append({
                        "title": format_html("Patches applied successfully"),
                        "type": "info",
                        "char": "G",
                        })
            if request.user.is_authenticated:
                url = reverse("git_reset",
                              kwargs={"series": message.message_id})
                message.extra_ops.append({"url": url,
                                          "icon": "refresh",
                                          "title": "Git reset",
                                          "class": "warning",
                                         })

    def render_result(self, result):
        if not result.is_completed():
            return None

        log_url = result.get_log_url()
        html_log_url = log_url + "?html=1"
        colorbox_a = format_html('<a class="cbox-log" data-link="{}" href="{}">apply log</a>',
                                 html_log_url, log_url)
        if result.is_failure():
            return format_html('Failed in applying to current master ({})', colorbox_a)
        else:
            if 'url' in result.data:
                s = format_html('<a href="{}">tree</a>, {}', result.data['url'], colorbox_a)
            else:
                s = colorbox_a
            s = format_html('Patches applied successfully ({})', s)
            if 'repo' in result.data and 'tag' in result.data:
                git_repo = result.data['repo']
                git_tag = result.data['tag']
                if git_tag.startswith('refs/tags/'):
                    git_tag = git_tag[5:]
                s += format_html('<br/><samp>git fetch {} {}</samp>', git_repo, git_tag)
            return s

    def get_result_log_url(self, result):
        return reverse("git-log", kwargs={'series': result.obj.message_id})

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Git configuration",
                                   "class": "info",
                                   "content_html": self.build_config_html(request,
                                                                          project)})

    def get_base(self, series):
        for tag in series.tags:
            if not tag.startswith("Based-on:"):
                continue
            base_id = tag[len("Based-on:"):].strip()
            if base_id.startswith("<") and base_id.endswith(">"):
                base_id = base_id[1:-1]
            base = Message.objects.series_heads().\
                    filter(project=series.project, message_id=base_id).first()
            if not base:
                return None
            r = base.git_result
            return r if r and r.data.get("repo") else None

    def www_view_git_reset(self, request, series):
        if not request.user.is_authenticated:
            raise PermissionDenied
        obj = Message.objects.find_series(series)
        if not obj:
            raise Http404("Not found: " + series)
        self.mark_as_pending_apply(obj)
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^git-reset/(?P<series>.*)/",
                               self.www_view_git_reset,
                               name="git_reset"))
        urlpatterns.append(url(r"^logs/(?P<series>.*)/git/",
                               GitLogViewer.as_view(),
                               name="git-log"))

class ApplierGetView(APILoginRequiredView):
    name = "applier-get"
    allowed_groups = ["importers"]

    def handle(self, request, target_repo=None):
        q = Message.objects.filter(results__name="git", results__status="pending")
        if target_repo is not None and target_repo != '':
            props = ProjectProperty.objects.filter(name='git.push_to')
            # unfortunately startswith does not work with JSONFields, so we have to hack
            # around it and look at the raw database representation.  This would fail
            # if we used PostgreSQL json fields!
            target_repo_escaped = json.dumps(target_repo)
            if target_repo[-1] != '/':
                props = props.extra(where=["value = %s or value like %s"],
                                    params=[target_repo_escaped,
                                            target_repo_escaped[0:-1] + '/%'])
            else:
                props = props.extra(where=["value like %s"],
                                    params=target_repo_escaped[0:-1] + '%')
            q = q.filter(project__in=[prop.project for prop in props.all()])
        m = q.first()
        if not m:
            return None

        response = prepare_series(request, m, fields=["project", "message-id", "patches",
                                                      "properties", "tags"])

        po = m.project
        config = _instance.get_project_config(po)
        for k, v in config.items():
            response["git." + k] = v
        base = _instance.get_base(m)
        if base:
            response["git.repo"] = base.data["repo"]
            response["git.base"] = base.data["tag"]
        response["project.git"] = po.git
        response["result_uri"] = reverse_detail(m.git_result, request)
        return response

class ApplierReportView(APILoginRequiredView):
    name = "applier-report"
    allowed_groups = ["importers"]

    def handle(self, request, project, message_id, tag, url, base, repo,
               failed, log, maintainers=[]):
        p = Project.objects.get(name=project)
        r = Message.objects.series_heads().get(project=p,
                                               message_id=message_id).git_result
        r.log = log
        r.message.maintainers = maintainers
        r.message.save()
        data = {}
        if failed:
            r.status = Result.FAILURE
        else:
            data['repo'] = repo
            data['tag'] = 'refs/tags/' + tag
            if url:
                data['url'] = url
            elif tag:
                config = _instance.get_project_config(p)
                url_template = config.get("url_template")
                if url_template:
                    data['url'] = url_template.replace("%t", tag)
            if base:
                data['base'] = base
            r.status = Result.SUCCESS
        r.data = data
        r.save()
