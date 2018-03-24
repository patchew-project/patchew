#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

import abc
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

class TestingTestCase(PatchewTestCase, metaclass=abc.ABCMeta):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")
        self.p.git = "dummy repo"
        self.p.save()

        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        create_test(self.p, "a")

    def _do_testing_done(self, obj, log, report):
        if not 'passed' in report:
            report['passed'] = True
        obj.set_property("testing.report.tests", report)
        if log is not None:
            obj.set_property("testing.log.tests", log)
        obj.set_property("testing.done", True)
        obj.set_property("testing.ready", None)

    def do_testing_report(self, **report):
        self.api_login()
        r = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
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
        return r['identity']

    @abc.abstractmethod
    def do_testing_done(self, log=None, **report):
        pass

    @abc.abstractmethod
    def get_test_result(self, test_name):
        pass

    def test_basic(self):
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertIn("head", td)

    def test_done(self):
        self.do_testing_done()
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertFalse(td)

    def test_rest_done_success(self):
        self.do_testing_done(log='everything good!', passed=True)
        resp = self.get_test_result('tests')
        self.assertEquals(resp.data['status'], 'success')
        self.assertEquals(resp.data['log'], 'everything good!')
        log = self.client.get(resp.data['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'everything good!')

    def test_rest_done_failure(self):
        self.do_testing_done(log='sorry no good', passed=False, random_stuff='xyz')
        resp = self.get_test_result('tests')
        self.assertEquals(resp.data['status'], 'failure')
        self.assertEquals(resp.data['data']['random_stuff'], 'xyz')
        self.assertEquals(resp.data['log'], 'sorry no good')
        log = self.client.get(resp.data['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'sorry no good')

    def test_api_report_success(self):
        self.api_login()
        self.do_testing_report(log='everything good!', passed=True)
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['data']['is_timeout'], False)
        self.assertEquals(resp.data['status'], 'success')
        log = self.client.get(resp.data['log_url'])
        self.assertEquals(resp.data['log'], 'everything good!')
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'everything good!')

    def test_api_report_failure(self):
        self.api_login()
        self.do_testing_report(log='sorry no good', passed=False)
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['data']['is_timeout'], False)
        self.assertEquals(resp.data['status'], 'failure')
        self.assertEquals(resp.data['log'], 'sorry no good')
        log = self.client.get(resp.data['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'sorry no good')

class MessageTestingTest(TestingTestCase):

    def setUp(self):
        super(MessageTestingTest, self).setUp()

        self.cli_login()
        self.cli_import('0001-simple-patch.mbox.gz')
        self.cli_logout()

        self.msg = Message.objects.all()[0]
        self.msg.save()
        self.msg.set_property("git.repo", "dummy repo")
        self.msg.set_property("git.tag", "dummy tag")
        self.msg.set_property("git.base", "dummy base")

    def do_testing_done(self, log=None, **report):
        self._do_testing_done(self.msg, log, report)

    def do_testing_report(self, **report):
        r = super(MessageTestingTest, self).do_testing_report(**report)
        self.assertEquals(r['type'], 'series')
        return r

    def get_test_result(self, test_name):
        return self.api_client.get('%sseries/%s/results/testing.%s/' % (
                                       self.PROJECT_BASE, self.msg.message_id, test_name))

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

class ProjectTestingTest(TestingTestCase):

    def setUp(self):
        super(ProjectTestingTest, self).setUp()
        self.p.set_property("git.head", "5678")
        self.p.set_property("testing.tested-head", "1234")
        self.p.set_property("testing.ready", 1)

    def do_testing_done(self, log=None, **report):
        self._do_testing_done(self.p, log, report)

    def do_testing_report(self, **report):
        r = super(ProjectTestingTest, self).do_testing_report(**report)
        self.assertEquals(r['type'], 'project')
        return r

    def get_test_result(self, test_name):
        return self.api_client.get('%sresults/testing.%s/' % (
                                       self.PROJECT_BASE, test_name))

class TesterTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

        self.p1 = self.add_project("QEMU", "qemu-devel@nongnu.org")
        create_test(self.p1, "a")
        self.p2 = self.add_project("UMEQ", "qemu-devel@nongnu.org")
        create_test(self.p2, "b")

        self.cli_login()
        self.cli_import('0001-simple-patch.mbox.gz')
        self.cli_logout()

        self.repo = os.path.join(self.get_tmpdir(), "repo")
        os.mkdir(self.repo)
        subprocess.check_output(["git", "init"], cwd=self.repo)
        for f in ["foo", "bar"]:
            self.add_file_and_commit(f)
        self.update_head(self.p1)
        self.update_head(self.p2)
        base = subprocess.check_output(["git", "rev-parse", "HEAD~1"],
                                       cwd=self.repo).decode()
        subprocess.check_output(["git", "tag", "test"], cwd=self.repo)

        for msg in Message.objects.all():
            msg.set_property("git.repo", self.repo)
            msg.set_property("git.tag", "test")
            msg.set_property("git.base", base)

    def add_file_and_commit(self, f):
        subprocess.check_output(["touch", f], cwd=self.repo)
        subprocess.check_output(["git", "add", f], cwd=self.repo)
        subprocess.check_output(["git", "commit", "-m", "add " + f],
                                cwd=self.repo)

    def update_head(self, p):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=self.repo).decode()
        p.set_property("git.head", head)

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

    def test_tester_project(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("Project: UMEQ\n", out)

        self.p1.git = self.repo
        self.p1.save()
        self.add_file_and_commit("baz")
        self.update_head(self.p1)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("'type': 'project'", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Nothing to test", out)
        self.cli_logout()

# do not run tests on the abstract class
del TestingTestCase

if __name__ == '__main__':
    main()
