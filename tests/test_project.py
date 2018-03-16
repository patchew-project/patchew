#!/usr/bin/env python3
#
# Copyright 2016 Red Hat, Inc.
#
# Authors:
#     Fam Zheng <famz@redhat.com>
#
# This work is licensed under the MIT License.  Please see the LICENSE file or
# http://opensource.org/licenses/MIT.

from patchewtest import PatchewTestCase, main

class ProjectTest(PatchewTestCase):

    def setUp(self):
        self.admin_user = self.create_superuser()

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

    def test_maintainers(self):
        p = self.add_project("TestProject")
        u1 = self.create_user(username='buddy', password='abc')
        u2 = self.create_user(username='mirage', password='def')
        u2.is_staff = True
        u2.save()
        p.maintainers.add(u1)
        self.assertTrue(p.maintained_by(self.admin_user))
        self.assertTrue(p.maintained_by(u1))
        self.assertFalse(p.maintained_by(u2))
        p.maintainers.add(u2)
        self.assertTrue(p.maintained_by(u1))
        self.assertTrue(p.maintained_by(u2))
        p.maintainers.clear()
        self.assertTrue(p.maintained_by(self.admin_user))
        self.assertFalse(p.maintained_by(u1))
        self.assertFalse(p.maintained_by(u2))

if __name__ == '__main__':
    main()
