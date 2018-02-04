#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import sys
import os
import datetime
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
from api.models import Message, Project

class TestingTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        self.p.set_property("testing.tests.a.timeout", 3600)
        self.p.set_property("testing.tests.a.enabled", True)
        self.p.set_property("testing.tests.a.script", "#!/bin/bash\ntrue")
        self.p.set_property("testing.tests.a.requirements", "")
        self.p.set_property("testing.tests.a.users", "")
        self.p.set_property("testing.tests.a.tester", "")

        self.cli_login()
        self.cli_import('0001-simple-patch.mbox.gz')
        self.cli_logout()

        self.msg = Message.objects.all()[0]
        self.msg.save()
        self.msg.set_property("git.repo", "dummy repo")
        self.msg.set_property("git.tag", "dummy tag")
        self.msg.set_property("git.base", "dummy base")

    def msg_testing_done(self, log=None, **report):
        if not 'passed' in report:
            report['passed'] = True
        self.msg.set_property("testing.report.tests", report)
        if log is not None:
            self.msg.set_property("testing.log.tests", log)
        self.msg.set_property("testing.done", True)

    def test_basic(self):
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertIn("head", td)

    def test_done(self):
        self.msg_testing_done()
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertFalse(td)

    def test_rest_basic(self):
        resp = self.api_client.get(self.PROJECT_BASE + 'series/' + self.msg.message_id + '/')
        self.assertEquals('testing.tests' in resp.data['results'], False)

    def test_rest_done_success(self):
        self.msg_testing_done(log='everything good!', passed=True)
        resp = self.api_client.get(self.PROJECT_BASE + 'series/' + self.msg.message_id + '/')
        self.assertEquals(resp.data['results']['testing.tests']['status'], 'success')
        log = self.client.get(resp.data['results']['testing.tests']['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'everything good!')

    def test_rest_done_failure(self):
        self.msg_testing_done(log='sorry no good', passed=False)
        resp = self.api_client.get(self.PROJECT_BASE + 'series/' + self.msg.message_id + '/')
        self.assertEquals(resp.data['results']['testing.tests']['status'], 'failure')
        log = self.client.get(resp.data['results']['testing.tests']['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'sorry no good')

if __name__ == '__main__':
    main()
