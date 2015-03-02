#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <fam@euphon.net>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
import shutil
import time
import subprocess
import tempfile
import os
import json
import sys
from gitutils import GitRepo
from message import Message

def dump_test_spec(spec):
    for k_, v in spec.iteritems():
        k = "%-30s :" % k_
        if isinstance(v, list):
            test_log(k, "[...]\n")
        elif "\n" in str(v):
            test_log(k)
            test_log(v, "\n")
        else:
            test_log(k, v, "\n")

def init_repo(git, spec, clone):
    """ Do git clone, add remote, fetch and checkout """
    git("clone", clone, ".")
    git("remote", "add", "patchew-base", spec['codebase'])
    git("fetch", "patchew-base")
    git("clean", "-dfx")
    git("checkout", "-f", "remotes/patchew-base/%s" % spec['branch'])

class TestLogger(file):
    _levels = []
    def write(self, *what):
        for w in what:
            w = str(w)
            file.write(self, w)
            sys.stdout.write(w)

    def __call__(self, *w):
        self.write(*w)

class Tester(object):
    VERSION = 1
    def __init__(self, logger, testdir, test_spec, test_script=None, docker_image=None, cache_repo=None):
        self._spec = test_spec
        self._testdir = testdir
        self.log = logger
        self._test_script = test_script
        self._test_script_base_name = os.path.basename(test_script or "")
        self._docker_image = docker_image
        self._cache_repo = cache_repo

    def _testdir_entry(self, fname):
        return os.path.join(self._testdir, fname)

    def _test_file(self, name):
        fname = _self._testdir_entry(name)
        return open(fname, "r+")

    def write_patches(self, odir):
        def build_patch_fname(idx, p):
            r = "%04d-" % idx
            try:
                msg = Message(p)
                p = msg.get_subject(strip_tags=True)
                for c in p:
                    if c.isalnum() or c in "-_[]":
                        r += c
                    else:
                        r += "-"
            except:
                r += "unknown"
            r += ".patch"
            return r

        os.mkdir(odir)
        idx = 1
        patch_list = []
        for p in self._spec['patches-mbox-list']:
            p = p.encode("utf-8", "ignore")
            fn = build_patch_fname(idx, p)
            self.log(fn, "\n")
            fn_full = os.path.join(odir, fn)
            patch_list.append(fn_full)
            f = open(fn_full, "w")
            f.write(p)
            f.close()
            idx += 1
        return patch_list

    def docker_test(self):
        self.log('\nCopying test script "%s"\n' % self._test_script)
        test_copy = self._testdir_entry(self._test_script_base_name)
        shutil.copy2(self._test_script, test_copy)

        cmd = ["docker", "run", "--net=none",
               "-v", "%s:/var/tmp/patchew-test" % self._testdir,
               self._docker_image,
               "timeout", "3600",
               "/var/tmp/patchew-test/" + self._test_script_base_name,
               "/var/tmp/patchew-test"]
        self.log("Starting docker...\n")
        self.log(" ".join(cmd), "\n")

        self.log.flush()
        tp = subprocess.Popen(cmd, stdout=self.log, stderr=self.log)
        tp.communicate()
        if tp.returncode != 0:
            step = ""
            try:
                step_file = self._test_file("step")
                step = step_file.read().splitlines()[-1]
                step_file.close()
            except:
                pass
            return False, step
        else:
            return True, ""

    def do_test(self):
        self.log("======================\n")
        self.log("Patchew tester started\n")
        self.log("======================\n")
        self.log("\n")
        self.log("Test directory: ", self._testdir, "\n")
        if not self._cache_repo:
            self._cache_repo = tempfile.mkdtemp(dir="/var/tmp")
            git = GitRepo(self._cache_repo)
            git("clone", "-q", self._spec['codebase'])

        clone = self._cache_repo

        repo = os.path.join(self._testdir, "git")
        os.mkdir(repo)
        git = GitRepo(repo, stdout=self.log, stderr=self.log)

        self.log("\n=== Initializing code base ===\n")
        init_repo(git, self._spec, clone)

        self.log("\nChecking if the code is already merged ...")
        if git.check_merged(self._spec['patches-message-id-list']):
            self.log("Yes.\n\n")
            return True, "merged"
        else:
            self.log("No.\n\n")

        self.log("\n=== Writing patches ===\n")
        patches_dir = self._testdir_entry("patches")
        patches = self.write_patches(patches_dir)

        self.log("\n=== Applying patches ===\n")

        if not git.apply_patches(patches):
            self.log.seek(0)
            print self.log.read()
            return False, "apply"

        if self._docker_image and self._test_script:
            self.log("\n=== Starting docker ===\n")
            passed, step = self.docker_test()
            if not passed:
                self.log("\nTest failed.\n")
                return False, step
        self.log("\n=== Test completed ===\n")
        return True, ""
