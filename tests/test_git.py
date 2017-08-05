#!/usr/bin/env python3
#
# Copyright 2017 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import sys
import os
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
import json
import tempfile
import shutil
import subprocess
from api.models import Message

class GitTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.repo = os.path.join(self.get_tmpdir(), "repo")
        os.mkdir(self.repo)
        subprocess.check_output(["git", "init"], cwd=self.repo)
        subprocess.check_output(["touch", "foo"], cwd=self.repo)
        subprocess.check_output(["git", "add", "foo"], cwd=self.repo)
        subprocess.check_output(["git", "commit", "-m", "initial commit"],
                                cwd=self.repo)
        p = self.add_project("QEMU", "qemu-devel@nongnu.org", git_repo=self.repo)
        p.set_property("git.push_to", self.repo)
        p.set_property("git.public_repo", self.repo)
        p.set_property("git.url_template", self.repo + " %t")

    def cleanUp(self):
        shutil.rmtree(self.repo)

    def do_apply(self):
        self.cli(["apply", "--applier-mode"])
        for s in Message.objects.series_heads():
            self.assertFalse(s.get_property("git.need-apply"))

    def test_need_apply(self):
        self.check_cli(["import", self.get_data_path("0001-simple-patch.mbox.gz")])
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.need-apply"), True)
        self.do_apply()

    def test_need_apply_multiple(self):
        self.check_cli(["import", self.get_data_path("0004-multiple-patch-reviewed.mbox.gz")])
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.need-apply"), True)
        self.do_apply()

    def test_need_apply_incomplete(self):
        self.check_cli(["import", self.get_data_path("0012-incomplete-series.mbox.gz")])
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, False)
        self.assertEqual(s.get_property("git.need-apply"), None)

    def test_apply(self):
        self.check_cli(["import", self.get_data_path("0013-foo-patch.mbox.gz")])
        self.do_apply()
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.repo"), self.repo)
        self.assertEqual(s.get_property("git.tag"),
                         "patchew/20160628014747.20971-1-famz@redhat.com")
        self.assertEqual(s.get_property("git.url"),
                         self.repo + " patchew/20160628014747.20971-1-famz@redhat.com")

    def test_apply_with_base(self):
        self.check_cli(["import", self.get_data_path("0013-foo-patch.mbox.gz")])
        self.do_apply()
        self.check_cli(["import", self.get_data_path("0014-bar-patch.mbox.gz")])
        self.do_apply()
        s = Message.objects.series_heads().filter(message_id="20160628014747.20971-2-famz@redhat.com")[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.repo"), self.repo)
        self.assertEqual(s.get_property("git.tag"),
                         "patchew/20160628014747.20971-2-famz@redhat.com")
        self.assertEqual(s.get_property("git.url"),
                         self.repo + " patchew/20160628014747.20971-2-famz@redhat.com")


if __name__ == '__main__':
    main()
