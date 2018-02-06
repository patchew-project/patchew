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

    def test_basic(self):
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertIn("head", td)

    def test_done(self):
        self.msg.set_property("testing.done", True)
        self.api_login()
        td = self.api_call("testing-get",
                           project="QEMU",
                           tester="dummy tester",
                           capabilities=[])
        self.assertFalse(td)

if __name__ == '__main__':
    main()
