import os
import subprocess
import tempfile
import shutil
from mod import PatchewModule
import hashlib
from event import register_handler

_default_config = """
[project QEMU]

# The local mirror of upstream repo to speed up clone
cache_repo=/var/tmp/patchew-git-cache-qemu

# The remote repo to push the new branch with the series applied
# You can specify a https based github repo with username/password embedded in
# the URL for authentication
push_to=https://your_name:your_pass@github.com/your_name/your_project

# The visible git repo URL that is visible to users
public_repo=https://github.com/your_name/your_project

# The url format of the hyperlink
url_template=https://github.com/your_name/your_project/tree/{tag_name}

"""

class GitModule(PatchewModule):
    """

Documentation
-------------

This module is configured in "INI" style.

Each section named like 'project FOO' provides information for automatical git
apply for each series in that project. A typical setup looks like:

    [project QEMU]
    cache_repo=/var/tmp/patchew-git-cache-qemu
    push_to=/path/to/your/repo
    public_repo=https://github.com/your_name/your_project
    url_template=https://github.com/your_name/your_project/tree/{tag_name}

The meaning of each option is:

  * **cache_repo**: Where to hold the local repo as a clone of project
    upstream. The server script must have write access to this location, and
    each project should have its own location.

  * **push_to**: Where to push (as in `git remote`) the git tag after
    successfully applying.

  * **public_repo**: The URL to the repo (as in HTML hyperlinks).

  * **url_template**: The template to generate a quick link to the pushed tag.
    '{tag_name}' in the template will be replaced with the actual tag name.

"""
    name = "git"
    default_config = _default_config

    def __init__(self):
        # Make sure git is available
        subprocess.check_output(["git", "version"])
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
        return self.get_config("project " + project, what)

    def _clone_repo(self, project_name, wd, repo, branch, logf):
        clone = os.path.join(wd, "src")
        cache_repo = self.get_project_config(project_name, "cache_repo")
        if not os.path.isdir(cache_repo):
            # Clone upstream to local cache
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
        subprocess.check_call(["git", "clone", "-q", "--branch", branch,
                              cache_repo, clone],
                              stderr=logf, stdout=logf)
        return clone

    def _update_series(self, wd, s):
        logf = tempfile.NamedTemporaryFile()
        project_name = s.project.name
        push_to = None
        try:
            project_git = s.project.git
            if not project_git:
                raise Exception("Project git repo not set")
            if len(project_git.split()) != 2:
                # Use master as the default branch
                project_git += " master"
            upstream, base_branch = project_git.split()[0:2]
            if not upstream or not base_branch:
                raise Exception("Project git repo invalid: %s" % project_git)
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
            push_to = self.get_project_config(project_name, "push_to")
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
            s.set_property("git.repo", self.get_project_config(project_name, "public_repo"))
            s.set_property("git.tag", new_branch)
            s.set_property("git.base", base)
            s.set_property("git.url",
                           self.get_project_config(project_name, "url_template")\
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
                log = log.replace(push_to, "$PUSH_TO")
            s.set_property("git.apply-log", log)

    def prepare_message_hook(self, message):
        if not message.is_series_head:
            return
        l = message.get_property("git.apply-log")
        if l:
            failed = message.get_property("git.apply-failed")
            message.extra_info.append({"title": "Git apply log",
                                       "is_error": failed,
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

