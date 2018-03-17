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
import shutil
import subprocess
from api.models import Message

class GitTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.cli_login()
        self.repo = self.create_git_repo()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org", git_repo=self.repo)
        self.p.set_property("git.push_to", self.repo)
        self.p.set_property("git.public_repo", self.repo)
        self.p.set_property("git.url_template", self.repo + " %t")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

    def cleanUp(self):
        shutil.rmtree(self.repo)

    def do_apply(self):
        self.cli(["apply", "--applier-mode"])
        for s in Message.objects.series_heads():
            self.assertFalse(s.get_property("git.need-apply"))

    def test_need_apply(self):
        self.cli_import("0001-simple-patch.mbox.gz")
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.need-apply"), True)
        self.do_apply()

    def test_need_apply_multiple(self):
        self.cli_import("0004-multiple-patch-reviewed.mbox.gz")
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.need-apply"), True)
        self.do_apply()

    def test_need_apply_incomplete(self):
        self.cli_import("0012-incomplete-series.mbox.gz")
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, False)
        self.assertEqual(s.get_property("git.need-apply"), None)

    def test_apply(self):
        self.cli_import("0013-foo-patch.mbox.gz")
        self.do_apply()
        s = Message.objects.series_heads()[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.repo"), self.repo)
        self.assertEqual(s.get_property("git.tag"),
                         "patchew/20160628014747.20971-1-famz@redhat.com")
        self.assertEqual(s.get_property("git.url"),
                         self.repo + " patchew/20160628014747.20971-1-famz@redhat.com")

    def test_apply_with_base(self):
        self.cli_import("0013-foo-patch.mbox.gz")
        self.do_apply()
        self.cli_import("0014-bar-patch.mbox.gz")
        self.do_apply()
        s = Message.objects.series_heads().filter(message_id="20160628014747.20971-2-famz@redhat.com")[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.repo"), self.repo)
        self.assertEqual(s.get_property("git.tag"),
                         "patchew/20160628014747.20971-2-famz@redhat.com")
        self.assertEqual(s.get_property("git.url"),
                         self.repo + " patchew/20160628014747.20971-2-famz@redhat.com")

    def test_apply_with_base_and_brackets(self):
        self.cli_import("0013-foo-patch.mbox.gz")
        self.do_apply()
        self.cli_import("0015-bar-patch-with-brackets.mbox.gz")
        self.do_apply()
        s = Message.objects.series_heads().filter(message_id="20160628014747.20971-2-famz@redhat.com")[0]
        self.assertEqual(s.is_complete, True)
        self.assertEqual(s.get_property("git.repo"), self.repo)
        self.assertEqual(s.get_property("git.tag"),
                         "patchew/20160628014747.20971-2-famz@redhat.com")
        self.assertEqual(s.get_property("git.url"),
                         self.repo + " patchew/20160628014747.20971-2-famz@redhat.com")

    def test_rest_need_apply(self):
        self.cli_import("0013-foo-patch.mbox.gz")
        MESSAGE_ID = '20160628014747.20971-1-famz@redhat.com'
        resp = self.api_client.get('%sseries/%s/results/git/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['log_url'], None)
        self.assertEqual(resp.data['log'], None)

    def test_rest_apply_failure(self):
        self.cli_import("0014-bar-patch.mbox.gz")
        self.do_apply()
        MESSAGE_ID = '20160628014747.20971-2-famz@redhat.com'
        resp = self.api_client.get('%sseries/%s/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['is_complete'], True)

        resp = self.api_client.get('%sseries/%s/results/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['results'][0]['name'], 'git')
        self.assertEqual('log' in resp.data['results'][0], False)
        self.assertEqual('log_url' in resp.data['results'][0], True)

        resp = self.api_client.get('%sseries/%s/results/git/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['status'], 'failure')
        self.assertEqual('repo' in resp.data, False)
        self.assertEqual('tag' in resp.data, False)
        log = self.client.get(resp.data['log_url'])
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.content.decode(), resp.data['log'])

    def test_rest_apply_success(self):
        self.cli_import("0013-foo-patch.mbox.gz")
        self.do_apply()
        MESSAGE_ID = '20160628014747.20971-1-famz@redhat.com'
        resp = self.api_client.get('%sseries/%s/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['is_complete'], True)
        resp = self.api_client.get('%sseries/%s/results/git/' % (self.PROJECT_BASE, MESSAGE_ID))
        self.assertEqual(resp.data['status'], 'success')
        self.assertEqual(resp.data['data']['repo'], self.repo)
        self.assertEqual(resp.data['data']['tag'], "refs/tags/patchew/20160628014747.20971-1-famz@redhat.com")
        log = self.client.get(resp.data['log_url'])
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.content.decode(), resp.data['log'])

if __name__ == '__main__':
    main()
