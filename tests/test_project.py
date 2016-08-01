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
from patchewtest import PatchewTestCase

class ProjectTest(PatchewTestCase):

    def setUp(self):
        self.create_superuser()

    def test_empty(self):
        projects = self.get_projects()
        self.assertFalse(projects)
        self.check_cli(["project"], stdout="")

    def test_add_one_model(self):
        projects = self.get_projects()
        self.assertFalse(projects)
        name = "TestProject"
        projects = self.add_project(name)
        self.check_cli(["project"], stdout=name)

    def test_add_one_cli(self):
        projects = self.get_projects()
        self.assertFalse(projects)
        name = "TestProject"
        self.cli_login()
        self.check_cli(["project", "add", name])
        self.check_cli(["project"], stdout=name)

    def test_add_multiple_model(self):
        projects = ["TestProject-%d" % x for x in range(5)]
        for p in projects:
            self.add_project(p)
        r, a, b = self.cli(["project"])
        for p in projects:
            self.assertIn(p, a.splitlines())

    def test_add_multiple_cli(self):
        self.cli_login()
        projects = ["TestProject-%d" % x for x in range(5)]
        for p in projects:
            self.check_cli(["project", "add", p])
        r, a, b = self.cli(["project"])
        for p in projects:
            self.assertIn(p, a.splitlines())

    def test_duplicated(self):
        self.add_project("TestProject")
        self.cli_login()
        r, a, b = self.cli(["project", "add", "TestProject"])
        self.assertNotEqual(r, 0)
        self.assertNotEqual(b, "")
def main():
    import unittest
    unittest.main()
