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
from patchewtest import PatchewTestCase, main
from api.models import Message, Project

class TestingTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

    def test_basic(self):
        prj = Project(name="TestProject")
        prj.save()
        prj.set_property("testing.tests.a.timeout", 3600)
        prj.set_property("testing.tests.a.enabled", True)
        prj.set_property("testing.tests.a.script", "#!/bin/bash\ntrue")
        prj.set_property("testing.tests.a.requirements", "")
        prj.set_property("testing.tests.a.users", "")
        prj.set_property("testing.tests.a.tester", "")
        msg = Message(project=prj,
                      date=datetime.datetime.now(),
                      is_series_head=True,
                      is_patch=True)
        msg.save()
        msg.set_property("git.repo", "dummy repo")
        msg.set_property("git.tag", "dummy tag")
        msg.set_property("git.base", "dummy base")
        self.api_login()
        td = self.api_call("testing-get",
                           project="TestProject",
                           tester="dummy tester",
                           capabilities=[])
        self.assertIn("head", td)

    def test_done(self):
        prj = Project(name="TestProject")
        prj.save()
        prj.set_property("testing.tests.a.timeout", 3600)
        prj.set_property("testing.tests.a.enabled", True)
        prj.set_property("testing.tests.a.script", "#!/bin/bash\ntrue")
        prj.set_property("testing.tests.a.requirements", "")
        prj.set_property("testing.tests.a.users", "")
        prj.set_property("testing.tests.a.tester", "")
        msg = Message(project=prj,
                      date=datetime.datetime.now(),
                      is_series_head=True,
                      is_patch=True)
        msg.save()
        msg.set_property("git.repo", "dummy repo")
        msg.set_property("git.tag", "dummy tag")
        msg.set_property("git.base", "dummy base")
        msg.set_property("testing.done", True)
        self.api_login()
        td = self.api_call("testing-get",
                           project="TestProject",
                           tester="dummy tester",
                           capabilities=[])
        self.assertFalse(td)

if __name__ == '__main__':
    main()
