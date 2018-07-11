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
from api.models import Message, MessageProperty, Project, Result
from api.rest import PluginMethodField
from api.views import APILoginRequiredView, prepare_series
from patchew.logviewer import LogView
from schema import *

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

    def mark_as_pending_apply(self, series):
        r = series.git_result or series.create_result(name='git')
        r.log = None
        r.status = Result.PENDING
        r.data = {}
        r.save()

    def on_series_update(self, event, series, **params):
        if series.is_complete:
            self.mark_as_pending_apply(series)

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

    def get_based_on(self, message, request, format):
        git_base = self.get_base(message)
        return git_base.data if git_base else None

    def rest_series_fields_hook(self, request, fields, detailed):
        fields['based_on'] = PluginMethodField(obj=self, required=False)

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
        for tag in series.get_property("tags", []):
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

    def prepare_series_hook(self, request, series, response):
        po = series.project
        for prop in ["git.push_to", "git.public_repo", "git.url_template"]:
            if po.get_property(prop):
                response[prop] = po.get_property(prop)
        base = self.get_base(series)
        if base:
            response["git.repo"] = base.data["repo"]
            response["git.base"] = base.data["tag"]

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

    def handle(self, request):
        m = Message.objects.filter(results__name="git", results__status="pending").first()
        if m:
            return prepare_series(request, m)

class ApplierReportView(APILoginRequiredView):
    name = "applier-report"
    allowed_groups = ["importers"]

    def handle(self, request, project, message_id, tag, url, base, repo,
               failed, log):
        p = Project.objects.get(name=project)
        r = Message.objects.series_heads().get(project=p,
                                               message_id=message_id).git_result
        r.log = log
        data = {}
        if failed:
            r.status = Result.FAILURE
        else:
            data['repo'] = repo
            data['tag'] = 'refs/tags/' + tag
            if url:
                data['url'] = url
            elif url_template and tag:
                url_template = p.get_property("git.url_template")
                data['url'] = url_template.replace("%t", tag)
            if base:
                data['base'] = base
            r.status = Result.SUCCESS
        r.data = data
        r.save()
