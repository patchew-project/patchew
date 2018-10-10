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
from tests.patchewtest import PatchewTestCase, main
from api.models import Message, Result

def create_test(project, name, requirements="", script="#!/bin/bash\ntrue"):
    prefix = "testing.tests." + name + "."
    project.set_property(prefix + "timeout", 3600)
    project.set_property(prefix + "enabled", True)
    project.set_property(prefix + "script", script)
    project.set_property(prefix + "requirements", requirements)

class TestingTestCase(PatchewTestCase, metaclass=abc.ABCMeta):

    def setUp(self):
        self.create_superuser()
        self.p = self.add_project("QEMU", "qemu-devel@nongnu.org")

        self.PROJECT_BASE = '%sprojects/%d/' % (self.REST_BASE, self.p.id)

        create_test(self.p, "a")

    def modify_test_result(self, obj, **kwargs):
        try:
            r = obj.results.get(name='testing.a')
        except:
            r = obj.create_result(name='testing.a')
            if 'status' not in kwargs:
                kwargs['status'] = Result.PENDING

        if kwargs['status'] == Result.SUCCESS or kwargs['status'] == Result.FAILURE:
            if 'data' not in kwargs:
                kwargs['data'] = {}
            if 'head' not in kwargs['data']:
                kwargs['data']['head'] = '0123456789abcdef'
        if len(kwargs):
            for k, v in kwargs.items():
                setattr(r, k, v)
            r.save()

    def _do_testing_done(self, obj, **kwargs):
        if not 'status' in kwargs:
            kwargs['status'] = Result.SUCCESS
        self.modify_test_result(obj, **kwargs)
        obj.set_property("testing.done", True)

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
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['status'], 'running')

    def test_done(self):
        self.do_testing_done()
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertFalse(td)

    def test_rest_basic(self):
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['status'], 'pending')

    def test_rest_done_success(self):
        self.do_testing_done(log='everything good!', status=Result.SUCCESS)
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['status'], 'success')
        self.assertEquals(resp.data['log'], 'everything good!')
        log = self.client.get(resp.data['log_url'])
        self.assertEquals(log.status_code, 200)
        self.assertEquals(log.content, b'everything good!')

    def test_rest_done_failure(self):
        self.do_testing_done(log='sorry no good', status=Result.FAILURE)
        resp = self.get_test_result('a')
        self.assertEquals(resp.data['status'], 'failure')
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
        self.cli_import('0013-foo-patch.mbox.gz')
        self.do_apply()
        self.cli_logout()
        self.msg = Message.objects.all()[0]

    def do_testing_done(self, **kwargs):
        self._do_testing_done(self.msg, **kwargs)

    def do_testing_report(self, **report):
        r = super(MessageTestingTest, self).do_testing_report(**report)
        self.assertEquals(r['type'], 'series')
        return r

    def get_test_result(self, test_name):
        return self.api_client.get('%sseries/%s/results/testing.%s/' % (
                                       self.PROJECT_BASE, self.msg.message_id, test_name))

    def test_testing_ready(self):
        self.assertEqual(self.msg.results.filter(name='testing.a').first().status,
                         Result.PENDING)

