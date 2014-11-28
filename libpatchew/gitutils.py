#!/usr/bin/env python2
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Fam Zheng <famcool@gmail.com>
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

import subprocess
import tempfile

class GitRepo(object):
    def __init__(self, directory, stdout=None, stderr=None):
        self._dir = directory
        self._stdout = stdout
        self._stderr = stderr

    def __call__(self, *args):
        p = subprocess.Popen(["git"] + list(args), cwd=self._dir,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        p.wait()
        self._stdout.write(p.stdout.read())
        self._stderr.write(p.stderr.read())
        return p.returncode

    def check_merged(self, msg_ids):
        cmd = ["log", "--oneline"]
        for i in msg_ids:
            cmd += ["--grep", "Message-id: " + i]
        try:
            out = subprocess.check_output(['git'] + list(cmd))
            if len(out.splitlines()) == len(msg_ids):
                return True
        except:
            pass
        return False

    def apply_patches(self, patches):
        cmd = ["am"] + list(patches)
        return self(*cmd) == 0
