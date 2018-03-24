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
from django.conf.urls import url
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.utils.html import format_html
from mod import PatchewModule
from event import declare_event, register_handler, emit_event
from api.models import Message, MessageProperty, Result
from api.views import APILoginRequiredView, prepare_series
from patchew.logviewer import LogView
from schema import *

_instance = None

class GitLogViewer(LogView):
    def content(self, request, **kwargs):
        series = kwargs['series']
        obj = Message.objects.find_series(series)
        if not obj:
            raise Http404("Object not found: " + series)
        log = obj.get_property("git.apply-log")
        if log is None:
            raise Http404("Git apply log not found")
        return log


class GitModule(PatchewModule):
    """Git module"""
    name = "git"

    project_property_schema = \
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

    def on_series_update(self, event, series, **params):
        if series.is_complete:
            series.set_property("git.need-apply", True)

    def get_project_config(self, project, what):
        return project.get_property("git." + what)

    def _is_repo(self, path):
        if not os.path.isdir(path):
            return False
        if 0 != subprocess.call(["git", "rev-parse", "--is-bare-repository"],
                                cwd=path,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE):
            return False
        return True

    def _update_cache_repo(self, project_name, repo, branch, logf=None):
        cache_repo = "/var/tmp/patchew-git-cache-%s" % project_name
        if not self._is_repo(cache_repo):
            # Clone upstream to local cache
            subprocess.call(["rm", "-rf", cache_repo],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.check_output(["git", "init", "--bare",
                                     cache_repo])
        remote_name = hashlib.sha1(repo).hexdigest()
        subprocess.call(["git", "remote", "remove", remote_name],
                        cwd=cache_repo,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
        subprocess.check_call(["git", "remote", "add", "-f", "--mirror=fetch",
                              remote_name, repo], cwd=cache_repo,
                              stdout=logf, stderr=logf)
        return cache_repo

    def _get_project_repo_and_branch(self, project):
        project_git = project.git
        if not project_git:
            raise Exception("Project git repo not set")
        if len(project_git.split()) != 2:
            # Use master as the default branch
            project_git += " master"
        upstream, branch = project_git.split()[0:2]
        if not upstream or not branch:
            raise Exception("Project git repo invalid: %s" % project_git)
        return upstream, branch

    def rest_results_hook(self, request, obj, results, detailed=False):
        if not isinstance(obj, Message):
            return
        log = obj.get_property("git.apply-log")
        data = None
        if log:
            if obj.get_property("git.apply-failed"):
                status = 'failure'
            else:
                git_repo = obj.get_property("git.repo")
                git_tag = obj.get_property("git.tag")
                data = {'repo': git_repo, 'tag': 'refs/tags/' + git_tag}
                status = 'success'
            log_url = reverse("git-log", kwargs={'series': obj.message_id})
        else:
            status = 'pending'
            log_url = None
        results.append(Result(name='git', obj=obj, status=status,
                              log=log, log_url=log_url, data=data,
                              request=request))

    def prepare_message_hook(self, request, message, detailed):
        if not message.is_series_head:
            return
        l = message.get_property("git.apply-log")
        if l:
            failed = message.get_property("git.apply-failed")
            log_url = reverse("git-log",
                              kwargs={"series": message.message_id})
            html_log_url = log_url + "?html=1"
            colorbox_a = format_html('<a class="cbox-log" data-link="{}" href="{}">apply log</a>',
                                     html_log_url, log_url)
            if failed:
                title = "Failed in applying to current master"
                message.status_tags.append({
                    "title": title,
                    "type": "default",
                    "char": "G",
                    })
                message.extra_status.append({
                    "kind": "alert",
                    "html": format_html('{} ({})', title, colorbox_a),
                })
            else:
                git_url = message.get_property("git.url")
                git_repo = message.get_property("git.repo")
                git_tag = message.get_property("git.tag")
                if git_url:
                    message.status_tags.append({
                        "url": git_url,
                        "title": format_html("Applied as tag {} in repo {}", git_tag, git_repo),
                        "type": "info",
                        "char": "G",
                        })
                    if git_repo and git_tag:
                        message.extra_status.append({
                            "kind": "good",
                            "html": format_html('Patches applied successfully (<a href="{}">tree</a>, {}).<br/><samp>git fetch {} {}</samp>',
                                                git_url, colorbox_a, git_repo, git_tag),
                        })
                else:
                    message.status_tags.append({
                        "title": format_html("Patches applied successfully"),
                        "type": "info",
                        "char": "G",
                        })
                    message.extra_status.append({
                        "kind": "good",
                        "html": format_html('Patches applied successfully ({})',
                                            colorbox_a),
                        "extra": colorbox_div,
                        "id": "gitlog"
                    })
        if request.user.is_authenticated:
            if message.get_property("git.apply-failed") != None or \
                 message.get_property("git.need-apply") == None:
                url = reverse("git_reset",
                              kwargs={"series": message.message_id})
                message.extra_ops.append({"url": url,
                                          "icon": "refresh",
                                          "title": "Git reset",
                                          "class": "warning",
                                         })

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Git configuration",
                                   "class": "info",
                                   "content_html": self.build_config_html(request,
                                                                          project)})

    def prepare_series_hook(self, request, series, response):
        po = series.project
        for prop in ["git.push_to", "git.public_repo", "git.url_template"]:
            if po.get_property(prop):
                response[prop] = po.get_property(prop)
        for tag in series.get_property("tags", []):
            if not tag.startswith("Based-on:"):
                continue
            base_id = tag[len("Based-on:"):].strip()
            if base_id.startswith("<") and base_id.endswith(">"):
                base_id = base_id[1:-1]
            base = Message.objects.series_heads().\
                    filter(project=po, message_id=base_id).first()
            if not base:
                break
            if not base.get_property("git.repo"):
                break
            response["git.repo"] = base.get_property("git.repo")
            response["git.base"] = base.get_property("git.tag")
            break

    def _poll_project(self, po):
        repo, branch = self._get_project_repo_and_branch(po)
        cache_repo = self._update_cache_repo(po.name, repo, branch)
        head = subprocess.check_output(["git", "rev-parse", branch],
                                       cwd=cache_repo).decode('utf-8').strip()
        old_head = po.get_property("git.head")
        if old_head != head:
            po.set_property("git.head", head)
            po.set_property("git.repo", repo)
            emit_event("ProjectGitUpdate", project=po.name)
        return cache_repo

    def www_view_git_reset(self, request, series):
        if not request.user.is_authenticated:
            raise PermissionDenied
        obj = Message.objects.find_series(series)
        if not obj:
            raise Http404("Not found: " + series)
        for p in obj.get_properties():
            if p.startswith("git.") and p != "git.need-apply":
                obj.set_property(p, None)
        obj.set_property("git.need-apply", True)
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

    def handle(self, request):
        mp = MessageProperty.objects.filter(name="git.need-apply",
                                            value='true',
                                            message__is_complete=True).first()
        if mp:
            return prepare_series(request, mp.message)

class ApplierReportView(APILoginRequiredView):
    name = "applier-report"
    allowed_groups = ["importers"]

    def handle(self, request, project, message_id, tag, url, base, repo,
               failed, log):
        s = Message.objects.series_heads().get(project__name=project,
                                               message_id=message_id)
        s.set_property("git.tag", tag)
        s.set_property("git.url", url)
        s.set_property("git.base", base)
        s.set_property("git.repo", repo)
        s.set_property("git.apply-failed", failed)
        s.set_property("git.apply-log", log)
        s.set_property("git.need-apply", False)
