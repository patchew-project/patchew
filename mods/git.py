import os
import subprocess
import tempfile
import shutil
import hashlib
from django.conf.urls import url
from django.http import HttpResponse, Http404
from django.template import Context, Template
from mod import PatchewModule
from event import declare_event, register_handler, emit_event
from api.models import Project
from schema import *

_instance = None

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
                                     desc="Publicly visible URL template for applied branch",
                                     required=True),
                   ])

    def __init__(self):
        global _instance
        assert _instance == None
        _instance = self
        # Make sure git is available
        subprocess.check_output(["git", "version"])
        declare_event("ProjectGitUpdate", project="the updated project name")
        register_handler("SeriesComplete", self.on_series_update)
        register_handler("TagsUpdate", self.on_series_update)

    def on_series_update(self, event, series, **params):
        if not series.is_complete:
            return
        wd = tempfile.mkdtemp(prefix="patchew-git-tmp-", dir="/var/tmp")
        try:
            self._update_series(wd, series)
        finally:
            shutil.rmtree(wd)

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

    def _clone_repo(self, project_name, wd, repo, branch, logf):
        cache_repo = self._update_cache_repo(project_name, repo, branch, logf)
        clone = os.path.join(wd, "src")
        subprocess.check_call(["git", "clone", "-q", "--branch", branch,
                              cache_repo, clone],
                              stderr=logf, stdout=logf)
        return clone

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

    def _update_series(self, wd, s):
        logf = tempfile.NamedTemporaryFile()
        project_name = s.project.name
        push_to = None
        try:
            upstream, base_branch = self._get_project_repo_and_branch(s.project)
            repo = self._clone_repo(project_name, wd, upstream, base_branch, logf)
            new_branch = s.message_id
            subprocess.check_call(["git", "checkout", "-q", "-b", new_branch],
                                  cwd=repo, stdout=logf, stderr=logf)
            base = subprocess.check_output(["git", "log", '-n', '1', "--format=%H"],
                                           cwd=repo).strip()
            logf.write("On top of commit: %s\n" % base)
            logf.flush()
            for p in s.get_patches():
                subprocess.check_call(["git", "am", p.get_mbox_path()],
                                      cwd=repo, stdout=logf, stderr=logf)
                filter_cmd = ""
                for t in ["Message-id: %s" % p.message_id] + \
                         p.get_property("tags", []):
                    filter_cmd += "echo '%s';" % t
                if filter_cmd:
                    subprocess.check_output(["git", "filter-branch", "-f",
                                             "--msg-filter", "cat; " + filter_cmd,
                                             "HEAD~1.."], cwd=repo)
            push_to = self.get_project_config(s.project, "push_to")
            if push_to:
                subprocess.check_call(["git", "remote", "add",
                                        "push_remote", push_to], cwd=repo,
                                        stdout=logf, stderr=logf)
                # Push the new branch to remote as a new tag with the same name
                subprocess.check_call(["git", "push", "-f",
                                       "push_remote",
                                       "refs/heads/%s:refs/tags/%s" % \
                                               (new_branch, new_branch)],
                                        cwd=repo,
                                        stdout=logf, stderr=logf)
                subprocess.call(["git", "push", "push_remote", base_branch],
                                cwd=repo,
                                stdout=logf, stderr=logf)
            public_repo = self.get_project_config(s.project, "public_repo")
            s.set_property("git.repo", public_repo)
            s.set_property("git.tag", new_branch)
            s.set_property("git.base", base)
            s.set_property("git.url",
                           self.get_project_config(s.project, "url_template")\
                                   .format(tag_name=new_branch))
            s.set_property("git.apply-failed", False)
        except Exception as e:
            logf.write(str(e))
            s.set_property("git.apply-failed", True)
            s.set_property("git.repo", None)
            s.set_property("git.tag", None)
            s.set_property("git.base", None)
            s.set_property("git.url", None)
        finally:
            logf.seek(0)
            log = logf.read()
            if push_to:
                log = log.replace(push_to, public_repo)
            s.set_property("git.apply-log", log)

    def prepare_message_hook(self, request, message):
        if not message.is_series_head:
            return
        l = message.get_property("git.apply-log")
        if l:
            failed = message.get_property("git.apply-failed")
            message.extra_info.append({"title": "Git apply log",
                                       "class": 'danger' if failed else 'default',
                                       "content": l})
            git_url = message.get_property("git.url")
            git_repo = message.get_property("git.repo")
            git_tag = message.get_property("git.tag")
            if failed:
                title = "Failed in applying to current master"
                message.status_tags.append({
                    "title": title,
                    "type": "default",
                    "char": "G",
                    })
            else:
                html = 'Git: <a href="%s">%s</a>' % (git_url, git_url)
                message.extra_headers.append(html)
                title = "Applied as tag %s in repo %s" % (git_tag, git_url)
                message.status_tags.append({
                    "url": git_url,
                    "title": title,
                    "type": "info",
                    "char": "G",
                    })

    def prepare_project_hook(self, request, project):
        if not project.maintained_by(request.user):
            return
        project.extra_info.append({"title": "Git config",
                                   "content": self.build_config_html(request,
                                                                     project)})

    def _poll_project(self, po):
        repo, branch = self._get_project_repo_and_branch(po)
        cache_repo = self._update_cache_repo(po.name, repo, branch)
        head = subprocess.check_output(["git", "rev-parse", branch],
                                       cwd=cache_repo).strip()
        old_head = po.get_property("git.head")
        if old_head != head:
            po.set_property("git.head", head)
            po.set_property("git.repo", repo)
            emit_event("ProjectGitUpdate", project=po.name)

    def www_view_git_poll(self, request):
        project = request.GET.get("project")
        if project:
            po = Project.objects.get(name=project)
            self._poll_project(po)
        else:
            for p in Project.objects.all():
                self._poll_project(p)
        return HttpResponse()

    def www_url_hook(self, urlpatterns):
        urlpatterns.append(url(r"^git-poll/", self.www_view_git_poll))
