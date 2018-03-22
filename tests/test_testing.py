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
import subprocess
sys.path.append(os.path.dirname(__file__))
from patchewtest import PatchewTestCase, main
from api.models import Message

def create_test(project, name):
    prefix = "testing.tests." + name + "."
    project.set_property(prefix + "timeout", 3600)
    project.set_property(prefix + "enabled", True)
    project.set_property(prefix + "script", "#!/bin/bash\ntrue")
    project.set_property(prefix + "requirements", "")
    project.set_property(prefix + "users", "")
    project.set_property(prefix + "tester", "")

class TestingTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        create_test(self.p, "a")

        self.cli_login()
        self.cli_import('0001-simple-patch.mbox.gz')
        self.cli_logout()

        self.msg = Message.objects.all()[0]
        self.msg.save()
        self.msg.set_property("git.repo", "dummy repo")
        self.msg.set_property("git.tag", "dummy tag")
        self.msg.set_property("git.base", "dummy base")

    def test_testing_ready(self):
        self.assertTrue(self.msg.get_property("testing.ready"))
        # Set property through series_heads elements must be handled the same
        self.msg.set_property("git.repo", None)
        self.msg.set_property("git.tag", None)
        self.msg.set_property("testing.ready", None)
        msg = Message.objects.series_heads()[0]
        self.assertEqual(self.msg.message_id, msg.message_id)
        msg.set_property("git.repo", "dummy repo")
        msg.set_property("git.tag", "dummy tag")
        msg.set_property("git.base", "dummy base")
        self.assertTrue(msg.get_property("testing.ready"))

    def msg_testing_done(self, log=None, **report):
        if not 'passed' in report:
            report['passed'] = True
        self.msg.set_property("testing.report.tests", report)
        if log is not None:
            self.msg.set_property("testing.log.tests", log)
        self.msg.set_property("testing.done", True)
        self.msg.set_property("testing.ready", None)

    def msg_testing_report(self, **report):
        self.api_login()
        r = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertEquals(r['identity']['type'], 'series')

        report['project'] = r["project"]
        report['identity'] = r["identity"]
        report['test'] = r["test"]["name"]
        report['tester'] = 'dummy_tester'
        report['head'] = r["head"]
        report['base'] = r["base"]
        if not 'passed' in report:
            report['passed'] = True
        if not 'log' in report:
            report['log'] = None
        if not 'is_timeout' in report:
            report['is_timeout'] = False

        self.api_call("testing-report", **report)
        return r['identity']['message-id']

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

    def test_api_report_success(self):
        self.api_login()
        msgid = self.msg_testing_report(log='everything good!', passed=True)
        resp = self.api_client.get(self.PROJECT_BASE + 'series/' + self.msg.message_id + '/')
        self.assertEquals(resp.data['results']['testing.a']['status'], 'success')
        log = self.client.get(resp.data['results']['testing.a']['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'everything good!')

    def test_api_report_failure(self):
        self.api_login()
        msgid = self.msg_testing_report(log='sorry no good', passed=False)
        resp = self.api_client.get(self.PROJECT_BASE + 'series/' + self.msg.message_id + '/')
        self.assertEquals(resp.data['results']['testing.a']['status'], 'failure')
        log = self.client.get(resp.data['results']['testing.a']['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'sorry no good')

class TesterTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

        p1 = self.add_project("QEMU", "qemu-devel@nongnu.org")
        create_test(p1, "a")
        p2 = self.add_project("UMEQ", "qemu-devel@nongnu.org")
        create_test(p2, "b")

        self.cli_login()
        self.cli_import('0001-simple-patch.mbox.gz')
        self.cli_logout()

        self.repo = os.path.join(self.get_tmpdir(), "repo")
        os.mkdir(self.repo)
        subprocess.check_output(["git", "init"], cwd=self.repo)
        for f in ["foo", "bar"]:
            subprocess.check_output(["touch", f], cwd=self.repo)
            subprocess.check_output(["git", "add", f], cwd=self.repo)
            subprocess.check_output(["git", "commit", "-m", "add " + f],
                                    cwd=self.repo)
        base = subprocess.check_output(["git", "rev-parse", "HEAD~1"],
                                       cwd=self.repo).decode()
        subprocess.check_output(["git", "tag", "test"], cwd=self.repo)

        for msg in Message.objects.all():
            msg.set_property("git.repo", self.repo)
            msg.set_property("git.tag", "test")
            msg.set_property("git.base", base)

    def test_tester(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("Project: UMEQ\n", out)
        self.cli_logout()

    def test_tester_single(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: QEMU\n", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: UMEQ\n", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Nothing to test", out)
        self.cli_logout()

if __name__ == '__main__':
    main()