class ProjectTestingTest(TestingTestCase):

    def setUp(self):
        super(ProjectTestingTest, self).setUp()
        self.p.set_property("git.head", "5678")
        self.p.set_property("testing.tested-head", "1234")

    def do_testing_done(self, **kwargs):
        self._do_testing_done(self.p, **kwargs)

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

        self.repo = self.create_git_repo("repo")

        self.p1 = self.add_project("QEMU", "qemu-devel@nongnu.org")
        create_test(self.p1, "a")

        self.p2 = self.add_project("UMEQ", "qemu-devel@nongnu.org")
        create_test(self.p2, "b")

        self.p3 = self.add_project("ALLOW", "qemu-devel@nongnu.org")
        self.p3.set_property("testing.requirements.allow.script",
                             "#!/bin/sh\ntrue")
        create_test(self.p3, "c", "allow")

        self.p4 = self.add_project("DENY", "qemu-devel@nongnu.org")
        self.p4.set_property("testing.requirements.deny.script",
                             "#!/bin/sh\nfalse")
        create_test(self.p4, "d", "deny")

        self.cli_login()
        self.cli_import('0013-foo-patch.mbox.gz')
        self.cli_logout()

        self.update_head(self.p1)
        self.update_head(self.p2)
        self.update_head(self.p3)
        self.update_head(self.p4)
        base = subprocess.check_output(["git", "rev-parse", "HEAD~1"],
                                       cwd=self.repo).decode()
        subprocess.check_output(["git", "tag", "test"], cwd=self.repo)

    def add_file_and_commit(self, f):
        subprocess.check_output(["touch", f], cwd=self.repo)
        subprocess.check_output(["git", "add", f], cwd=self.repo)
        subprocess.check_output(["git", "commit", "-m", "add " + f],
                                cwd=self.repo)

    def update_head(self, p):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=self.repo).decode()
        p.set_property("git.head", head)

    def test_print_capability(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "ALLOW", "--print-capabilities"])
        self.assertEqual(out, 'allow')
        out, err = self.check_cli(["tester", "-p", "DENY", "--print-capabilities"])
        self.assertEqual(out, '')
        self.cli_logout()

    def test_tester(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("Project: UMEQ\n", out)
        self.assertIn("Project: ALLOW\n", out)
        self.assertNotIn("Project: DENY\n", out)
        self.cli_logout()

    def test_tester_single(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: QEMU\n", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: UMEQ\n", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: ALLOW\n", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Nothing to test", out)
        self.cli_logout()

    def test_tester_project(self):
        self.cli_login()
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("Project: UMEQ\n", out)
        self.assertIn("Project: ALLOW\n", out)
        self.assertNotIn("Project: DENY\n", out)

        self.p1.git = self.repo
        self.p1.save()
        self.add_file_and_commit("baz")
        self.update_head(self.p1)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Project: QEMU\n", out)
        self.assertIn("'type': 'project'", out)
        out, err = self.check_cli(["tester", "-p", "QEMU,UMEQ,ALLOW,DENY",
                                   "--no-wait", "-N", "1"])
        self.assertIn("Nothing to test", out)
        self.cli_logout()

class TestingResetTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

        self.repo = self.create_git_repo("repo")

        self.p1 = self.add_project("QEMU", "qemu-devel@nongnu.org")
        create_test(self.p1, "a")
        create_test(self.p1, "b")
        create_test(self.p1, "c", script="#!/bin/bash\nfalse")

    def verify_results(self, m, results):
        for r in m.results.filter():
            self.assertEqual(r.status, results[r.name])

    def test_reset_one(self):
        self.cli_login()
        self.cli_import('0013-foo-patch.mbox.gz')
        self.do_apply()
        out, err = self.check_cli(["tester", "-p", "QEMU", "--no-wait"])
        self.assertIn("Project: QEMU\n", out)
        self.cli_logout()

        msg = Message.objects.all()[0]
        self.verify_results(msg, {"git": Result.SUCCESS,
                                  "testing.a": Result.SUCCESS,
                                  "testing.b": Result.SUCCESS,
                                  "testing.c": Result.FAILURE})
        self.assertTrue(msg.get_property("testing.done"))

        self.api_login()
        self.client.post('/login/', {'username': self.user, 'password': self.password})
        self.client.get('/testing-reset/%s/?type=message&test=a' % msg.message_id)

        msg = Message.objects.all()[0]
        self.verify_results(msg, {"git": Result.SUCCESS,
                                  "testing.a": Result.PENDING,
                                  "testing.b": Result.SUCCESS,
                                  "testing.c": Result.FAILURE})
        self.assertFalse(msg.get_property("testing.done"))

        self.client.get('/testing-reset/%s/?type=message&test=b' % msg.message_id)
        self.client.get('/testing-reset/%s/?type=message&test=c' % msg.message_id)
        self.verify_results(msg, {"git": Result.SUCCESS,
                                  "testing.a": Result.PENDING,
                                  "testing.b": Result.PENDING,
                                  "testing.c": Result.PENDING})
        self.assertFalse(msg.get_property("testing.done"))

class TestingDisableTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

        self.repo = self.create_git_repo("repo")

        self.p1 = self.add_project("QEMU", "qemu-devel@nongnu.org")
        create_test(self.p1, "a")

    def test_disable_test(self):
        self.cli_login()
        self.cli_import('0013-foo-patch.mbox.gz')
        self.do_apply()
        self.p1.set_property("testing.tests.a.enabled", False)
        out, err = self.check_cli(["tester", "-p", "QEMU", "--no-wait"])
        self.assertNotIn("Project: QEMU\n", out)
        self.cli_logout()

# do not run tests on the abstract class
del TestingTestCase

if __name__ == '__main__':
    main()
